#!/usr/bin/env python3
"""Statusline cho Claude Code: model · effort · context · hạn mức 5 giờ · hạn mức tuần.

Đồng thời ghi state/limits.json để hook UserPromptSubmit cảnh báo khi sắp hết hạn mức.
Kích hoạt trong settings: {"statusLine": {"type": "command", "command": "python3 <đường dẫn file này>"}}
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin" / "lib"))
import agentstack as A  # noqa: E402

GREEN, YELLOW, RED, DIM, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"


def colored(label: str, pct, warn: float, crit: float) -> str:
    if pct is None:
        return f"{DIM}{label} –{RESET}"
    pct = float(pct)
    color = RED if pct >= crit else (YELLOW if pct >= warn else GREEN)
    return f"{color}{label} {pct:.0f}%{RESET}"


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        data = {}
    model = data.get("model") or {}
    name = model.get("display_name") or model.get("id") or "?"
    effort = (data.get("effort") or {}).get("level")
    ctx = (data.get("context_window") or {}).get("used_percentage")
    limits = data.get("rate_limits") or {}
    parts = [name] + ([effort] if effort else [])
    parts.append(colored("ctx", ctx, 60, 80))
    parts.append(colored("5h", (limits.get("five_hour") or {}).get("used_percentage"), 70, 90))
    parts.append(colored("7d", (limits.get("seven_day") or {}).get("used_percentage"), 70, 85))
    A.record_limits(data)
    if os.environ.get("NO_COLOR"):
        parts = [p.replace(GREEN, "").replace(YELLOW, "").replace(RED, "").replace(DIM, "").replace(RESET, "")
                 for p in parts]
    sys.stdout.write(" · ".join(parts))


if __name__ == "__main__":
    main()
