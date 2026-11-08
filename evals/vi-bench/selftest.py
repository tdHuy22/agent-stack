#!/usr/bin/env python3
"""Tự kiểm bộ bài tiếng Việt (vi-bench) mà không cần Docker hay model.

Với mỗi bài (thư mục có task.toml):
  - cấu trúc đúng khuôn: Dockerfile và tests/test.sh giống hệt bản ở _lib/, tests/vncheck.py giống _lib/vncheck.py;
    task.toml có tên agent-stack/<thư mục>, nhóm khớp tiền tố tên, độ khó công bố; đề bằng tiếng Việt, dạng NFC;
    không có file .yml/.yaml hay symlink trong environment/ (kiểm an toàn của harbor_bench sẽ loại bài đó)
  - chép environment/app/ vào thư mục tạm, chạy tests/check.py: phải TRƯỢT (bài chưa làm)
  - chạy solution/solve.sh trên bản chép đó, chạy lại check.py: phải ĐẠT
  - mỗi thư mục solution/dat-khac/<n>/ (nếu có): chép đè lên một bản app/ mới, check.py phải ĐẠT. Đây là bài làm đúng mà
    viết khác lời giải mẫu, để bài chấm không ép một cách diễn đạt (nhất là nhóm viet-)
  - mỗi thư mục solution/truot/<n>/ (nếu có): chép đè như trên, check.py phải TRƯỢT (bài làm sai mà agent hay mắc)
APP_DIR trỏ check.py và solve.sh vào bản chép thay cho /app; VI_METRICS trỏ chỉ số phụ vào thư mục tạm.

  selftest.py [TÊN…] [--expect-per-group N] [-v]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "_lib"
GROUPS = ("code", "chu", "viet")
LEVELS = ("medium", "hard", "extreme")
sys.path.insert(0, str(LIB))
import vncheck  # noqa: E402


def task_dirs(names=None) -> list:
    dirs = sorted(p.parent for p in ROOT.glob("*/task.toml"))
    if names:
        dirs = [d for d in dirs if d.name in names]
    return dirs


def structure(d: Path) -> list:
    errs = []
    for rel in ("task.toml", "instruction.md", "environment/Dockerfile", "environment/app", "tests/test.sh",
                "tests/check.py", "tests/vncheck.py", "solution/solve.sh"):
        if not (d / rel).exists():
            errs.append(f"thiếu {rel}")
    if errs:
        return errs
    for rel, ref in (("environment/Dockerfile", LIB / "Dockerfile"), ("tests/test.sh", LIB / "test.sh"),
                     ("tests/vncheck.py", LIB / "vncheck.py")):
        if (d / rel).read_bytes() != ref.read_bytes():
            errs.append(f"{rel} khác bản chuẩn {ref.relative_to(ROOT)}")
    try:
        cfg = tomllib.loads((d / "task.toml").read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return errs + [f"task.toml lỗi: {exc}"]
    if (cfg.get("task") or {}).get("name") != f"agent-stack/{d.name}":
        errs.append(f"task.name phải là agent-stack/{d.name}")
    meta = cfg.get("metadata") or {}
    if meta.get("category") not in GROUPS or not d.name.startswith(f"{meta.get('category')}-"):
        errs.append(f"metadata.category phải thuộc {GROUPS} và khớp tiền tố tên thư mục")
    if meta.get("difficulty") not in LEVELS:
        errs.append(f"metadata.difficulty phải thuộc {LEVELS}")
    text = (d / "instruction.md").read_text(encoding="utf-8")
    if not vncheck.is_nfc(text):
        errs.append("instruction.md không ở dạng NFC")
    if vncheck.accent_ratio(text) < 0.3:
        errs.append("instruction.md có vẻ không viết bằng tiếng Việt")
    for p in (d / "environment").rglob("*"):
        if p.is_symlink():
            errs.append(f"symlink trong environment/: {p.relative_to(d)}")
        elif p.suffix.lower() in (".yml", ".yaml"):
            errs.append(f"file YAML trong environment/ (bị loại khi kiểm an toàn): {p.relative_to(d)}")
    return errs


def run(cmd, app: Path, timeout=180):
    env = {**os.environ, "APP_DIR": str(app), "PYTHONDONTWRITEBYTECODE": "1",
           "VI_METRICS": str(app.parent / "vi-metrics.json")}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=app)
    except subprocess.TimeoutExpired:
        return None, f"quá {timeout} giây"
    return r.returncode, (r.stdout + r.stderr).strip()


def behaviour(d: Path) -> tuple:
    """(lỗi, ghi chú): check.py trượt trên bản gốc, solve.sh chạy được, check.py đạt sau đó."""
    with tempfile.TemporaryDirectory(prefix="vi-bench-") as tmp:
        app = Path(tmp) / "app"
        shutil.copytree(d / "environment" / "app", app)
        code, out = run([sys.executable, str(d / "tests" / "check.py")], app)
        if code is None or code == 0:
            return [f"check.py không trượt trên bài chưa làm ({out[-300:] or 'không in gì'})"], ""
        before = out.splitlines()[-1] if out else ""
        code, out = run(["bash", str(d / "solution" / "solve.sh")], app)
        if code != 0:
            return [f"solve.sh lỗi (mã {code}): {out[-400:]}"], ""
        code, out = run([sys.executable, str(d / "tests" / "check.py")], app)
        if code != 0:
            return [f"check.py không đạt lời giải mẫu: {out[-600:]}"], ""
    errs = []
    for kind, want_pass in (("dat-khac", True), ("truot", False)):
        for v in sorted(p for p in (d / "solution" / kind).glob("*") if p.is_dir()):
            with tempfile.TemporaryDirectory(prefix="vi-bench-") as tmp:
                app = Path(tmp) / "app"
                shutil.copytree(d / "environment" / "app", app)
                shutil.copytree(v, app, dirs_exist_ok=True)
                code, out = run([sys.executable, str(d / "tests" / "check.py")], app)
                if (code == 0) != want_pass:
                    errs.append(f"solution/{kind}/{v.name}: phải {'ĐẠT' if want_pass else 'TRƯỢT'}, được: {out[-400:]}")
    return errs, before


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--expect-per-group", type=int)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    dirs = task_dirs(args.names)
    if not dirs:
        print("Không thấy bài nào", file=sys.stderr)
        return 1
    bad = 0
    for d in dirs:
        errs = structure(d)
        note = ""
        if not errs:
            errs, note = behaviour(d)
        if errs:
            bad += 1
            print(f"✗ {d.name}")
            for e in errs:
                print(f"    {e}")
        elif args.verbose:
            print(f"✓ {d.name}  (bản chưa làm: {note})")
    counts = {g: sum(1 for d in dirs if d.name.startswith(g + "-")) for g in GROUPS}
    print(f"{len(dirs) - bad}/{len(dirs)} bài đạt tự kiểm · " + ", ".join(f"{g} {n}" for g, n in counts.items()))
    if args.expect_per_group is not None and not args.names:
        off = {g: n for g, n in counts.items() if n != args.expect_per_group}
        if off:
            print(f"✗ cần đúng {args.expect_per_group} bài mỗi nhóm, đang có: {off}")
            return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
