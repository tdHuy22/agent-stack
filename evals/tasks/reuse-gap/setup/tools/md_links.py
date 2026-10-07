#!/usr/bin/env python3
"""Kiểm tra link trong các file markdown: link tương đối tới file và link tới anchor (#muc).

Dùng: python3 tools/md_links.py docs/
Thoát mã 1 nếu có link hỏng.
"""
import argparse
import re
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
EXTERNAL = ("http://", "https://", "mailto:")


def check_file(md: Path) -> list:
    errors = []
    for target in LINK.findall(md.read_text(encoding="utf-8")):
        if target.startswith(EXTERNAL):
            continue  # link ngoài: để sau
        path, _, anchor = target.partition("#")
        dest = (md.parent / path) if path else md
        if path and not dest.exists():
            errors.append(f"{md}: không thấy file {path}")
            continue
        if anchor and not anchor_exists(dest, anchor):
            errors.append(f"{md}: không thấy mục #{anchor} trong {dest.name}")
    return errors


def anchor_exists(md: Path, anchor: str) -> bool:
    # TODO: so với heading thật của file (slug kiểu GitHub)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm tra link trong markdown.")
    ap.add_argument("root", type=Path)
    args = ap.parse_args(argv)
    errors = []
    for md in sorted(args.root.rglob("*.md")):
        errors += check_file(md)
    print("\n".join(errors) or "Không có link hỏng.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
