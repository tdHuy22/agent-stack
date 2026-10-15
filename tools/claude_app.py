#!/usr/bin/env python3
"""In đường dẫn binary Claude Code mà app desktop đang dùng (bản mới nhất app đã tải).

`claude` trong PATH (brew, kênh stable) có thể cũ hơn app. Mod giao diện của plugin
(`plugin/hooks/ui.tsx`) chạy trong engine của app, nên validate và test mod phải gọi
đúng binary này.

Ví dụ:
  "$(python3 tools/claude_app.py)" plugin test plugin
  python3 tools/claude_app.py --version      # chỉ in số phiên bản
Không tìm thấy app thì thoát mã 1 và không in gì ra stdout.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BASE = Path.home() / "Library" / "Application Support" / "Claude" / "claude-code"
BINARY = Path("claude.app") / "Contents" / "MacOS" / "claude"


def version_key(name: str):
    """Khóa sắp xếp số phiên bản kiểu 2.1.295; tên lạ thì None."""
    if not re.fullmatch(r"\d+(\.\d+)*", name):
        return None
    return tuple(int(x) for x in name.split("."))


def find(base: Path = BASE):
    """(phiên bản, đường dẫn binary) mới nhất còn file chạy được, hay None."""
    found = []
    if not base.is_dir():
        return None
    for vdir in base.iterdir():
        key = version_key(vdir.name)
        if key is None or not vdir.is_dir():
            continue
        for build in vdir.iterdir():
            exe = build / BINARY
            if exe.is_file():
                found.append((key, vdir.name, exe))
    if not found:
        return None
    _, name, exe = max(found)
    return name, exe


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", action="store_true", help="chỉ in số phiên bản")
    args = ap.parse_args(argv)
    hit = find()
    if hit is None:
        print("Không thấy Claude Code của app desktop trong " + str(BASE), file=sys.stderr)
        return 1
    print(hit[0] if args.version else hit[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
