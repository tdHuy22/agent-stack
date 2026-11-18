#!/usr/bin/env python3
"""Chọn test theo dòng cho mutation.py (spec `mutation-chon-test`, TM-143–145). Chỉ chạy trong bản chép ở thư mục tạm.

  mutation_select.py trace --out MAP --targets a.py,b.py --site DIR -- <đối số sau `-m unittest`>
      Chạy unittest trong tiến trình này, ghi vết bằng `sys.settrace`: mỗi dòng của file đích được test nào đi qua.
      Tiến trình Python con ghi qua `sitecustomize.py` trong DIR (đặt vào PYTHONPATH chỉ cho bước này). Ghi MAP
      dạng {"file": {"dòng": ["test id", ...]}}; mã 0 khi mọi test đạt và ghi được ít nhất một dòng.
  config_text(MAP, PY) (mutation.py gọi)
      Nội dung `mutmut_config.py` cho bản chép: `pre_mutation` đặt lệnh test của đột biến thành các test đi qua dòng đó
      (`PY -m unittest -f -q <id…>`, theo thứ tự chạy gốc). mutmut chạy với `--rerun-all`: đột biến sống với lệnh
      thu hẹp được chạy lại cả lệnh test, nên trạng thái cuối khi test chọn không bắt do lệnh đầy đủ quyết (S2).
  mutation_select.py reap --parent PID --dir TMP
      Tiến trình canh (tách session): cha chết (kể cả SIGKILL) thì giết mọi nhóm tiến trình ghi trong TMP/pgids và xóa
      TMP (S6). TMP mất (cha dọn xong) thì tự thoát.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

TRACE_ENV = "AGENT_STACK_MUT_TRACE"
TARGETS_ENV = "AGENT_STACK_MUT_TARGETS"
OUT_ENV = "AGENT_STACK_MUT_OUT"
TEST_ENV = "AGENT_STACK_MUT_TEST"
PGIDS = "pgids"
ALONE_TIMEOUT = 300

# sitecustomize cho tiến trình Python con của bước ghi vết: chỉ bật khi đủ biến môi trường, ghi khi thoát.
SITE = r'''
import os, sys
if os.environ.get("AGENT_STACK_MUT_TRACE") and os.environ.get("AGENT_STACK_MUT_OUT"):
    import atexit, json, threading
    _t = json.loads(os.environ.get("AGENT_STACK_MUT_TARGETS") or "{}")  # realpath tuyệt đối -> đường dẫn trong bản chép
    _seen, _known = {}, {}
    def _local(frame, event, arg):
        if event == "line":
            _seen.setdefault(_known[frame.f_code.co_filename], set()).add(frame.f_lineno)
        return _local
    def _glob(frame, event, arg):
        name = frame.f_code.co_filename
        if name not in _known:
            _known[name] = _t.get(os.path.realpath(name))
        if _known[name] is None:
            return None
        _seen.setdefault(_known[name], set()).add(frame.f_lineno)
        return _local
    def _dump():
        sys.settrace(None)
        test = os.environ.get("AGENT_STACK_MUT_TEST", "")
        if not (_seen and test):
            return
        path = os.path.join(os.environ["AGENT_STACK_MUT_OUT"], f"{os.getpid()}-{id(_seen)}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"test": test, "lines": {k: sorted(v) for k, v in _seen.items()}}, f)
        except OSError:
            pass
    atexit.register(_dump)
    threading.settrace(_glob)
    sys.settrace(_glob)
'''


class Tracer:
    """Ghi (file đích, dòng) theo test đang chạy. `targets`: realpath → đường dẫn tương đối trong bản chép."""

    def __init__(self, targets: dict):
        self.targets = targets
        self.known: dict = {}
        self.test = ""
        self.order: dict = {}  # test -> thứ tự chạy
        self.lines: dict = {}  # file -> dòng -> set(test)

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
        rel = self.target(frame.f_code.co_filename)
        if rel is None:
            return None
        self.add(rel, frame.f_lineno)
        return self.local


def make_result(tracer: Tracer):
    class Result(unittest.TextTestResult):
        def startTest(self, test):
            tracer.test = test.id()
            tracer.order.setdefault(tracer.test, len(tracer.order))
            os.environ[TEST_ENV] = tracer.test
            super().startTest(test)

        def stopTest(self, test):
            super().stopTest(test)
            tracer.test = ""
            os.environ.pop(TEST_ENV, None)
    return Result


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


def alone_fails(names: list, env: dict) -> set:
    """Test trượt (hay quá giờ) khi chạy một mình trong tiến trình riêng: nó cần test khác chạy trước, nên nhóm thu hẹp
    có nó có thể trượt trên code gốc và làm đột biến bị tính bắt sai (TM-143). Chạy song song, mỗi test một lần."""
    def fails(name):
        try:
            return subprocess.run([sys.executable, "-m", "unittest", "-q", name], env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=ALONE_TIMEOUT).returncode != 0
        except (OSError, subprocess.SubprocessError):
            return True
    jobs = max(1, min(4, (os.cpu_count() or 2) // 2))
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return {name for name, bad in zip(names, pool.map(fails, names)) if bad}  # noqa: B905 (cùng độ dài)


def cmd_trace(out: str, targets: list, site: str, argv: list) -> int:
    import threading
    plain = dict(os.environ)  # môi trường gốc cho bước chạy riêng từng test (không ghi vết tiến trình con)
    os.makedirs(site, exist_ok=True)
    child_out = os.path.join(site, "out")
    os.makedirs(child_out, exist_ok=True)
    with open(os.path.join(site, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(SITE)
    os.environ[TRACE_ENV] = "1"
    os.environ[TARGETS_ENV] = json.dumps({os.path.realpath(t): t for t in targets})  # tiến trình con có thể ở cwd khác
    os.environ[OUT_ENV] = child_out
    os.environ["PYTHONPATH"] = os.pathsep.join([site] + [p for p in [os.environ.get("PYTHONPATH")] if p])
    sys.path.insert(0, os.getcwd())
    tracer = Tracer({os.path.realpath(t): t for t in targets})
    with open(os.devnull, "w", encoding="utf-8") as sink:
        runner = unittest.TextTestRunner(stream=sink, resultclass=make_result(tracer),  # type: ignore[arg-type]
                                         verbosity=0)
        threading.settrace(tracer.glob)
        sys.settrace(tracer.glob)
        try:
            prog = unittest.main(module=None, argv=["python -m unittest", *argv], testRunner=runner, exit=False)
        finally:
            sys.settrace(None)
            threading.settrace(None)
    lines = tracer.lines
    for name in sorted(os.listdir(child_out)):
        try:
            with open(os.path.join(child_out, name), encoding="utf-8") as f:
                rec = json.load(f)
            for rel, nums in rec["lines"].items():
                for n in nums:
                    lines.setdefault(rel, {}).setdefault(int(n), set()).add(rec["test"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    ok = prog.result.wasSuccessful() and prog.result.testsRun > 0
    if not ok:
        return 2
    used = sorted({x for by in lines.values() for tests in by.values() for x in tests}, key=lambda x: (
        tracer.order.get(x) is None, tracer.order.get(x, 0)))
    bad = {name for name in used if not loadable(name)}
    plain[TRACE_ENV] = "1"  # bước ghi vết vẫn đang chạy (S3), nhưng không ghi vết tiến trình con nữa
    bad |= alone_fails([x for x in used if x not in bad and x in tracer.order], plain)
    rank = tracer.order.get
    # dòng có test không nạp lại được theo tên, trượt khi chạy một mình, hay test lạ từ tiến trình con: dòng đó chạy
    # cả lệnh test
    data = {}
    for rel, by in lines.items():
        keep = {str(n): sorted(tests, key=rank) for n, tests in sorted(by.items())
                if all(rank(x) is not None and x not in bad for x in tests)}
        if keep:
            data[rel] = keep
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return 0 if data else 2  # không còn dòng nào chọn được: tắt chọn, ghi đúng lý do


CONFIG = """# Viết bởi mutation.py của agent-stack, chỉ trong bản chép ở thư mục tạm (spec mutation-chon-test).
import json, os, shlex
_MAP = json.load(open({map!r}, encoding="utf-8"))
_PY = {py!r}


def pre_mutation(context):
    config = context.config  # mutmut chép config riêng cho mỗi đột biến (queue_mutants: copy_obj)
    tests = _MAP.get(os.path.normpath(context.filename), {{}}).get(str(context.current_line_index + 1))
    if tests:  # không test nào đi qua dòng này: giữ cả lệnh test
        config.test_command = shlex.join([_PY, "-m", "unittest", "-f", "-q", *tests])
        # sống với lệnh thu hẹp thì --rerun-all chạy thêm cả lệnh: cộng một lần chạy gốc vào ngưỡng "đáng ngờ" để
        # đột biến bị lệnh đầy đủ bắt không thành suspicious chỉ vì chạy hai lần
        config.test_time_base += config.baseline_time_elapsed
"""


def config_text(map_path: str, py: str) -> str:
    return CONFIG.format(map=map_path, py=py)


def cmd_reap(parent: int, tmp: str) -> int:
    while os.path.isdir(tmp):
        if os.getppid() != parent:  # cha chết thì tiến trình canh được gán cho cha khác (launchd, init)
            try:
                with open(os.path.join(tmp, PGIDS), encoding="utf-8") as f:
                    pgids = {int(x) for x in f.read().split() if x.isdigit()}
            except OSError:
                pgids = set()
            for pg in pgids:
                try:
                    os.killpg(pg, signal.SIGKILL)
                except OSError:
                    pass
            shutil.rmtree(tmp, ignore_errors=True)
            return 0
        time.sleep(0.5)
    return 0


def main(argv: list) -> int:
    if "--" in argv:
        i = argv.index("--")
        head, rest = argv[:i], argv[i + 1:]
    else:
        head, rest = argv, []
    if not head:
        return 2
    opts = {head[i]: head[i + 1] for i in range(1, len(head) - 1, 2)}
    if head[0] == "trace":
        return cmd_trace(opts["--out"], [t for t in opts["--targets"].split(",") if t], opts["--site"], rest)
    if head[0] == "reap":
        return cmd_reap(int(opts["--parent"]), opts["--dir"])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
