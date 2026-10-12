#!/usr/bin/env python3
"""Hook StopFailure: Claude Code gọi hook này thay cho Stop khi lỗi API (rate limit, quá tải, hết hạn mức, lỗi máy
chủ...) kết thúc lượt. Ghi lượt cuối ở trạng thái "dừng vì lỗi", kèm file đã đổi tới lúc đó và đoạn chữ gần nhất
Claude viết trong lượt, để phiên sau biết lượt dừng ở đâu. Claude Code bỏ qua đầu ra và mã thoát của hook này, nên
hook không in gì.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402

ERROR_RE = re.compile(r"[a-z_]{1,40}")
ERROR_LABELS = {"rate_limit": "rate limit hay hết hạn mức", "overloaded": "máy chủ quá tải",
                "server_error": "lỗi máy chủ", "max_output_tokens": "chạm trần token ra",
                "authentication_failed": "lỗi đăng nhập", "billing_error": "lỗi thanh toán"}


def main():
    data = A.read_hook_input()
    sid = data.get("session_id", "")
    if not sid or not data.get("cwd"):
        return
    root = A.project_root(data.get("cwd"))
    turn = A.load_turn(sid)
    if turn and turn.get("root") != str(root):
        turn = None
    since = turn["ts"] if turn else 0
    error = str(data.get("error") or "unknown")
    error = error if ERROR_RE.fullmatch(error) else "unknown"
    details = data.get("error_details")
    note = f"dừng vì lỗi API: {ERROR_LABELS.get(error, error)} (`{error}`)"
    if isinstance(details, str) and details.strip():
        note += f": {A.clip(A.redact_secrets(details), 160)}"  # che khóa trước rồi mới cắt
    partial = A.last_assistant_text(data.get("transcript_path"), since) if data.get("transcript_path") else ""
    request = A.request_text(sid)
    # Ghi ngay, rồi ghi lại khi đã biết file đổi (git status, git log): hook có bị ngắt vì quá giờ thì vẫn còn bản đầu.
    A.record_turn(root, sid, state="failed", request=request, answer=partial, note=note)
    changed = A.changed_since(root, since) if turn else []
    if changed:
        A.record_turn(root, sid, state="failed", request=request, answer=partial, changed=changed, note=note)
    A.log_event("stop-failure", {"session": sid, "cwd": str(root), "error": error, "changed": len(changed)})


if __name__ == "__main__":
    A.run_hook(main)
