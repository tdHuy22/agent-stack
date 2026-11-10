#!/usr/bin/env python3
"""Theo dõi một lệnh theo chu kỳ và chỉ báo khi kết quả đổi.

Dùng với công cụ theo dõi nền của Claude Code (Monitor, hay Bash chạy nền) để theo dõi job, CI, máy đo, thay cho vòng
hẹn giờ đánh thức phiên: mỗi lần đánh thức, phiên dài đọc lại cả hội thoại (hàng trăm nghìn token) chỉ để thấy "chưa
có gì mới". Script này chạy ngoài phiên, im lặng khi kết quả không đổi, và chỉ in khi đổi (lần đầu luôn in).

Ví dụ:
  python3 watch_change.py --every 300 -- gh run list --limit 1
  python3 watch_change.py --every 600 --until 'completed|failed' --max-hours 6 -- kaggle kernels status user/job
  python3 watch_change.py --every 60 -- sh -c 'tail -n 3 train.log'

Mỗi lần in: một dòng `HH:MM [mã thoát N]` rồi vài dòng kết quả đã cắt gọn (stdout và stderr gộp; khóa sk-ant-... và
chuỗi giống khóa bị che). "Đổi" tính trên kết quả đã chuẩn hóa khoảng trắng cùng mã thoát. Lệnh chạy không qua shell
(muốn pipe thì tự truyền `sh -c '...'`).

Thoát: `--until REGEX` khớp kết quả thì in rồi thoát 0; `--max-hours` hết giờ thì in một dòng rồi thoát 0; Ctrl-C thoát
êm (0). Mỗi lần chạy lệnh bị giới hạn `--run-timeout` giây (mặc định 120); quá hạn tính là kết quả "hết giờ chạy".
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_-]+")
MAX_LINES = 6
MAX_LINE_CHARS = 200
MAX_TOTAL_CHARS = 800

try:  # che thêm token, khóa kiểu khác bằng bộ che chung nếu import được
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from agentstack import redact_secrets as _lib_redact  # noqa: E402
except Exception:  # noqa: BLE001
    _lib_redact = None


def redact(text: str) -> str:
    text = KEY_RE.sub("[KHÓA]", text)
    if _lib_redact:
        try:
            text = _lib_redact(text)
        except Exception:  # noqa: BLE001
            pass
    return text


def run_once(cmd, timeout):
    """(mã thoát, kết quả gộp stdout+stderr). Không chạy được hay quá hạn thì mã 127 hay 124 kèm lời nói rõ."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"hết giờ chạy lệnh sau {timeout:g} giây"
    except OSError as exc:
        return 127, f"không chạy được lệnh: {exc}"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def normalize(text: str) -> str:
    return " ".join(text.split())


def trim(text: str) -> str:
    """Vài dòng đầu (bỏ dòng trống), mỗi dòng và cả khối đều bị cắt."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out = [ln[:MAX_LINE_CHARS] + ("…" if len(ln) > MAX_LINE_CHARS else "") for ln in lines[:MAX_LINES]]
    if len(lines) > MAX_LINES:
        out.append(f"… (+{len(lines) - MAX_LINES} dòng)")
    body = "\n".join(out)
    return body[:MAX_TOTAL_CHARS] + ("…" if len(body) > MAX_TOTAL_CHARS else "")


def emit(header: str, body: str = "") -> None:
    print(header, flush=True)
    if body:
        print(body, flush=True)


def stamp() -> str:
    return time.strftime("%H:%M")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chạy lệnh theo chu kỳ, chỉ in khi kết quả đổi.")
    ap.add_argument("--every", type=float, required=True, help="số giây giữa hai lần chạy (cho phép số thực)")
    ap.add_argument("--until", metavar="REGEX", help="kết quả khớp thì in rồi thoát 0")
    ap.add_argument("--max-hours", type=float, help="quá số giờ này thì in một dòng và thoát 0")
    ap.add_argument("--run-timeout", type=float, default=120, help="giới hạn mỗi lần chạy lệnh, giây (mặc định 120)")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- lệnh [đối số...]")
    args = ap.parse_args(argv)
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    if not cmd or args.every <= 0:
        ap.error("cần --every > 0 và lệnh sau dấu --")
    until = re.compile(args.until) if args.until else None
    deadline = time.monotonic() + args.max_hours * 3600 if args.max_hours else None
    last = None
    try:
        while True:
            code, output = run_once(cmd, args.run_timeout)
            seen = normalize(output)
            if (seen, code) != last:
                last = (seen, code)
                emit(f"{stamp()} [mã thoát {code}]", trim(redact(output)))
            if until and until.search(seen):
                return 0
            if deadline is not None and time.monotonic() >= deadline:
                emit(f"{stamp()} hết thời gian theo dõi ({args.max_hours:g} giờ), dừng.")
                return 0
            wait = args.every if deadline is None else max(0.0, min(args.every, deadline - time.monotonic()))
            time.sleep(wait)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
