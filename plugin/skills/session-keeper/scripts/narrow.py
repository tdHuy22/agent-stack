#!/usr/bin/env python3
"""Bộ test thu hẹp (việc F1a, TM-156–160): khi đang làm chỉ chạy các test chạm dòng vừa đổi; cả bộ vẫn chạy một lần
trước commit. Biên nhận của bộ thu hẹp mang `scope: narrow` và không thay biên nhận cả bộ (hook Stop, done-gate).

Vết (bảng dòng → test, file test đọc, thư mục test liệt kê, công cụ ngoài test chạy trong repo) ghi một lần bằng
`record`, cùng cách ghi vết của mutation.py (`plugin/lib/linetrace.py`), lưu ở `state/narrow/` (ngoài git) kèm mã blob
của mọi file lúc ghi, nên biết file nào đã đổi từ đó (vết cũ). Chỉ cho lệnh test dạng `python3 -m unittest`.

Lệnh:
  narrow.py record [--project DIR] [--jobs N] [--timeout GIÂY] [-- <đối số sau `-m unittest`>]
      Chạy cả bộ test có ghi vết, mỗi module test một tiến trình, N tiến trình cùng lúc (mặc định: số lõi/2, tối
      đa 8); mặc định đối số `discover -s tests -t .`, hay chỉ tên module, test (không nhận cờ). Mã 0: ghi được vết
      và mọi test đạt; 1: ghi được vết nhưng có test trượt (ghi tên); 2: không ghi được.
  narrow.py run [--project DIR] [--base REF] [--head REF] [--plan] [--json] [--align-stale] [--timeout GIÂY]
      Diff: cây làm việc (cả file mới chưa track) so với REF (mặc định HEAD); `--head REF` thay cây làm việc bằng
      commit đó (để đo trên diff cũ: chạy test trên code hiện tại, không ghi biên nhận). In test được chọn và vì sao,
      rồi chạy qua `receipt.py run --narrow` (bộ thu hẹp) hay `receipt.py run` (rơi về cả bộ). `--plan`: chỉ in.
      `--align-stale`: file đã đổi sau khi ghi vết thì ánh xạ dòng theo nội dung thay vì lấy mọi test chạm file, và
      không rơi về cả bộ vì vết cũ (chỉ để đo, ví dụ với `--head`). Mã thoát là mã của lệnh test; 2 khi tham số sai.
  narrow.py status [--project DIR]
      Vết ghi lúc nào, ở commit nào, bao nhiêu file đã đổi từ đó.
  narrow.py exec [--project DIR] -- <tên test…>
      (receipt.py chạy lệnh này) chạy các test; trượt thì chạy lại cả danh sách với test trượt thay bằng cả module
      của nó, mã thoát là của lần chạy lại: đạt thì test đó cần test khác chạy trước, được ghi vào vết để lần sau chạy
      cả module.

Rơi về chạy rộng hơn, in lý do: chưa có vết, vết hỏng hay có tham số lạ, diff rỗng, vết cũ (quá DRIFT_LIMIT file
code đổi từ lúc ghi), file mới không test nào chạm thư mục của nó, dòng mức module đổi trong file chỉ được nạp lúc nạp
module test, file không phải Python với vết bản 1, file dữ liệu do code ngoài repo đọc, chọn từ FULL_SHARE số test trở
lên (cả bộ); file đổi sau khi ghi vết (trong hay ngoài diff), dòng mức module (cả decorator, chữ ký hàm, docstring)
hay hàm không test nào đi qua (mọi test chạm file); dòng trình ghi vết không thấy (`else:`, dòng tiếp của lệnh nhiều
dòng), chèn dòng, đổi cấu trúc hay đổi phạm vi tên (mọi test đi qua hàm); file dữ liệu (mọi test chạy qua file .py đã
đọc nó); file test đổi hay mới, test không nạp lại được theo tên, test trượt khi chạy một mình (cả module).
"""
from __future__ import annotations

import argparse
import ast
import difflib
import functools
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import symtable
import sys
import tempfile
import time
import tokenize
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
LIB = HERE.parents[3] / "lib"
sys.path.insert(0, str(LIB))
import agentstack as A  # noqa: E402
import linetrace as LT  # noqa: E402

del sys.path[0]

# 2: thêm `openers` (file .py nào đã mở file dữ liệu), `loaded_by` (test của các module test đã nạp file .py), gán
# setUpClass/setUpModule cho test của lớp/module, đọc qua linecache tính là đọc file. Vết bản 1 chỉ dùng được cho thay
# đổi trong thân hàm của file Python; còn lại chạy cả bộ.
VERSION = 2
VERSIONS = (1, 2)
# Hàm đọc file chung trong plugin/lib, không tự giữ nội dung (không cache, không biến toàn cục; test_narrow kiểm): người
# đọc file là khung gọi bên ngoài nó. Thêm hàm vào đây chỉ khi đúng như vậy.
PASSTHROUGH = (("plugin/lib/agentstack.py", "read_json"), ("plugin/lib/stackcfg.py", "read_file"))
PREFIX = "AGENT_STACK_NARROW"
DEFAULT_ARGS = ["discover", "-s", "tests", "-t", "."]
NAME_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")  # tên test, module: không thể là cờ (TM-156)
REF_RE = re.compile(r"^[\w./@{}~^+-]+$")  # ref do người gõ (TM-157)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DRIFT_LIMIT = 10  # số file code đổi sau khi ghi vết (ngoài diff) quá mức này thì vết cũ: chạy cả bộ
FULL_SHARE = 0.7  # chọn từ tỉ lệ này trở lên thì chạy cả bộ (biên nhận cả bộ)
NARROW_LABEL = "thu hẹp (narrow.py)"
MAX_LISTED = 20
GIT_TIMEOUT = 60


class Bad(Exception):
    """Tham số sai: mã 2, không chạy gì."""


# ---------------------------------------------------------------- git và file

def git(root: Path, *args: str, timeout: float = GIT_TIMEOUT):
    """stdout (bytes) của lệnh git chỉ đọc, hay None khi lỗi. Không qua shell."""
    try:
        out = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                             capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def repo_root(project: str) -> Path:
    place = Path(project).expanduser()
    out = git(place, "rev-parse", "--show-toplevel") if place.is_dir() else None
    if not out:
        raise Bad(f"{project}: không phải thư mục trong git repo")
    return Path(os.path.realpath(out.decode("utf-8", "surrogateescape").strip()))


def resolve_ref(root: Path, ref: str) -> str:
    """Mã commit 40 hex của REF; REF bắt đầu bằng `-` hay có ký tự lạ thì từ chối (TM-157)."""
    if not ref or ref.startswith("-") or not REF_RE.match(ref) or ".." in ref:
        raise Bad(f"ref không hợp lệ: {ref!r}")
    out = git(root, "rev-parse", "--verify", "--quiet", "--end-of-options", ref + "^{commit}")
    sha = (out or b"").decode("ascii", "replace").strip()
    if not SHA_RE.match(sha):
        raise Bad(f"không tìm thấy commit {ref!r}")
    return sha


def tree_of(root: Path, sha: str):
    """{đường dẫn: blob} của commit (bỏ submodule), hay None khi git lỗi."""
    if not SHA_RE.match(sha):
        return None
    out = git(root, "ls-tree", "-r", "-z", "--full-tree", sha)
    if out is None:
        return None
    blobs = {}
    for entry in out.decode("utf-8", "surrogateescape").split("\0"):
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if path and len(parts) == 3 and parts[1] == "blob":
            blobs[path] = parts[2]
    return blobs


def blob_bytes(root: Path, blob):
    if not blob or not re.fullmatch(r"[0-9a-f]{40,64}", blob):
        return None
    return git(root, "cat-file", "blob", blob)


def read_current(root: Path, rel: str):
    """Nội dung file trong cây làm việc, chỉ khi nó nằm thật trong repo và không qua symlink (TM-158)."""
    path = root / rel
    try:
        if path.is_symlink() or not os.path.realpath(path).startswith(str(root) + os.sep):
            return None
        return path.read_bytes()
    except OSError:
        return None


def text_lines(data: bytes) -> list:
    lines = data.decode("utf-8", "replace").split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def state_file(root: Path) -> Path:
    return A.state_dir() / "narrow" / (hashlib.sha1(str(root).encode("utf-8", "surrogateescape")).hexdigest()[:12]
                                        + ".json")


def tmp_base() -> Path:
    home = A.home_dir()
    base = (Path(home) if home else HERE.parents[4]) / ".tmp"
    base.mkdir(parents=True, exist_ok=True)
    return base


def dirs_of(paths) -> set:
    out = {""}
    for p in paths:
        parts = p.split("/")[:-1]
        out.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    return out


def module_name(rel: str):
    """`tests/test_x.py` → `tests.test_x` khi mọi phần là định danh (TM-156), không thì None."""
    if not rel.endswith(".py"):
        return None
    name = rel[:-3].replace("/", ".")
    return name if NAME_RE.match(name) and not name.endswith("__init__") else None


# ---------------------------------------------------------------- ghi vết

class _Collect:
    """Runner giả cho unittest.TestProgram: giữ suite, không chạy."""
    suite = None

    def run(self, test):
        _Collect.suite = test
        return unittest.TestResult()


def flatten(suite) -> list:
    out, stack = [], [suite]
    while stack:
        item = stack.pop(0)
        if isinstance(item, unittest.TestSuite):
            stack[:0] = list(item)
        else:
            out.append(item)
    return out


def discover(root: Path, args: list):
    """(danh sách (id, module) theo thứ tự chạy, lỗi nạp) như `python -m unittest <args>` đứng ở root."""
    os.chdir(root)
    sys.path[0:0] = [str(root)]
    unittest.TestProgram(module=None, argv=["python -m unittest", *args], testRunner=_Collect, exit=False)
    tests, broken = [], []
    for case in flatten(_Collect.suite):
        tid = case.id()
        if type(case).__name__ in ("_FailedTest", "_ErrorHolder") or not NAME_RE.match(tid):
            broken.append(tid)
        else:
            tests.append((tid, type(case).__module__))
    return tests, broken


def cmd_shard(root: str, out: str, site: str, targets_file: str, modules: list) -> int:
    """Một tiến trình ghi vết (record chạy mỗi module test một tiến trình): chạy các module, ghi JSON (tên test dạng
    chữ) vào `out`. Code chạy trong setUpClass/setUpModule (cả tiến trình con khởi động từ đó) được gán cho mọi test của
    lớp, module đó; `loads`: mọi file .py nạp trong tiến trình (kể cả gián tiếp, kể cả lúc nạp module test)."""
    os.chdir(root)
    sys.path[0] = root  # như `python -m unittest`: thư mục chạy đứng đầu sys.path, không phải thư mục script
    for name in ("agentstack", "linetrace"):  # test tự nạp lib như khi chạy `python -m unittest`
        sys.modules.pop(name, None)
    with open(targets_file, encoding="utf-8") as f:
        targets = json.load(f)
    child_out = os.path.join(site, f"out-{os.getpid()}")
    os.makedirs(child_out, exist_ok=True)
    os.environ.update({f"{PREFIX}_TRACE": "1", f"{PREFIX}_OUT": child_out, f"{PREFIX}_TARGETS_FILE": targets_file,
                       f"{PREFIX}_ROOT": root, f"{PREFIX}_LIB": str(LIB), f"{PREFIX}_SITE": site})
    os.environ["PYTHONPATH"] = os.pathsep.join([site] + [p for p in [os.environ.get("PYTHONPATH")] if p])
    tracer = LT.Tracer(targets)
    tracer.skip |= LT.own_codes()
    touches = LT.Touches(root, functools.partial(getattr, tracer, "test"), f"{PREFIX}_TRACE", site,
                         passthrough=PASSTHROUGH)
    sys.addaudithook(touches.hook)
    import threading
    timings: dict = {}
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    restore = LT.fixture_scope(tracer, f"{PREFIX}_TEST")
    with open(os.devnull, "w", encoding="utf-8") as sink:
        runner = unittest.TextTestRunner(stream=sink, verbosity=0,  # type: ignore[arg-type]
                                         resultclass=LT.make_result(tracer, f"{PREFIX}_TEST", timings))
        threading.settrace(tracer.glob)
        sys.settrace(tracer.glob)
        try:
            result = runner.run(suite)
        finally:
            sys.settrace(None)
            threading.settrace(None)
            restore()
    touches.busy = True
    failed = sorted({t.id() for t, _ in result.failures + result.errors})
    order = sorted(tracer.order, key=tracer.order.get)

    def real(name) -> list:
        return LT.expand_fixture(name, order)
    rec = {"order": order, "secs": {k: round(v, 3) for k, v in timings.items()},
           "failed": failed, "unloadable": [x for x in tracer.order if not LT.loadable(x)],
           "modules": {}, "lines": {}, "reads": {}, "imports": {}, "loaded": sorted(touches.loaded), "dirs": {},
           "spawns": {}, "openers": {k: set(v) for k, v in touches.openers.items()}, "mods": list(modules),
           "loads": sorted(set(touches.imports) | touches.loaded)}
    for m in modules:
        path = getattr(sys.modules.get(m), "__file__", None)
        real_path = os.path.realpath(path) if path else ""
        if real_path.startswith(root + os.sep):
            rec["modules"][m] = real_path[len(root) + 1:]

    def put(kind, key, test):
        rec[kind].setdefault(key, set()).update(real(test))
    for rel, by in tracer.lines.items():
        for n, tests in by.items():
            for t in tests:
                rec["lines"].setdefault(rel, {}).setdefault(str(n), set()).update(real(t))
    for kind in ("reads", "imports", "dirs"):
        for rel, tests in getattr(touches, kind).items():
            for t in tests:
                put(kind, rel, t)
    for t, items in touches.spawns.items():
        for x in real(t):
            rec["spawns"].setdefault(x, []).extend([p, w, list(a)] for p, w, a in items)
    for name in sorted(os.listdir(child_out)):
        try:
            with open(os.path.join(child_out, name), encoding="utf-8") as f:
                child = json.load(f)
            tests = real(child["test"])
            for rel, nums in child["lines"].items():
                for n in nums:
                    rec["lines"].setdefault(rel, {}).setdefault(str(int(n)), set()).update(tests)
            for kind in ("reads", "imports", "dirs"):
                for rel in child.get(kind, []):
                    put(kind, rel, child["test"])
            for x in tests:
                rec["spawns"].setdefault(x, []).extend(child.get("spawns", []))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for rel, by in rec["lines"].items():
        rec["lines"][rel] = {n: sorted(t) for n, t in by.items()}
    for kind in ("reads", "imports", "dirs", "openers"):
        rec[kind] = {k: sorted(v) for k, v in rec[kind].items()}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f)
    return 0


def opaque(spawn, inventory: dict, tracked_dirs: set) -> bool:
    """Tiến trình con không ghi vết được mà chạy trong thư mục của repo hay nhận đường dẫn trong repo: nó có thể đọc
    bất kỳ file nào (ruff, git ls-files, claude plugin validate)."""
    _prog, where, args = spawn
    return (where is not None and where in tracked_dirs) or any(a in inventory or a in tracked_dirs for a in args)


def cmd_record(root: Path, args: list, jobs: int, timeout: float) -> int:
    started = time.monotonic()
    if A.local_clean_filters(root):
        print("[narrow] repo có clean filter riêng (git sẽ chạy lệnh của repo khi băm file): không ghi vết")
        return 2
    inventory = A.tree_blobs(root)
    head = (git(root, "rev-parse", "--verify", "--quiet", "HEAD") or b"").decode("ascii", "replace").strip() or None
    if inventory is None:
        print("[narrow] không đọc được danh sách file (git lỗi)")
        return 2
    tests, broken = discover(root, args)
    if broken:
        print(f"[narrow] {len(broken)} module test không nạp được: {', '.join(broken[:5])}")
        return 2
    if not tests:
        print("[narrow] không tìm thấy test nào")
        return 2
    modules = list(dict.fromkeys(m for _, m in tests))
    old = load_raw(root)
    weight: dict = {}
    if old and not valid_map(old, root):
        for sec, mi in zip(old["secs"], old["module_of"], strict=False):
            if mi >= 0:
                name = old["modules"][mi][0]
                weight[name] = weight.get(name, 0.0) + float(sec)
    if not weight:
        for _, m in tests:
            weight[m] = weight.get(m, 0.0) + 1.0
    # mỗi module test một tiến trình (tối đa `jobs` cùng lúc, module lâu chạy trước): danh sách file nạp của tiến trình
    # là của đúng module đó
    queue = sorted(range(len(modules)), key=lambda i: -weight.get(modules[i], 1.0))
    tmp = Path(tempfile.mkdtemp(prefix="narrow-", dir=str(tmp_base())))
    procs: list = []
    try:
        site = tmp / "site"
        site.mkdir()
        (site / "sitecustomize.py").write_text(LT.site_source(PREFIX), encoding="utf-8")
        targets = {}
        for rel in inventory:
            path = root / rel
            if rel.endswith(".py") and not path.is_symlink() and path.is_file():
                targets[os.path.realpath(path)] = rel
        (tmp / "targets.json").write_text(json.dumps(targets), encoding="utf-8")
        print(f"[narrow] ghi vết {len(tests)} test trong {len(modules)} module, mỗi module một tiến trình, "
              f"{jobs} tiến trình cùng lúc…", flush=True)
        deadline = time.monotonic() + timeout
        running: list = []
        bad: list = []
        while (queue or running) and not bad:
            while queue and len(running) < jobs:
                i = queue.pop(0)
                log = open(tmp / f"log-{i}", "wb")  # noqa: SIM115 (đóng sau khi chờ)
                proc = subprocess.Popen([sys.executable, str(HERE), "_shard", "--root", str(root), "--out",
                                         str(tmp / f"shard-{i}.json"), "--site", str(site), "--targets",
                                         str(tmp / "targets.json"), "--", modules[i]], cwd=str(root),
                                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
                procs.append((proc, log, i))
                running.append((proc, log, i))
            for item in list(running):
                code = item[0].poll()
                if code is not None:
                    running.remove(item)
                    item[1].close()
                    if code != 0:
                        bad.append((item[2], code))
            if time.monotonic() > deadline:
                bad += [(i, None) for _, _, i in running]
                break
            if running:
                time.sleep(0.05)
        if bad:
            for proc, _, _ in procs:
                try:
                    os.killpg(proc.pid, 9)
                except OSError:
                    pass
            for i, code in bad:
                tail = (tmp / f"log-{i}").read_bytes()[-1500:].decode("utf-8", "replace")
                print(f"[narrow] tiến trình ghi vết {modules[i]} {'quá giờ' if code is None else f'lỗi mã {code}'}:"
                      f"\n{tail}")
            return 2
        data = merge(root, head, args, inventory, tests, [json.loads((tmp / f"shard-{i}.json").read_text("utf-8"))
                                                          for i in range(len(modules))])
    finally:
        for proc, log, _ in procs:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, 9)
                except OSError:
                    pass
            log.close()
        shutil.rmtree(tmp, ignore_errors=True)
    data["seconds"] = round(time.monotonic() - started, 1)
    path = state_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    A.write_json_atomic(path, data)
    failed = [data["tests"][i] for i in data["failed"]] + data["failed_other"]
    n_opaque = len(data["opaque"])
    print(f"[narrow] đã ghi vết: {len(data['tests'])} test, {len(data['lines'])} file Python có dòng được chạy, "
          f"{len(data['reads'])} file được đọc, {n_opaque} test chạy công cụ ngoài trong repo; "
          f"{data['seconds']} giây; {path}")
    if failed:
        print(f"[narrow] {len(failed)} test trượt lúc ghi vết (vết vẫn ghi): " + ", ".join(failed[:MAX_LISTED]))
        return 1
    return 0


def merge(root: Path, head, args, inventory: dict, tests: list, parts: list) -> dict:
    """Gộp kết quả các tiến trình thành vết: tên test thay bằng chỉ số, tập test giống nhau dùng chung (`sets`)."""
    order: list = []
    seen: set = set()
    for part in parts:
        for x in part["order"]:
            if x not in seen:
                seen.add(x)
                order.append(x)
    index = {t: i for i, t in enumerate(order)}
    module_list, module_index = [], {}
    rel_of = {}
    for part in parts:
        rel_of.update(part["modules"])
    for _tid, m in tests:
        if m not in module_index:
            module_index[m] = len(module_list)
            module_list.append([m, rel_of.get(m)])
    of_test = dict(tests)
    sets, set_index = [], {}

    def intern(names):
        key = tuple(sorted({index[n] for n in names if n in index}))
        if not key:
            return None
        if key not in set_index:
            set_index[key] = len(sets)
            sets.append(list(key))
        return set_index[key]
    lines: dict = {}
    for part in parts:
        for rel, by in part["lines"].items():
            if rel in inventory:
                for n, names in by.items():
                    lines.setdefault(rel, {}).setdefault(n, set()).update(names)
    tracked_dirs = dirs_of(inventory)
    out = {"version": VERSION, "root": str(root), "created": datetime.now().astimezone().isoformat(timespec="seconds"),
           "head": head, "args": list(args), "inventory": inventory, "tests": order,
           "module_of": [module_index.get(of_test.get(t), -1) for t in order], "modules": module_list,
           "secs": [0.0] * len(order), "failed": [], "failed_other": [], "unloadable": [], "alone_bad": [], "sets": sets,
           "lines": {}, "reads": {}, "imports": {}, "dirs": {}, "loaded": [], "opaque": {}, "openers": {}}
    for rel, by in lines.items():
        out["lines"][rel] = {n: s for n, names in by.items() if (s := intern(names)) is not None}
    for kind, keep in (("reads", inventory), ("imports", inventory), ("dirs", tracked_dirs)):
        merged: dict = {}
        for part in parts:
            for rel, names in part[kind].items():
                if rel in keep:
                    merged.setdefault(rel, set()).update(names)
        out[kind] = {rel: s for rel, names in merged.items() if (s := intern(names)) is not None}
    openers: dict = {}
    for part in parts:
        for rel, who in part["openers"].items():
            if rel in inventory:  # file .py ngoài inventory (chưa track, sinh ra): coi như không biết ("")
                openers.setdefault(rel, set()).update(w if w in inventory else "" for w in who)
    out["openers"] = {rel: sorted(who) for rel, who in sorted(openers.items())}
    by_module: dict = {}
    for t, m in tests:
        by_module.setdefault(m, []).append(t)
    loaded_by: dict = {}
    for part in parts:  # tiến trình chạy nhiều module thì mọi module của nó tính là đã nạp (thà thừa)
        owners = [t for m in part["mods"] for t in by_module.get(m, [])]
        for rel in part["loads"]:
            if rel in inventory:
                loaded_by.setdefault(rel, set()).update(owners)
    out["loaded_by"] = {rel: s for rel, names in sorted(loaded_by.items()) if (s := intern(names)) is not None}
    loaded = set()
    for part in parts:
        loaded.update(r for r in part["loaded"] if r in inventory)
        for t, s in part["secs"].items():
            if t in index:
                out["secs"][index[t]] = s
        out["failed"] += [index[t] for t in part["failed"] if t in index]
        out["failed_other"] += [t for t in part["failed"] if t not in index]  # setUpClass, module lỗi: chỉ để in
        out["unloadable"] += [index[t] for t in part["unloadable"] if t in index]
        for t, spawns in part["spawns"].items():
            progs = sorted({s[0] for s in spawns if opaque(s, inventory, tracked_dirs)})
            if progs and t in index:
                out["opaque"][str(index[t])] = progs
    out["loaded"] = sorted(loaded)
    return out


# ---------------------------------------------------------------- đọc vết

def args_ok(args) -> bool:
    """Đối số unittest của vết: đúng mặc định, hay danh sách tên module/test (TM-159). Không nhận cờ (`-k`, `-s` ra
    ngoài repo): cả bộ chạy theo vết phải là cả bộ thật."""
    return isinstance(args, list) and (args == DEFAULT_ARGS or (bool(args) and all(
        isinstance(a, str) and NAME_RE.match(a) for a in args)))


def load_raw(root: Path):
    data = A.read_json(state_file(root), None)
    return data if isinstance(data, dict) else None


def valid_map(data, root: Path):
    """Lý do vết không dùng được (TM-159), hay None khi dùng được."""
    if data is None:
        return "chưa có vết"
    if data.get("version") not in VERSIONS:
        return "vết khác phiên bản"
    if data.get("root") != str(root):
        return "vết của repo khác"
    if not args_ok(data.get("args")):
        return "vết có tham số unittest lạ (chỉ nhận mặc định hay tên module, test)"
    try:
        tests = data["tests"]
        if not all(isinstance(t, str) and NAME_RE.match(t) for t in tests):
            return "vết có tên test lạ"
        if not all(isinstance(m, list) and len(m) == 2 and isinstance(m[0], str) and NAME_RE.match(m[0])
                   for m in data["modules"]):
            return "vết có tên module lạ"
        n = len(tests)
        if len(data["module_of"]) != n or not all(isinstance(i, int) and -1 <= i < len(data["modules"])
                                                   for i in data["module_of"]):
            return "vết hỏng (module_of)"
        if not all(isinstance(s, list) and all(isinstance(i, int) and 0 <= i < n for i in s) for s in data["sets"]):
            return "vết hỏng (sets)"
        ns = len(data["sets"])
        for kind in ("reads", "imports", "dirs") + (("loaded_by",) if data["version"] >= 2 else ()):
            if not all(isinstance(v, int) and 0 <= v < ns for v in data[kind].values()):
                return f"vết hỏng ({kind})"
        for by in data["lines"].values():
            if not all(isinstance(v, int) and 0 <= v < ns for v in by.values()):
                return "vết hỏng (lines)"
        if not isinstance(data["inventory"], dict) or not all(isinstance(i, int) and 0 <= i < n
                                                                for i in data["failed"] + data["unloadable"]):
            return "vết hỏng"
        if len(data["secs"]) != n or not all(isinstance(x, (int, float)) and x >= 0 for x in data["secs"]):
            return "vết hỏng (secs)"
        if not all(isinstance(t, str) and NAME_RE.match(t) for t in data.get("alone_bad", [])):
            return "vết có tên test lạ (alone_bad)"
        if not all(k.isdigit() and int(k) < n for k in data["opaque"]):
            return "vết hỏng (opaque)"
        if data["version"] >= 2 and not all(isinstance(v, list) and all(isinstance(w, str) for w in v)
                                            for v in data["openers"].values()):
            return "vết hỏng (openers)"
    except (KeyError, TypeError, AttributeError):
        return "vết hỏng"
    return None


# ---------------------------------------------------------------- chọn test

SCOPE_SKIP = {"lambda", "listcomp", "setcomp", "dictcomp", "genexpr"}  # phạm vi chỉ chạy trên chính dòng của nó


def code_lines(text: str):
    """Dòng có token mã (kể cả dòng giữa chuỗi nhiều dòng), hay None khi không tách token được."""
    out = set()
    skip = (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type not in skip:
                out.update(range(tok.start[0], tok.end[0] + 1))
    except (tokenize.TokenError, SyntaxError, ValueError):
        return None
    return out


def own_nodes(node):
    """Các nút thuộc thân hàm `node`, không đi vào hàm, lớp, lambda lồng bên trong."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        item = stack.pop()
        yield item
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(item))


def scope_table(text: str) -> dict:
    """{đường dẫn tên: [{tên: (cục bộ, toàn cục, nonlocal, tự do, tham số)}]} của mọi hàm (symtable), {} khi lỗi."""
    try:
        top = symtable.symtable(text, "<narrow>", "exec")
    except (SyntaxError, ValueError, TypeError):
        return {}
    out: dict = {}
    stack = [(top, ())]
    while stack:
        table, path = stack.pop()
        for child in table.get_children():
            name = child.get_name()
            sub = path + (name,)
            if str(child.get_type()).lower().endswith("function") and name not in SCOPE_SKIP:
                out.setdefault(sub, []).append({sym.get_name(): (sym.is_local(), sym.is_global(), sym.is_nonlocal(),
                                                                 sym.is_free(), sym.is_parameter())
                                                for sym in child.get_symbols()})
            stack.append((child, sub))
    return out


class FileView:
    """Một phía của diff hay bản lúc ghi vết. Dòng có mã (`code`); `inner`: dòng chỉ chạy khi hàm chứa nó được gọi
    (thân hàm, không gồm decorator, chữ ký: những dòng này chạy lúc định nghĩa hàm); `docs`: dòng docstring (module,
    lớp, hàm; đọc được qua `__doc__` mà không chạy dòng nào); `funcs`: (dòng đầu thân, dòng cuối, đường dẫn tên);
    `by_qual`: đường dẫn tên → [(dòng đầu kể cả decorator, dòng cuối)]."""

    def __init__(self, data):
        self.lines = text_lines(data or b"")
        text = "\n".join(self.lines) + "\n"
        code = code_lines(text) if data is not None else set()
        self.code = set(range(1, len(self.lines) + 1)) if code is None else code
        self.parsed = False
        self.inner, self.docs = set(), set()
        self.funcs: list = []
        self.by_qual: dict = {}
        self.gen: dict = {}
        self.scopes: dict = {}
        if data is not None:
            self.parse(text)

    def parse(self, text: str):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return
        self.parsed = True
        stack = [(tree, ())]
        while stack:
            node, path = stack.pop()
            body = getattr(node, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                    and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str) \
                    and isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                self.docs.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sub = path + (child.name,)
                    self.function(child, sub)
                    stack.append((child, sub))
                elif isinstance(child, ast.ClassDef):
                    stack.append((child, path + (child.name,)))
                else:
                    stack.append((child, path))
        self.scopes = scope_table(text)

    def function(self, node, path):
        args = node.args
        parts = [*node.decorator_list, *args.posonlyargs, *args.args, *args.kwonlyargs, *args.defaults,
                 *[d for d in args.kw_defaults if d is not None], args.vararg, args.kwarg, node.returns]
        header = max([node.lineno, node.body[0].lineno - 1]
                     + [(p.end_lineno or p.lineno) for p in parts if p is not None])
        end = node.end_lineno or node.lineno
        start = min([d.lineno for d in node.decorator_list] + [node.lineno])
        self.inner.update(range(header + 1, end + 1))
        self.funcs.append((header + 1, end, path))
        self.by_qual.setdefault(path, []).append((start, end))
        self.gen.setdefault(path, []).append(isinstance(node, ast.AsyncFunctionDef) or any(
            isinstance(n, (ast.Yield, ast.YieldFrom)) for n in own_nodes(node)))

    def is_code(self, n: int) -> bool:
        return n in self.code

    def module_level(self, n: int) -> bool:
        """Dòng có mã chạy lúc nạp module (hay đọc được qua `__doc__`), không phải chỉ khi một hàm được gọi."""
        return n in self.code and (not self.parsed or n in self.docs or n not in self.inner)

    def qual_at(self, n: int):
        """Đường dẫn tên của hàm trong cùng có thân chứa dòng n, hay () khi không có."""
        best = max((f for f in self.funcs if f[0] <= n <= f[1]), key=lambda f: f[0], default=None)
        return best[2] if best else ()

    def under(self, table: dict, path) -> dict:
        return {k: v for k, v in table.items() if k[:len(path)] == path}


def same_shape(old: FileView, new: FileView, ol, nl) -> bool:
    """Khối thay đổi giữ nguyên cấu trúc: cùng số dòng, mỗi cặp dòng cùng thụt lề và cùng là mã hay không."""
    if len(ol) != len(nl):
        return False
    for a, b in zip(ol, nl, strict=True):
        x, y = old.lines[a - 1], new.lines[b - 1]
        if x[:len(x) - len(x.lstrip())] != y[:len(y) - len(y.lstrip())] or old.is_code(a) != new.is_code(b):
            return False
    return True


def scope_changed(old: FileView, new: FileView, path):
    """Hàm ngoài cùng trên `path` (có ở cả hai phía) có dấu phạm vi khác nhau, hay None. Gán một tên trong một nhánh
    làm tên đó cục bộ cho cả hàm, thêm `yield` biến hàm thành generator: mọi lần gọi hàm đều đổi, không chỉ dòng đổi."""
    for k in range(1, len(path) + 1):
        sub = path[:k]
        if sub in old.by_qual and sub in new.by_qual and scopes_differ(old, new, sub):
            return sub
    return None


def scopes_differ(old: FileView, new: FileView, path) -> bool:
    """Hàm `path` hay hàm lồng trong nó (có ở cả hai phía) đổi loại của một tên có ở cả hai phía (cục bộ, toàn cục,
    nonlocal, tự do, tham số), hay đổi generator. Tên mới chỉ có ở một phía không đổi nghĩa dòng khác."""
    a, b = old.under(old.scopes, path), new.under(new.scopes, path)
    for key in a.keys() & b.keys():
        if len(a[key]) != len(b[key]):
            return True
        for x, y in zip(a[key], b[key], strict=True):
            if any(x[name] != y[name] for name in x.keys() & y.keys()):
                return True
    ga, gb = old.under(old.gen, path), new.under(new.gen, path)
    return any(ga[key] != gb[key] for key in ga.keys() & gb.keys())


def change_blocks(old: list, new: list):
    """Các khối khác nhau (tag, dòng cũ, dòng mới), đánh số từ 1."""
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag != "equal":
            yield tag, list(range(i1 + 1, i2 + 1)), list(range(j1 + 1, j2 + 1))


def align(rec: list, new: list) -> dict:
    """Dòng mới → dòng lúc ghi vết, theo các khối giống nhau."""
    out = {}
    for a, b, size in difflib.SequenceMatcher(None, rec, new, autojunk=False).get_matching_blocks():
        for k in range(size):
            out[b + k + 1] = a + k + 1
    return out


class Selector:
    def __init__(self, root: Path, data: dict, align_stale: bool, worktree: dict | None = None):
        self.root, self.data, self.align_stale = root, data, align_stale
        self.worktree = worktree or {}
        self.tests = data["tests"]
        self.sets = data["sets"]
        self.ids: set = set()
        self.modules: set = set()  # module chạy cả
        self.items: list = []  # (file, lý do, số test)
        self.full: list = []  # lý do chạy cả bộ
        self.rel_module = {rel: m for m, rel in data["modules"] if rel}
        self.module_names = {m for m, _ in data["modules"]}
        self.position = {t: i for i, t in enumerate(self.tests)}
        self.module_size: dict = {}
        for mi in data["module_of"]:
            if mi >= 0:
                self.module_size[data["modules"][mi][0]] = self.module_size.get(data["modules"][mi][0], 0) + 1

    def tests_of(self, idx) -> set:
        return {self.tests[i] for i in self.sets[idx]} if idx is not None else set()

    def file_tests(self, rel: str) -> set:
        out = set()
        for idx in self.data["lines"].get(rel, {}).values():
            out |= self.tests_of(idx)
        for kind in ("reads", "imports", "loaded_by"):
            out |= self.tests_of(self.data.get(kind, {}).get(rel))
        return out

    def note(self, rel, why, found):
        self.items.append((rel, why, len(found)))

    def add(self, found: set):
        self.ids |= found

    def test_module(self, rel: str):
        """Tên module test khi `rel` là file test: đã có trong vết, hay tên `test*.py` cùng thư mục với module test
        đã ghi (file test mới)."""
        if rel in self.rel_module:
            return self.rel_module[rel]
        name = module_name(rel)
        if not name or not Path(rel).name.startswith("test"):
            return None
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        known = {r.rsplit("/", 1)[0] if "/" in r else "" for r in self.rel_module}
        return name if parent in known else None

    def python_file(self, rel, old_b, new_b, rec_b, rec_kind):
        """Chọn theo dòng cho một file Python có trong vết. Mỗi khối đổi (bỏ khối chỉ đổi chú thích, dòng trống):
        - có dòng chạy lúc nạp module (import, hằng, thân lớp, decorator, chữ ký hàm, docstring): mọi test chạm file;
        - giữ cấu trúc (cùng số dòng, thụt lề) và mọi dòng mã phía vết đều có test đi qua: các test đó;
        - còn lại (dòng trình ghi vết không thấy như `else:`, dòng tiếp của lệnh nhiều dòng; chèn dòng; đổi cấu trúc;
          đổi tên nào là biến cục bộ hay thêm `yield`): mọi test đi qua bất kỳ dòng nào của hàm chứa khối, hàm không
          test nào đi qua thì mọi test chạm file."""
        old, new = FileView(old_b), FileView(new_b)
        rec = old if rec_kind == "old" else new if rec_kind == "new" else FileView(rec_b)
        mapping = align(rec.lines, new.lines) if rec_kind == "align" else None
        by_line = self.data["lines"].get(rel, {})

        def traced(n):
            return self.tests_of(by_line.get(str(n)))
        found, paths = set(), set()
        module_change, line_blocks = False, 0
        for tag, ol, nl in change_blocks(old.lines, new.lines):
            if not any(old.is_code(n) for n in ol) and not any(new.is_code(n) for n in nl):
                continue  # chỉ chú thích, dòng trống
            if any(old.module_level(n) for n in ol) or any(new.module_level(n) for n in nl):
                module_change = True
                continue
            here = {old.qual_at(n) for n in ol if old.is_code(n)} | {new.qual_at(n) for n in nl if new.is_code(n)}
            wider = {w for q in here if (w := scope_changed(old, new, q))}
            if wider:
                paths |= wider
                continue
            if rec_kind == "old":
                side = ol if tag != "insert" else None
            elif rec_kind == "new":
                side = nl if tag != "delete" else None
            else:
                side = [mapping[n] for n in nl] if tag != "delete" and all(n in mapping for n in nl) else None
            if side is not None and (tag != "replace" or same_shape(old, new, ol, nl)):
                hits = [traced(n) for n in side if rec.is_code(n)]
                if hits and all(hits):
                    found = found.union(*hits)
                    line_blocks += 1
                    continue
            paths |= here
        whole_funcs = set()
        for path in paths:
            got = self.function_tests(rec, path, traced)
            if got is None:
                module_change = True
            elif got:
                whole_funcs |= got
            else:
                module_change = True  # hàm không test nào đi qua: mọi test chạm file
        if module_change:
            self.legacy(rel, "dòng mức module đổi")
            wide = self.file_tests(rel)
            if not wide and rel in self.data["loaded"]:
                self.full.append(f"{rel}: dòng mức module đổi mà file chỉ được nạp lúc nạp module test")
            self.add(wide)
            self.note(rel, "dòng mức module đổi (import, hằng, lớp, chữ ký, docstring) hay hàm không test nào đi qua: "
                           "mọi test chạm file", wide)
            return
        if whole_funcs:
            self.add(whole_funcs)
            self.note(rel, "dòng đổi mà trình ghi vết không thấy, chèn dòng hay đổi cấu trúc: mọi test đi qua hàm "
                           "chứa nó", whole_funcs)
        if found:
            self.add(found)
            self.note(rel, f"{line_blocks} khối đổi: test đi qua đúng các dòng đó", found)
        if not found and not whole_funcs:
            self.note(rel, "không test nào đi qua dòng đổi (hay chỉ đổi chú thích, dòng trống)", set())

    def function_tests(self, rec: FileView, path, traced):
        """Mọi test đi qua một dòng bất kỳ của hàm `path` (hay hàm bao ngoài gần nhất có trong bản lúc ghi vết); None
        khi không tìm thấy hàm nào."""
        for k in range(len(path), 0, -1):
            spans_ = rec.by_qual.get(path[:k])
            if spans_:
                out = set()
                for start, end in spans_:
                    for n in range(start, end + 1):
                        out |= traced(n)
                return out
        return None

    def changed(self, rel, old_b, new_b, ob, nb):
        inv = self.data["inventory"]
        rb = inv.get(rel)
        mod = self.test_module(rel)
        if mod and nb is not None:
            self.modules.add(mod)
            if mod in self.module_names:
                self.items.append((rel, "file test đổi: cả module", self.module_size.get(mod, 0)))
            else:
                self.items.append((rel, "file test mới chưa có trong vết: cả module", 0))
                if rb is None:
                    return
        if not rel.endswith(".py") and self.data["version"] < 2:
            self.full.append(f"{rel}: vết bản cũ không biết file .py nào đọc file này (đọc một lần rồi giữ trong bộ nhớ "
                             "thì chỉ ghi được test đầu tiên); ghi lại bằng `narrow.py record`")
            return
        readers = self.tests_of(self.data["reads"].get(rel))
        if readers:
            self.add(readers)
            self.note(rel, "test đọc file này", readers)
        via = self.opener_tests(rel)
        if via:
            self.add(via)
            self.note(rel, "file .py đọc file này lúc ghi vết: mọi test chạy qua file đó (đọc một lần rồi giữ trong bộ nhớ)",
                      via)
        if rb is None and nb is not None and not mod:
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            near = self.tests_of(self.data["dirs"].get(parent))
            for other in inv:
                if (other.rsplit("/", 1)[0] if "/" in other else "") == parent:
                    near |= self.file_tests(other)
            if near:
                self.add(near)
                self.note(rel, f"file mới chưa có trong vết: mọi test chạm thư mục {parent or '.'}", near)
            else:
                self.full.append(f"{rel}: file mới, không test nào chạm thư mục {parent or '.'}")
            return
        if nb is None:  # file bị xóa
            self.legacy(rel, "file bị xóa")
            gone = self.file_tests(rel) | self.tests_of(self.data["dirs"].get(rel.rsplit("/", 1)[0]
                                                                                  if "/" in rel else ""))
            self.add(gone)
            self.note(rel, "file bị xóa: mọi test chạm file và thư mục của nó", gone)
            return
        if not rel.endswith(".py"):
            if not readers and not via:
                self.note(rel, "không test nào đọc file này lúc ghi vết", set())
            return
        if new_b is None:
            self.legacy(rel, "không đọc được nội dung")
            wide = self.file_tests(rel)
            self.add(wide)
            self.note(rel, "không đọc được nội dung (symlink hay ra ngoài repo): mọi test chạm file", wide)
            return
        if rb == ob:
            kind = "old"
        elif rb == nb:
            kind = "new"
        elif self.align_stale and (rec_b := self.recorded(rel, rb)) is not None:
            self.python_file(rel, old_b, new_b, rec_b, "align")
            return
        else:
            self.legacy(rel, "đổi sau khi ghi vết")
            wide = self.file_tests(rel)
            if not wide and rel in self.data["loaded"]:
                self.full.append(f"{rel}: đổi sau khi ghi vết, không test nào chạm, chỉ được nạp lúc nạp module test")
            self.add(wide)
            self.note(rel, "file đã đổi sau khi ghi vết (vết cũ cho file này): mọi test chạm file", wide)
            return
        if not self.data["lines"].get(rel) and not self.file_tests(rel):
            if rel in self.data["loaded"]:
                self.full.append(f"{rel}: chỉ được nạp lúc nạp module test, không biết test nào dùng")
            else:
                self.note(rel, "không test nào nạp hay đọc file này lúc ghi vết", set())
            return
        self.python_file(rel, old_b, new_b, None, kind)

    def legacy(self, rel: str, why: str):
        """Vết bản 1 không biết module test nào đã nạp file .py (test chỉ đọc hằng, tên của module không chạy dòng nào
        của nó): mọi thay đổi cần "mọi test chạm file" của file .py thì chạy cả bộ."""
        if self.data["version"] < 2 and rel.endswith(".py"):
            self.full.append(f"{rel}: {why}, vết bản cũ không biết module test nào nạp file này; ghi lại bằng "
                             "`narrow.py record`")

    def opener_tests(self, rel: str) -> set:
        """Mọi test chạy qua một dòng của các file .py đã mở `rel` lúc ghi vết (kể cả lúc nạp module): file đọc một lần
        rồi giữ trong bộ nhớ chỉ ghi được test đọc đầu tiên. Không biết file .py nào, hay file đó không test nào chạy
        qua: chạy cả bộ. Vết bản 1 không có thông tin này: tập rỗng (người gọi tự xử)."""
        out = set()
        for who in (self.data.get("openers") or {}).get(rel, []):
            if not who:
                self.full.append(f"{rel}: được đọc từ code không nằm trong repo hay chưa track, không biết test nào dùng")
                continue
            got = set()
            for idx in self.data["lines"].get(who, {}).values():
                got |= self.tests_of(idx)
            got = got or self.file_tests(who)
            if not got:
                self.full.append(f"{rel}: được {who} đọc mà không test nào chạy qua {who}")
            out |= got
        return out

    def drifted(self, rel: str, present: dict):
        """File đổi sau lúc ghi vết, ngoài diff: vết của các file khác có thể cũ theo (đường gọi đã đổi), nên thêm mọi
        test chạm file này. File Python chỉ được nạp lúc nạp module test mà không test nào chạm: chạy cả bộ."""
        if not rel.endswith(".py") and self.data["version"] < 2:
            self.full.append(f"{rel}: đổi sau khi ghi vết, vết bản cũ không biết file .py nào đọc nó; ghi lại bằng "
                             "`narrow.py record`")
            return
        self.legacy(rel, "đổi sau khi ghi vết")
        wide = self.file_tests(rel) | self.opener_tests(rel)
        if rel not in present:
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            wide |= self.tests_of(self.data["dirs"].get(parent))
        if not wide and rel.endswith(".py") and rel in self.data["loaded"]:
            self.full.append(f"{rel}: đổi sau khi ghi vết, không test nào chạm, chỉ được nạp lúc nạp module test")
        self.add(wide)
        self.note(rel, "đổi sau khi ghi vết, ngoài diff (vết có thể cũ): mọi test chạm file", wide)

    def recorded(self, rel: str, rb):
        """Nội dung file lúc ghi vết: blob trong git, hay file trong cây làm việc khi nó vẫn đúng bản đó (chưa commit)."""
        data = blob_bytes(self.root, rb)
        if data is None and rb and self.worktree.get(rel) == rb:
            data = read_current(self.root, rel)
        return data

    def module_of(self, tid: str):
        mi = self.data["module_of"][self.position[tid]] if tid in self.position else -1
        return self.data["modules"][mi][0] if mi >= 0 else None


def plan_full(reasons: list, data=None) -> dict:
    total = len(data["tests"]) if data else None
    return {"mode": "full", "reasons": reasons, "items": [], "names": [], "selected": total, "total": total,
            "estimate": round(sum(data["secs"]), 1) if data else None}


def select(root: Path, base_ref: str, head_ref, align_stale: bool) -> dict:
    data = load_raw(root)
    why = valid_map(data, root)
    base = resolve_ref(root, base_ref or "HEAD")
    head = resolve_ref(root, head_ref) if head_ref else None
    if why:
        return plan_full([f"{why}: ghi bằng `narrow.py record`"])
    if A.local_clean_filters(root):
        return plan_full(["repo có clean filter riêng (git chạy lệnh của repo khi băm file)"], data)
    old_tree = tree_of(root, base)
    worktree = A.tree_blobs(root)
    new_tree = tree_of(root, head) if head else worktree
    if old_tree is None or new_tree is None or worktree is None:
        return plan_full(["git lỗi khi đọc diff"], data)
    changed = sorted(p for p in set(old_tree) | set(new_tree) if old_tree.get(p) != new_tree.get(p))
    if not changed:
        return plan_full([f"diff rỗng so với {base[:12]} (đã commit thì nêu --base <commit trước đó>)"], data)
    sel = Selector(root, data, align_stale, worktree)
    inv = data["inventory"]
    docs = A.doc_filter(root) or (lambda p: False)
    drift = sorted(p for p in set(inv) | set(new_tree) if inv.get(p) != new_tree.get(p) and p not in changed)
    if not align_stale:
        drift_code = [p for p in drift if not docs(p) and not sel.test_module(p)]
        if len(drift_code) > DRIFT_LIMIT:
            return plan_full([f"vết cũ: {len(drift_code)} file code đổi từ lúc ghi vết ({data.get('created')}), ngoài "
                              f"diff; ghi lại bằng `narrow.py record`"], data)
        for p in drift:
            mod = sel.test_module(p)
            if mod:
                if p in new_tree:
                    sel.modules.add(mod)
                    sel.note(p, "file test đổi hay mới sau khi ghi vết: cả module", {mod})
            else:
                sel.drifted(p, new_tree)
    for rel in changed:
        ob, nb = old_tree.get(rel), new_tree.get(rel)
        old_b = blob_bytes(sel.root, ob) if ob else None
        if nb is None:
            new_b = None
        elif head:
            new_b = blob_bytes(sel.root, nb)
        else:
            new_b = read_current(root, rel)
        if ob and old_b is None:
            return plan_full([f"git lỗi khi đọc {rel}"], data)
        sel.changed(rel, old_b, new_b, ob, nb)
    if sel.full:
        return plan_full(sel.full, data)
    op = {sel.tests[int(i)] for i in data["opaque"]}
    if op:
        sel.add(op)
        progs = sorted({p for v in data["opaque"].values() for p in v})
        sel.items.append(("(công cụ ngoài)", "test chạy " + ", ".join(progs[:6]) + " trong repo (đọc được mọi file)",
                          len(op)))
    return finish(sel, data, worktree)


def finish(sel: Selector, data: dict, present: dict) -> dict:
    """Danh sách tên cho unittest: module chạy cả, còn lại từng test, theo thứ tự lúc ghi vết. Module có file không
    còn trong cây làm việc (`present`, nơi test sẽ chạy) bị bỏ: unittest không nạp được tên của nó."""
    tests = data["tests"]
    gone = {m for m, rel in data["modules"] if rel and rel not in present}
    expand = {tests[i] for i in data["unloadable"]} | set(data.get("alone_bad", []))
    module_of = {t: sel.module_of(t) for t in sel.ids}
    for t in sel.ids & expand:
        if module_of.get(t):
            sel.modules.add(module_of[t])
    if expand & sel.ids:
        sel.items.append(("(test riêng lẻ)", "test không nạp lại được theo tên hay trượt khi chạy một mình: cả module",
                          len(expand & sel.ids)))
    per_module: dict = {}
    for i, t in enumerate(tests):
        mi = data["module_of"][i]
        per_module.setdefault(data["modules"][mi][0] if mi >= 0 else None, []).append(t)
    chosen = set(sel.ids)
    for m in sel.modules:
        chosen |= set(per_module.get(m, []))
    names, count = [], 0
    for m, members in per_module.items():
        picked = [t for t in members if t in chosen]
        if not picked or m in gone:
            continue
        if m and (m in sel.modules or len(picked) == len(members)):
            names.append(m)
        else:
            names.extend(picked)
        count += len(picked)
    new_modules = sorted(m for m in sel.modules if m not in per_module)
    names.extend(new_modules)
    secs = dict(zip(tests, data["secs"], strict=False))
    estimate = round(sum(secs.get(t, 0.0) for t in chosen), 1)
    total = len(tests)
    if count >= FULL_SHARE * total:
        out = plan_full([f"chọn {count}/{total} test (từ {int(FULL_SHARE * 100)}% trở lên): chạy cả bộ"], data)
        out["items"] = sel.items
        return out
    mode = "narrow" if names else "none"
    return {"mode": mode, "reasons": [], "items": sel.items, "names": names, "selected": count, "total": total,
            "new_modules": new_modules, "estimate": estimate}


# ---------------------------------------------------------------- chạy

def describe(plan: dict, data) -> list:
    out = []
    root = data.get("root") if isinstance(data, dict) else None
    if isinstance(root, str) and not valid_map(data, Path(root)):
        out.append(f"[narrow] vết ghi {data.get('created')} ở {str(data.get('head'))[:12]}: {len(data['tests'])} test")
    for rel, why, n in plan["items"][:MAX_LISTED]:
        out.append(f"- {rel}: {why}" + (f" ({n} test)" if n else ""))
    if len(plan["items"]) > MAX_LISTED:
        out.append(f"- … và {len(plan['items']) - MAX_LISTED} file khác")
    if plan["mode"] == "full":
        out.append("[narrow] chạy cả bộ: " + "; ".join(plan["reasons"]))
    elif plan["mode"] == "none":
        out.append(f"[narrow] không test nào chạm phần đổi (0/{plan['total']} test): không chạy gì")
    else:
        extra = f" + {len(plan['new_modules'])} module test mới" if plan.get("new_modules") else ""
        out.append(f"[narrow] chọn {plan['selected']}/{plan['total']} test{extra}, ước {plan['estimate']} giây theo lúc "
                   "ghi vết (đã gồm chậm do ghi vết)")
    return out


def unittest_args(data) -> list:
    """Đối số cho chế độ cả bộ: của vết khi hợp lệ (args_ok), không thì mặc định."""
    args = data.get("args") if isinstance(data, dict) else None
    return list(args) if args_ok(args) else list(DEFAULT_ARGS)


def receipt_cmd(root: Path, plan: dict, data, timeout: float) -> list:
    receipt = HERE.parent / "receipt.py"
    base = [sys.executable, str(receipt), "run", "--project", str(root), "--timeout", str(int(timeout))]
    if plan["mode"] == "full":
        return [*base, "--", sys.executable, "-m", "unittest", *unittest_args(data)]
    return [*base, "--narrow", "--label", NARROW_LABEL, "--", sys.executable, str(HERE), "exec", "--project",
            str(root), "--", *plan["names"]]


def cmd_run(root: Path, base, head, plan_only: bool, as_json: bool, align_stale: bool, timeout: float) -> int:
    plan = select(root, base, head, align_stale)
    data = load_raw(root)
    if as_json:
        print(json.dumps(plan, ensure_ascii=False))
        return 0
    print("\n".join(describe(plan, data)), flush=True)
    if plan_only or plan["mode"] == "none":
        return 0
    if head:  # đo diff cũ: chạy trên code hiện tại, không ghi biên nhận
        if plan["mode"] == "full":
            print(f"[narrow] đo: cả bộ, không chạy lại (ước {plan['estimate']} giây theo lúc ghi vết)")
            return 0
        argv = [sys.executable, "-m", "unittest", *plan["names"]]
        started = time.monotonic()
        code = subprocess.run(argv, cwd=str(root), stdin=subprocess.DEVNULL).returncode
        print(f"[narrow] đo: {plan['selected']}/{plan['total']} test, {time.monotonic() - started:.1f} giây, mã {code} "
              "(không ghi biên nhận)")
        return code
    return subprocess.run(receipt_cmd(root, plan, data, timeout), cwd=str(root), stdin=subprocess.DEVNULL).returncode


FAIL_RE = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([\w.]+)\)", re.M)


def cmd_exec(root: Path, names: list) -> int:
    """Chạy bộ thu hẹp. Có test trượt mà module của nó chưa chạy trọn thì chạy lại TOÀN BỘ danh sách, với mỗi test trượt
    thay bằng cả module của nó (test cần test khác chạy trước), và lấy mã thoát của lần chạy lại: mọi lỗi khác của lần
    đầu (test khác, module không nạp được) vẫn có trong lần đó, không bị lần chạy lại che đi."""
    if not names or not all(NAME_RE.match(n) for n in names):
        print("[narrow] tên test không hợp lệ")
        return 2
    first = subprocess.run([sys.executable, "-m", "unittest", *names], cwd=str(root), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, errors="replace")
    sys.stdout.write(first.stdout)
    sys.stdout.write(first.stderr)
    if first.returncode == 0:
        return 0
    data = load_raw(root)
    known = {m for m, _ in data["modules"]} if data and not valid_map(data, root) else set()
    failing, modules = set(), set()
    for name, where in FAIL_RE.findall(first.stdout + first.stderr):
        tid = where if where.endswith("." + name) else f"{where}.{name}"
        mod = max((m for m in known if tid.startswith(m + ".")), key=len, default=None)
        if mod and mod not in names and NAME_RE.match(tid):
            failing.add(tid)
            modules.add(mod)
    if not modules or len(failing) > 20:
        return first.returncode
    again_names, seen = [], set()
    for n in names:
        owner = next((m for m in modules if n == m or n.startswith(m + ".")), None)
        item = owner or n
        if item not in seen:
            seen.add(item)
            again_names.append(item)
    print(f"[narrow] {len(failing)} test trượt trong bộ thu hẹp; chạy lại cả bộ thu hẹp với module "
          f"{', '.join(sorted(modules))} chạy trọn, để phân biệt lỗi thật với test cần test khác chạy trước", flush=True)
    again = subprocess.run([sys.executable, "-m", "unittest", *again_names], cwd=str(root),
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")
    sys.stdout.write(again.stdout)
    sys.stdout.write(again.stderr)
    if again.returncode != 0:
        print("[narrow] lần chạy lại vẫn trượt: lỗi thật (hay cần test của module khác chạy trước; chạy cả bộ để chắc)")
        return again.returncode
    print("[narrow] lần chạy lại đạt: " + ", ".join(sorted(failing)) + " trượt khi chạy riêng; lần sau chạy cả module")
    if data and not valid_map(data, root):
        data["alone_bad"] = sorted(set(data.get("alone_bad", [])) | failing)
        try:
            A.write_json_atomic(state_file(root), data)
        except OSError:
            pass
    return 0


def cmd_status(root: Path) -> int:
    data = load_raw(root)
    why = valid_map(data, root)
    if why:
        print(f"[narrow] {why}: ghi bằng `narrow.py record --project {root}`")
        return 1
    now = A.tree_blobs(root) or {}
    inv = data["inventory"]
    drift = sorted(p for p in set(inv) | set(now) if inv.get(p) != now.get(p))
    print(f"[narrow] vết ghi {data.get('created')} ở {str(data.get('head'))[:12]}, {len(data['tests'])} test, "
          f"{data.get('seconds')} giây; {len(drift)} file khác lúc ghi"
          + (": " + ", ".join(drift[:10]) if drift else ""))
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["_shard"]:
        rest = argv[argv.index("--") + 1:] if "--" in argv else []
        head = argv[1:argv.index("--")] if "--" in argv else argv[1:]
        opts = dict(zip(head[0::2], head[1::2], strict=False))
        return cmd_shard(opts["--root"], opts["--out"], opts["--site"], opts["--targets"], rest)
    ap = argparse.ArgumentParser(description="Chạy bộ test thu hẹp theo dòng đổi.", allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="ghi vết cả bộ test", allow_abbrev=False)
    rec.add_argument("--project", default=".")
    rec.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)))
    rec.add_argument("--timeout", type=float, default=3600)
    rec.add_argument("args", nargs=argparse.REMAINDER)
    run = sub.add_parser("run", help="chọn và chạy test chạm dòng đổi", allow_abbrev=False)
    run.add_argument("--project", default=".")
    run.add_argument("--base", default="HEAD")
    run.add_argument("--head")
    run.add_argument("--plan", action="store_true", help="chỉ in, không chạy")
    run.add_argument("--json", action="store_true", help="in kế hoạch dạng JSON, không chạy")
    run.add_argument("--align-stale", action="store_true", help="chỉ để đo: ánh xạ dòng của file đã đổi sau khi ghi vết")
    run.add_argument("--timeout", type=float, default=1800)
    st = sub.add_parser("status", help="vết ghi lúc nào, cũ chưa", allow_abbrev=False)
    st.add_argument("--project", default=".")
    ex = sub.add_parser("exec", help="(receipt.py gọi) chạy các test đã chọn", allow_abbrev=False)
    ex.add_argument("--project", default=".")
    ex.add_argument("names", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    try:
        root = repo_root(args.project)
        if args.cmd == "record":
            rest = args.args[1:] if args.args[:1] == ["--"] else args.args
            if rest and not args_ok(rest):
                raise Bad("đối số sau `--` chỉ nhận đúng mặc định hay tên module, test (không nhận cờ như -k)")
            return cmd_record(root, rest or list(DEFAULT_ARGS), max(1, args.jobs), args.timeout)
        if args.cmd == "run":
            return cmd_run(root, args.base, args.head, args.plan, args.json, args.align_stale, args.timeout)
        if args.cmd == "status":
            return cmd_status(root)
        names = args.names[1:] if args.names[:1] == ["--"] else args.names
        return cmd_exec(root, names)
    except Bad as exc:
        print(f"[narrow] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
