#!/usr/bin/env python3
"""Theo dõi một lệnh theo chu kỳ và chỉ báo khi kết quả đổi.

Dùng với công cụ theo dõi nền (Monitor của Claude Code đánh thức phiên ở mỗi dòng in ra; Bash chạy nền chỉ báo khi
script thoát, nên khi đó bắt buộc có --until hay --max-hours) để theo dõi job, CI, máy đo, thay cho vòng
hẹn giờ đánh thức phiên: mỗi lần đánh thức, phiên dài đọc lại cả hội thoại (hàng trăm nghìn token) chỉ để thấy "chưa
có gì mới". Script này chạy ngoài phiên, im lặng khi kết quả không đổi, và chỉ in khi đổi (lần đầu luôn in).

Lệnh kiểm phải ra kết quả ổn định khi trạng thái không đổi: lệnh có đồng hồ chạy (như cột ELAPSED của `gh run list`)
đổi mỗi lần và đánh thức phiên mỗi chu kỳ. Chọn trường trạng thái, như ví dụ dưới.

Ví dụ:
  python3 watch_change.py --every 300 --until completed --max-hours 6 -- gh run view 123 --json status,conclusion -q '.status+" "+.conclusion'
  python3 watch_change.py --every 600 --until 'COMPLETE|ERROR' --max-hours 6 -- kaggle kernels status user/job
  python3 watch_change.py --every 60 -- sh -c 'tail -n 3 train.log'

Mỗi lần in: một dòng `HH:MM [mã thoát N]` rồi vài dòng kết quả đã cắt gọn (stdout và stderr gộp; khóa sk-ant-... và
chuỗi giống khóa bị che). "Đổi" tính trên kết quả đã chuẩn hóa khoảng trắng cùng mã thoát. Lệnh chạy không qua shell
(muốn pipe thì tự truyền `sh -c '...'`).

Thoát: `--until REGEX` khớp kết quả thì in rồi thoát 0; `--max-hours` hết giờ thì in một dòng rồi thoát 0; Ctrl-C thoát
êm (0). Mỗi lần chạy lệnh bị giới hạn `--run-timeout` giây (mặc định 120); quá hạn tính là kết quả "hết giờ chạy".
"""
import argparse
import os
import re
import signal
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
    """(mã thoát, kết quả gộp stdout+stderr). Không chạy được hay quá hạn thì mã 127 hay 124 kèm lời nói rõ. Lệnh chạy
    trong nhóm tiến trình riêng để khi quá hạn giết cả tiến trình cháu (`sh -c 'a | b'`), không để lại tiến trình mồ côi."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                                start_new_session=True)
    except OSError as exc:
        return 127, f"không chạy được lệnh: {exc}"
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(proc)
        proc.communicate()
        return 124, f"hết giờ chạy lệnh sau {timeout:g} giây"
    except BaseException:  # Ctrl-C hay SIGTERM giữa lúc lệnh chạy: nhóm riêng không nhận tín hiệu, phải tự dọn
        kill_group(proc)
        raise
    return proc.returncode, (out or "") + (err or "")


def kill_group(proc) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        proc.kill()


def normalize(text: str) -> str:
    return " ".join(text.split())


def trim(text: str) -> str:
    """Vài dòng đầu (bỏ dòng trống) nối thành MỘT dòng bằng " ⏎ " (Monitor coi mỗi dòng in ra là một sự kiện),
    mỗi đoạn và cả khối đều bị cắt."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out = [ln[:MAX_LINE_CHARS] + ("…" if len(ln) > MAX_LINE_CHARS else "") for ln in lines[:MAX_LINES]]
    if len(lines) > MAX_LINES:
        out.append(f"… (+{len(lines) - MAX_LINES} dòng)")
    body = " ⏎ ".join(out)
    return body[:MAX_TOTAL_CHARS] + ("…" if len(body) > MAX_TOTAL_CHARS else "")


def emit(header: str, body: str = "") -> None:
    """Một lần đổi in đúng một dòng, để công cụ theo dõi nền đánh thức phiên một lần."""
    print(f"{header} {body}" if body else header, flush=True)


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
    # SIGTERM (công cụ theo dõi nền dừng script) đi cùng đường Ctrl-C để lệnh đang chạy được dọn
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        until = re.compile(args.until) if args.until else None
    except re.error as exc:
        ap.error(f"--until không phải regex hợp lệ: {exc}")
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
