"""Thư viện dùng chung cho hook và skill của agent-stack (chỉ thư viện chuẩn, Python 3.9+).

Gồm: vị trí thư mục state, đọc/ghi JSON của hook, tìm file kế hoạch của project,
đọc mục §0 "Đang ở đâu, việc tiếp theo", đếm checkbox, lấy trạng thái git chỉ đọc,
và biên nhận kiểm tra (kết quả test gắn với nội dung code lúc chạy).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------- vị trí

def home_dir():
    """Thư mục gốc agent-stack (có file .agent-stack-root), nếu tìm được."""
    env = os.environ.get("AGENT_STACK_HOME")
    if env:
        return Path(env).expanduser()
    for parent in LIB_DIR.parents:
        if (parent / ".agent-stack-root").exists():
            return parent
    return None


def state_dir() -> Path:
    """Nơi lưu trạng thái chạy. Ưu tiên agent-stack/state; plugin cài dạng bản sao thì dùng dữ liệu plugin."""
    env = os.environ.get("AGENT_STACK_STATE")
    if env:
        path = Path(env).expanduser()
    elif home_dir() is not None:
        path = home_dir() / "state"
    elif os.environ.get("CLAUDE_PLUGIN_DATA"):
        path = Path(os.environ["CLAUDE_PLUGIN_DATA"]) / "state"
    else:
        path = Path("~/.cache/agent-stack").expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------- hook I/O

def read_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def emit(event: str, context: str = "", system: str = "") -> None:
    """In JSON đầu ra của hook. Không có gì để báo thì không in gì."""
    out = {}
    if system:
        out["systemMessage"] = system
    if context:
        out["hookSpecificOutput"] = {"hookEventName": event, "additionalContext": context}
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=False))


def run_hook(main) -> None:
    """Chạy hàm main của hook; mọi lỗi đều ghi log và thoát 0 để không làm kẹt phiên."""
    try:
        main()
    except Exception as exc:  # noqa: BLE001 (hook không được phép làm hỏng phiên)
        try:
            log_event("hook-error", {"hook": Path(sys.argv[0]).name, "error": repr(exc)[:300]})
        except Exception:  # noqa: BLE001
            pass
    sys.exit(0)


def once(key: str, ttl_seconds: float) -> bool:
    """True nếu đây là lần đầu `key` xuất hiện trong `ttl_seconds` giây.

    Dùng để chống chạy trùng khi hook được đăng ký hai lần, và chống nhắc lặp lại.
    Tạo file đánh dấu bằng O_EXCL nên hai tiến trình chạy song song chỉ một bên thắng.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key)[:150]
    marker_dir = state_dir() / "once"
    marker_dir.mkdir(exist_ok=True)
    marker = marker_dir / safe
    try:
        fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except FileExistsError:
        try:
            if time.time() - marker.stat().st_mtime < ttl_seconds:
                return False
            os.utime(str(marker))
            return True
        except OSError:
            return True
    except OSError:
        return True


def prune(directory: Path, max_age_days: float) -> None:
    """Xóa file cũ trong thư mục state (đánh dấu once, thông tin phiên)."""
    cutoff = time.time() - max_age_days * 86400
    try:
        for path in directory.iterdir():
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
    except OSError:
        pass


def log_event(kind: str, data: dict, filename: str = "events.jsonl") -> None:
    path = state_dir() / filename
    try:
        if path.exists() and path.stat().st_size > 1_000_000:
            path.replace(path.with_suffix(".old.jsonl"))
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "kind": kind, **data}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json_atomic(path: Path, data) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- văn bản

def fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt (đ → d), để so khớp từ khóa."""
    text = text.replace("đ", "d").replace("Đ", "D")
    norm = unicodedata.normalize("NFD", text)
    return "".join(c for c in norm if unicodedata.category(c) != "Mn").lower()


def strip_md(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def clip(text: str, limit: int) -> str:
    text = strip_md(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------- file kế hoạch

PLAN_CANDIDATES = (".agent/HANDOFF.md", "PLAN.md", ".agent/PLAN.md", "PROGRESS.md", "TODO.md")


def project_root(cwd) -> Path:
    """Thư mục gần nhất (từ cwd lên tới gốc git) có file kế hoạch; không có thì lấy gốc git, rồi tới cwd."""
    cwd = Path(cwd or os.getcwd()).resolve()
    out = git_out(cwd, "rev-parse", "--show-toplevel")
    top = Path(out.strip()).resolve() if out else None
    for candidate in [cwd, *cwd.parents]:
        if find_plans(candidate):
            return candidate
        if top is None or candidate == top:
            break
    return top or cwd


def find_plans(root: Path) -> list:
    return [root / rel for rel in PLAN_CANDIDATES if (root / rel).is_file()]


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
SECTION0_RE = re.compile(r"^0\s*[.):]?\s|dang o dau|viec tiep theo|where (we are|things stand)|next steps?", re.I)
LABELS = (
    ("in_progress", ("dang do", "dang lam", "in progress", "wip", "unfinished")),
    ("done", ("xong", "da xong", "hoan thanh", "done")),
    ("next", ("viec tiep theo", "tiep theo", "buoc tiep", "next")),
    ("decisions", ("quyet dinh", "con treo", "open question", "blocked", "cho duyet")),
    ("checks", ("moc kiem tra", "moc test", "kiem chung", "baseline", "checks")),
    ("after_interrupt", ("sau khi bi ngat", "sau moi lan bi ngat", "bi ngat", "after interruption", "resume checklist")),
)
DATE_RE = re.compile(r"(?:cập nhật|cap nhat|updated)\D{0,12}(?:(\d{1,2})/(\d{1,2})/(\d{4})|(\d{4})-(\d{2})-(\d{2}))", re.I)
EMPTY_VALUES = ("khong co", "chua co", "none", "n/a", "-")


def classify_label(label: str):
    f = fold(label)
    for key, needles in LABELS:
        if any(n in f for n in needles):
            return key
    return None


def section0(text: str):
    """Trả về (tiêu_đề, nội_dung) của mục §0, hoặc None nếu không có."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and SECTION0_RE.search(fold(m.group(2))):
            level = len(m.group(1))
            body = []
            for nxt in lines[i + 1:]:
                h = HEADING_RE.match(nxt)
                if h and len(h.group(1)) <= level:
                    break
                body.append(nxt)
            return m.group(2), "\n".join(body)
    return None


def parse_section0(text: str) -> dict:
    """Đọc mục §0 thành các trường: done, in_progress, next (danh sách), decisions, checks, after_interrupt."""
    found = section0(text)
    result = {"heading": None, "updated": None, "fields": {}, "next": [], "after_interrupt": [], "notes": []}
    if not found:
        return result
    result["heading"], body = found
    m = DATE_RE.search(body)
    if m:
        if m.group(1):
            result["updated"] = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        else:
            result["updated"] = f"{m.group(4)}-{m.group(5)}-{m.group(6)}"
    current_key, current_text, children = None, "", []

    def flush():
        if current_key is None and not current_text:
            return
        if current_key in ("next", "after_interrupt"):
            items = children or ([current_text] if current_text else [])
            result[current_key] = [clip(x, 220) for x in items if strip_md(x)]
            if current_text and children:
                result["fields"][current_key + "_intro"] = clip(current_text, 220)
        elif current_key:
            extra = (" " + " ".join(children)) if children else ""
            result["fields"][current_key] = clip(current_text + extra, 400)
        else:
            result["notes"].append(clip(current_text, 300))

    for line in body.splitlines():
        top = re.match(r"^[-*]\s+(.*)$", line)
        child = re.match(r"^\s{2,}(?:[-*]|\d+[.)])\s+(.*)$", line)
        if top:
            flush()
            content = top.group(1)
            lab = re.match(r"^\*\*([^*]+?):?\*\*:?\s*(.*)$", content)
            if lab:
                current_key, current_text = classify_label(lab.group(1)), lab.group(2)
                if current_key is None:
                    current_text = lab.group(1).rstrip(":") + ": " + lab.group(2)
            else:
                current_key, current_text = None, content
            children = []
        elif child and (current_key is not None or current_text):
            children.append(child.group(1))
        elif line.strip() and (current_text or children) and not line.lstrip().startswith(("|", "#", "```")):
            if children:
                children[-1] += " " + line.strip()
            else:
                current_text += " " + line.strip()
    flush()
    return result


def baseline_anywhere(text: str):
    """Tìm mốc kiểm tra ở bất kỳ đâu trong file (ví dụ 'Mốc test hiện hành: `274 passed`')."""
    m = re.search(r"\*\*\s*Mốc (?:kiểm tra|test)[^*`]*?`([^`]+)`", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"Mốc (?:kiểm tra|test)[^\n`]*`([^`]+)`", text, re.I)
    return m.group(1) if m else None


def checkbox_progress(text: str) -> dict:
    """Đếm checkbox theo từng tiêu đề; giai đoạn hiện tại là tiêu đề đầu tiên còn ô chưa tick."""
    phases, current = [], None
    for line in text.splitlines():
        h = HEADING_RE.match(line)
        if h:
            current = {"title": clip(h.group(2), 90), "done": 0, "todo": 0, "first_todo": None}
            phases.append(current)
            continue
        box = re.match(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$", line)
        if box:
            if current is None:
                current = {"title": "(đầu file)", "done": 0, "todo": 0, "first_todo": None}
                phases.append(current)
            if box.group(1).strip():
                current["done"] += 1
            else:
                current["todo"] += 1
                if current["first_todo"] is None:
                    current["first_todo"] = clip(box.group(2), 200)
    phases = [p for p in phases if p["done"] or p["todo"]]
    done = sum(p["done"] for p in phases)
    total = done + sum(p["todo"] for p in phases)
    active = next((p for p in phases if p["todo"]), None)
    return {"done": done, "total": total, "phases": phases, "current": active}


# ---------------------------------------------------------------- git (chỉ đọc)

def git_out(cwd: Path, *args: str, timeout: float = 3.0):
    """Chạy git chỉ đọc. --no-optional-locks để không ghi .git/index của project khác."""
    try:
        out = subprocess.run(["git", "--no-optional-locks", "-C", str(cwd), *args], capture_output=True,
                             text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def git_summary(root: Path) -> dict:
    status = git_out(root, "status", "--porcelain=v1", "-b")
    if status is None:
        return {"is_repo": False}
    lines = status.splitlines()
    branch_line = lines[0] if lines and lines[0].startswith("##") else ""
    dirty = [ln[3:] for ln in lines[1:] if ln.strip()]
    branch = re.sub(r"^##\s+", "", branch_line).split("...")[0]
    ahead = re.search(r"ahead (\d+)", branch_line)
    behind = re.search(r"behind (\d+)", branch_line)
    last = git_out(root, "log", "-1", "--format=%ct%x09%s")
    last_ts, last_subject = None, None
    if last and "\t" in last:
        ts, last_subject = last.strip().split("\t", 1)
        last_ts = int(ts)
    stash = git_out(root, "stash", "list")
    return {"is_repo": True, "branch": branch.replace("No commits yet on ", ""), "dirty": dirty,
            "ahead": int(ahead.group(1)) if ahead else 0, "behind": int(behind.group(1)) if behind else 0,
            "last_commit_ts": last_ts, "last_commit": last_subject,
            "stash": len(stash.splitlines()) if stash else 0}


# ---------------------------------------------------------------- hồ sơ project

# Nhóm file theo phần mở rộng. Dùng để chọn skill hợp với project ngay khi mở phiên.
PROFILE_EXT = {
    "python": {".py", ".pyi", ".ipynb"},
    "c_cpp": {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh"},
    "hdl": {".v", ".sv", ".svh", ".vh", ".vhd", ".vhdl"},
    "web": {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html", ".css"},
    "rust": {".rs"},
    "go": {".go"},
    "jvm": {".java", ".kt", ".scala"},
    "docs": {".md", ".mdx", ".rst", ".tex", ".txt"},
}
PROFILE_SKIP = {"node_modules", ".git", ".venv", "venv", "dist", "build", "vendor", "third_party", "__pycache__",
                ".tmp", ".cache", "state", "backups", ".vet-cache"}
SECURITY_NAME = re.compile(r"(auth|login|passw|crypt|secret|permission|acl|oauth|jwt|sanitiz|secur|csrf|xss)",
                           re.IGNORECASE)
# Code mẫu, test và dữ liệu eval không cho biết bản thân project có xử lý dữ liệu nhạy cảm hay không.
NOT_PRODUCT_CODE = re.compile(r"(^|/)(tests?|spec|__tests__|evals?|fixtures?|examples?|samples?|docs?)/", re.IGNORECASE)
TEST_NAME = re.compile(r"(^|/)(tests?|spec|__tests__)/|(^|/)test_[^/]+$|_test\.[a-z]+$|\.(test|spec)\.[a-z]+$")
PROFILE_TTL = 6 * 3600


def project_files(root: Path, limit: int = 20000) -> list:
    """Đường dẫn tương đối của file trong project: theo git (đã theo dõi và file mới chưa bị ignore),
    hoặc duyệt thư mục có giới hạn khi không phải git repo."""
    out = git_out(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", timeout=5.0)
    if out is not None:
        return [f for f in out.split("\0") if f and not set(Path(f).parts) & PROFILE_SKIP][:limit]
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PROFILE_SKIP and not d.startswith(".")]
        for name in filenames:
            files.append(os.path.relpath(os.path.join(dirpath, name), root))
            if len(files) >= limit:
                return files
    return files


def project_profile(root: Path, use_cache: bool = True):
    """Hồ sơ ngắn của project: loại file chính và dấu hiệu (có test, CI, Docker, code nhạy cảm bảo mật).
    Chỉ làm cho git repo hoặc thư mục có file kế hoạch, để không quét những thư mục lớn như ~/Documents.
    None nếu không đủ điều kiện."""
    root = Path(root)
    is_repo = git_out(root, "rev-parse", "--show-toplevel") is not None
    if not is_repo and not find_plans(root):
        return None
    cache = state_dir() / "profiles" / (hashlib.sha1(str(root).encode()).hexdigest()[:12] + ".json")
    cached = read_json(cache) if use_cache else None
    if cached and time.time() - float(cached.get("ts", 0)) < PROFILE_TTL:
        return cached
    files = project_files(root)
    counts = {}
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        for kind, exts in PROFILE_EXT.items():
            if ext in exts:
                counts[kind] = counts.get(kind, 0) + 1
    total = sum(counts.values()) or 1
    kinds = [k for k, n in sorted(counts.items(), key=lambda kv: -kv[1]) if n >= 3 and n / total >= 0.15][:3]
    markers = []
    if any(TEST_NAME.search(f) for f in files):
        markers.append("tests")
    if any(f.startswith(".github/workflows/") or f in (".gitlab-ci.yml", "Jenkinsfile") for f in files):
        markers.append("ci")
    if any(os.path.basename(f).lower() in ("dockerfile", "docker-compose.yml", "compose.yaml") for f in files):
        markers.append("docker")
    code_ext = set().union(*(v for k, v in PROFILE_EXT.items() if k != "docs"))
    if sum(1 for f in files if os.path.splitext(f)[1].lower() in code_ext and SECURITY_NAME.search(f)
           and not NOT_PRODUCT_CODE.search(f)) >= 2:
        markers.append("security")
    profile = {"root": str(root), "ts": time.time(), "files": len(files), "kinds": kinds, "counts": counts,
               "markers": markers, "has_plan": bool(find_plans(root))}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(cache, profile)
    except OSError:
        pass
    return profile

# ---------------------------------------------------------------- biên nhận kiểm tra

def tree_fingerprint(root: Path):
    """Dấu vân tay nội dung của cây làm việc: file đang theo dõi và file mới chưa bị ignore.
    Chỉ phụ thuộc nội dung, nên giống nhau trước và sau khi commit. Chỉ đọc (hash-object không ghi object).
    None nếu không phải git repo hoặc git lỗi."""
    top = (git_out(root, "rev-parse", "--show-toplevel") or "").strip()
    if not top:
        return None
    listing = git_out(Path(top), "ls-files", "-s", "-z")
    status = git_out(Path(top), "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if listing is None or status is None:
        return None
    blobs = {}
    for entry in listing.split("\0"):
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if path and len(parts) >= 3:
            blobs[path] = parts[1]
    changed, tokens, i = [], status.split("\0"), 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if len(token) < 4:
            continue
        xy, path = token[:2], token[3:]
        if xy[0] in "RC":
            i += 1  # với đổi tên, token kế tiếp là đường dẫn cũ
        if not (Path(top) / path).exists():
            blobs.pop(path, None)
        elif xy == "??" or xy[1] != " ":
            changed.append(path)
    if changed:
        try:
            out = subprocess.run(["git", "--no-optional-locks", "-C", top, "hash-object", "--stdin-paths"],
                                 input="\n".join(changed) + "\n", capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        shas = out.stdout.split()
        if out.returncode != 0 or len(shas) != len(changed):
            return None
        blobs.update(zip(changed, shas))
    digest = hashlib.sha1()
    for path in sorted(blobs):
        digest.update(f"{path}\0{blobs[path]}\n".encode("utf-8", "surrogateescape"))
    return digest.hexdigest()[:16]


def receipt_path(root: Path) -> Path:
    return state_dir() / "tests" / (hashlib.sha1(str(root).encode()).hexdigest()[:12] + ".json")


def receipt_status(root: Path) -> dict:
    """Các lần kiểm tra đã ghi cho project, kèm cờ fresh: kết quả còn khớp nội dung code hiện tại không.
    {} nếu chưa có biên nhận nào. fresh là None khi không xác định được (không phải git repo)."""
    data = read_json(receipt_path(root), {}) or {}
    checks = data.get("checks") or {}
    if not checks:
        return {}
    now = tree_fingerprint(root)
    out = {}
    for label, rec in checks.items():
        fresh = None if now is None or not rec.get("fingerprint") else rec["fingerprint"] == now
        out[label] = dict(rec, fresh=fresh)
    return out

# ---------------------------------------------------------------- bản tóm tắt cho hook

def read_plan(root: Path):
    """Trả về (đường_dẫn, nội_dung, §0) của file kế hoạch mới sửa nhất, hoặc None."""
    found = []
    for path in find_plans(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            mtime = path.stat().st_mtime
        except OSError:
            continue
        sec = parse_section0(text)
        if sec["heading"] or path.name in ("HANDOFF.md", "PROGRESS.md", "TODO.md"):
            found.append((mtime, path, text, sec))
    if not found:
        return None
    _, path, text, sec = max(found, key=lambda item: item[0])
    return path, text, sec


def has_value(value) -> bool:
    return bool(value) and not fold(strip_md(value)).startswith(EMPTY_VALUES)


def brief(root: Path, max_next: int = 3) -> dict:
    """Bản tóm tắt ngắn cho hook SessionStart: dòng cho Claude và dòng cho người dùng."""
    found = read_plan(root)
    if not found:
        return {}
    path, text, sec = found
    git = git_summary(root)
    progress = checkbox_progress(text)
    f = sec["fields"]
    rel = path.relative_to(root) if str(path).startswith(str(root)) else path
    lines = [f"[agent-stack] Trạng thái project `{root.name}` theo `{rel}`"
             + (f" (cập nhật {sec['updated']})" if sec["updated"] else "") + ":"]
    if has_value(f.get("in_progress")):
        lines.append(f"- Đang dở: {clip(f['in_progress'], 220)}")
    if sec["next"]:
        lines.append("- Việc tiếp theo: " + " | ".join(f"{i}) {clip(x, 160)}" for i, x in enumerate(sec["next"][:max_next], 1)))
    elif progress["current"] and progress["current"]["first_todo"]:
        cur = progress["current"]
        lines.append(f"- Giai đoạn hiện tại: {cur['title']} ({cur['done']}/{cur['done'] + cur['todo']}); "
                     f"việc chưa xong đầu tiên: {cur['first_todo']}")
    if has_value(f.get("decisions")):
        lines.append(f"- Quyết định còn treo: {clip(f['decisions'], 160)}")
    checks = f.get("checks") or baseline_anywhere(text)
    if checks:
        lines.append(f"- Mốc kiểm tra: {clip(checks, 160)}")
    warn = []
    if git.get("is_repo"):
        lines.append(f"- Git: nhánh {git['branch'] or '?'}, {len(git['dirty'])} file chưa commit"
                     + (f", {git['ahead']} commit chưa push" if git["ahead"] else "")
                     + (f", {git['stash']} stash" if git["stash"] else ""))
        try:
            if git["last_commit_ts"] and path.stat().st_mtime + 600 < git["last_commit_ts"]:
                warn.append("file kế hoạch cập nhật trước commit gần nhất, có thể đã cũ")
        except OSError:
            pass
    if warn:
        lines.append("- Cảnh báo: " + "; ".join(warn))
    lines.append(f"Đọc mục §0 trong `{rel}` trước khi làm việc khác. Trước khi dừng phiên, cập nhật §0.")
    user = f"📍 {root.name}: " + (f"tiếp theo → {clip(sec['next'][0], 90)}" if sec["next"]
                                   else (f"đang dở → {clip(f['in_progress'], 90)}" if has_value(f.get("in_progress"))
                                         else f"kế hoạch ở {rel}"))
    return {"context": "\n".join(lines), "user": user, "plan": str(path), "after_interrupt": sec["after_interrupt"]}
