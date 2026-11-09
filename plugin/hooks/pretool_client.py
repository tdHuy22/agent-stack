#!/usr/bin/env python3
"""Hook PreToolUse cho công cụ `mcp__ccd_turn__*` của app Desktop: kiểm nơi người dùng gõ (Mac hay điện thoại) một lần
mỗi lượt, lúc tin vừa gửi đã nằm trong transcript, và chỉ chèn lời nhắc khi nơi gõ đổi (xem plugin/lib/client_place.py).

Không cho phép hay chặn công cụ nào: chỉ thêm ngữ cảnh. Mọi lỗi đều nuốt, thoát 0.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402
import client_place  # noqa: E402


def main():
    note = client_place.check(A.read_hook_input())
    if note:
        A.emit("PreToolUse", note)


if __name__ == "__main__":
    A.run_hook(main)
