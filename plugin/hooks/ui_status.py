#!/usr/bin/env python3
"""Status line cho mod giao diện (plugin/hooks/ui.tsx).

Nhận số liệu dạng statusline của Claude Code qua stdin (mod dựng từ `$.session.usage()`), ghi state/limits.json
để hook UserPromptSubmit cảnh báo hạn mức cả trên app desktop (nơi statusline không chạy), rồi in một dòng không
màu: `ctx 23% · 5h 41% · 7d 12%`. Luôn thoát mã 0.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402


def pct_text(label: str, pct) -> str:
    try:
        return f"{label} {float(pct):.0f}%"
    except (TypeError, ValueError):
        return f"{label} –"


def line(data: dict) -> str:
    limits = data.get("rate_limits") or {}
    return " · ".join([
        pct_text("ctx", (data.get("context_window") or {}).get("used_percentage")),
        pct_text("5h", (limits.get("five_hour") or {}).get("used_percentage")),
        pct_text("7d", (limits.get("seven_day") or {}).get("used_percentage")),
    ])


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict):
            data = {}
        A.record_limits(data)
        sys.stdout.write(line(data))
    except Exception as exc:  # noqa: BLE001 (status chỉ là phần thêm, không bao giờ làm lỗi mod)
        A.log_event("hook-error", {"hook": "ui_status", "error": repr(exc)[:300]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
