"""Ghi vết test theo dòng, dùng chung cho `mutation_select.py` (done-gate) và `narrow.py` (session-keeper).

Tracer: `sys.settrace` ghi (file đích, dòng) theo test đang chạy. Touches: audit hook (PEP 578) ghi file test mở, thư
mục test liệt kê và tiến trình con không ghi vết được (công cụ ngoài như ruff, git chạy trong repo). site_source:
nội dung `sitecustomize.py` cho tiến trình Python con (đặt vào PYTHONPATH chỉ cho bước ghi vết), cùng cách ghi.
Chỉ thư viện chuẩn; không import gì ngoài stdlib (luật lib chỉ import lib).
"""
from __future__ import annotations

import linecache
import os
import re
import sys
import unittest
import unittest.suite
import unittest.util

PY_NAME_RE = re.compile(r"python(3(\.\d+)*)?$")
# Khung gọi của bộ nạp module (cả zipimport dò file script chính): mở file .py để nạp, không phải đọc dữ liệu. linecache
# (inspect.getsource, traceback, warnings) tính là đọc dữ liệu: test so mã nguồn phải được chọn khi file đổi.
IMPORT_PREFIXES = ("<frozen importlib._bootstrap", "<frozen zipimport>")


class Tracer:
    """Ghi (file đích, dòng) theo test đang chạy. `targets`: realpath → đường dẫn tương đối của file đích."""

    def __init__(self, targets: dict):
        self.targets = targets
        self.known: dict = {}
        self.test = ""
        self.order: dict = {}  # test -> thứ tự chạy
        self.lines: dict = {}  # file -> dòng -> set(test)
        self.skip: set = set()  # code object của chính bộ ghi vết (audit hook, TestResult): không ghi

    def target(self, name):
        if name not in self.known:
            self.known[name] = self.targets.get(os.path.realpath(name))
        return self.known[name]

    def add(self, rel, line):
        if self.test:
            self.lines.setdefault(rel, {}).setdefault(line, set()).add(self.test)

    def local(self, frame, event, arg):
        if event == "line":
            self.add(self.known[frame.f_code.co_filename], frame.f_lineno)
        return self.local

    def glob(self, frame, event, arg):
        if frame.f_code in self.skip:
            return None
        rel = self.target(frame.f_code.co_filename)
        if rel is None:
            return None
        self.add(rel, frame.f_lineno)
        return self.local


def isolating(argv) -> bool:
    """Lệnh python có cờ bỏ PYTHONPATH hay site (`-I`, `-E`, `-S`): sitecustomize ghi vết không chạy trong nó."""
    for arg in list(argv)[1:]:
        if not isinstance(arg, str) or not arg.startswith("-") or arg.startswith("--") or arg in ("-c", "-m"):
            break
        if set(arg[1:]) & set("IES"):
            return True
    return False


PYC_RE = re.compile(r"^(?:(.*)/)?__pycache__/([^/.]+)\.[^/]*\.pyc$")


class Touches:
    """Audit hook: file (`open`), thư mục (`os.listdir`, `os.scandir`) trong `root` mà test đang chạy chạm tới, và tiến
    trình con không ghi vết được (không phải python, python có `-I/-E/-S`, hay env thiếu biến ghi vết `trace_env` hoặc
    thiếu thư mục `site` trong PYTHONPATH): (tên chương trình, thư mục chạy tương đối hay None khi ngoài root, các đối
    số trỏ vào root). Mở file .py hay .pyc để nạp module tính riêng (`imports`; ngoài test thì vào `loaded`), không tính
    là đọc dữ liệu. `openers`: file .py trong root gần nhất trên ngăn xếp lúc mở file dữ liệu ("" khi không có; bỏ qua
    khi đó là chính hàm test đang chạy), ghi cả lúc không có test (nạp module, setUpClass): file đọc một lần rồi giữ
    trong bộ nhớ (lru_cache, biến module, thuộc tính lớp) chỉ ghi được người đọc đầu tiên, nên chọn test theo file .py
    đã đọc nó. Tiến trình con (sitecustomize) không ghi `openers`: nó chỉ sống trong một test. Lỗi trong hook bị nuốt: hook không bao giờ làm hỏng thao tác của test."""

    def __init__(self, root: str, current, trace_env: str, site: str = "", passthrough=()):
        self.root = os.path.realpath(root)
        self.prefix = self.root + os.sep
        self.current = current  # hàm trả về id test đang chạy ("" khi không có)
        self.trace_env = trace_env
        self.site = site
        self.reads: dict = {}  # rel -> set(test)
        self.imports: dict = {}  # rel .py -> set(test)
        self.loaded: set = set()  # rel .py nạp khi không có test nào chạy (lúc nạp module test)
        self.dirs: dict = {}  # rel thư mục ("" là gốc) -> set(test)
        self.spawns: dict = {}  # test -> set((tên, cwd rel hay None, tuple đối số rel))
        self.openers: dict = {}  # rel file dữ liệu -> set(rel .py đã mở nó, "" khi không biết)
        self.passthrough = set(passthrough)  # (rel .py, qualname) của hàm đọc file chung không giữ nội dung: bỏ qua
        self.cache: dict = {}
        self.busy = False

    def rel(self, path):
        if isinstance(path, int):
            return None
        try:
            path = os.fsdecode(path)
        except TypeError:
            return None
        key = (path, os.getcwd()) if not os.path.isabs(path) else path
        if key not in self.cache:
            real = os.path.realpath(path)
            self.cache[key] = "" if real == self.root else real[len(self.prefix):] if real.startswith(self.prefix) \
                else None
        return self.cache[key]

    def hook(self, event, args):
        if self.busy or event not in ("open", "os.listdir", "os.scandir", "subprocess.Popen"):
            return
        self.busy = True
        try:
            test = self.current()
            if event == "open":
                rel = self.rel(args[0])
                if not rel:
                    return
                pyc = PYC_RE.match(rel)
                if pyc or (rel.endswith(".py") and self.from_import()):
                    src = ((pyc.group(1) + "/" if pyc.group(1) else "") + pyc.group(2) + ".py") if pyc else rel
                    if test:
                        self.imports.setdefault(src, set()).add(test)
                    else:
                        self.loaded.add(src)
                else:
                    who = self.opener(test)
                    if who is not None:
                        self.openers.setdefault(rel, set()).add(who)
                    if test:
                        self.reads.setdefault(rel, set()).add(test)
            elif not test:
                return
            elif event in ("os.listdir", "os.scandir"):
                rel = self.rel(args[0] if args and args[0] is not None else ".")
                if rel is not None:
                    self.dirs.setdefault(rel, set()).add(test)
            else:
                self.spawn(test, *args[:4])
        except Exception:  # noqa: BLE001
            pass
        finally:
            self.busy = False

    @staticmethod
    def from_import() -> bool:
        """Lần mở này do bộ nạp module hay trình thông dịch (mở file script chính, không có khung Python nào)."""
        try:
            frame = sys._getframe(2)
        except ValueError:
            return True
        for _ in range(8):
            if frame is None:
                return False
            name = frame.f_code.co_filename
            if name.startswith(IMPORT_PREFIXES):
                return True
            frame = frame.f_back
        return False

    def opener(self, test):
        """File .py trong root của khung gọi gần nhất (bỏ khung của hook), "" khi không có. None khi khung đó là chính
        hàm test đang chạy: hàm test chạy một lần cho mỗi test nên không giữ nội dung cho test khác."""
        try:
            frame = sys._getframe(2)
        except ValueError:
            return ""
        while frame is not None:
            code = frame.f_code
            rel = self.rel(code.co_filename)
            qual = getattr(code, "co_qualname", code.co_name)
            if rel and rel.endswith(".py") and (rel, qual) not in self.passthrough:
                own = rel[:-3].replace("/", ".") + "." + qual
                return None if test and test == own else rel
            frame = frame.f_back
        return ""

    def traced_env(self, env) -> bool:
        """Tiến trình con nhận env này có chạy sitecustomize ghi vết không."""
        if env is None:
            return True
        found = {os.fsdecode(k): v for k, v in env.items()}
        path = found.get("PYTHONPATH")
        paths = os.fsdecode(path).split(os.pathsep) if path is not None else []
        return self.trace_env in found and (not self.site or self.site in paths)

    def spawn(self, test, exe, argv, cwd, env):
        if isinstance(argv, (str, bytes)):
            argv = [argv]
        argv = [os.fsdecode(a) if isinstance(a, (str, bytes, os.PathLike)) else str(a) for a in (argv or [])]
        prog = os.path.basename(os.fsdecode(exe) if exe else (argv[0].split()[0] if argv and argv[0].split() else ""))
        if PY_NAME_RE.match(prog) and not isolating(argv) and self.traced_env(env):
            return  # tiến trình con python có sitecustomize: tự ghi vết
        place = os.fsdecode(cwd) if cwd is not None else os.getcwd()
        if prog == "git":  # `git -C <dir>` (có thể lặp, tương đối với dir trước): git làm việc ở dir đó
            i = 1
            while i < len(argv) and argv[i].startswith("-"):
                if argv[i] in ("-C", "-c") and i + 1 < len(argv):
                    if argv[i] == "-C":
                        place = os.path.join(place, argv[i + 1])
                    i += 2
                else:
                    i += 1
        where = self.rel(place)
        inside =tuple(sorted({r for r in (self.rel(a) for a in argv[1:] if os.path.isabs(a)) if r is not None}))
        self.spawns.setdefault(test, set()).add((prog, where, inside))


def own_codes() -> set:
    """Code object của audit hook: chạy giữa test nhưng không phải code của test, Tracer bỏ qua."""
    return {f.__code__ for f in (Touches.hook, Touches.rel, Touches.spawn, Touches.from_import,
                                  Touches.traced_env, Touches.opener, isolating)}


def make_result(tracer, test_env: str, timings: dict | None = None):
    """Lớp TestResult đặt test đang chạy cho tracer (và biến môi trường `test_env` cho tiến trình con); `timings`
    nhận số giây mỗi test."""
    import time

    class Result(unittest.TextTestResult):
        def startTest(self, test):
            linecache.clearcache()  # mỗi test tự đọc lại mã nguồn qua linecache: lần đọc được ghi cho test đó
            tracer.test = test.id()
            tracer.order.setdefault(tracer.test, len(tracer.order))
            os.environ[test_env] = tracer.test
            self._t0 = time.monotonic()
            super().startTest(test)

        def stopTest(self, test):
            super().stopTest(test)
            if timings is not None:
                timings[test.id()] = timings.get(test.id(), 0.0) + time.monotonic() - self._t0
            tracer.test = ""
            os.environ.pop(test_env, None)
    tracer.skip |= {Result.startTest.__code__, Result.stopTest.__code__}
    return Result


def fixture_scope(tracer, test_env: str):
    """Gán code chạy trong setUpClass/tearDownClass, setUpModule/tearDownModule (cả tiến trình con khởi động từ đó)
    cho tên giả `@class:<module>.<lớp>`, `@module:<module>`; người gọi mở tên giả thành mọi test của lớp, module đó.
    Vá các hàm riêng của unittest.TestSuite (Python 3.11); trả về hàm khôi phục."""
    suite = unittest.suite.TestSuite
    saved = {}

    def label(name, args, self):
        if name == "_handleClassSetUp":
            return "@class:" + unittest.util.strclass(args[0].__class__)
        if name == "_handleModuleFixture":
            return "@module:" + args[0].__class__.__module__
        if name == "_tearDownPreviousClass":
            prev = getattr(args[1], "_previousTestClass", None)
            return "@class:" + unittest.util.strclass(prev) if prev is not None else ""
        prev = self._get_previous_module(args[0])
        return "@module:" + prev if prev else ""

    def wrap(name):
        original = getattr(suite, name)

        def run(self, *args):
            key = "" if tracer.test else label(name, args, self)
            if key:
                tracer.test = key
                os.environ[test_env] = key
            try:
                return original(self, *args)
            finally:
                if key:
                    tracer.test = ""
                    os.environ.pop(test_env, None)
        tracer.skip.add(run.__code__)
        saved[name] = original
        setattr(suite, name, run)
    for name in ("_handleClassSetUp", "_handleModuleFixture", "_tearDownPreviousClass", "_handleModuleTearDown"):
        if hasattr(suite, name):
            wrap(name)
    tracer.skip.add(label.__code__)

    def restore():
        for name, original in saved.items():
            setattr(suite, name, original)
    return restore


def expand_fixture(name: str, tests) -> list:
    """Tên giả của fixture_scope → các test (trong `tests`) của lớp hay module đó; tên test thật giữ nguyên."""
    for tag in ("@class:", "@module:"):
        if name.startswith(tag):
            prefix = name[len(tag):] + "."
            return [t for t in tests if t.startswith(prefix)]
    return [name]


def loadable(name: str) -> bool:
    """`python -m unittest <name>` nạp đúng một test có id này (test sinh động, `load_tests` lạ thì không)."""
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName(name)
    except Exception:  # noqa: BLE001
        return False
    found = []
    stack = [suite]
    while stack:
        item = stack.pop()
        if isinstance(item, unittest.TestSuite):
            stack.extend(item)
        else:
            found.append(item.id())
    return found == [name]


# sitecustomize cho tiến trình Python con: chỉ bật khi đủ biến môi trường (tiền tố P), ghi JSON khi thoát. File đích:
# P_TARGETS (JSON realpath → rel) hay P_TARGETS_FILE (đường dẫn file JSON đó). P_ROOT có thì ghi thêm file, thư mục
# chạm tới và tiến trình con không ghi vết được (như Touches).
SITE_TEMPLATE = r'''
import os, sys
if os.environ.get("@P@_TRACE") and os.environ.get("@P@_OUT"):
    import atexit, json, threading
    if os.environ.get("@P@_TARGETS_FILE"):
        try:
            with open(os.environ["@P@_TARGETS_FILE"], encoding="utf-8") as _h:
                _t = json.load(_h)
        except (OSError, ValueError):
            _t = {}
    else:
        _t = json.loads(os.environ.get("@P@_TARGETS") or "{}")  # realpath tuyệt đối -> đường dẫn trong bản chép
    _seen, _known, _skip = {}, {}, set()
    def _local(frame, event, arg):
        if event == "line":
            _seen.setdefault(_known[frame.f_code.co_filename], set()).add(frame.f_lineno)
        return _local
    def _glob(frame, event, arg):
        if frame.f_code in _skip:
            return None
        name = frame.f_code.co_filename
        if name not in _known:
            _known[name] = _t.get(os.path.realpath(name))
        if _known[name] is None:
            return None
        _seen.setdefault(_known[name], set()).add(frame.f_lineno)
        return _local
    _touch = None
    if os.environ.get("@P@_ROOT") and os.environ.get("@P@_LIB"):
        try:
            sys.path.append(os.environ["@P@_LIB"])
            import linetrace as _lt
            sys.path.remove(os.environ["@P@_LIB"])
            _touch = _lt.Touches(os.environ["@P@_ROOT"], lambda: os.environ.get("@P@_TEST", ""), "@P@_TRACE",
                                 os.environ.get("@P@_SITE", ""))
            _skip |= _lt.own_codes()
            sys.addaudithook(_touch.hook)
        except Exception:
            _touch = None
    def _dump():
        sys.settrace(None)
        test = os.environ.get("@P@_TEST", "")
        if _touch is not None:
            _touch.busy = True
        if not test or not (_seen or (_touch is not None and (_touch.reads or _touch.imports or _touch.dirs
                                                                or _touch.spawns))):
            return
        rec = {"test": test, "lines": {k: sorted(v) for k, v in _seen.items()}}
        if _touch is not None:
            rec["reads"] = sorted(_touch.reads)
            rec["imports"] = sorted(_touch.imports)
            rec["dirs"] = sorted(_touch.dirs)
            rec["spawns"] = sorted([p, w, list(a)] for s in _touch.spawns.values() for p, w, a in s)
        path = os.path.join(os.environ["@P@_OUT"], f"{os.getpid()}-{id(_seen)}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rec, f)
        except OSError:
            pass
    atexit.register(_dump)
    threading.settrace(_glob)
    sys.settrace(_glob)
'''


def site_source(prefix: str) -> str:
    """Nội dung sitecustomize với biến môi trường tiền tố `prefix` (ví dụ `AGENT_STACK_MUT`)."""
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", prefix):
        raise ValueError(prefix)
    return SITE_TEMPLATE.replace("@P@", prefix)
