#!/usr/bin/env python3
"""Đóng gói một skill trong claude-ai-skills/ thành file .skill (zip) để tải lên claude.ai.

  python3 claude-ai-skills/package.py paper-anatomy        # → .tmp/dist/paper-anatomy.skill

Zip chứa thư mục <tên-skill>/ ở gốc, bỏ __pycache__, *.pyc, .DS_Store. Kiểm trước khi đóng gói: có SKILL.md,
`name` trùng tên thư mục, description không quá 1.024 ký tự.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE.parent / ".tmp" / "dist"
SKIP_DIRS = {"__pycache__"}
SKIP_FILES = {".DS_Store"}


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    data, key = {}, None
    for line in m.group(1).splitlines():
        top = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if top:
            key, value = top.group(1), top.group(2).strip()
            data[key] = "" if value in (">-", ">", "|", "|-") else value
        elif key and line.startswith((" ", "\t")):
            data[key] = (data[key] + " " + line.strip()).strip()
    return data


def check(skill_dir: Path) -> list:
    problems = []
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return [f"thiếu {md}"]
    fm = frontmatter(md.read_text(encoding="utf-8"))
    if fm.get("name") != skill_dir.name:
        problems.append(f"name trong SKILL.md ({fm.get('name')!r}) khác tên thư mục ({skill_dir.name!r})")
    if not 40 < len(fm.get("description", "")) <= 1024:
        problems.append(f"description dài {len(fm.get('description', ''))} ký tự (cần 41–1.024)")
    return problems


def package(name: str) -> Path:
    skill_dir = HERE / name
    problems = check(skill_dir)
    if problems:
        raise SystemExit("Không đóng gói được:\n" + "\n".join(f"- {p}" for p in problems))
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / f"{name}.skill"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            rel = path.relative_to(skill_dir)
            if not path.is_file() or path.name in SKIP_FILES or path.suffix == ".pyc" or SKIP_DIRS & set(rel.parts):
                continue
            zf.write(path, f"{name}/{rel.as_posix()}")
    return out


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print(__doc__.strip())
        return 2
    out = package(args[0])
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    print(f"Đã tạo {out} ({out.stat().st_size} byte, {len(names)} file):")
    print("\n".join(f"  {n}" for n in names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
