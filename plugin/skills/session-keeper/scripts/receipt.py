#!/usr/bin/env python3
"""Biên nhận kiểm tra: chạy một lệnh kiểm tra (test, lint, build) và ghi kết quả gắn với nội dung code
lúc chạy, để phiên sau và skill tien-do biết kết quả đó còn đúng cho code hiện tại hay đã cũ.

Kết quả đạt cũ không chứng minh cho code đã sửa sau đó. Biên nhận lưu dấu vân tay nội dung của cây làm
việc (file đang theo dõi và file mới), nên commit mà không đổi nội dung thì biên nhận vẫn còn khớp.

Lệnh:
  receipt.py run [--project DIR] [--label TÊN] [--timeout GIÂY] -- <lệnh> [tham số...]
      Chạy lệnh (không qua shell), in output, ghi biên nhận. Mã thoát của receipt.py là mã thoát của lệnh.
  receipt.py show [--project DIR] [--json]
      In các lần kiểm tra đã ghi và cho biết từng kết quả còn khớp code hiện tại không.
  receipt.py forget [--project DIR] TÊN [TÊN...]
      Xoá biên nhận theo tên (tên như `show` in ra). Mã thoát 1 nếu có tên không tìm thấy.
  receipt.py prune [--project DIR] [--dry-run]
      Xoá biên nhận trượt của lệnh test trỏ tới module hay file test không còn trong project (ví dụ
      `python3 -m unittest tests.test_cu` sau khi xoá tests/test_cu.py), vì chạy lại lệnh đó chỉ trượt mãi.
      Không chắc (discover, gói ngoài project, giá trị của option) thì giữ, để không che một test đang trượt thật.

Biên nhận nằm trong state/tests/ của agent-stack, không ghi gì vào project.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))
import agentstack as A  # noqa: E402

TAIL_CHARS = 1500
MAX_CHECKS = 20


def summary_line(output: str) -> str:
    """Dòng tổng kết đáng tin nhất trong output (dòng cuối có chữ số hoặc từ khóa kết quả)."""
    keys = ("passed", "failed", "error", "ok", "fail", "ran ", "đạt", "lỗi", "tests", "warning")
    for line in reversed([ln.strip() for ln in output.splitlines() if ln.strip()]):
        if any(k in line.lower() for k in keys):
            return A.clip(line, 160)
    return ""


def record(root: Path, label: str, cmd: list, code: int, output: str, seconds: float,
           before, after) -> dict:
    path = A.receipt_path(root)
    data = A.read_json(path, {}) or {}
    checks = data.get("checks") or {}
    rec = {"cmd": cmd, "ok": code == 0, "exit": code, "summary": summary_line(output),
           "tail": output[-TAIL_CHARS:], "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "seconds": round(seconds, 1), "fingerprint": after, "fingerprint_before": before,
           "changed_tree": before is not None and after is not None and before != after}
    checks[label] = rec
    if len(checks) > MAX_CHECKS:  # giữ các lần kiểm tra mới nhất
        checks = dict(sorted(checks.items(), key=lambda kv: kv[1].get("ts", ""))[-MAX_CHECKS:])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        A.write_json_atomic(path, {"root": str(root), "checks": checks})
        rec["saved"] = True
    except OSError as exc:  # không ghi được biên nhận thì vẫn trả kết quả của lệnh
        rec["saved"] = False
        rec["save_error"] = str(exc)
    return rec


def cmd_run(root: Path, label: str, cmd: list, timeout: float) -> int:
    before = A.tree_fingerprint(root)
    start = time.time()
    try:
        out = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=timeout)
        code, output = out.returncode, (out.stdout or "") + (out.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code = 124
        output = ((exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        output += f"\n[receipt] dừng sau {timeout:.0f} giây"
    except OSError as exc:
        code, output = 127, f"[receipt] không chạy được lệnh: {exc}"
    seconds = time.time() - start
    rec = record(root, label, cmd, code, output, seconds, before, A.tree_fingerprint(root))
    sys.stdout.write(output if output.endswith("\n") or not output else output + "\n")
    mark = "✓ đạt" if rec["ok"] else f"✗ trượt (mã {code})"
    note = " · lệnh đã làm thay đổi file trong project" if rec["changed_tree"] else ""
    where = "" if rec["fingerprint"] else " · không phải git repo nên không theo dõi được code có đổi sau đó không"
    saved = "đã ghi biên nhận" if rec["saved"] else f"KHÔNG ghi được biên nhận ({rec['save_error']})"
    print(f"[receipt] {mark} · {label} · {rec['seconds']} giây · {saved}{note}{where}")
    return code


MODULE_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")
PYTEST_VALUE_OPTS = ("--ignore", "--deselect", "--ignore-glob", "-k", "-m", "-p", "-c", "-o", "--rootdir",
                     "--junitxml", "--basetemp", "--confcutdir")
PYTEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")


def load_checks(root: Path) -> dict:
    """Các biên nhận đã ghi; bỏ qua phần hỏng (file không phải dict, mục không phải dict)."""
    data = A.read_json(A.receipt_path(root), {})
    checks = data.get("checks") if isinstance(data, dict) else None
    if not isinstance(checks, dict):
        return {}
    return {label: rec for label, rec in checks.items() if isinstance(label, str) and isinstance(rec, dict)}


def save_checks(root: Path, checks: dict):
    """Ghi lại biên nhận (xoá file khi không còn mục nào). Trả về lỗi dạng chữ, hoặc None khi ghi được."""
    path = A.receipt_path(root)
    try:
        if checks:
            path.parent.mkdir(parents=True, exist_ok=True)
            A.write_json_atomic(path, {"root": str(root), "checks": checks})
        elif path.exists():
            path.unlink()
    except OSError as exc:
        return str(exc)
    return None


def unittest_missing(root: Path, args: list) -> list:
    if "discover" in args:
        return []  # discover tự tìm test theo pattern: không biết chắc module nào
    missing, skip = [], False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in ("-k",):
            skip = True  # giá trị của -k là mẫu tên test, không phải module
            continue
        if arg.startswith("-") or not MODULE_RE.match(arg):
            continue
        parts = arg.split(".")
        if not ((root / parts[0]).is_dir() or (root / f"{parts[0]}.py").is_file()):
            continue  # gốc không nằm trong project (gói đã cài, hay lớp test): không đoán
        # Còn khi có một tiền tố là file .py (phần sau là lớp, hàm test), hoặc cả tên là một gói.
        as_file = any((root / Path(*parts[:i])).with_suffix(".py").is_file() for i in range(1, len(parts) + 1))
        if not as_file and not (root / Path(*parts) / "__init__.py").is_file():
            missing.append(arg)
    return missing


def missing_targets(root: Path, cmd) -> list:
    """Module hay file test mà lệnh nhắc tới nhưng không còn trong project; rỗng khi không chắc. Chỉ xét
    `python -m unittest a.b.c` (module, lớp hay hàm test, gốc `a` phải nằm trong project; bỏ qua discover và giá
    trị của -k) và pytest với tham số là file test theo quy ước tên (`test_*.py`, `*_test.py`, kể cả `::test_y`)
    trong thư mục đang có. Lệnh khác trả về rỗng."""
    if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) for x in cmd):
        return []
    for i, arg in enumerate(cmd):
        if arg == "unittest" and i > 0 and cmd[i - 1] == "-m":
            return unittest_missing(root, cmd[i + 1:])
    pytest_at = next((i for i, arg in enumerate(cmd)
                      if (arg == "pytest" and i > 0 and cmd[i - 1] == "-m")
                      or (i == 0 and Path(arg).name in ("pytest", "py.test"))), None)
    if pytest_at is None:
        return []
    missing, skip = [], False
    for arg in cmd[pytest_at + 1:]:
        if skip:
            skip = False
            continue
        if arg in PYTEST_VALUE_OPTS:
            skip = True  # file bị loại khỏi lần chạy (--ignore x.py): mất cũng không làm lệnh trượt
            continue
        target = arg.split("::", 1)[0]
        if arg.startswith("-") or not PYTEST_FILE_RE.search(target):
            continue
        if (root / target).parent.is_dir() and not (root / target).exists():
            missing.append(arg)
    return missing


def cmd_forget(root: Path, labels: list) -> int:
    checks = load_checks(root)
    labels = list(dict.fromkeys(labels))
    gone = [label for label in labels if label in checks]
    unknown = [label for label in labels if label not in checks]
    for label in gone:
        del checks[label]
    error = save_checks(root, checks) if gone else None
    if error:
        print(f"Không ghi được biên nhận ({error}); chưa xoá gì.")
        return 1
    for label in gone:
        print(f"Đã xoá biên nhận: {label}")
    for label in unknown:
        print(f"Không có biên nhận tên {label!r}.")
    if unknown and checks:
        print("Các tên hiện có: " + "; ".join(sorted(checks)))
    return 1 if unknown else 0


def cmd_prune(root: Path, dry_run: bool) -> int:
    """Chỉ xoá biên nhận trượt; biên nhận đạt luôn giữ."""
    checks = load_checks(root)
    stale = {label: missing_targets(root, rec.get("cmd")) for label, rec in checks.items() if rec.get("ok") is False}
    stale = {label: miss for label, miss in stale.items() if miss}
    if not stale:
        print("Không có biên nhận nào trỏ tới test đã xoá.")
        return 0
    for label in stale:
        checks.pop(label)
    error = None if dry_run else save_checks(root, checks)
    if error:
        print(f"Không ghi được biên nhận ({error}); chưa xoá gì.")
        return 1
    verb = "Sẽ xoá" if dry_run else "Đã xoá"
    for label, miss in stale.items():
        print(f"{verb} biên nhận: {label} (không còn: {', '.join(miss)})")
    return 0


def ago(ts: str) -> str:
    try:
        delta = time.time() - datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return "?"
    if delta < 3600:
        return f"{int(delta // 60)} phút trước"
    if delta < 86400:
        return f"{int(delta // 3600)} giờ trước"
    return f"{int(delta // 86400)} ngày trước"


def describe(label: str, rec: dict) -> str:
    mark = "✓ đạt" if rec.get("ok") else f"✗ trượt (mã {rec.get('exit')})"
    fresh = {True: "còn khớp code hiện tại", False: "code đã đổi sau lần chạy này, cần chạy lại",
             None: "không rõ code có đổi sau đó không"}[rec.get("fresh")]
    summary = f" · {rec['summary']}" if rec.get("summary") else ""
    return f"- {label}: {mark}, {ago(rec.get('ts'))}, {fresh}{summary}"


def cmd_show(root: Path, as_json: bool) -> int:
    checks = A.receipt_status(root)
    if as_json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        return 0
    if not checks:
        print(f"Chưa có biên nhận kiểm tra nào cho {root.name}. Ghi bằng: receipt.py run -- <lệnh kiểm tra>")
        return 0
    print(f"Kiểm tra đã ghi cho {root.name}:")
    for label, rec in sorted(checks.items(), key=lambda kv: kv[1].get("ts", ""), reverse=True):
        print(describe(label, rec))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Biên nhận kiểm tra gắn với nội dung code.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="chạy lệnh kiểm tra và ghi biên nhận")
    run.add_argument("--project", default=".")
    run.add_argument("--label", help="tên lần kiểm tra (mặc định: chính câu lệnh)")
    run.add_argument("--timeout", type=float, default=1800)
    run.add_argument("command", nargs=argparse.REMAINDER, help="-- <lệnh> [tham số...]")
    show = sub.add_parser("show", help="xem các biên nhận đã ghi")
    show.add_argument("--project", default=".")
    show.add_argument("--json", action="store_true")
    forget = sub.add_parser("forget", help="xoá biên nhận theo tên")
    forget.add_argument("--project", default=".")
    forget.add_argument("labels", nargs="+", metavar="TÊN")
    prune = sub.add_parser("prune", help="xoá biên nhận trượt của test đã bị xoá khỏi project")
    prune.add_argument("--project", default=".")
    prune.add_argument("--dry-run", action="store_true", help="chỉ in, không xoá")
    args = ap.parse_args(argv)
    root = A.project_root(Path(args.project).expanduser().resolve())
    if args.cmd == "show":
        return cmd_show(root, args.json)
    if args.cmd == "forget":
        return cmd_forget(root, args.labels)
    if args.cmd == "prune":
        return cmd_prune(root, args.dry_run)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        ap.error("thiếu lệnh kiểm tra, ví dụ: receipt.py run -- python3 -m pytest -q")
    return cmd_run(root, args.label or A.clip(" ".join(command), 80), command, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
