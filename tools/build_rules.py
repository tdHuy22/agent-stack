#!/usr/bin/env python3
"""Ghép luật cho OpenCode: global/AGENTS.global.md = SHARED.global.md + OPENCODE.global.md.

  python3 tools/build_rules.py          # ghi lại file ghép nếu nguồn đã đổi
  python3 tools/build_rules.py --check  # chỉ kiểm; thoát 1 nếu file ghép cũ hơn nguồn

Claude Code nạp SHARED.global.md qua dòng @import đầu CLAUDE.global.md, nên không nạp phần riêng OpenCode.
OpenCode không hiểu @import, nên đọc một file ghép sẵn: ~/.config/opencode/AGENTS.md trỏ tới AGENTS.global.md.
Sửa luật thì sửa file nguồn, rồi chạy script này.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

GLOBAL = Path(__file__).resolve().parents[1] / "global"
SOURCES = ("SHARED.global.md", "OPENCODE.global.md")
TARGET = "AGENTS.global.md"
HEADER = "<!-- Ghép từ SHARED.global.md và OPENCODE.global.md bằng tools/build_rules.py; đừng sửa tay. -->\n\n"


def build(root: Path = GLOBAL) -> str:
    return HEADER + "\n".join((root / name).read_text(encoding="utf-8").strip() + "\n" for name in SOURCES)


def main(argv=None, root: Path = GLOBAL) -> int:
    ap = argparse.ArgumentParser(description="Ghép luật chung và phần riêng OpenCode thành AGENTS.global.md.")
    ap.add_argument("--check", action="store_true", help="chỉ kiểm, không ghi")
    args = ap.parse_args(argv)
    target = root / TARGET
    text = build(root)
    current = target.read_text(encoding="utf-8") if target.exists() else None
    if current == text:
        print(f"{TARGET} khớp nguồn.")
        return 0
    if args.check:
        print(f"{TARGET} cũ hơn nguồn. Chạy: python3 tools/build_rules.py")
        return 1
    target.write_text(text, encoding="utf-8")
    print(f"Đã ghi {TARGET}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
