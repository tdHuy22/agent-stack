#!/usr/bin/env python3
"""Đọc và tạo file trạng thái công việc của một project (dùng cho skill session-keeper).

Lệnh:
  state.py show    [--project DIR] [--json]   in mục §0, tiến độ checkbox và trạng thái git
  state.py init    [--project DIR]            tạo .agent/PLAN.md từ mẫu (project chưa có file kế hoạch)
  state.py handoff [--project DIR]            tạo .agent/HANDOFF.md, điền sẵn §0 và trạng thái git
  state.py trim    [--project DIR] [--keep N] [--dry-run] [--newest-first | --newest-last]
                                              chuyển mục "Xong" cũ, bước đã xong của §0 và mốc đã xong hết sang
                                              .agent/NHAT-KY.md, để file kế hoạch ngắn (agent đọc nó mỗi phiên)

Chỉ `trim` sửa file kế hoạch, và không xóa gì: phần chuyển đi nằm nguyên văn trong nhật ký, đợt mới nhất ở trên.
`handoff` sao lưu HANDOFF.md cũ trước khi ghi mới.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))
import agentstack as A  # noqa: E402

TEMPLATES = HERE.parents[1] / "templates"
HISTORY_REL = A.HISTORY_REL


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


# ---------------------------------------------------------------- trim: dời lịch sử ra nhật ký

def merge_history(old: str, part: str, project: str, plan_rel: str) -> str:
    """Chèn đợt mới lên trên các đợt cũ (sau phần mở đầu)."""
    if not old.strip():
        return (f"# Nhật ký: {project}\n\nViệc đã xong, chuyển ra khỏi `{plan_rel}` bằng `state.py trim` để file kế "
                "hoạch ngắn (agent đọc §0 mỗi phiên). Đợt mới nhất ở trên. Chỉ đọc khi cần tra lại.\n\n" + part)
    m = re.search(r"(?m)^## ", old)
    if not m:
        return old.rstrip() + "\n\n" + part
    return old[:m.start()] + part + "\n" + old[m.start():]


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    if path.exists():
        os.chmod(tmp, path.stat().st_mode & 0o777)
    os.replace(tmp, path)


def cmd_trim(root: Path, keep: int, dry_run: bool, order) -> int:
    found = A.trim_target(root)
    if not found:
        print("Không có PLAN.md hay .agent/PLAN.md có mục §0: không có gì để chuyển.")
        return 1
    path, text = found
    plan_rel = path.relative_to(root).as_posix()
    try:
        res = A.trim_plan(text, keep, time.strftime("%d/%m/%Y %H:%M"), plan_rel, order)
    except A.TrimOrderUnknown:
        print("Mục Xong trong §0 không ghi đủ ngày nên không biết mục nào mới nhất. Chạy lại với --newest-first (mục "
              "mới nhất ở trên) hoặc --newest-last (mục mới nhất ở dưới). Chưa ghi gì.")
        return 2
    if not res["part"]:
        print(f"`{plan_rel}` đã gọn: không có mục Xong nào ngoài {keep} mục mới nhất, bước nào đã xong, mốc nào đã xong hết.")
        return 0
    print(f"Chuyển {res['n_done']} mục Xong, {res['n_steps']} bước đã xong và {res['n_phases']} mốc đã xong hết sang "
          f"`{HISTORY_REL}`; `{plan_rel}` từ {len(text):,} còn {len(res['text']):,} ký tự, §0 còn "
          f"{res['section0_chars']:,} ký tự.")
    if dry_run:
        print("Giữ trong §0:")
        print("\n".join(f"  {A.clip(x.strip(), 100)}" for x in res["kept"]) or "  (không có mục Xong)")
        print("Dời (dòng đầu):")
        shown = res["moved"][:12]
        print("\n".join(f"  {A.clip(x.strip(), 100)}" for x in shown)
              + (f"\n  … và {len(res['moved']) - len(shown)} mục khác" if len(res["moved"]) > len(shown) else ""))
        print("(chạy thử: chưa ghi gì)")
        return 0
    history = root / HISTORY_REL
    history.parent.mkdir(parents=True, exist_ok=True)
    old = history.read_text(encoding="utf-8") if history.exists() else ""
    write_atomic(history, merge_history(old, res["part"], root.name, plan_rel))  # ghi nhật ký trước: lỡ ngắt thì chỉ thừa
    write_atomic(path, res["text"])
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trạng thái công việc của project.")
    ap.add_argument("cmd", choices=("show", "init", "handoff", "trim"))
    ap.add_argument("--project", default=".", help="thư mục project (mặc định: thư mục hiện tại)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--keep", type=int, default=3, help="trim: số mục Xong mới nhất giữ lại trong §0 (mặc định 3)")
    ap.add_argument("--dry-run", action="store_true", help="trim: chỉ báo sẽ giữ gì, dời gì")
    order = ap.add_mutually_exclusive_group()
    order.add_argument("--newest-first", dest="order", action="store_const", const="first",
                       help="trim: mục Xong mới nhất ở trên (mặc định đoán theo ngày ghi trong mục)")
    order.add_argument("--newest-last", dest="order", action="store_const", const="last",
                       help="trim: mục Xong mới nhất ở dưới")
    args = ap.parse_args(argv)
    root = A.project_root(Path(args.project).expanduser().resolve())
    if args.cmd == "show":
        return cmd_show(root, args.json)
    if args.cmd == "init":
        return cmd_init(root)
    if args.cmd == "trim":
        return cmd_trim(root, max(0, args.keep), args.dry_run, args.order)
    return cmd_handoff(root)


if __name__ == "__main__":
    sys.exit(main())
