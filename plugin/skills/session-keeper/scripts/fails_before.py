"""Bằng chứng test bắt được lỗi (FAIL_TO_PASS, khái niệm lấy từ SWE-bench): chạy cùng một lệnh test trên code
trước bản sửa (cây của commit gốc + file test hiện tại) và sau bản sửa (cây gốc + mọi thay đổi hiện tại), mỗi bên
một cây riêng trong thư mục tạm của hệ điều hành.

- Trước trượt, sau đạt: test bắt được lỗi (mã 0).
- Đạt cả hai: test không bắt được lỗi (mã 1).
- Sau cũng trượt: không kết luận được, thường vì thư mục tạm thiếu môi trường (mã 2).
- Trước trượt mà không phải ở assert (không chạy được lệnh, thiếu import hay fixture), hay môi trường nạp code từ
  thư mục làm việc thật (cài kiểu editable, PYTHONPATH) nên cả hai phía chạy code đã sửa: cũng mã 2, kèm lý do.

Không đụng thư mục làm việc và không chạy lệnh nào do repo đặt (TM-57): cây gốc đọc bằng `git ls-tree` và
`git cat-file --batch` (không checkout, không archive, không worktree), file hiện tại đọc thẳng từ đĩa và tự tính
mã băm kiểu git (không `git diff`, nên không clean filter). Không ghi qua symlink (TM-56); `--link` chỉ nhận đường
dẫn bị git bỏ qua (TM-58); thư mục tạm quyền 0700 và luôn bị xóa (TM-59).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

GIT = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.quotePath=false"]
SUBMODULE, SYMLINK, EXECUTABLE = "160000", "120000", "100755"
TAIL_LINES = 15
# Phía "trước" trượt vì những lỗi này mà không có lỗi assert nào thì chưa chứng minh test bắt được lỗi.
SETUP_CODES = {124: "hết giờ", 126: "lệnh không chạy được", 127: "không tìm thấy lệnh"}
SETUP_ERROR_RE = re.compile(r"ImportError|ModuleNotFoundError|No module named|cannot import name|SyntaxError|"
                            r"IndentationError|AttributeError: module '[^']+' has no attribute|"
                            r"NameError: name '[^']+' is not defined|fixture '[^']+' not found|Cannot find module|"
                            r"command not found|No such file or directory|Ran 0 tests|no tests ran|collected 0 items|"
                            r"undefined: |\[build failed\]|could not compile|unresolved import|error TS\d+|"
                            r"undefined reference to")
# Dấu hiệu trượt ở assert (unittest, pytest, Go, Rust, Jest); hẹp để tên như ExpectedResult hay thư mục assert/ trong
# dòng lỗi import không bị tính là assert.
ASSERT_FAIL_RE = re.compile(r"AssertionError|^FAIL:|^--- FAIL:|failures=|^E\s+assert\b|^\s*Expected:|"
                            r"expect\(received\)|panicked at", re.M)
PYTHON_RE = re.compile(r"^python[0-9.]*$")
HOME_VARS = ("PYTHONPATH", "NODE_PATH", "PERL5LIB", "RUBYLIB", "CLASSPATH")
PROBE = "import sys\nfor p in sys.path: print(p)"


class Problem(Exception):
    """Không chạy được; thông điệp viết cho người dùng."""


def git(top: Path, *args: str, data: bytes = None) -> bytes:
    out = subprocess.run(GIT + ["-C", str(top), *args], input=data, capture_output=True)
    if out.returncode != 0:
        raise Problem(f"git {args[0]} lỗi: {out.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return out.stdout


def base_entries(top: Path, base: str) -> dict:
    """{đường dẫn: (mode, mã băm)} của cây ở commit `base`."""
    entries = {}
    for record in git(top, "ls-tree", "-r", "-z", "--full-tree", base + "^{tree}").split(b"\0"):
        meta, _, path = record.partition(b"\t")
        parts = meta.split()
        if path and len(parts) == 3:
            entries[path.decode("utf-8", "surrogateescape")] = (parts[0].decode(), parts[2].decode())
    return entries


def read_blobs(top: Path, shas) -> dict:
    """{mã băm: nội dung} qua một lần `git cat-file --batch` (đọc thẳng object, không qua filter)."""
    shas = sorted(set(shas))
    if not shas:
        return {}
    out, blobs, i = git(top, "cat-file", "--batch", data=("\n".join(shas) + "\n").encode()), {}, 0
    while i < len(out):
        end = out.index(b"\n", i)
        header = out[i:end].split()
        i = end + 1
        if len(header) != 3:  # "<sha> missing"
            continue
        size = int(header[2])
        blobs[header[0].decode()] = out[i:i + size]
        i += size + 1
    return blobs


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def current_files(top: Path) -> dict:
    """{đường dẫn: (mode, nội dung)} của file đang theo dõi và file mới chưa bị ignore, đọc thẳng từ đĩa.
    Symlink giữ nguyên dạng symlink (nội dung là đích), không theo nó."""
    listed = git(top, "ls-files", "-z") + b"\0" + git(top, "ls-files", "--others", "--exclude-standard", "-z")
    files = {}
    for raw in listed.split(b"\0"):
        if not raw:
            continue
        path = raw.decode("utf-8", "surrogateescape")
        full = top / path
        try:
            st = os.lstat(full)
            if os.path.islink(full):
                files[path] = (SYMLINK, os.fsencode(os.readlink(full)))
            elif os.path.isfile(full):
                mode = EXECUTABLE if st.st_mode & 0o111 else "100644"
                files[path] = (mode, full.read_bytes())
        except OSError:
            continue  # đã xóa khỏi đĩa: coi là bị xóa
    return files


def diff(base: dict, current: dict):
    """(file đổi hay mới: {đường dẫn: (mode, nội dung)}, file bị xóa)."""
    changed = {p: v for p, v in current.items()
               if p not in base or base[p][0] != v[0] or base[p][1] != blob_sha(v[1])}
    deleted = {p for p, (mode, _) in base.items() if p not in current and mode != SUBMODULE}
    return changed, deleted


def safe_parent(tree: Path, rel: str) -> Path:
    """Thư mục cha của `rel` trong `tree`, tạo dần từng cấp; từ chối đường dẫn tuyệt đối, `..`, hay một cấp là
    symlink (ghi qua đó sẽ ra ngoài thư mục tạm)."""
    parts = PurePosixPath(rel).parts
    if not parts or PurePosixPath(rel).is_absolute() or any(p in ("", ".", "..", ".git") for p in parts):
        raise Problem(f"đường dẫn không an toàn trong repo: {rel!r}")
    folder = tree
    for part in parts[:-1]:
        folder = folder / part
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise Problem(f"không ghi qua symlink hay file: {rel!r}")
        if not folder.exists():
            folder.mkdir()
    return folder


def put(tree: Path, rel: str, mode: str, data: bytes) -> None:
    target = safe_parent(tree, rel) / PurePosixPath(rel).name
    remove(target)
    if mode == SYMLINK:
        os.symlink(os.fsdecode(data), target)
    else:
        target.write_bytes(data)
        os.chmod(target, 0o755 if mode == EXECUTABLE else 0o644)


def remove(target: Path) -> None:
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)  # nằm trong thư mục tạm; rmtree không theo symlink


def build(tree: Path, base: dict, blobs: dict, overlay: dict, deleted=()) -> None:
    tree.mkdir(parents=True)
    for rel, (mode, sha) in base.items():
        if mode != SUBMODULE and rel not in deleted:
            if sha not in blobs:
                raise Problem(f"thiếu object git {sha[:12]} của {rel} (repo clone một phần hay object hỏng)")
            put(tree, rel, mode, blobs[sha])
    for rel, (mode, data) in overlay.items():
        put(tree, rel, mode, data)


def check_links(root: Path, top: Path, links) -> list:
    """Đường dẫn (tính từ gốc repo) để nối vào cây tạm: phải nằm trong project, có thật, bị git bỏ qua và không
    đang được theo dõi, để lệnh test không ghi đè code thật qua link."""
    out = []
    for link in links or ():
        full = (root / link).resolve() if not Path(link).is_absolute() else Path(link).resolve()
        try:
            rel = full.relative_to(top.resolve()).as_posix()
            full.relative_to(root.resolve())
        except ValueError:
            raise Problem(f"--link phải nằm trong project: {link}") from None
        if not full.exists():
            raise Problem(f"--link không tồn tại: {link}")
        ignored = subprocess.run(GIT + ["-C", str(top), "check-ignore", "-q", "--no-index", "--", rel],
                                 capture_output=True).returncode == 0
        tracked = bool(git(top, "ls-files", "-z", "--", rel).strip(b"\0"))
        if not ignored or tracked:
            raise Problem(f"--link chỉ nhận thư mục hay file bị git bỏ qua (như .venv), không nhận: {link}")
        out.append(rel)
    return out


def run(cmd, cwd: Path, timeout: float):
    start = time.time()
    try:
        out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, errors="replace", timeout=timeout)
        code, output = out.returncode, (out.stdout or "") + (out.stderr or "")
    except subprocess.TimeoutExpired:
        code, output = 124, f"[receipt] dừng sau {timeout:.0f} giây"
    except OSError as exc:
        code, output = 127, f"[receipt] không chạy được lệnh: {exc}"
    return code, output, time.time() - start


def tail(output: str) -> str:
    return "\n".join(output.rstrip().splitlines()[-TAIL_LINES:])


def verdict(before: int, after: int, before_out: str = "", home: str = None, probed: bool = True):
    """(mã thoát, kết luận). `home`: lý do môi trường nạp code từ thư mục làm việc thật, nếu có; `probed`: đã dò
    được môi trường của lệnh chưa (lệnh bọc ngoài như `sh -c`, `npm test` thì không)."""
    if after != 0:
        return 2, f"? không kết luận được: sau bản sửa cũng trượt trong thư mục tạm (mã {after})"
    if before == 0:
        if home:
            return 2, (f"? không kết luận được: {home}, nên phía trước bản sửa có thể đã chạy code đã sửa; chạy "
                       "với môi trường không trỏ về thư mục làm việc")
        if not probed:
            return 1, ("✗ test không bắt được lỗi: đạt cả trên code trước bản sửa (không dò được môi trường của lệnh "
                       "này: trước khi sửa test, kiểm tay xem nó có nạp code từ thư mục làm việc không, như cài kiểu "
                       "editable hay node_modules liên kết)")
        return 1, "✗ test không bắt được lỗi: đạt cả trên code trước bản sửa"
    if before in SETUP_CODES:
        return 2, f"? không kết luận được: trước bản sửa {SETUP_CODES[before]} (mã {before}), không phải trượt ở assert"
    setup = SETUP_ERROR_RE.search(before_out)
    if setup and not ASSERT_FAIL_RE.search(before_out):
        line = next((ln.strip() for ln in before_out.splitlines() if SETUP_ERROR_RE.search(ln)), setup.group(0))
        return 2, (f"? không kết luận được: trước bản sửa trượt vì thiếu import, tên, lệnh hay fixture, không phải ở "
                   f"assert ({line[:120]}); test cần gọi hành vi của bản sửa qua code đã có ở commit gốc")
    return 0, f"✓ test bắt được lỗi: trước bản sửa trượt (mã {before}), sau bản sửa đạt"


def under(path: str, real: str, base: Path) -> bool:
    """`path` (tương đối thì tính từ `base`) nằm trong `real` sau khi giải symlink, so theo cấp thư mục."""
    path = path.strip()
    if not path:
        return False
    full = os.path.realpath(path if os.path.isabs(path) else base / path)
    return full == real or full.startswith(real + os.sep)


def interpreter(cmd, cwd: Path):
    """Trình thông dịch Python mà lệnh dùng: chính lệnh khi tên là python*, hay dòng shebang của script (như
    `pytest`, `.venv/bin/xyz`); None khi không biết (lệnh bọc ngoài như `sh -c`, `uv run`, `npm test`)."""
    if not cmd:
        return None
    if PYTHON_RE.match(Path(cmd[0]).name):
        return cmd[0]
    exe = cmd[0] if "/" in cmd[0] else shutil.which(cmd[0])
    if not exe:
        return None
    try:
        with open(exe if os.path.isabs(exe) else cwd / exe, "rb") as f:
            line = f.readline(300)
    except OSError:
        return None
    parts = line[2:].decode("utf-8", "replace").split() if line.startswith(b"#!") else []
    if parts and Path(parts[0]).name == "env":
        parts = parts[1:]
    return parts[0] if parts and PYTHON_RE.match(Path(parts[0]).name) else None


def env_points_home(top: Path, cmd, cwd: Path, env=None):
    """(lý do hay None, đã dò được không): lệnh có thể nạp code từ thư mục làm việc thật thay vì cây tạm, qua biến
    môi trường, hay qua `sys.path` và file `.pth`, `__editable__*` (pip install -e) của trình thông dịch Python."""
    env = os.environ if env is None else env
    real = os.path.realpath(top)
    for var in HOME_VARS:
        if any(under(p, real, cwd) for p in env.get(var, "").split(os.pathsep)):
            return f"biến {var} trỏ về thư mục làm việc", True
    python = interpreter(cmd, cwd)
    if not python:
        return None, False
    try:
        out = subprocess.run([python, "-c", PROBE], cwd=str(cwd), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None, False
    paths = [p for p in out.stdout.splitlines() if p]
    for p in paths:
        if under(p, real, cwd):
            return f"sys.path của {python} có {p}", True
    for p in paths:
        folder = Path(p)
        if not folder.is_dir() or folder.name not in ("site-packages", "dist-packages"):
            continue
        for f in list(folder.glob("*.pth")) + list(folder.glob("__editable__*.py")):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            candidates = [ln for ln in text.splitlines() if ln and not ln.startswith(("#", "import"))]
            candidates += re.findall(r"""['"](/[^'"]+)['"]""", text)
            if any(under(c, real, folder) for c in candidates):
                return f"{f.name} trong {folder} trỏ về thư mục làm việc (cài kiểu editable)", True
    return None, True


def fails_before(root: Path, cmd: list, base: str, tests, links, timeout: float, is_test) -> dict:
    """Chạy hai phía và trả kết quả (exit, verdict, output, seconds, base, tests, before_exit, after_exit).
    `is_test(đường dẫn tính từ gốc repo)` chọn file test khi không nêu `tests`. Lỗi đầu vào ném Problem."""
    top_out = subprocess.run(GIT + ["-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top_out.returncode != 0:
        raise Problem("không phải git repo: cần lịch sử git để dựng code trước bản sửa")
    top = Path(top_out.stdout.strip())
    try:
        sha = git(top, "rev-parse", "--verify", "-q", base + "^{commit}").decode().strip()
    except Problem:
        raise Problem(f"không tìm thấy commit {base}") from None
    entries, current = base_entries(top, sha), current_files(top)
    changed, deleted = diff(entries, current)
    sub = root.resolve().relative_to(top.resolve()).as_posix()
    if not changed and not deleted:
        raise Problem(f"không có thay đổi nào so với {base}: bản sửa đã commit thì thêm --base <commit ngay trước "
                      "bản sửa>")
    if tests:
        picked = {}
        for t in tests:
            full = (root / t).resolve()
            try:
                rel = full.relative_to(top.resolve()).as_posix()
            except ValueError:
                raise Problem(f"file test nằm ngoài repo: {t}") from None
            if rel not in current:
                raise Problem(f"không thấy file test: {t}")
            picked[rel] = current[rel]
    else:
        picked = {p: v for p, v in changed.items() if is_test(p)}
    if not picked:
        raise Problem(f"không thấy file test nào đổi so với {base}; nêu bằng --tests <file>")
    if not (set(changed) - set(picked)) and not deleted:
        raise Problem(f"không có thay đổi nào ngoài file test so với {base}: bản sửa đã commit thì thêm "
                      "--base <commit ngay trước bản sửa>")
    rel_links = check_links(root, top, links)
    blobs = read_blobs(top, [s for m, s in entries.values() if m != SUBMODULE])
    tmp = Path(tempfile.mkdtemp(prefix="receipt-fails-before-"))  # quyền 0700
    previous = signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        # Dựng xong cả hai cây rồi mới chạy lệnh nào: lệnh "trước" (code của repo) không đặt được gì vào chỗ cây "sau"
        # sắp dựng.
        trees = {}
        for side, overlay, gone in (("before", picked, ()), ("after", changed, deleted)):
            tree = tmp / side / top.name
            build(tree, entries, blobs, overlay, gone)
            for rel in rel_links:
                put(tree, rel, SYMLINK, os.fsencode(str(top / rel)))
            trees[side] = tree / sub if sub != "." else tree
        sides = {side: run(cmd, cwd, timeout) for side, cwd in trees.items()}
        home, probed = (env_points_home(top, cmd, trees["before"]) if sides["before"][0] == 0
                        and sides["after"][0] == 0 else (None, True))
    finally:
        signal.signal(signal.SIGTERM, previous)
        shutil.rmtree(tmp, ignore_errors=True)
    (b_code, b_out, b_sec), (a_code, a_out, a_sec) = sides["before"], sides["after"]
    code, text = verdict(b_code, a_code, b_out, home, probed)
    submodules = sorted(p for p, (m, _) in entries.items() if m == SUBMODULE)
    lines = [f"[receipt] trước bản sửa (commit {sha[:12]} + {len(picked)} file test): "
             f"{'đạt' if b_code == 0 else f'trượt (mã {b_code})'} · {b_sec:.1f} giây",
             f"[receipt] sau bản sửa (commit {sha[:12]} + {len(changed)} file đổi, {len(deleted)} file xóa): "
             f"{'đạt' if a_code == 0 else f'trượt (mã {a_code})'} · {a_sec:.1f} giây"]
    if submodules:
        lines.append(f"[receipt] không dựng submodule: {', '.join(submodules[:5])}")
    output = ("--- trước bản sửa ---\n" + tail(b_out) + "\n--- sau bản sửa ---\n" + tail(a_out) + "\n"
              + "\n".join(lines))
    return {"exit": code, "verdict": text, "output": output, "seconds": b_sec + a_sec, "base": sha,
            "tests": sorted(picked), "before_exit": b_code, "after_exit": a_code, "lines": lines}
