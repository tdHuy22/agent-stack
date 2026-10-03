#!/usr/bin/env python3
"""Kiểm tra định kỳ (mỗi tháng khoảng 30 phút) cho agent-stack. Chỉ đọc, trừ khi có --clean-cache.

Kiểm tra:
  1. Phiên bản Claude Code và OpenCode (cần Claude Code ≥ 2.1.277 để đọc AGENTS.md)
  2. Đồ bên thứ ba trong vetted.lock đã có commit mới chưa (cần kiểm duyệt lại trước khi cập nhật)
  3. Test và `claude plugin validate`
  4. Ngân sách mô tả skill (description quá dài làm Claude Code cắt bớt)
  5. Mức dùng 7 ngày so với BASELINE.md
  6. Dung lượng .vet-cache, các bản cache không còn trong vetted.lock
  7. Công cụ dòng lệnh khuyến nghị đã cài chưa (chỉ báo, không tự cài)

Ví dụ:
  python3 tools/maintain.py                 # đầy đủ (cần mạng cho mục 2)
  python3 tools/maintain.py --offline       # bỏ mục 2
  python3 tools/maintain.py --clean-cache   # xóa cache không còn dùng
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOME_STACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME_STACK / "plugin" / "skills" / "vet-skill" / "scripts"))
sys.path.insert(0, str(HOME_STACK / "tools"))
MIN_CLAUDE = (2, 1, 277)
# (lệnh, cách cài, để làm gì). Chỉ báo; cài toàn cục là việc của người dùng.
RECOMMENDED_CLI = (
    ("gitleaks", "brew install gitleaks", "quét secret trước khi commit"),
    ("osv-scanner", "brew install osv-scanner", "quét lỗ hổng đã biết trong thư viện"),
)
# pyright và clangd chỉ cần trong project bật LSP riêng; router đề xuất lúc mở phiên ở project đủ lớn.
LSP_NOTE = ("- `pyright`, `clangd`: chỉ cần khi bật LSP theo project (pyright-lsp, clangd-lsp); "
            "hồ sơ project lúc mở phiên sẽ đề xuất ở project cần, kèm lệnh cài.")


def sh(*args, cwd=None, timeout=300):
    try:
        out = subprocess.run(list(args), cwd=str(cwd or HOME_STACK), capture_output=True, text=True, timeout=timeout)
        return out.returncode, (out.stdout + out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def version_tuple(text: str):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def check_versions(lines: list) -> None:
    lines.append("## 1. Phiên bản")
    code, out = sh("claude", "--version")
    v = version_tuple(out)
    status = "?" if v is None else ("đủ mới" if v >= MIN_CLAUDE else "cũ, nên nâng cấp: `brew upgrade --cask claude-code`")
    lines.append(f"- Claude Code CLI: `{out.splitlines()[0] if out else '?'}` → {status}")
    code, out = sh("opencode", "--version")
    lines.append(f"- OpenCode: `{out.splitlines()[0] if out else '?'}`")


def upstream_drift(lock: dict, resolve) -> list:
    """Trả về các mục GitHub mà ref đã trỏ tới commit khác với commit đã kiểm."""
    drift = []
    for key, entry in sorted(lock.items()):
        source = entry.get("source", "")
        if not source.startswith("github:") or not entry.get("ref"):
            continue
        if re.fullmatch(r"[0-9a-f]{40}", entry["ref"]):
            continue  # đã ghim theo SHA: không trôi
        owner, repo = source[len("github:"):].split("/", 1)
        try:
            head = resolve(owner, repo, entry["ref"])
        except Exception as exc:  # noqa: BLE001
            drift.append((key, entry["sha"], f"lỗi: {exc.__class__.__name__}"))
            continue
        if head != entry["sha"]:
            drift.append((key, entry["sha"], head))
    return drift


def check_drift(lines: list, offline: bool) -> None:
    lines.append("## 2. Đồ bên thứ ba có bản mới")
    if offline:
        lines.append("- Bỏ qua (--offline).")
        return
    import vet
    lock = vet.load_lock(HOME_STACK)["entries"]
    drift = upstream_drift(lock, vet.resolve_sha)
    if not drift:
        lines.append("- Không có. Mọi mục vẫn ở đúng commit đã kiểm.")
    for key, old, new in drift:
        target = key if ":" not in key else key  # khóa trùng với cú pháp đích của vet.py
        lines.append(f"- `{key}`: đã kiểm `{old[:12]}`, hiện tại `{new[:12]}` → "
                     f"`python3 plugin/skills/vet-skill/scripts/vet.py scan \"{target}\"`, đọc diff rồi approve lại")


def check_quality(lines: list, skip_tests: bool) -> None:
    lines.append("## 3. Test và validate")
    if skip_tests:
        lines.append("- Bỏ qua (--skip-tests).")
    else:
        code, out = sh(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", timeout=900)
        summary = next((ln for ln in reversed(out.splitlines()) if ln.startswith(("OK", "FAILED"))), "?")
        ran = next((ln for ln in out.splitlines() if ln.startswith("Ran ")), "")
        lines.append(f"- Test: {ran} → **{summary}**")
    code, out = sh("claude", "plugin", "validate", str(HOME_STACK / "plugin"), timeout=120)
    lines.append(f"- Plugin: {'passed' if 'Validation passed' in out else 'LỖI: ' + out[-200:]}")


def check_skill_budget(lines: list) -> None:
    import vet
    lines.append("## 4. Mô tả skill")
    total = 0
    for path in sorted((HOME_STACK / "plugin" / "skills").glob("*/SKILL.md")):
        fm = vet.frontmatter(path.read_text(encoding="utf-8"))
        n = len(fm.get("description", "")) + len(fm.get("when_to_use", ""))
        total += n
        warn = " ⚠️ dài" if n > 1200 else ""
        lines.append(f"- `{path.parent.name}`: {n} ký tự{warn}")
    lines.append(f"- Tổng: {total} ký tự. Claude Code dành khoảng 1% context cho phần mô tả của mọi skill; "
                 "chạy `/skill-doctor` trong một phiên để xem skill nào tốn mà ít dùng.")


def check_usage(lines: list) -> None:
    import usage_snapshot as us
    from datetime import datetime, timedelta, timezone
    lines.append("## 5. Mức dùng 7 ngày (so với BASELINE.md)")
    until = datetime.now(timezone.utc)
    summary = us.summarize(us.collect(Path("~/.claude/projects").expanduser(), until - timedelta(days=7), until))
    baseline = (HOME_STACK / "BASELINE.md").read_text(encoding="utf-8")
    m = re.search(r"Tổng ước tính: \*\*([\d.]+) USD\*\*", baseline)
    base = float(m.group(1)) if m else None
    trend = f" (nền: {base:.0f} USD)" if base else ""
    lines.append(f"- Ước tính theo giá niêm yết: **{summary['total_cost']:.0f} USD**{trend}; "
                 f"subagent/workflow {summary['subagent_cost_share']:.0%}; đọc từ cache {summary['cache_read_share']:.0%}.")
    top = sorted(summary["by_model"].items(), key=lambda kv: -kv[1]["cost"])[:3]
    lines.append("- Theo model: " + ", ".join(f"`{k}` {v['cost'] / (summary['total_cost'] or 1):.0%}" for k, v in top))


def check_cache(lines: list, clean: bool) -> None:
    import vet
    lines.append("## 6. Cache kiểm duyệt")
    cache = HOME_STACK / ".vet-cache"
    if not cache.exists():
        lines.append("- Trống.")
        return
    used = {Path(e["report"]).stem for e in vet.load_lock(HOME_STACK)["entries"].values()}
    stale = [d for d in cache.iterdir() if d.is_dir() and d.name not in used]
    size = sum(f.stat().st_size for f in cache.rglob("*") if f.is_file()) / 1e6
    lines.append(f"- {len(list(cache.iterdir()))} bản, {size:.0f} MB; {len(stale)} bản không còn trong vetted.lock.")
    if clean and stale:
        for d in stale:
            shutil.rmtree(d, ignore_errors=True)
        lines.append(f"- Đã xóa {len(stale)} bản cũ.")
    elif stale:
        lines.append("- Xóa bằng `python3 tools/maintain.py --clean-cache`.")


def check_cli(lines: list, which=shutil.which) -> None:
    lines.append("## 7. Công cụ dòng lệnh khuyến nghị")
    for name, install, why in RECOMMENDED_CLI:
        lines.append(f"- `{name}` ({why}): " + ("có" if which(name) else f"chưa cài, bạn tự chạy `{install}` nếu cần"))
    lines.append(LSP_NOTE)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm tra định kỳ cho agent-stack.")
    ap.add_argument("--offline", action="store_true", help="không gọi GitHub")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--clean-cache", action="store_true")
    args = ap.parse_args(argv)
    lines = ["# Kiểm tra định kỳ agent-stack", ""]
    for step in (check_versions,
                 lambda L: check_drift(L, args.offline),
                 lambda L: check_quality(L, args.skip_tests),
                 check_skill_budget, check_usage,
                 lambda L: check_cache(L, args.clean_cache), check_cli):
        try:
            step(lines)
        except Exception as exc:  # noqa: BLE001 (một mục lỗi không được chặn các mục khác)
            lines.append(f"- Lỗi khi kiểm tra: {exc!r}")
        lines.append("")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
