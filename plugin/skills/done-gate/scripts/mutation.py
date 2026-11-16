#!/usr/bin/env python3
"""Mutation trên dòng vừa đổi (done-gate bước 4, mức cao; GĐ6, S9): cài lỗi nhỏ vào dòng code vừa đổi rồi chạy test;
đột biến nào test không bắt (sống) là chỗ test còn yếu. Chỉ để báo, không chặn: luôn thoát mã 0, dòng cuối `Mutation:`.

Python dùng mutmut 2.5.1 (bạn duyệt 16/11/2026, cài vào `.venv-mutmut/` của agent-stack bằng `mutation.py setup`):
`--runner` nhận lệnh test bất kỳ, `--use-patch-file` chỉ đột biến dòng thêm trong bản vá. mutmut sửa file tại chỗ và nạp
`mutmut_config.py` ở thư mục đang chạy, nên luôn chạy trong bản chép cây làm việc ở thư mục tạm của hệ điều hành, xóa
bản chép khi xong, kể cả khi quá giờ (TM-129). Rust (cargo-mutants), Go (gremlins), TypeScript (Stryker) chưa vet: báo
"chưa chạy".

Lệnh:
  mutation.py [--project DIR] [--base REF] [--cmd "<lệnh test>"] [--timeout GIÂY] [--mutmut PATH] [--link PATH...]
              [--json]
      Lệnh test: `--cmd`, không thì `cmd` trong sổ khóa của các file test đã khóa có trong diff. mutmut: `--mutmut`,
      biến AGENT_STACK_MUTMUT, rồi `<agent-stack>/.venv-mutmut/bin/mutmut`.
  mutation.py setup
      Tạo `.venv-mutmut/` của agent-stack từ `tools/mutmut-requirements.txt` (mã băm) và
      `tools/mutmut-build-constraints.txt`; mã thoát khác 0 khi cài hỏng.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))
sys.path.insert(0, str(HERE.parents[2] / "session-keeper" / "scripts"))  # fails_before: dựng bản chép
sys.path.insert(0, str(HERE.parent))
IMPORT_ERROR = None
try:  # bản cài hỏng cũng phải thoát 0 với dòng trạng thái (S9)
    import agentstack as A
    import fails_before as FB
    import risk
    import testlock as TL
except Exception as exc:  # noqa: BLE001
    IMPORT_ERROR = exc

DEFAULT_TIMEOUT = 540.0  # dưới trần 600 giây của lệnh Bash chạy trước mặt, để kịp in dòng trạng thái
QUERY_TIMEOUT = 60
MAX_LISTED = 12
OTHER_LANGS = {".rs": "Rust (cargo-mutants)", ".go": "Go (gremlins)", ".ts": "TypeScript (Stryker)",
               ".tsx": "TypeScript (Stryker)", ".js": "JavaScript (Stryker)", ".jsx": "JavaScript (Stryker)",
               ".mjs": "JavaScript (Stryker)", ".cjs": "JavaScript (Stryker)"}


class Skip(Exception):
    """Không chạy được: lý do vào dòng trạng thái "chưa chạy: …"."""


class Args(argparse.ArgumentParser):
    def error(self, message):  # tham số sai cũng không được thoát khác 0 (S9)
        raise Skip(f"tham số sai ({message})")


def stack_root() -> Path:
    try:
        return Path(A.home_dir())
    except Exception:  # noqa: BLE001
        return HERE.parents[4]


def find_mutmut(option) -> Path:
    value = option or os.environ.get("AGENT_STACK_MUTMUT") or str(stack_root() / ".venv-mutmut" / "bin" / "mutmut")
    path = Path(value).expanduser()
    if not (path.is_file() and os.access(path, os.X_OK)):
        raise Skip(f"thiếu mutmut ({path}); cài bằng `python3 {HERE} setup` (bạn đã duyệt mutmut 2.5.1, 16/11/2026)")
    return path


def runner_for(option, book: dict, changed) -> str:
    """Lệnh test cho `--runner` (một chuỗi; mutmut tách bằng shlex, không qua shell)."""
    if option:
        return option
    cmds = []
    for rel, entry in sorted(book["files"].items()):
        cmd = entry.get("cmd")
        if rel in changed and isinstance(cmd, list) and cmd and all(isinstance(x, str) for x in cmd) and cmd not in cmds:
            cmds.append(cmd)
    if not cmds:
        raise Skip("không biết lệnh test: nêu --cmd \"<lệnh test>\", hay khóa test trước (`receipt.py lock --red`) để sổ "
                   "khóa có lệnh")
    if len(cmds) == 1:
        return shlex.join(cmds[0])
    return shlex.join(["sh", "-c", " && ".join(shlex.join(c) for c in cmds)])


def make_patch(paths, entries: dict, blobs: dict, current: dict, prefix: str) -> str:
    """Bản vá hợp nhất cho các file Python đổi (đường dẫn tính từ thư mục chạy mutmut, không có `./`)."""
    out = []
    for rel in paths:
        old = blobs.get(entries[rel][1], b"") if rel in entries else b""
        new = current[rel][1]
        name = rel[len(prefix):] if prefix else rel

        def lines(data: bytes) -> list:
            return [x if x.endswith("\n") else x + "\n" for x in data.decode("utf-8", "replace").splitlines(True)]
        out += difflib.unified_diff(lines(old), lines(new), fromfile=f"a/{name}", tofile=f"b/{name}")
    return "".join(out)


def tests_dir(cwd: Path, book: dict, prefix: str) -> str:
    for name in ("tests", "test"):
        if (cwd / name).is_dir():
            return name
    for rel in sorted(book["files"]):
        if rel.startswith(prefix) and risk.kind(rel) == "test":
            parent = Path(rel[len(prefix):]).parent.as_posix()
            if (cwd / parent).is_dir():
                return parent
    return "."


RUNNING: list = []  # tiến trình mutmut đang chạy, để SIGTERM và finally giết cả nhóm (TM-129)


def kill_group(proc) -> None:
    """Giết cả nhóm tiến trình của mutmut, kể cả khi mutmut đã thoát mà lệnh test con còn sống trong nhóm."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def run_group(cmd: list, cwd: Path, timeout: float, log: Path):
    """(mã thoát hay None khi quá giờ, output). Output ghi ra file (không qua pipe: tiến trình cháu tách session mà giữ
    pipe thì đọc pipe treo mãi). Quá giờ thì giết cả nhóm tiến trình (lệnh test con của mutmut)."""
    with open(log, "wb") as out:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    RUNNING.append(proc)
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        code = None
    finally:
        kill_group(proc)  # cả khi xong: lệnh test con có thể còn sống trong nhóm
        RUNNING.remove(proc)
    try:
        text = log.read_bytes()[-20000:].decode("utf-8", "replace")
    except OSError:
        text = ""
    return code, text


def on_term(*_):
    for proc in RUNNING:
        kill_group(proc)
    sys.exit(143)


def query(mutmut: Path, cwd: Path, *args: str) -> str:
    try:
        out = subprocess.run([str(mutmut), *args], cwd=str(cwd), capture_output=True, text=True, errors="replace",
                             timeout=QUERY_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout or ""


def parse_results(xml_text: str) -> dict:
    """Kết quả từ `mutmut junitxml`: mỗi testcase là một đột biến; có <failure> là sống, <error type=timeout> là quá
    giờ. XML hỏng thì như không có kết quả."""
    res = {"total": 0, "survived": [], "timeout": 0}
    try:
        root = ET.fromstring(xml_text) if xml_text.strip() else None
    except ET.ParseError:
        root = None
    if root is None:
        return res
    for case in root.iter("testcase"):
        res["total"] += 1
        try:
            line = int(case.get("line") or 0)
        except ValueError:
            line = 0
        failure = case.find("failure")
        error = case.find("error")
        if failure is not None:
            diff = (failure.text or failure.get("message") or "").strip()
            res["survived"].append({"file": case.get("file") or "?", "line": line, "diff": diff[:600]})
        elif error is not None and (error.get("type") or "") == "timeout":
            res["timeout"] += 1
    return res


STATUSES = ("killed", "survived", "timeout", "suspicious", "untested", "skipped")
MAX_SHOW = 40  # số đột biến sống lấy vị trí bằng `mutmut show` khi junitxml hỏng


def parse_show(text: str):
    """Vị trí đột biến từ `mutmut show <id>` (bản vá hợp nhất): file ở dòng `--- `, dòng = đầu đoạn phía cũ cộng số
    dòng ngữ cảnh đứng trước dòng `-` đầu tiên."""
    path, start, offset = None, None, 0
    for line in text.splitlines():
        if line.startswith("--- ") and path is None:
            path = line[4:].strip().split("\t")[0]
            path = path.removeprefix("a/")
        elif line.startswith("@@") and start is None:
            m = re.match(r"@@ -(\d+)", line)
            start = int(m.group(1)) if m else None
        elif start is not None and line.startswith("-"):
            return {"file": path or "?", "line": start + offset, "diff": text.strip()[:600]}
        elif start is not None and line.startswith(" "):
            offset += 1
    return None


def results_by_ids(mutmut: Path, cwd: Path) -> dict:
    """Kết quả khi `mutmut junitxml` hỏng (mutmut 2.5.1 văng lỗi pony sau khi lần chạy bị giết vì quá giờ): đếm bằng
    `result-ids`, vị trí đột biến sống bằng `show`."""
    ids = {st: query(mutmut, cwd, "result-ids", st).split() for st in STATUSES}
    survived = []
    for i, mid in enumerate(ids["survived"]):
        loc = parse_show(query(mutmut, cwd, "show", mid)) if i < MAX_SHOW else None
        survived.append(loc or {"file": "?", "line": 0, "diff": ""})
    return {"total": sum(len(v) for v in ids.values()), "survived": survived, "timeout": len(ids["timeout"]),
            "killed": len(ids["killed"]), "untested": len(ids["untested"])}


def count_ids(text: str) -> int:
    return len([x for x in text.split() if x.strip()])


def analyse(args) -> dict:
    root = Path(args.project).expanduser()
    if not root.is_dir():
        raise Skip(f"không thấy thư mục project {root}")
    root = root.resolve()
    top_out = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top_out.returncode != 0 or not top_out.stdout.strip():
        raise Skip("không phải git repo (cần git để biết dòng nào vừa đổi)")
    top = Path(top_out.stdout.strip()).resolve()
    try:
        sha = FB.git(top, "rev-parse", "--verify", "-q", args.base + "^{commit}").decode().strip()
        entries, current = FB.base_entries(top, sha), FB.current_files(top)
    except FB.Problem as exc:
        raise Skip(str(exc)) from None
    changed, _deleted = FB.diff(entries, current)
    sub = root.relative_to(top).as_posix()
    prefix = "" if sub == "." else sub + "/"
    code = [p for p in sorted(changed) if risk.kind(p) == "code" and p.startswith(prefix)]
    py = [p for p in code if p.endswith(".py")]
    others = sorted({OTHER_LANGS[Path(p).suffix] for p in code if Path(p).suffix in OTHER_LANGS})
    notes = [f"chưa chạy cho {lang}: công cụ chưa vet (ngoài phạm vi GĐ6)" for lang in others]
    if not py:
        raise Skip("không có file Python nào đổi so với " + args.base + (f" ({'; '.join(notes)})" if notes else ""))
    mutmut = find_mutmut(args.mutmut)
    book = TL.load(top)
    runner = runner_for(args.cmd, book, changed)
    links = FB.check_links(root, top, args.link)
    blobs = FB.read_blobs(top, [entries[p][1] for p in py if p in entries])
    return {"top": top, "sub": sub, "prefix": prefix, "py": py, "notes": notes, "mutmut": mutmut, "book": book,
            "runner": runner, "links": links, "entries": entries, "blobs": blobs, "current": current}


def run(args) -> dict:
    info = analyse(args)
    top, prefix = info["top"], info["prefix"]
    tmp = Path(tempfile.mkdtemp(prefix="mutation-"))  # quyền 0700
    previous = signal.signal(signal.SIGTERM, on_term)
    try:
        tree = tmp / top.name
        tree.mkdir()
        for rel, (mode, data) in info["current"].items():
            FB.put(tree, rel, mode, data)
        for rel in info["links"]:
            FB.put(tree, rel, FB.SYMLINK, os.fsencode(str(top / rel)))
        cwd = tree / info["sub"] if info["sub"] != "." else tree
        patch = tmp / "mutmut.patch"
        patch.write_text(make_patch(info["py"], info["entries"], info["blobs"], info["current"], prefix),
                         encoding="utf-8")
        targets = [p[len(prefix):] for p in info["py"]]
        cmd = [str(info["mutmut"]), "run", "--paths-to-mutate", ",".join(targets), "--runner", info["runner"],
               "--use-patch-file", str(patch), "--tests-dir", tests_dir(cwd, info["book"], prefix)]
        code, output = run_group(cmd, cwd, args.timeout, tmp / "mutmut-run.log")
        res = parse_results(query(info["mutmut"], cwd, "junitxml"))
        if res["total"]:
            res["killed"] = count_ids(query(info["mutmut"], cwd, "result-ids", "killed"))
            res["untested"] = count_ids(query(info["mutmut"], cwd, "result-ids", "untested"))
        else:
            res = results_by_ids(info["mutmut"], cwd)
    finally:
        signal.signal(signal.SIGTERM, previous)
        shutil.rmtree(tmp, ignore_errors=True)
    res.update(notes=info["notes"], files=info["py"], runner=info["runner"])
    if code is None:
        res.update(status="partial" if res["total"] else "skipped", reason=f"quá giờ sau {args.timeout:g} giây")
    elif not res["total"]:
        tail = " ".join(output.strip().splitlines()[-2:])[-200:]
        why = ("test không đạt trên code hiện tại (mutmut cần test xanh trước khi đột biến)"
               if "don't run cleanly" in output or "cleanly" in output else
               "mutmut không sinh đột biến nào trên dòng đổi (dòng đổi chỉ là chú thích hay chuỗi tài liệu, hay "
               "đường dẫn trong bản vá lệch)")
        res.update(status="skipped", reason=why + (f"; mutmut: {tail}" if tail else ""))
    else:
        res.update(status="ran")
    return res


def summary(res: dict) -> list:
    lines = [f"- {n}" for n in res.get("notes") or []]
    survived = res.get("survived") or []
    for s in survived[:MAX_LISTED]:
        first = next((ln for ln in s["diff"].splitlines() if ln.startswith("+") and not ln.startswith("+++")), "")
        lines.append(f"- sống: {s['file']}:{s['line']}" + (f"  {first.strip()[:120]}" if first else ""))
    if len(survived) > MAX_LISTED:
        lines.append(f"- và {len(survived) - MAX_LISTED} đột biến sống khác")
    where = ", ".join(f"{s['file']}:{s['line']}" for s in survived[:MAX_LISTED])
    counts = (f"{res['total']} đột biến trên dòng đổi, {res['killed']} bị bắt, {len(survived)} sống"
              + (f", {res['timeout']} quá giờ" if res.get("timeout") else "")
              + (f", {res['untested']} chưa chạy tới" if res.get("untested") else ""))
    if res["status"] == "ran":
        lines.append(f"Mutation: {counts}" + (f" ({where})" if where else ""))
    elif res["status"] == "partial":
        lines.append(f"Mutation: chưa chạy xong: {res['reason']}; đã có {counts}" + (f" ({where})" if where else ""))
    else:
        lines.append(f"Mutation: chưa chạy: {res['reason']}")
    return lines


def cmd_setup() -> int:
    """Cài mutmut 2.5.1 vào `.venv-mutmut/` của agent-stack, đúng bộ gói đã vet (mã băm), không cài toàn cục."""
    home = stack_root()
    venv, req = home / ".venv-mutmut", home / "tools" / "mutmut-requirements.txt"
    build = home / "tools" / "mutmut-build-constraints.txt"
    uv = shutil.which("uv")
    if uv is None:
        print("[mutation] thiếu uv (cài qua install.sh của agent-stack)")
        return 2
    env = dict(os.environ, UV_CACHE_DIR=str(home / ".cache" / "uv"), UV_PYTHON_DOWNLOADS="never")
    steps = []
    if not (venv / "bin" / "python").exists():
        steps.append([uv, "venv", "--python", "3.11", "--python-preference", "only-system", str(venv)])
    steps.append([uv, "pip", "install", "--python", str(venv / "bin" / "python"), "--require-hashes", "-r", str(req),
                  "--build-constraints", str(build)])
    steps.append([str(venv / "bin" / "mutmut"), "version"])
    for step in steps:
        out = subprocess.run(step, cwd=str(home), env=env, capture_output=True, text=True)
        print((out.stdout + out.stderr).strip()[-800:])
        if out.returncode != 0:
            print(f"[mutation] lỗi ở bước: {' '.join(step[:3])} (mã {out.returncode})")
            return out.returncode
    print(f"[mutation] đã cài mutmut vào {venv}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["setup"]:
        return cmd_setup()
    as_json = "--json" in argv
    try:
        ap = Args(description="Mutation trên dòng vừa đổi (chỉ để báo, luôn thoát 0).")
        ap.add_argument("--project", default=".")
        ap.add_argument("--base", default="HEAD")
        ap.add_argument("--cmd", help="lệnh test cho mutmut --runner (mặc định: lệnh trong sổ khóa)")
        ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="giới hạn cả lần chạy, giây")
        ap.add_argument("--mutmut", help="đường dẫn mutmut (mặc định: .venv-mutmut của agent-stack)")
        ap.add_argument("--link", action="append", metavar="PATH", help="nối thư mục bị git bỏ qua, như .venv")
        ap.add_argument("--json", action="store_true")
        args = ap.parse_args(argv)
        if IMPORT_ERROR is not None:
            raise Skip(f"không nạp được thư viện của agent-stack ({IMPORT_ERROR!r})"[:300])
        res = run(args)
    except Skip as exc:
        res: dict = {"status": "skipped", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 (chỉ để báo: lỗi nào cũng không được làm trượt done-gate)
        res = {"status": "skipped", "reason": f"lỗi bất ngờ: {exc!r}"[:300]}
    res.setdefault("total", 0)
    res.setdefault("killed", 0)
    res.setdefault("survived", [])
    res.setdefault("timeout", 0)
    res.setdefault("untested", 0)
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("\n".join(summary(res)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
