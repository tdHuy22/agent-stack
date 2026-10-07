#!/usr/bin/env python3
"""Dọn thư mục: gom file theo loại, xóa file tạm, báo file trùng."""
import argparse
import sys
from pathlib import Path

TEMP_SUFFIXES = (".tmp", ".crdownload", ".part")


def remove_temp_files(root: Path) -> int:
    count = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in TEMP_SUFFIXES:
            path.unlink()
            count += 1
    return count


def find_duplicates(root: Path) -> list:
    """Các nhóm file có nội dung giống hệt nhau."""
    raise NotImplementedError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dọn thư mục.")
    ap.add_argument("root", type=Path)
    args = ap.parse_args(argv)
    print(f"Đã xóa {remove_temp_files(args.root)} file tạm.")
    for group in find_duplicates(args.root):
        print("Trùng:", ", ".join(str(p) for p in group))
    return 0


if __name__ == "__main__":
    sys.exit(main())
