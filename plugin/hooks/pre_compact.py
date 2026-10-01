#!/usr/bin/env python3
"""Hook PreCompact: ghi sự kiện và nhắc người dùng nếu §0 đã lâu chưa cập nhật. Không chặn compact."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402


def main():
    data = A.read_hook_input()
    root = A.project_root(data.get("cwd"))
    A.log_event("pre-compact", {"session": data.get("session_id"), "trigger": data.get("trigger"),
                                "cwd": str(root)}, "sessions.jsonl")
    found = A.read_plan(root)
    if not found:
        return
    path = found[0]
    minutes = (time.time() - path.stat().st_mtime) / 60
    message = f"Sắp compact. Sau compact, hook sẽ nạp lại §0 từ {path.name} (cập nhật {minutes:.0f} phút trước)."
    if minutes > 30 and A.git_summary(root).get("dirty"):
        message += " §0 đã khá cũ so với các thay đổi đang có; nên cập nhật §0 trước."
    A.emit("PreCompact", "", message)


if __name__ == "__main__":
    A.run_hook(main)
