#!/usr/bin/env python3
"""Status line cho mod giao diện (plugin/hooks/ui.tsx).

Nhận số liệu dạng statusline của Claude Code qua stdin (mod dựng từ `$.session.usage()`), ghi state/limits.json
để hook UserPromptSubmit cảnh báo hạn mức cả trên app desktop (nơi statusline không chạy), rồi in một dòng không
màu: `ctx 23% · 5h 41% · 7d 12%` (phần chưa có số liệu thì bỏ). Payload có `turn_end` (mod gửi sau lượt phiên chính) thì ghi thêm số liệu phiên vào
state/session-usage/ cho router (A.record_mod_usage). Với `--router`: in gợi ý router của tin vừa gửi (JSON) cho dải trên ô nhập. Với `--prompt` (mod gọi trong UserPromptSubmit, trước hook
Python) chỉ cập nhật model hiện tại của file đó, không in gì. Với `--tree-shown` (mod gọi sau khi /cay in cây dạng
chữ) ghi dấu đã hiện cây cho hook Stop. Luôn thoát mã 0.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402


def pct_text(label: str, pct):
    """`ctx 23%`; không có số liệu thì None (bỏ phần đó khỏi dòng)."""
    try:
        return f"{label} {float(pct):.0f}%"
    except (TypeError, ValueError):
        return None


def line(data: dict) -> str:
    """Chỉ các phần có số liệu; chưa có gì (phiên mới, chưa gọi API lần nào) thì chuỗi rỗng để mod xoá dòng."""
    limits = data.get("rate_limits") or {}
    parts = [
        pct_text("ctx", (data.get("context_window") or {}).get("used_percentage")),
        pct_text("5h", (limits.get("five_hour") or {}).get("used_percentage")),
        pct_text("7d", (limits.get("seven_day") or {}).get("used_percentage")),
    ]
    return " · ".join(p for p in parts if p)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict):
            data = {}
        if "--router" in argv:
            sys.stdout.write(json.dumps(A.read_router(data.get("session_id")) or {}, ensure_ascii=False))
            return 0
        if "--prompt" in argv:
            A.record_mod_usage(data, at_prompt=True)
            return 0
        if "--tree-shown" in argv:
            A.mark_tree_shown(data.get("session_id"))
            return 0
        A.record_limits(data)
        if data.get("turn_end") is True:
            A.record_mod_usage(data)
        sys.stdout.write(line(data))
    except Exception as exc:  # noqa: BLE001 (status chỉ là phần thêm, không bao giờ làm lỗi mod)
        A.log_event("hook-error", {"hook": "ui_status", "error": repr(exc)[:300]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
