#!/usr/bin/env python3
"""Dọn rác của agent-stack không dùng model (việc G mục 2, 19/11/2026). MẶC ĐỊNH CHỈ LIỆT KÊ, không xóa gì.

Liệt kê, kèm dung lượng trên đĩa:
  worktree  worktree git trong <root>/.claude/worktrees/ đã gộp vào nhánh chính và không còn thay đổi chưa commit;
            gỡ bằng `git worktree remove` (không --force), nhánh giữ nguyên
  tmp       mục trong <root>/.tmp/ không đổi từ --days ngày
  eval      kết quả trong <root>/evals/results/ cũ hơn --days ngày, trừ --keep-results lần chạy mới nhất
  scratch   thư mục phiên trong --scratch-root (mặc định /private/tmp/claude-<uid>) không đổi từ --days ngày

--apply dựng lại đúng danh sách đó rồi xóa từng mục; không xóa gì ngoài danh sách. Chốt chặn (TM-151..153): không
theo symlink (symlink chỉ bị gỡ chính nó, đo dung lượng không đi qua nó), thư mục gốc của một loại là symlink thì bỏ
qua cả loại, mỗi mục phải nằm trong thư mục gốc của loại đó, không bao giờ đụng ~/.claude/projects (transcript).

Ví dụ:
  python3 tools/cleanup.py                    # liệt kê
  python3 tools/cleanup.py --only tmp,eval    # liệt kê hai loại
  python3 tools/cleanup.py --apply            # xóa đúng các mục liệt kê
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KINDS = ("worktree", "tmp", "eval", "scratch")
SHOW = 15  # số dòng in tối đa mỗi loại ở chế độ chữ


def tree_stats(path: Path) -> tuple:
    """(số byte trên đĩa, mtime mới nhất) của cả cây, không theo symlink."""
    try:
        st = os.lstat(path)
    except OSError:
        return 0, 0.0
    size, newest = _disk_bytes(st), st.st_mtime
    if stat.S_ISDIR(st.st_mode):
        for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
            for name in dirnames + filenames:
                try:
                    sub = os.lstat(os.path.join(dirpath, name))
                except OSError:
                    continue
                size += _disk_bytes(sub)
                newest = max(newest, sub.st_mtime)
    return size, newest


def _disk_bytes(st) -> int:
    blocks = getattr(st, "st_blocks", None)
    return blocks * 512 if blocks is not None else st.st_size


def forbidden(path: Path) -> bool:
    """Đường dẫn nằm trong ~/.claude/projects (transcript) thì không bao giờ được đụng."""
    projects = (Path.home() / ".claude" / "projects").resolve()
    try:
        full = path.parent.resolve() / path.name
    except OSError:
        return True
    return full == projects or projects in full.parents or full in projects.parents


def inside(path: Path, base: Path) -> bool:
    """`path` là con trực tiếp hay gián tiếp của `base` (thư mục cha resolve, chính nó không theo symlink)."""
    try:
        full = path.parent.resolve() / path.name
        return base.resolve() in full.parents
    except OSError:
        return False


def usable_base(base: Path) -> bool:
    return base.is_dir() and not base.is_symlink() and not forbidden(base)


def git(cwd: Path, *args: str):
    try:
        out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out if out.returncode == 0 else None


def main_branch(root: Path) -> str | None:
    for name in ("main", "master"):
        if git(root, "rev-parse", "--verify", "-q", f"refs/heads/{name}"):
            return name
    return None


def worktree_items(root: Path):
    base = root / ".claude" / "worktrees"
    items, kept = [], []
    if not usable_base(base):
        return items, kept
    listing = git(root, "worktree", "list", "--porcelain")
    target = main_branch(root)
    if not listing or not target:
        return items, kept
    for block in listing.stdout.strip().split("\n\n"):
        info = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            info[key] = value
        path = Path(info.get("worktree", ""))
        if not info.get("worktree") or not inside(path, base) or path.is_symlink():
            continue
        head, branch = info.get("HEAD", ""), info.get("branch", "").removeprefix("refs/heads/")
        why = None
        if "locked" in info:
            why = "worktree bị khóa"
        elif branch == target:
            why = "đang checkout nhánh chính"
        elif not head or git(root, "merge-base", "--is-ancestor", head, target) is None:
            why = f"chưa gộp vào {target}"
        else:
            status = git(path, "status", "--porcelain")
            if status is None:
                why = "không đọc được git status"
            elif status.stdout.strip():
                why = "còn thay đổi chưa commit"
        size, _ = tree_stats(path)
        entry = {"kind": "worktree", "path": str(path), "bytes": size, "branch": branch or head[:12]}
        if why:
            kept.append({**entry, "why": why})
        else:
            items.append({**entry, "why": f"đã gộp vào {target}, sạch"})
    return items, kept


def aged_entries(base: Path, kind: str, days: float, now: float, skip=frozenset()):
    items = []
    if not usable_base(base):
        return items
    for child in sorted(base.iterdir()):
        if child.name in skip or forbidden(child) or not inside(child, base):
            continue
        size, newest = tree_stats(child)
        old = (now - newest) / 86400
        if old >= days:
            items.append({"kind": kind, "path": str(child), "bytes": size, "age_days": round(old, 1),
                          "why": f"không đổi {old:.0f} ngày"})
    return items


def eval_items(root: Path, days: float, keep: int, now: float):
    base = root / "evals" / "results"
    if not usable_base(base):
        return []
    stems = sorted({p.name.split(".", 1)[0] for p in base.iterdir()}, reverse=True)
    newest = set(stems[:max(keep, 0)])
    return [item for item in aged_entries(base, "eval", days, now)
            if Path(item["path"]).name.split(".", 1)[0] not in newest]


def scratch_items(scratch_root: Path, days: float, now: float):
    items = []
    if not usable_base(scratch_root):
        return items
    for project in sorted(scratch_root.iterdir()):
        if project.is_symlink() or not project.is_dir() or forbidden(project):
            continue
        items += aged_entries(project, "scratch", days, now)
    return items


def collect(args) -> dict:
    now = time.time()
    root = Path(args.root).expanduser()
    kinds = set(args.only.split(",")) if args.only else set(KINDS)
    items, kept = [], []
    if "worktree" in kinds:
        found, held = worktree_items(root)
        items += found
        kept += held
    if "tmp" in kinds:
        items += aged_entries(root / ".tmp", "tmp", args.days, now)
    if "eval" in kinds:
        items += eval_items(root, args.days, args.keep_results, now)
    if "scratch" in kinds:
        items += scratch_items(Path(args.scratch_root).expanduser(), args.days, now)
    items = [item for item in items if not forbidden(Path(item["path"]))]
    return {"root": str(root), "items": items, "kept": kept, "total_bytes": sum(i["bytes"] for i in items)}


def remove(item: dict, root: Path):
    path = Path(item["path"])
    if forbidden(path):
        return "đường dẫn bị cấm"
    if item["kind"] == "worktree":
        out = subprocess.run(["git", "-C", str(root), "worktree", "remove", str(path)], capture_output=True,
                             text=True, timeout=60)
        return None if out.returncode == 0 else (out.stderr.strip() or "git worktree remove lỗi")
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISDIR(st.st_mode):
        shutil.rmtree(path)  # rmtree không đi vào symlink con, chỉ gỡ chính symlink
    else:
        os.unlink(path)  # file thường hay symlink: gỡ chính nó, không đụng đích
    return None


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--root", default=str(REPO), help="thư mục repo (mặc định: agent-stack)")
    ap.add_argument("--days", type=float, default=7, help="tuổi tối thiểu, ngày (mặc định 7)")
    ap.add_argument("--keep-results", type=int, default=5, help="số lần chạy eval mới nhất luôn giữ (mặc định 5)")
    ap.add_argument("--scratch-root", default=f"/private/tmp/claude-{os.getuid()}",
                    help="thư mục scratchpad của Claude Code")
    ap.add_argument("--only", help="loại cần xét, ngăn cách bằng dấu phẩy: " + ",".join(KINDS))
    ap.add_argument("--apply", action="store_true", help="xóa đúng các mục liệt kê")
    ap.add_argument("--json", action="store_true", help="in JSON")
    args = ap.parse_args(argv)
    if args.only and set(args.only.split(",")) - set(KINDS):
        ap.error("--only chỉ nhận: " + ",".join(KINDS))
    report = collect(args)
    report["applied"], report["removed"], report["errors"] = bool(args.apply), [], []
    if args.apply:
        for item in report["items"]:
            try:
                err = remove(item, Path(report["root"]))
            except OSError as exc:
                err = str(exc)
            if err:
                report["errors"].append({"path": item["path"], "error": err})
            else:
                report["removed"].append(item["path"])
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report["errors"] else 0
    print("agent-stack cleanup · " + ("XÓA" if args.apply else "CHỈ LIỆT KÊ (thêm --apply để xóa đúng các mục dưới)"))
    for kind in KINDS:
        group = [i for i in report["items"] if i["kind"] == kind]
        if group:
            print(f"[{kind}] {len(group)} mục, {human(sum(i['bytes'] for i in group))}")
            for item in group[:SHOW]:
                print(f"  {human(item['bytes']):>9}  {item['path']}  ({item['why']})")
            if len(group) > SHOW:
                print(f"  … và {len(group) - SHOW} mục nữa (--json để xem đủ)")
    for item in report["kept"]:
        print(f"  giữ  {item['path']}  ({item['why']})")
    print(f"Tổng: {len(report['items'])} mục, {human(report['total_bytes'])}"
          + (f"; đã xóa {len(report['removed'])}, lỗi {len(report['errors'])}" if args.apply else ""))
    for err in report["errors"]:
        print(f"  ! {err['path']}: {err['error']}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
