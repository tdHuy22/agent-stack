#!/usr/bin/env python3
"""Hook SessionEnd: ghi lại phiên vừa kết thúc, để skill tien-do gợi ý `claude --resume`.

SessionEnd chỉ có khoảng 1,5 giây, nên hook này chỉ ghi một dòng vào file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402


def main():
    data = A.read_hook_input()
    A.log_event("session-end", {"session": data.get("session_id"), "cwd": data.get("cwd"),
                                "reason": data.get("reason")}, "sessions.jsonl")


if __name__ == "__main__":
    A.run_hook(main)
