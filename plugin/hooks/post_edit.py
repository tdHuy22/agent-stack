#!/usr/bin/env python3
"""Hook PostToolUse sau Edit, Write, MultiEdit (và Bash, cho phần archctl): giới hạn 2 giây, báo cho Claude qua
additionalContext, không có gì thì im lặng. Luôn thoát 0.

1. Project có `.arch/system.arch`: chạy `archctl check <file>` (Bash: `--changed`), đưa dòng vi phạm về agent ngay
   lượt sửa file (`plugin/lib/archgate.py`). Hook mà `archctl init` sinh thoát mã 1 nên agent không thấy (tái hiện
   14/11/2026). Bash chỉ chạy khi cây làm việc đổi và chỉ báo khối chưa báo trong lượt; thiếu archctl thì nhắc một
   lần mỗi phiên.
2. Linter nhanh (ruff, shellcheck; thiếu thì kiểm cú pháp) trên đúng file vừa sửa: lỗi ở dòng vừa sửa (hay lỗi cú
   pháp ở bất kỳ đâu). Phần kiểm nằm ở `quick_lint` của skills/done-gate/scripts/checks.py (cùng bộ đọc output với
   done-gate bước 4).
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
import archgate  # noqa: E402

MAX_BYTES = 2_000_000  # file lớn hơn thì bỏ qua (giống quick_lint)
MAX_HITS = 200  # chuỗi mới trùng quá nhiều chỗ thì thôi tìm, lấy dòng đổi theo git
ARCH_TIMEOUT = 1.0  # giây cho archctl, phần còn lại cho linter


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


def tree_state(top: Path):
    """(dấu, file đổi) của cây làm việc repo `top`: dấu gồm `git status` và cỡ, mtime từng file đổi, nên lệnh Bash
    không đổi file nào (chạy test, `ls`) giữ nguyên dấu và hook không gọi archctl; ghi tiếp vào file đã dirty thì dấu
    đổi. Lỗi hay quá hạn thì (None, [])."""
    import hashlib
    try:
        out = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=", "-C", str(top), "status",
                              "--porcelain", "-z", "--untracked-files=all"], capture_output=True, timeout=0.4)
    except (OSError, subprocess.TimeoutExpired):
        return None, []
    if out.returncode != 0:
        return None, []
    digest, files, skip_next = hashlib.sha256(out.stdout), [], False
    for entry in out.stdout.split(b"\0"):
        if skip_next:  # mục đổi tên, chép (R, C) có thêm trường tên cũ
            skip_next = False
            continue
        if len(entry) <= 3:
            continue
        skip_next = entry[:1] in (b"R", b"C")
        path = top / entry[3:].decode("utf-8", "replace")
        if len(files) < 2000:
            files.append(path)
            try:
                st = path.stat()
                digest.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
            except OSError:
                digest.update(b"-")
    return digest.hexdigest(), files


def nested_roots(top: Path) -> list:
    """Gốc có luật nằm dưới gốc repo, sâu tối đa hai cấp (`svc/.arch`, `services/x/.arch`): monorepo mà agent đứng ở
    gốc repo. Chỉ liệt kê thư mục, không quét sâu."""
    found = []
    for pattern in ("*/.arch/system.arch", "*/*/.arch/system.arch"):
        found += [p.parent.parent for p in top.glob(pattern)][:10]
    return found[:10]


def block_keys(lines: list) -> list:
    """Khóa so khối đã báo: dòng vi phạm bỏ bộ đếm của archctl (tăng mỗi lần check), bỏ dòng tổng và dòng gợi ý
    dừng (chỉ có khi bộ đếm đủ lớn)."""
    keys = []
    for line in lines:
        if line.startswith("…") or archgate.SUMMARY_RE.match(line) or archgate.COUNTER_RE.search(line):
            continue
        if line.strip().startswith("archctl block --on") or line.strip().startswith("archctl propose"):
            continue
        keys.append(line)
    return keys


def missing_note(sid: str, root: Path) -> str:
    if sid and A.once(f"archctl-missing:{sid}:{root}", 86400):
        return (f"[agent-stack] Project `{root.name}` có `.arch/system.arch` (luật kiến trúc) nhưng máy chưa có "
                "archctl, nên chưa kiểm luật sau khi sửa file. Báo người dùng: cài qua `./install.sh` của "
                "agent-stack (mục cargo:archctl). done-gate cũng sẽ báo chưa kiểm.")
    return ""


def remember(turn: dict, sid: str, lines_by_root: list, fp) -> list:
    """Ghi khối vi phạm đã báo (bỏ bộ đếm, kèm gốc có luật để hai service trùng đường dẫn không che nhau) và dấu cây
    vào lượt (`fp` None thì giữ dấu cũ); trả khối mới."""
    seen = turn.get("arch_seen") if isinstance(turn.get("arch_seen"), list) else []
    fresh = [f"{root}|{k}" for root, lines in lines_by_root for k in block_keys(lines)]
    fresh = [k for k in fresh if k not in seen]
    turn["arch_seen"] = (seen + fresh)[-200:]
    if fp is not None:
        turn["arch_fp"] = fp
    A.save_turn(sid, turn)
    return fresh


def arch_note(data: dict, path, what: str) -> str:
    """Lời báo của archctl sau lần sửa file `path` (rỗng nếu project không có `.arch/system.arch` hay không có gì để
    báo): kiểm đúng file đó và ghi lại khối đã báo trong lượt."""
    root = archgate.find_root(path.parent)
    if root is None or archgate.ARCH_DIR in [p.casefold() for p in path.parts]:
        return ""
    sid = data.get("session_id") or ""
    status, lines = archgate.check_paths(root, [path], ARCH_TIMEOUT)
    if status == "missing":
        return missing_note(sid, root)
    turn = A.load_turn(sid) if sid else None
    if turn is not None and status != "skip":
        top = archgate.git_top(root)
        remember(turn, sid, [(root, lines)], tree_state(top)[0] if top is not None else None)
    return archgate.hook_message(status, lines, what)


def arch_note_bash(data: dict) -> str:
    """Sau lệnh Bash: chỉ gọi archctl khi cây làm việc đổi từ lần kiểm trước trong lượt (không có lượt, hay không
    tính được dấu, thì chỉ khi lệnh có dấu hiệu ghi file), `check --changed` ở gốc có luật của thư mục đang làm hay của
    các file vừa đổi (monorepo, tối đa 3 gốc), và chỉ báo khối chưa báo trong lượt."""
    cwd = Path(data.get("cwd") or os.getcwd())
    here = archgate.find_root(cwd)
    top = archgate.git_top(here or cwd)
    if here is None and (top is None or not nested_roots(top)):
        return ""
    sid = data.get("session_id") or ""
    turn = A.load_turn(sid) if sid else None
    fp, files = tree_state(top) if top is not None and turn is not None else (None, [])
    command = str((data.get("tool_input") or {}).get("command") or "")
    if (turn is None or fp is None) and not A.BASH_WRITE_RE.search(command):
        return ""
    if turn is not None and fp is not None and turn.get("arch_fp") == fp:
        return ""
    roots = [here] if here is not None else []
    for f in files[:200]:
        r = archgate.find_root(f.parent)
        if r is not None and r not in roots:
            roots.append(r)
    lines_all, by_root, status_all, complete = [], [], "ok", len(roots) <= 3
    for root in roots[:3]:
        status, lines = archgate.check_paths(root, [], ARCH_TIMEOUT / max(1, min(3, len(roots))))
        if status == "missing":
            return missing_note(sid, root)
        if status == "skip":
            complete = False  # quá hạn: không ghi dấu, lần sau kiểm lại
        if status in ("violations", "invalid"):
            status_all = status if status_all != "invalid" else status_all
            lines_all += lines
            by_root.append((root, lines))
    if turn is not None:
        fresh = remember(turn, sid, by_root, fp if complete else None)
        if status_all == "violations" and not fresh:
            return ""
    return archgate.hook_message(status_all, lines_all, "lệnh shell vừa chạy")


def main():
    data = A.read_hook_input()
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    if tool == "Bash":
        if isinstance(ti, dict) and isinstance(ti.get("command"), str):
            note = arch_note_bash(data)
            if note:
                A.emit("PostToolUse", note)
        return
    if tool not in ("Edit", "Write", "MultiEdit"):
        return
    raw = ti.get("file_path")
    if not raw:
        return
    path = Path(raw)
    if not path.is_absolute():
        path = Path(data.get("cwd") or os.getcwd()) / path
    notes = []
    try:
        note = arch_note(data, path, f"lần sửa `{path.name}`")
    except Exception as exc:  # noqa: BLE001 (lỗi phần archctl không được tắt linter)
        A.log_event("hook-error", {"hook": "post_edit.archctl", "error": repr(exc)[:300]})
        note = ""
    if note:
        notes.append(note)
    found = lint(tool, ti, path, data)
    if found:
        notes.append("[agent-stack] Linter sau khi sửa file, lỗi ở dòng vừa đổi (hay lỗi cú pháp):\n"
                     + "\n".join(f"- {x}" for x in found)
                     + "\nSửa ngay nếu đúng là lỗi; done-gate bước 4 (`checks.py`) sẽ kiểm lại.")
    if notes:
        A.emit("PostToolUse", "\n\n".join(notes))


def lint(tool: str, ti: dict, path: Path, data: dict) -> list:
    """Lỗi linter ở dòng vừa đổi; rỗng khi file không kiểm, quá lớn hay hết giờ."""
    import checks  # noqa: E402
    if checks.lang_of(path.name) is None and path.suffix:
        return []  # loại file không kiểm: khỏi tốn thời gian
    try:
        if path.stat().st_size > MAX_BYTES:
            return []
    except OSError:
        return []
    lines = edited_lines(tool, ti, path, data.get("tool_response"))
    left = BUDGET - (time.time() - START)
    if left < 0.2:
        return []
    found = checks.quick_lint(path, lines, left)
    if not found or time.time() - START > BUDGET + 0.15:
        return []
    return found


if __name__ == "__main__":
    A.run_hook(main)
