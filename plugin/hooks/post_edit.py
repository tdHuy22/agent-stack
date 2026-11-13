#!/usr/bin/env python3
"""Hook PostToolUse sau Edit, Write, MultiEdit: chạy linter nhanh (ruff, shellcheck; thiếu thì kiểm cú pháp) trên
đúng file vừa sửa, giới hạn 2 giây. Có lỗi ở dòng vừa sửa (hay lỗi cú pháp ở bất kỳ đâu) thì báo cho Claude qua
additionalContext; file sạch, loại file không kiểm, hết giờ hay có lỗi thì im lặng. Luôn thoát 0.

Phần kiểm nằm ở `quick_lint` của skills/done-gate/scripts/checks.py (cùng bộ đọc output với done-gate bước 4).
"""
import os
import subprocess
import sys
import time
from pathlib import Path

START = time.time()
BUDGET = 1.8  # giây cho cả hook, chừa phần khởi động Python trong giới hạn 2 giây
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
sys.path.insert(0, str(HERE.parent / "skills" / "done-gate" / "scripts"))
import agentstack as A  # noqa: E402


MAX_BYTES = 2_000_000  # file lớn hơn thì bỏ qua (giống quick_lint)
MAX_HITS = 200  # chuỗi mới trùng quá nhiều chỗ thì thôi tìm, lấy dòng đổi theo git


def patch_lines(response) -> set:
    """Dòng vừa thêm theo `tool_response.structuredPatch` của Edit/MultiEdit (số dòng chính xác). Hunk chỉ xóa thì lấy
    dòng ngay chỗ xóa. Rỗng nếu không có patch."""
    lines = set()
    hunks = (response or {}).get("structuredPatch") if isinstance(response, dict) else None
    for hunk in hunks or []:
        if not isinstance(hunk, dict) or not isinstance(hunk.get("newStart"), int):
            continue
        n, removed_at = hunk["newStart"], None
        for raw in hunk.get("lines") or []:
            if not isinstance(raw, str):
                continue
            if raw.startswith("+"):
                lines.add(n)
                n += 1
            elif raw.startswith("-"):
                removed_at = n
            else:
                n += 1
        if removed_at is not None:
            lines.add(max(removed_at, 1))
    return lines


def edited_lines(tool: str, ti: dict, path: Path, response=None):
    """Tập dòng (đánh số từ 1) vừa ghi; None nếu cả file là mới (Write). Ưu tiên patch có sẵn trong payload; không có
    thì tìm chuỗi mới trong file (có giới hạn cỡ file và số chỗ trùng), cuối cùng lấy dòng đổi theo git."""
    found = patch_lines(response)
    if found:
        return found
    if tool == "Write":  # ghi đè file git đang theo dõi: chỉ dòng khác HEAD; file mới thì cả file
        try:
            tracked = subprocess.run(["git", "--no-optional-locks", "ls-files", "--error-unmatch", "--", path.name],
                                     cwd=path.parent, capture_output=True, timeout=0.5).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            tracked = False
        return git_lines(path) if tracked else None
    news = [ti.get("new_string")] if tool == "Edit" else [e.get("new_string") for e in ti.get("edits") or []
                                                         if isinstance(e, dict)]
    try:
        if path.stat().st_size > MAX_BYTES:
            return set()
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    lines, hits = set(), 0
    for new in news:
        if not new or not isinstance(new, str):
            continue
        pos, line_no, start = 0, 1, text.find(new)
        while start != -1:
            hits += 1
            if hits > MAX_HITS or time.time() - START > BUDGET / 2:
                return git_lines(path)
            line_no += text.count("\n", pos, start)  # đếm nối tiếp từ chỗ trùng trước, không đếm lại từ đầu
            pos = start
            lines.update(range(line_no, line_no + new.count("\n") + 1))
            start = text.find(new, start + len(new))
    return lines or git_lines(path)


def git_lines(path: Path) -> set:
    """Dòng đổi của file so với HEAD (đoạn vừa xóa, hay khi không tìm thấy chuỗi mới)."""
    try:
        out = subprocess.run(["git", "--no-optional-locks", "diff", "-U0", "--no-color", "--no-ext-diff",
                              "--src-prefix=a/", "--dst-prefix=b/", "HEAD", "--",
                              path.name], cwd=path.parent, capture_output=True, text=True, timeout=0.5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    import checks  # noqa: E402
    found = checks.parse_diff(out)
    return set().union(*found.values()) if found else set()


def main():
    data = A.read_hook_input()
    tool = data.get("tool_name") or ""
    if tool not in ("Edit", "Write", "MultiEdit"):
        return
    ti = data.get("tool_input") or {}
    raw = ti.get("file_path")
    if not raw:
        return
    path = Path(raw)
    if not path.is_absolute():
        path = Path(data.get("cwd") or os.getcwd()) / path
    import checks  # noqa: E402
    if checks.lang_of(path.name) is None and path.suffix:
        return  # loại file không kiểm: khỏi tốn thời gian
    try:
        if path.stat().st_size > MAX_BYTES:
            return
    except OSError:
        return
    lines = edited_lines(tool, ti, path, data.get("tool_response"))
    left = BUDGET - (time.time() - START)
    if left < 0.2:
        return
    found = checks.quick_lint(path, lines, left)
    if not found or time.time() - START > BUDGET + 0.15:
        return
    A.emit("PostToolUse", "[agent-stack] Linter sau khi sửa file, lỗi ở dòng vừa đổi (hay lỗi cú pháp):\n"
           + "\n".join(f"- {x}" for x in found) + "\nSửa ngay nếu đúng là lỗi; done-gate bước 4 (`checks.py`) sẽ kiểm lại.")


if __name__ == "__main__":
    A.run_hook(main)
