#!/usr/bin/env python3
"""Đọc và tạo file trạng thái công việc của một project (dùng cho skill session-keeper).

Lệnh:
  state.py show    [--project DIR] [--json]   in mục §0, tiến độ checkbox và trạng thái git
  state.py init    [--project DIR]            tạo .agent/PLAN.md từ mẫu (project chưa có file kế hoạch)
  state.py handoff [--project DIR]            tạo .agent/HANDOFF.md, điền sẵn §0 và trạng thái git

Script không bao giờ sửa file kế hoạch đang có. `handoff` sao lưu HANDOFF.md cũ trước khi ghi mới.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))
import agentstack as A  # noqa: E402

TEMPLATES = HERE.parents[1] / "templates"


def today() -> str:
    return time.strftime("%d/%m/%Y")


def cmd_show(root: Path, as_json: bool) -> int:
    found = A.read_plan(root)
    git = A.git_summary(root)
    if not found:
        payload = {"project": str(root), "plan": None, "git": git}
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Project {root.name} chưa có file kế hoạch (PLAN.md có mục §0 hoặc .agent/HANDOFF.md).")
            print("Tạo bằng: state.py init")
        return 1
    path, text, sec = found
    progress = A.checkbox_progress(text)
    payload = {"project": str(root), "plan": str(path), "section0": sec, "progress": progress, "git": git,
               "baseline": sec["fields"].get("checks") or A.baseline_anywhere(text)}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(A.brief(root)["context"])
    if progress["total"]:
        print(f"Checkbox: {progress['done']}/{progress['total']} đã xong.")
    return 0


def cmd_init(root: Path) -> int:
    existing = A.find_plans(root)
    if existing:
        print(f"Đã có file kế hoạch: {existing[0]}. Không tạo mới.")
        return 1
    target = root / ".agent" / "PLAN.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = (TEMPLATES / "PLAN-0.md").read_text(encoding="utf-8")
    target.write_text(text.replace("{project}", root.name).replace("{date}", today()), encoding="utf-8")
    print(f"Đã tạo {target}. Hãy điền mục §0.")
    return 0


def bullet_list(items, empty="(chưa ghi)") -> str:
    return "\n".join(f"  {i}. {x}" for i, x in enumerate(items, 1)) if items else f"  1. {empty}"


def cmd_handoff(root: Path) -> int:
    found = A.read_plan(root)
    sec = found[2] if found else {"fields": {}, "next": [], "after_interrupt": []}
    text = found[1] if found else ""
    f = sec["fields"]
    git = A.git_summary(root)
    if git.get("is_repo"):
        last = A.git_out(root, "log", "-5", "--format=- %h %s (%cr)") or ""
        git_text = (f"- Nhánh: `{git['branch']}`; {len(git['dirty'])} file chưa commit"
                    + (f"; {git['ahead']} commit chưa push" if git["ahead"] else "") + "\n"
                    + "".join(f"  - `{p}`\n" for p in git["dirty"][:30])
                    + "- Commit gần nhất:\n" + "".join(f"  {ln}\n" for ln in last.splitlines()))
    else:
        git_text = "- Project không phải git repo."
    template = (TEMPLATES / "HANDOFF.md").read_text(encoding="utf-8")
    body = (template.replace("{project}", root.name).replace("{date}", today())
            .replace("{done}", f.get("done") or "(chưa ghi)")
            .replace("{in_progress}", f.get("in_progress") or "(chưa ghi)")
            .replace("{next}", bullet_list(A.next_open(sec)))
            .replace("{decisions}", f.get("decisions") or "không có")
            .replace("{checks}", f.get("checks") or A.baseline_anywhere(text) or "(chưa ghi)")
            .replace("{after}", "; ".join(sec["after_interrupt"]) or "chạy `git status`, chạy mốc kiểm tra")
            .replace("{git}", git_text.rstrip()))
    target = root / ".agent" / "HANDOFF.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.replace(target.with_name("HANDOFF.prev.md"))
    target.write_text(body, encoding="utf-8")
    print(f"Đã tạo {target}. Điền các chỗ <!-- điền --> rồi kiểm tra lại các mục đã điền sẵn.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trạng thái công việc của project.")
    ap.add_argument("cmd", choices=("show", "init", "handoff"))
    ap.add_argument("--project", default=".", help="thư mục project (mặc định: thư mục hiện tại)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = A.project_root(Path(args.project).expanduser().resolve())
    if args.cmd == "show":
        return cmd_show(root, args.json)
    if args.cmd == "init":
        return cmd_init(root)
    return cmd_handoff(root)


if __name__ == "__main__":
    sys.exit(main())
