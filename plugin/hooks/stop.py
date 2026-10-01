#!/usr/bin/env python3
"""Hook Stop: nhắc cập nhật §0 khi đã có nhiều file đổi sau lần cập nhật §0 gần nhất.

Chỉ hiện thông báo cho người dùng (systemMessage). Không chặn, không thêm context,
vì additionalContext ở Stop sẽ khiến Claude chạy thêm một lượt và tốn token.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402

MIN_CHANGED = 3
REMIND_EVERY_SECONDS = 30 * 60


def changed_paths(root: Path, porcelain_paths):
    for item in porcelain_paths:
        item = item.split(" -> ")[-1].strip().strip('"')
        path = root / item
        if path.is_file():
            yield path


def main():
    data = A.read_hook_input()
    if data.get("stop_hook_active"):
        return
    root = A.project_root(data.get("cwd"))
    found = A.read_plan(root)
    if not found:
        return
    plan = found[0]
    git = A.git_summary(root)
    if not git.get("is_repo") or not git.get("dirty"):
        return
    plan_mtime = plan.stat().st_mtime
    newer = [p for p in changed_paths(root, git["dirty"]) if p != plan and p.stat().st_mtime > plan_mtime + 60]
    if len(newer) < MIN_CHANGED:
        return
    if not A.once(f"stop-remind-{data.get('session_id', '')}", REMIND_EVERY_SECONDS):
        return
    A.emit("Stop", "", f"📝 Có {len(newer)} file đổi sau lần cập nhật §0 gần nhất ({plan.name}). "
                       "Khi xong việc, nhờ Claude cập nhật §0 (skill session-keeper).")


if __name__ == "__main__":
    A.run_hook(main)
