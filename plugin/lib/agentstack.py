"""Thư viện dùng chung cho hook và skill của agent-stack (chỉ thư viện chuẩn, Python 3.9+).

Gồm: vị trí thư mục state, đọc/ghi JSON của hook, tìm file kế hoạch của project,
đọc mục §0 "Đang ở đâu, việc tiếp theo", đếm checkbox, lấy trạng thái git chỉ đọc,
biên nhận kiểm tra (kết quả test gắn với nội dung code lúc chạy),
và yêu cầu gần nhất của người dùng theo từng phiên (che khóa, để đưa cho subagent chạy context riêng).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------- vị trí

def home_dir():
    """Thư mục gốc agent-stack (có file .agent-stack-root), nếu tìm được.
    Claude Code chép plugin vào ~/.claude/plugins/cache/ khi cài, nên bản chép không nằm trong repo;
    install.py ghi đường dẫn repo vào plugin/.agent-stack-home (được chép theo) để bản chép tìm về."""
    env = os.environ.get("AGENT_STACK_HOME")
    if env:
        return Path(env).expanduser()
    for parent in LIB_DIR.parents:
        if (parent / ".agent-stack-root").exists():
            return parent
    pointer = LIB_DIR.parent / ".agent-stack-home"
    try:
        target = Path(pointer.read_text(encoding="utf-8").strip()).expanduser()
    except OSError:
        return None
    return target if (target / ".agent-stack-root").exists() else None


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

def _clean_text(value):
    """Chuỗi ghi được ra UTF-8: ký tự thay thế đơn lẻ (lone surrogate, do JSON như "\\ud83d" mang tới) thành "?".
    Không làm thì mọi lần ghi file sau đó văng lỗi và hook bỏ qua các bước còn lại."""
    if isinstance(value, str):
        return value.encode("utf-8", "replace").decode("utf-8")
    if isinstance(value, list):
        return [_clean_text(v) for v in value]
    if isinstance(value, dict):
        return {_clean_text(k): _clean_text(v) for k, v in value.items()}
    return value


def read_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return _clean_text(data) if isinstance(data, dict) else {}
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


def emit_block(reason: str, system: str = "") -> None:
    """Đầu ra của hook Stop khi muốn Claude làm thêm trước khi kết thúc lượt: Claude đọc `reason`."""
    out = {"decision": "block", "reason": reason}
    if system:
        out["systemMessage"] = system
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


def record_limits(data: dict) -> None:
    """Ghi state/limits.json từ số liệu dạng statusline (statusline của terminal, hay ui_status.py của mod giao diện
    trên app desktop) để hook UserPromptSubmit cảnh báo hạn mức. Không có số liệu hạn mức thì không ghi."""
    limits = data.get("rate_limits") or {}
    if not isinstance(limits, dict):
        return
    now = time.time()
    # Bỏ cửa sổ đã qua giờ reset: số đọc lúc resume phiên cũ không được coi là mới.
    limits = {k: v for k, v in limits.items() if not (isinstance(v, dict) and isinstance(v.get("resets_at"), (int, float))
                                                      and v["resets_at"] < now)}
    if not limits:
        return
    try:
        write_json_atomic(state_dir() / "limits.json", {
            "ts": time.time(), "rate_limits": limits, "model": data.get("model") or {},
            "effort": (data.get("effort") or {}).get("level"), "session_id": data.get("session_id")})
    except OSError:
        pass


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
# §0 dài hơn mức này (khoảng 4K token) thì nhắc dời việc đã xong sang nhật ký: agent đọc §0 mỗi phiên.
SECTION0_LONG_CHARS = 12_000
HISTORY_REL = ".agent/NHAT-KY.md"  # nhật ký việc đã xong, do `state.py trim` của session-keeper ghi
TRIM_CMD = "~/Documents/Claude/agent-stack/plugin/skills/session-keeper/scripts/state.py trim"


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
    """Loại nhãn của §0 theo từ khóa; bỏ phần trong ngoặc, để "Việc của user (không chặn việc tiếp theo)" hay
    "Ghi nhớ (đã xong, …)" không bị nhận là "Việc tiếp theo", "Xong"."""
    f = fold(re.sub(r"\([^)]*\)", " ", label))
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
    """Đọc mục §0 thành các trường: done, in_progress, next (danh sách phẳng mọi cấp), next_open (bước chưa xong,
    bỏ cả mục con của bước đã xong), decisions, checks, after_interrupt."""
    found = section0(text)
    result = {"heading": None, "updated": None, "fields": {}, "next": [], "next_open": [], "after_interrupt": [],
              "notes": []}
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
            result[current_key] += [clip(x, 220) for x in items if strip_md(x)]  # nhiều nhãn cùng loại thì gộp
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

    def open_flat(nodes):
        out = []
        for node in nodes:
            if strip_md(node["text"]) and not step_done(node["text"]):
                out.append(clip(node["text"], 220))
                out.extend(open_flat(node["kids"]))
        return out

    result["next_open"] = open_flat(section0_outline(text, "next"))
    return result


def section0_outline(text: str, key: str) -> list:
    """Các mục con dưới một nhãn của §0 (key theo classify_label, ví dụ "next", "decisions"), giữ cấp lồng nhau:
    [{"text", "kids": [...]}]. Nhãn không có mục con thì là một mục với phần chữ ngay sau nhãn. Dòng nối tiếp
    được ghép vào mục gần nhất ở trên."""
    found = section0(text)
    if not found:
        return []
    out, active, inline, stack = [], False, "", []  # stack: [(độ thụt, mục)]
    has_kids = False  # nhãn đang đọc đã có mục con chưa

    def flush():
        if active and not has_kids and inline.strip():
            out.append({"text": inline, "kids": []})

    for line in found[1].splitlines():
        head = re.match(r"^[-*]\s+(.*)$", line)
        if head:
            flush()
            label = re.match(r"^\*\*([^*]+?):?\*\*:?\s*(.*)$", head.group(1))
            active = bool(label) and classify_label(label.group(1)) == key
            inline, stack, has_kids = (label.group(2) if label else ""), [], False
            continue
        if not active:
            continue
        child = re.match(r"^(\s{2,})(?:[-*]|\d+[.)])\s+(.*)$", line)
        if child:
            width, node = len(child.group(1)), {"text": child.group(2), "kids": []}
            while stack and stack[-1][0] >= width:
                stack.pop()
            (stack[-1][1]["kids"] if stack else out).append(node)
            stack.append((width, node))
            has_kids = True
        elif line.strip() and not line.lstrip().startswith(("|", "#", "```")):
            if stack:
                stack[-1][1]["text"] += " " + line.strip()
            elif inline.strip():
                inline += " " + line.strip()
    flush()
    return out


def section0_items(text: str, key: str) -> list:
    """Các mục con cấp cao nhất dưới một nhãn của §0 (key theo classify_label, ví dụ "done", "decisions");
    nhãn không có mục con thì lấy phần chữ ngay sau nhãn. Dòng nối tiếp của một mục được ghép vào mục đó."""
    return [node["text"] for node in section0_outline(text, key)]


DONE_STEP_RE = re.compile(r"^(?:~~|✅|✔|☑|\[[xX]\])|^[^:~]{1,40}:\s*(?:✅|✔|☑)")


def step_done(text: str) -> bool:
    """Bước đã xong: bị gạch (~~...~~), hay mở đầu bằng ✅ (kể cả sau nhãn ngắn như "Bước 3: ✅ …")."""
    raw = (text or "").strip()
    return raw.startswith("~~") or bool(DONE_STEP_RE.match(strip_md(raw)))


def next_open(sec: dict) -> list:
    """Các bước chưa xong trong "Việc tiếp theo" của §0 đã đọc bằng parse_section0: mục con của bước đã xong (dù
    không đánh dấu) cũng bị bỏ. Dict không có "next_open" thì lọc danh sách phẳng."""
    if "next_open" in sec:
        return sec["next_open"]
    return [step for step in sec.get("next") or [] if not step_done(step)]


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
    """Chạy git chỉ đọc. --no-optional-locks để không ghi .git/index của project khác; tắt core.fsmonitor vì repo lạ
    có thể đặt nó thành một lệnh bất kỳ mà `git status` sẽ chạy."""
    try:
        out = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(cwd), *args],
                             capture_output=True,
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
    steps = next_open(sec)
    if steps:
        lines.append("- Việc tiếp theo: " + " | ".join(f"{i}) {clip(x, 160)}" for i, x in enumerate(steps[:max_next], 1)))
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
    user = f"📍 {root.name}: " + (f"tiếp theo → {clip(steps[0], 90)}" if steps
                                   else (f"đang dở → {clip(f['in_progress'], 90)}" if has_value(f.get("in_progress"))
                                         else f"kế hoạch ở {rel}"))
    return {"context": "\n".join(lines), "user": user, "plan": str(path), "after_interrupt": sec["after_interrupt"]}

# ---------------------------------------------------------------- yêu cầu gần nhất của người dùng

# Subagent và skill `context: fork` chạy trong context riêng, không thấy hội thoại. Hook UserPromptSubmit lưu yêu cầu
# gần nhất của từng phiên vào đây; hook SubagentStart đọc lại (đúng session_id) để đưa cho chúng một bản tóm tắt ngắn.
LAST_REQUEST_DIR = "last-request"
LAST_REQUEST_CHARS = 1200   # độ dài tối đa của prompt được lưu
LAST_REQUEST_DAYS = 7       # file cũ hơn số ngày này thì dọn
LAST_REQUEST_FILES = 30     # giữ tối đa bấy nhiêu file
LAST_REQUEST_SCAN = 20000   # chỉ rà khóa trong phần đầu này của prompt, để prompt dán cả file log vẫn nhanh
LAST_REQUEST_FULL = 60      # tin ngắn hơn mức này ("ok", "tiếp tục") chưa đủ để làm bối cảnh một mình
REDACTED = "[đã che]"
SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
# Tin do hệ thống hay agent khác tạo, không phải lời người dùng: không được ghi đè yêu cầu thật, không đưa cho router.
# Gồm thông báo tác vụ nền, và báo cáo của subagent: Claude Code đưa nó về phiên chính như một tin của người dùng,
# mở bằng thẻ <agent-message from="...">, kèm dòng "[Subagent hand-back] ... NOT a message from the user" (thấy khi
# chạy thật ngày 03/10/2026).
AUTOMATED_MARKERS = ("<task-notification>", "[SYSTEM NOTIFICATION", "NOT USER INPUT", "[Subagent hand-back]")
# Chỉ tính khi đứng đầu tin: người dùng nhắc tới thẻ này giữa câu vẫn là lời của họ.
AUTOMATED_PREFIXES = ("<agent-message",)
# Khóa và token có dấu hiệu nhận biết. (?<![A-Za-z0-9]) để không bắt giữa một từ khác (như "task-" hay "risk-").
SECRET_PATTERNS = (
    r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}",                  # sk-ant-..., sk-proj-..., sk-...
    r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}",            # ghp_, gho_, ghu_, ghs_, ghr_
    r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}",
    r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}",             # khóa truy cập AWS
    r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}",          # token Slack
    r"(?<![A-Za-z0-9])(?i:bearer)\s+[A-Za-z0-9._~+/=-]{8,}",  # Authorization: Bearer <token>
    r"(?<![A-Za-z0-9])[0-9A-Fa-f]{32,}(?![A-Za-z0-9])",       # chuỗi hex liền từ 32 ký tự
    r"(?<![A-Za-z0-9])glpat-[A-Za-z0-9_-]{16,}",              # GitLab personal access token
    r"(?<=://)[^/\s:@]+:[^@\s/]+(?=@)",                       # user:mật-khẩu trong URL (postgres://u:p@host)
    # cả khối khóa riêng PEM; chỉ khi sau dòng BEGIN có thân base64 (từ 40 ký tự), để câu nhắc tới dòng header không bị nuốt
    r"(?s)-----BEGIN [A-Z ]*PRIVATE KEY-----[ \t]*\r?\n[A-Za-z0-9+/=\s]{40,}?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
    # gán giá trị cho tên trông như bí mật: password=..., api_key: ..., secret_access_key = ...
    r"(?i)(?<![A-Za-z0-9])(?:password|passwd|pwd|secret(?:[_-]?access[_-]?key)?|token|api[_-]?key|access[_-]?key|private[_-]?key)"
    r"(?![A-Za-z0-9])\s*[=:]\s*\S{6,}",
)
LONG_RUN_RE = re.compile(r"[A-Za-z0-9+/_-]{32,}={0,2}")


def is_command_prompt(prompt) -> bool:
    """True với lệnh slash (/compact), lệnh shell (!ls) hay ghi chú bộ nhớ (#...): không phải yêu cầu công việc.
    Cùng quy ước với router (task-router bỏ qua tin bắt đầu bằng / ! #)."""
    return isinstance(prompt, str) and prompt.lstrip()[:1] in ("/", "!", "#")


def is_automated_prompt(prompt) -> bool:
    """True với tin do hệ thống hay agent khác tạo (thông báo tác vụ nền, báo cáo của subagent), không phải lời của
    người dùng."""
    if not isinstance(prompt, str):
        return False
    return prompt.lstrip().startswith(AUTOMATED_PREFIXES) or any(marker in prompt for marker in AUTOMATED_MARKERS)


def _mask_long_run(match) -> str:
    """Chuỗi liền từ 32 ký tự kiểu base64 chỉ bị che khi trông như dữ liệu ngẫu nhiên: có cả chữ hoa lẫn chữ thường,
    có chữ số (hoặc kết thúc bằng '=' của base64), và không giống đường dẫn (nhiều dấu '/'). Nhờ vậy đường dẫn dài,
    tên hàm, UUID không bị che nhầm."""
    run = match.group(0)
    random_like = (any(c.isupper() for c in run) and any(c.islower() for c in run)
                   and (any(c.isdigit() for c in run) or run.endswith("=")))
    # Khóa bí mật AWS dài 40 ký tự base64 và hay chứa vài dấu '/', nên được nới số dấu '/' cho độ dài gần đó.
    return REDACTED if random_like and run.count("/") <= (3 if 40 <= len(run) <= 44 else 2) else run


def redact_secrets(text: str) -> str:
    """Che khóa API, token, chuỗi hex và chuỗi base64 dài bằng [đã che]."""
    for pattern in SECRET_PATTERNS:
        text = re.sub(pattern, REDACTED, text)
    return LONG_RUN_RE.sub(_mask_long_run, text)


def _session_key(session_id):
    """session_id dùng được làm tên file (chỉ chữ, số, _ và -, tối đa 128 ký tự), hoặc None."""
    return session_id if isinstance(session_id, str) and SESSION_ID_RE.fullmatch(session_id) else None


def _prune_last_requests(directory: Path, keep: Path) -> None:
    """Dọn file cũ hơn LAST_REQUEST_DAYS ngày, rồi bỏ file cũ nhất cho tới khi còn tối đa LAST_REQUEST_FILES. Giữ `keep`."""
    prune(directory, LAST_REQUEST_DAYS)
    try:
        files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime)
        others = [p for p in files if p != keep]
        for old in others[: max(0, len(files) - LAST_REQUEST_FILES)]:
            old.unlink()
    except OSError:
        pass


def _full_request(old):
    """Yêu cầu đủ dài gần nhất trong bản ghi cũ ({ts, prompt}) hoặc None: chính prompt cũ nếu đủ dài, không thì `earlier`."""
    if not isinstance(old, dict):
        return None
    for cand in (old, old.get("earlier")):
        if isinstance(cand, dict) and isinstance(cand.get("prompt"), str) and len(cand["prompt"]) >= LAST_REQUEST_FULL:
            ts = cand.get("ts")
            return {"ts": float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) else None,
                    "prompt": cand["prompt"]}
    return None


def save_last_request(session_id, cwd, prompt):
    """Lưu yêu cầu gần nhất của người dùng trong một phiên, để hook SubagentStart đưa cho subagent.

    Ghi state/last-request/<session_id>.json gồm {ts, cwd, prompt}. Che khóa trước rồi mới cắt còn LAST_REQUEST_CHARS
    ký tự, để khóa nằm sát mốc cắt không để lại nửa chuỗi. Khi tin mới quá ngắn ("ok", "tiếp tục") mà tin dài gần nhất
    trước đó còn đó, thêm `earlier` {ts, prompt} để subagent vẫn thấy việc thật. Mỗi lần ghi dọn file cũ. Trả None,
    không văng lỗi, khi session_id lạ, prompt rỗng, lệnh slash/shell/ghi chú, hoặc tin do hệ thống tạo. Nếu ghi được
    thì trả về đường dẫn file."""
    try:
        key = _session_key(session_id)
        if key is None or not isinstance(prompt, str) or is_automated_prompt(prompt) or is_command_prompt(prompt):
            return None
        text = redact_secrets(prompt[:LAST_REQUEST_SCAN]).strip()[:LAST_REQUEST_CHARS]
        if not text:
            return None
        directory = state_dir() / LAST_REQUEST_DIR
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / f"{key}.json"
        record = {"ts": time.time(), "cwd": str(cwd or ""), "prompt": text}
        if len(text) < LAST_REQUEST_FULL:
            earlier = _full_request(read_json(path))
            if earlier:
                record["earlier"] = earlier
        write_json_atomic(path, record)
        os.chmod(str(path), 0o600)  # prompt là thông tin riêng của người dùng
        _prune_last_requests(directory, path)
        return path
    except Exception as exc:  # noqa: BLE001 (phần phụ, không được làm hỏng hook)
        try:
            log_event("hook-error", {"hook": "save_last_request", "error": repr(exc)[:300]})
        except Exception:  # noqa: BLE001
            pass
        return None


def load_last_request(session_id):
    """Yêu cầu gần nhất đã lưu của ĐÚNG phiên này, dạng {ts, cwd, prompt[, earlier: {ts, prompt}]}. None nếu chưa có,
    file hỏng hoặc session_id lạ. ts là None nếu không đọc được thời điểm. Không bao giờ văng lỗi."""
    try:
        key = _session_key(session_id)
        if key is None:
            return None
        data = read_json(state_dir() / LAST_REQUEST_DIR / f"{key}.json")
        if not isinstance(data, dict) or not isinstance(data.get("prompt"), str) or not data["prompt"].strip():
            return None
        ts = data.get("ts")
        out = {"ts": float(ts) if isinstance(ts, (int, float)) and not isinstance(ts, bool) else None,
               "cwd": data["cwd"] if isinstance(data.get("cwd"), str) else "", "prompt": data["prompt"]}
        earlier = data.get("earlier")
        if isinstance(earlier, dict) and isinstance(earlier.get("prompt"), str) and earlier["prompt"].strip():
            ets = earlier.get("ts")
            out["earlier"] = {"ts": float(ets) if isinstance(ets, (int, float)) and not isinstance(ets, bool) else None,
                              "prompt": earlier["prompt"]}
        return out
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- cổng nhắc audit trước phát hành

# Hook PreToolUse chặn lần đầu Claude tạo tag hay bản phát hành, để lời nhắc audit tới được Claude: lý do kèm "ask" chỉ
# hiện cho người dùng, và ở auto mode câu hỏi có thể được duyệt mà không ai đọc (kiểm 10/10/2026, Claude Code 2.1.295).
# Lệnh chỉ qua khi người dùng đã nhắn sau lần chặn. Mốc chặn lưu ở state/audit-nudge/<session_id>.json: {khóa: ts};
# lúc người dùng nhắn gần nhất ở state/user-msg/<session_id>.json: {ts}. Mốc này tính cả lệnh slash (`/claude-security`
# là câu trả lời tự nhiên cho lời nhắc), khác state/last-request vốn bỏ lệnh. Khóa đã qua thì cả phiên không nhắc lại.
AUDIT_NUDGE_DIR = "audit-nudge"
USER_MSG_DIR = "user-msg"
AUDIT_NUDGE_DAYS = 7


def mark_user_message(session_id, prompt) -> None:
    """Ghi lúc người dùng nhắn, gồm cả lệnh slash, `!`, `#`; bỏ tin rỗng và tin do hệ thống hay agent khác tạo. Không
    bao giờ văng lỗi."""
    try:
        key = _session_key(session_id)
        if key is None or not isinstance(prompt, str) or not prompt.strip() or is_automated_prompt(prompt):
            return
        directory = state_dir() / USER_MSG_DIR
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_json_atomic(directory / f"{key}.json", {"ts": time.time()})
        prune(directory, AUDIT_NUDGE_DAYS)
    except Exception:  # noqa: BLE001
        pass


def release_gate(session_id, keys: list):
    """"pass" khi người dùng đã nhắn (tin thật, không phải tin hệ thống) sau lần chặn của mọi khóa; "nudge" khi phải chặn,
    sau khi ghi mốc chặn cho các khóa chưa qua; None khi không theo dõi được phiên (session_id lạ, không ghi được
    state). Phiên chưa ghi tin nào của người dùng thì vẫn chặn. Không bao giờ văng lỗi."""
    try:
        key = _session_key(session_id)
        if key is None:
            return None
        spoke = (read_json(state_dir() / USER_MSG_DIR / f"{key}.json", {}) or {})
        spoke = spoke.get("ts") if isinstance(spoke, dict) else None
        spoke = spoke if isinstance(spoke, (int, float)) and not isinstance(spoke, bool) else None
        directory = state_dir() / AUDIT_NUDGE_DIR
        path = directory / f"{key}.json"
        nudges = read_json(path, {})
        nudges = nudges if isinstance(nudges, dict) else {}
        pending = [k for k in keys
                   if not (spoke is not None and isinstance(nudges.get(k), (int, float)) and nudges[k] < spoke)]
        if not pending:
            return "pass"
        nudges.update({k: time.time() for k in pending})
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_json_atomic(path, nudges)
        prune(directory, AUDIT_NUDGE_DAYS)
        return "nudge"
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- lượt cuối (ghi sau mỗi lượt)

# Hook UserPromptSubmit ghi lúc bắt đầu mỗi lượt và dấu §0 lúc đó vào state/turns/<session>.json. Hook Stop dựa vào
# đó để biết lượt vừa xong đã đổi file nào và §0 đã được cập nhật chưa, rồi ghi .agent/LAST-TURN.md trong project:
# yêu cầu, câu trả lời cuối (đã che khóa), việc tiếp theo, file đổi. Hook SessionStart nạp file này vào phiên mới.
LAST_TURN_REL = ".agent/LAST-TURN.md"
TURN_DIR = "turns"
TURN_DAYS = 7
TURN_FILES = 50
LAST_TURN_ANSWER_CHARS = 1500   # câu trả lời cuối lưu trong file
LAST_TURN_REQUEST_CHARS = 600
LAST_TURN_FILES = 15            # số tên file ghi ra
CHANGED_SCAN = 500              # chỉ xét bấy nhiêu dòng git status, để repo lớn vẫn nhanh
LAST_TURN_HEADER_RE = re.compile(r"<!-- agent-stack last-turn ts=(\d+(?:\.\d+)?) session=([A-Za-z0-9_-]*)"
                                 r"(?: state=(running|done|failed))?(?: sig=([0-9a-f]{32}))? -->")
LAST_TURN_STATE_DIR = "last-turn"       # lượt cuối của thư mục chung (home, ~/.claude, thư mục tạm...)
LAST_TURN_KEY = "last-turn.key"         # khóa HMAC ký mỗi bản ghi; bản không ký đúng không được nạp
LAST_TURN_PREV_CHARS = 700              # câu trả lời của lượt xong trước đó, khi lượt mới đang chạy hay lỗi
LAST_TURN_OTHERS = 3                    # số phiên khác giữ lại
LAST_TURN_OTHERS_SECONDS = 24 * 3600    # chỉ giữ phiên khác trong khoảng này
STATE_LABELS = {"done": "xong", "running": "đang chạy", "failed": "dừng vì lỗi"}
NEXT_LINE_RE = re.compile(r"^[ \t]*➡️?[ \t]*Tiếp:[ \t]*(.+?)[ \t]*$", re.M)


def is_project(root: Path) -> bool:
    """Thư mục đáng ghi lượt cuối: là git repo hoặc có file kế hoạch. Thư mục tùy ý (như ~) thì không."""
    return bool(find_plans(root)) or git_out(root, "rev-parse", "--git-dir") is not None


def plan_done_count(root: Path):
    """{"path", "count"}: file kế hoạch đang dùng và số việc đã xong trong đó (ô đã tick cộng bước đã xong trong
    "Việc tiếp theo" của §0: gạch ~~...~~ hay đánh ✅). Hook Stop so đầu và cuối lượt, chỉ khi cùng file, để biết
    lượt vừa xong một việc. None nếu không có file kế hoạch."""
    found = read_plan(root)
    if not found:
        return None
    path, text, sec = found
    ticked = len(re.findall(r"(?m)^\s*[-*]\s+\[[xX]\]\s", text))
    count = ticked + sum(1 for step in sec.get("next") or [] if step_done(step))
    return {"path": str(path), "count": count}


def tool_used_since(transcript_path, since: float, needle: str, tool_suffix: str = "",
                    tail_bytes: int = 2_000_000) -> bool:
    """Trong transcript (JSONL), từ thời điểm `since`, có lời gọi công cụ nào (tên kết thúc bằng `tool_suffix`, nếu
    có) chứa `needle` trong đầu vào không. Chỉ đọc phần cuối file; lỗi đọc thì coi như có (không nhắc oan)."""
    try:
        path = Path(transcript_path)
        with path.open("rb") as fh:
            size = path.stat().st_size
            fh.seek(max(0, size - tail_bytes))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError, ValueError):
        return True
    for line in reversed(lines):
        if needle not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        stamp = entry.get("timestamp") or ""
        try:
            ts = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if ts < since:
            return False
        content = ((entry.get("message") or {}).get("content")) or []
        if any(isinstance(c, dict) and c.get("type") == "tool_use" and str(c.get("name") or "").endswith(tool_suffix)
               and needle in json.dumps(c.get("input"), ensure_ascii=False) for c in content):
            return True
    return False


def transcript_offers_tool(transcript_path, suffix: str, head_bytes: int = 1_000_000) -> bool:
    """Phiên có công cụ tên kết thúc bằng `suffix` không, theo danh sách công cụ Claude Code ghi vào phần đầu transcript:
    tên trong attachment deferred_tools_delta (công cụ hoãn) và prompt_snapshot (công cụ nạp sẵn). Chỉ khớp theo tên
    công cụ, không khớp chữ trong CLAUDE.md hay tin nhắn. Định dạng này không được công bố nên lỗi đọc hay không thấy
    thì coi như không có."""
    try:
        with Path(transcript_path).open("rb") as fh:
            lines = fh.read(head_bytes).decode("utf-8", "replace").splitlines()
    except (OSError, TypeError, ValueError):
        return False
    for line in lines:
        if suffix not in line or '"attachment"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue  # dòng bị cắt ở cuối phần đã đọc
        att = entry.get("attachment") if entry.get("type") == "attachment" else None
        if not isinstance(att, dict):
            continue
        if att.get("type") == "deferred_tools_delta":
            names = [n for key in ("addedNames", "readdedNames") for n in att.get(key) or []]
            gone = set(att.get("removedNames") or [])
            names = [n for n in names if n not in gone]
        elif att.get("type") == "prompt_snapshot":
            names = [t.get("name") for t in att.get("tools") or [] if isinstance(t, dict)]
        else:
            continue
        if any(isinstance(n, str) and n.endswith(suffix) for n in names):
            return True
    return False


def section0_digest(root: Path):
    """Dấu của mục §0 (file kế hoạch đang dùng + nội dung §0), hoặc None nếu project không có §0."""
    found = read_plan(root)
    if not found:
        return None
    path, text, _ = found
    sec = section0(text)
    if not sec:
        return None
    return hashlib.sha1(f"{path}\n{sec[0]}\n{sec[1]}".encode("utf-8", "replace")).hexdigest()[:16]


def _turn_path(session_id):
    key = _session_key(session_id)
    return state_dir() / TURN_DIR / f"{key}.json" if key else None


def start_turn(session_id, cwd, extra=None):
    """Ghi lúc bắt đầu lượt, dấu §0 và HEAD lúc đó, cho hook Stop so sánh. Gọi ở mọi tin, kể cả tin do hệ thống tạo,
    vì tin nào cũng mở một lượt mới. `extra` thêm cờ của lượt (ví dụ threat_model: router thấy chức năng đụng ranh
    giới tin cậy). Không bao giờ văng lỗi; trả về bản ghi hoặc None."""
    try:
        path = _turn_path(session_id)
        if path is None:
            return None
        root = project_root(cwd)
        record = {"ts": time.time(), "root": str(root), "plan_digest": section0_digest(root),
                  "plan_done": plan_done_count(root),
                  "head": (git_out(root, "rev-parse", "--verify", "-q", "HEAD") or "").strip() or None}
        record.update(extra or {})
        path.parent.mkdir(mode=0o700, exist_ok=True)
        write_json_atomic(path, record)
        prune(path.parent, TURN_DAYS)
        files = sorted(path.parent.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for old in [p for p in files if p != path][: max(0, len(files) - TURN_FILES)]:
            old.unlink()
        return record
    except Exception as exc:  # noqa: BLE001
        log_event("hook-error", {"hook": "start_turn", "error": repr(exc)[:300]})
        return None


CHOT_VIEC_DIR = "chot-viec"


def _chot_viec_path(root: Path) -> Path:
    return state_dir() / CHOT_VIEC_DIR / (hashlib.sha1(str(Path(root).resolve()).encode()).hexdigest()[:16] + ".json")


def mark_chot_viec(root, files=None) -> None:
    """risk.py (bước 3 của chot-viec) ghi lúc nó chạy cho project này, và dấu băm các dòng thêm vào lúc đó theo từng
    file, để hook Stop biết lượt đã chốt việc chưa và ở lượt sau chỉ chấm phần mới."""
    try:
        path = _chot_viec_path(project_root(root))
        path.parent.mkdir(mode=0o700, exist_ok=True)
        write_json_atomic(path, {"ts": time.time(), "root": str(project_root(root)), "files": files or {}})
    except Exception as exc:  # noqa: BLE001
        log_event("hook-error", {"hook": "mark_chot_viec", "error": repr(exc)[:300]})


def chot_viec_mark(root) -> dict:
    data = read_json(_chot_viec_path(root)) or {}
    return data if isinstance(data, dict) and isinstance(data.get("ts"), (int, float)) else {}


def chot_viec_ran_since(root, since: float) -> bool:
    return chot_viec_mark(root).get("ts", 0) >= since


def load_turn(session_id):
    path = _turn_path(session_id)
    data = read_json(path) if path else None
    if not isinstance(data, dict) or not isinstance(data.get("ts"), (int, float)):
        return None
    return data


def save_turn(session_id, record: dict) -> None:
    path = _turn_path(session_id)
    if path is not None:
        path.parent.mkdir(mode=0o700, exist_ok=True)
        write_json_atomic(path, record)


def changed_since(root: Path, since: float) -> list:
    """File trong project đổi sau thời điểm `since`: file chưa commit có mtime mới hơn, cộng file trong các commit
    tạo sau đó. Bỏ file kế hoạch và chính LAST-TURN.md. File đã xóa không xét được thời điểm nên bỏ qua."""
    skip = set(PLAN_CANDIDATES) | {LAST_TURN_REL}
    found = []
    top_out = git_out(root, "rev-parse", "--show-toplevel")
    top = Path(top_out.strip()).resolve() if top_out else None
    root = root.resolve()
    # git status --porcelain luôn in đường dẫn tính từ gốc repo, kể cả khi chạy trong thư mục con: ghép với gốc repo
    # rồi đổi về đường dẫn tính từ project; `-- .` giới hạn trong project.
    status = git_out(root, "-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all",
                     "--", ".") if top else None
    for line in (status or "").splitlines()[:CHANGED_SCAN]:
        path = top / line[3:].split(" -> ")[-1].strip().strip('"')
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if not rel or rel in skip:
            continue
        try:
            if path.stat().st_mtime > since:
                found.append(rel)
        except OSError:
            continue
    log = git_out(root, "-c", "core.quotePath=false", "log", "-n", "20", "--format=@%ct", "--name-only",
                  "--relative") or ""
    recent = False
    for line in log.splitlines():
        if line.startswith("@"):
            recent = line[1:].strip().isdigit() and int(line[1:].strip()) >= int(since)
        elif line.strip() and recent and line.strip() not in skip and line.strip() not in found:
            found.append(line.strip())
    return found


def extract_next(message):
    """Việc tiếp theo trong dòng `➡️ Tiếp: … · Model: …` cuối câu trả lời, hoặc None nếu không có."""
    if not isinstance(message, str):
        return None
    hits = NEXT_LINE_RE.findall(message)
    if not hits:
        return None
    text = re.split(r"\s+·\s+Model:", hits[-1])[0].strip()
    return text or None


def strip_next(message: str) -> str:
    return NEXT_LINE_RE.sub("", message).strip()


def _one_line(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def ensure_git_exclude(root: Path) -> None:
    """Thêm LAST-TURN.md vào .git/info/exclude của repo (bỏ qua cục bộ, không sửa file nào được commit),
    để file không hiện trong git status và không bị commit nhầm."""
    top = git_out(root, "rev-parse", "--show-toplevel")
    rel_exclude = git_out(root, "rev-parse", "--git-path", "info/exclude")
    if not top or not rel_exclude:
        return
    top = Path(top.strip()).resolve()
    exclude = Path(rel_exclude.strip())
    if not exclude.is_absolute():
        exclude = (root / exclude).resolve()
    try:
        pattern = "/" + (root.resolve() / LAST_TURN_REL).relative_to(top).as_posix()
    except ValueError:
        return
    try:
        current = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if pattern in current.splitlines():
            return
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write(("" if not current or current.endswith("\n") else "\n")
                     + "# agent-stack: lượt cuối do hook Stop ghi, chỉ dùng trên máy này\n" + pattern + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- lượt cuối: nơi ghi, chữ ký

def _shared_dir(root: Path) -> bool:
    """Thư mục chung, không nên rải file của agent-stack vào: home và các thư mục cha của nó, thư mục cấu hình của
    công cụ (~/.claude, ~/.config, ~/Library...), thư mục tạm của hệ điều hành."""
    try:
        root = Path(root).resolve()
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        return True
    if root == home or root in home.parents:
        return True
    bases = [home / rel for rel in (".claude", ".config", ".cache", ".local", "Library")]
    bases += [Path(tempfile.gettempdir()), Path("/tmp"), Path("/var/folders"), Path("/private/var/folders")]
    for base in bases:
        try:
            base = base.resolve()
        except (OSError, RuntimeError):
            continue
        if root == base or base in root.parents:
            return True
    return False


def _workspace_dir(root: Path, scan: int = 300) -> bool:
    """Thư mục chứa từ hai project trở lên ở ngay cấp dưới (như ~/Documents/Claude): nơi gom nhiều project, không phải
    một việc riêng."""
    count = 0
    try:
        for i, child in enumerate(Path(root).iterdir()):
            if i >= scan:
                break
            if child.name.startswith(".") or not child.is_dir():
                continue
            if (child / ".git").exists() or find_plans(child):
                count += 1
                if count >= 2:
                    return True
    except OSError:
        pass
    return False


def _in_folder_ok(root: Path) -> bool:
    """Ghi được .agent/LAST-TURN.md ngay trong thư mục: `.agent` và file đích không phải symlink hay thứ lạ, nằm trong
    thư mục, và file không do git theo dõi (repo clone có thể cài sẵn file này để nhồi chữ vào phiên sau)."""
    agent = Path(root) / ".agent"
    target = agent / "LAST-TURN.md"
    try:
        if agent.is_symlink() or target.is_symlink():
            return False
        if agent.exists() and not agent.is_dir():
            return False
        if target.exists() and not target.is_file():
            return False
        if agent.exists() and Path(root).resolve() not in agent.resolve().parents:
            return False
        if agent.exists() and hasattr(os, "getuid") and agent.stat().st_uid != os.getuid():
            return False  # thư mục nhiều người cùng ghi: `.agent` của người khác
    except OSError:
        return False
    tracked = git_out(Path(root), "ls-files", "--", LAST_TURN_REL)
    return not (tracked and tracked.strip())


def last_turn_path(root: Path) -> Path:
    """Nơi ghi lượt cuối của thư mục làm việc. Mặc định `.agent/LAST-TURN.md` ngay trong thư mục, kể cả thư mục không
    phải project, để project tự đọc được mà không cần agent-stack. Thư mục chung (home, ~/.claude, thư mục tạm, thư mục
    gom nhiều project) và chỗ không ghi an toàn được thì ghi vào state/last-turn/<băm đường dẫn>.md."""
    root = Path(root)
    shared = _shared_dir(root) or (not is_project(root) and _workspace_dir(root))
    if not shared and _in_folder_ok(root):
        return root / LAST_TURN_REL
    return _state_path(root)


def _scope(root: Path) -> str:
    """Thư mục mà bản ghi thuộc về; nằm trong chữ ký, nên chép bản ghi sang thư mục khác thì không được nạp."""
    try:
        return str(Path(root).resolve())
    except (OSError, RuntimeError):
        return str(root)


def _state_path(root: Path) -> Path:
    key = hashlib.sha1(_scope(root).encode("utf-8", "replace")).hexdigest()[:16]
    return state_dir() / LAST_TURN_STATE_DIR / f"{key}.md"


def _last_turn_key() -> bytes:
    """Khóa HMAC riêng của máy này (state/last-turn.key, quyền 0600). Chỉ tạo khóa mới khi chưa có file, hay file có mà
    nội dung hỏng thật; lỗi đọc tạm thời thì văng lỗi (bản ghi lần đó không ký được) chứ không thay khóa."""
    path = state_dir() / LAST_TURN_KEY
    for _ in range(3):
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            raw = None
        if raw is None:
            key = os.urandom(32)
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                time.sleep(0.05)  # tiến trình khác vừa tạo: đọc khóa của nó
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(key.hex())
            return key
        try:
            key = bytes.fromhex(raw)
        except ValueError:
            key = b""
        if len(key) >= 16:
            return key
        if raw:  # nội dung hỏng thật: thay bằng khóa mới (bản ghi cũ mất hiệu lực, lỗi theo hướng an toàn)
            key = os.urandom(32)
            tmp = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
            fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(key.hex())
            tmp.replace(path)
            return key
        time.sleep(0.05)  # file rỗng: tiến trình khác đang ghi dở
    raise OSError("không đọc được khóa ký lượt cuối")


def _sign(ts: str, session: str, state: str, body: str, scope: str) -> str:
    message = f"{ts}|{session}|{state}|{scope}\n{body}".encode("utf-8", "replace")
    return hmac.new(_last_turn_key(), message, hashlib.sha256).hexdigest()[:32]


# ---------------------------------------------------------------- lượt cuối: viết và đọc

SEC_ANSWER = "## Câu trả lời cuối (đã che khóa)"
SEC_PARTIAL = "## Phần trả lời trước khi dừng (đã che khóa)"
SEC_PREVIOUS = "## Lượt xong trước đó (đã che khóa)"
SEC_OTHERS = "## Phiên khác gần đây"
OTHER_LINE_RE = re.compile(r"^- <!-- ts=(\d+(?:\.\d+)?) session=([A-Za-z0-9_-]+) state=(running|done|failed) --> "
                           r"`[^`]*` · [^·]* · [^·]* · yêu cầu: (.*?)(?: · tiếp: (.*))?$")
FIELD_RE = re.compile(r"^- \*\*(.+?):\*\* (.*)$", re.M)


NEWLINES_RE = re.compile("\r\n?|[\u2028\u2029\x0b\x0c\x1c\x1d\x1e\x85]")


def _norm_newlines(text: str) -> str:
    """Mọi kiểu xuống dòng (kể cả U+2028, \\x85, \\r) thành \\n, để file chỉ có một nghĩa của "dòng" khi ghi, ký và đọc."""
    return NEWLINES_RE.sub("\n", text or "")


def _sane_ts(value) -> bool:
    """Mốc thời gian hợp lý: số hữu hạn, sau năm 2001 và không quá một ngày trong tương lai."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return False
    return 1e9 < value < time.time() + 86400


def _demote(text: str) -> str:
    """Dòng `## ` trong câu trả lời thành `### `, để không lẫn với các mục của file."""
    return re.sub(r"(?m)^## ", "### ", text or "")


def _when(ts: float) -> str:
    try:
        return time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))
    except (OverflowError, OSError, ValueError):
        return "?"


def _short_when(ts: float) -> str:
    try:
        return time.strftime("%H:%M %d/%m", time.localtime(ts))
    except (OverflowError, OSError, ValueError):
        return "?"


def _render_other(o: dict) -> str:
    line = (f"- <!-- ts={float(o['ts']):.0f} session={o['session']} state={o['state']} --> `{o['session'][:8]}` · "
            f"{_short_when(float(o['ts']))} · {STATE_LABELS.get(o['state'], o['state'])} · "
            f"yêu cầu: {_one_line(redact_secrets(o.get('request') or '?'), 160).replace(' · tiếp: ', ' - tiếp: ')}")
    if o.get("next"):
        line += f" · tiếp: {_one_line(redact_secrets(o['next']), 160)}"
    return line


def _render_last_turn(rec: dict, in_git: bool, scope: str) -> str:
    """Nội dung file lượt cuối (đã ký). `rec`: ts, session, state, fields (thứ tự giữ nguyên), answer, previous
    ({fields, answer} hay None), others (danh sách {ts, session, state, request, next})."""
    where = ("File này chỉ nằm trên máy (đã thêm vào `.git/info/exclude`)." if in_git
             else "File này chỉ nằm trên máy.")
    lines = ["# Lượt cuối", "",
             f"Hook của agent-stack tự ghi lúc bắt đầu và kết thúc mỗi lượt; đừng sửa tay (sửa thì bản ghi không được "
             f"nạp vào phiên sau). {where}", ""]
    lines += [f"- **{k}:** {v}" for k, v in rec["fields"].items() if v]
    if rec["state"] != "running":
        lines += ["", SEC_PARTIAL if rec["state"] == "failed" else SEC_ANSWER, ""]
        lines.append(_demote(rec.get("answer") or "") or "(Claude Code không gửi câu trả lời cuối cho hook)")
    prev = rec.get("previous")
    if prev and rec["state"] != "done":
        lines += ["", SEC_PREVIOUS, ""]
        lines += [f"- **{k}:** {v}" for k, v in prev.get("fields", {}).items() if v]
        if prev.get("answer"):
            lines += ["", _demote(clip(prev["answer"], LAST_TURN_PREV_CHARS))]
    if rec.get("others"):
        lines += ["", SEC_OTHERS, ""] + [_render_other(o) for o in rec["others"]]
    body = _norm_newlines("\n".join(lines) + "\n").encode("utf-8", "replace").decode("utf-8")
    ts = f"{float(rec['ts']):.0f}"
    sig = _sign(ts, rec["session"], rec["state"], body, scope)
    return f"<!-- agent-stack last-turn ts={ts} session={rec['session']} state={rec['state']} sig={sig} -->\n{body}"


def _parse_last_turn(text: str, scope: str):
    """Đọc nội dung file lượt cuối của thư mục `scope`. None nếu không có header, chữ ký sai hay thiếu (file không do
    hook trên máy này ghi cho đúng thư mục này, hoặc bị sửa tay), hay mốc thời gian vô lý."""
    first, _, body = text.partition("\n")
    m = LAST_TURN_HEADER_RE.fullmatch(first.strip())
    if not m or not m.group(4) or not _sane_ts(m.group(1)):
        return None
    ts, session, state = m.group(1), m.group(2), m.group(3) or "done"
    if not hmac.compare_digest(_sign(ts, session, state, body, scope), m.group(4)):
        return None
    sections, current = {"": []}, ""
    for line in body.split("\n"):  # đúng nghĩa "dòng" lúc ký: chỉ \n
        if line.startswith("## "):
            current = line.strip()
            sections[current] = []
        else:
            sections[current].append(line)
    head = "\n".join(sections[""])
    fields = {}
    for label, value in FIELD_RE.findall(head):
        fields.setdefault(label, value)
    answer = "\n".join(sections.get(SEC_ANSWER) or sections.get(SEC_PARTIAL) or []).strip()
    previous = None
    if SEC_PREVIOUS in sections:
        prev_text = "\n".join(sections[SEC_PREVIOUS])
        pf = {}
        for label, value in FIELD_RE.findall(prev_text):
            pf.setdefault(label, value)
        prev_answer = FIELD_RE.sub("", prev_text).strip()
        previous = {"fields": pf, "answer": prev_answer}
    others = []
    for line in sections.get(SEC_OTHERS) or []:
        om = OTHER_LINE_RE.match(line.strip())
        if om and _sane_ts(om.group(1)):
            others.append({"ts": float(om.group(1)), "session": om.group(2), "state": om.group(3),
                           "request": om.group(4), "next": om.group(5)})
    return {"ts": float(ts), "session": session, "state": state, "fields": fields, "answer": answer,
            "previous": previous, "others": others}


def read_last_turn(root: Path):
    """Đọc lượt cuối của thư mục: {ts, session, state, fields{Trạng thái, Lúc, Yêu cầu, …}, answer, previous, others,
    path}, hoặc None nếu chưa có, hỏng, hay không mang chữ ký đúng của máy này."""
    best = None
    for path in dict.fromkeys((last_turn_path(root), _state_path(root))):  # bản trong thư mục, và bản dự phòng
        rec = _read_record(path, _scope(root))
        if rec and (best is None or rec["ts"] > best["ts"]):
            best = rec
    return best


def _read_record(path: Path, scope: str):
    try:
        if path.is_symlink():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        rec = _parse_last_turn(text, scope)
    except (ValueError, OverflowError):
        rec = None
    if rec is None:
        log_event("last-turn-unsigned", {"path": str(path)})
        return None
    rec["path"] = path
    return rec


def _summary_of(rec: dict) -> dict:
    f = rec.get("fields") or {}
    nxt = f.get("Tiếp", "")
    return {"ts": rec["ts"], "session": rec["session"], "state": rec.get("state", "done"),
            "request": f.get("Yêu cầu", ""), "next": None if not nxt or nxt.startswith(("không rõ", "(")) else nxt}


def record_turn(root: Path, session_id, *, state: str, request: str, answer: str = "", next_step=None,
                changed=(), dirty_count=None, branch=None, plan_status: str = "", note: str = "",
                ts: float = None):
    """Ghi lượt cuối của thư mục (state: running lúc bắt đầu lượt, done khi xong, failed khi lỗi API kết thúc lượt).
    Giữ lại lượt xong trước đó của cùng phiên khi lượt mới đang chạy hay lỗi, và tối đa LAST_TURN_OTHERS phiên khác
    trong 24 giờ. Mọi chữ được che khóa; file quyền 0600, ký HMAC. Trả về đường dẫn đã ghi."""
    ts = ts or time.time()
    key = _session_key(session_id) or ""
    root = Path(root)
    path = last_turn_path(root)
    old = read_last_turn(root)
    req = redact_secrets(request or "").strip()[:LAST_TURN_REQUEST_CHARS] or "(không lưu được)"
    fields = {}
    if state == "running":
        fields["Trạng thái"] = (f"đang chạy từ {_short_when(ts)} (chưa xong; phiên đó đã đóng mà vẫn thấy dòng này "
                                "thì lượt bị ngắt giữa chừng: Esc, crash, đóng app, máy ngủ)")
    elif state == "failed":
        fields["Trạng thái"] = _one_line(redact_secrets(note or "dừng vì lỗi API"), 300)
    else:
        fields["Trạng thái"] = "xong"
    fields["Lúc"] = f"{_when(ts)} · phiên `{key[:8] or '?'}`" + (f" · nhánh `{branch}`" if branch else "")
    fields["Yêu cầu"] = _one_line(req, LAST_TURN_REQUEST_CHARS)
    if state != "running":
        files = ", ".join(f"`{f}`" for f in list(changed)[:LAST_TURN_FILES]) + (
            " …" if len(changed) > LAST_TURN_FILES else "")
        fields["Tiếp"] = (_one_line(redact_secrets(next_step), 300) if next_step
                          else ("(lượt dừng giữa chừng)" if state == "failed"
                                else "không rõ (câu trả lời không có dòng ➡️)"))
        fields["File đổi trong lượt"] = files or "không có"
        if dirty_count is not None:
            fields["File chưa commit"] = str(dirty_count)
        if plan_status:
            fields["§0"] = plan_status
    ans = redact_secrets(_norm_newlines(answer)).strip()
    if len(ans) > LAST_TURN_ANSWER_CHARS:
        ans = ans[:LAST_TURN_ANSWER_CHARS].rstrip() + "\n…(đã cắt)"
    previous = None
    if old and old["session"] == key:
        if old["state"] == "done":
            previous = {"fields": {k: old["fields"].get(k) for k in ("Lúc", "Yêu cầu", "Tiếp")},
                        "answer": old.get("answer", "")}
        else:
            previous = old.get("previous")
    others = [o for o in (old or {}).get("others", []) if o["session"] != key]
    if old and old["session"] and old["session"] != key:
        others.insert(0, _summary_of(old))
    seen, kept = set(), []
    for o in others:
        if o["session"] in seen or not _sane_ts(o["ts"]) or ts - float(o["ts"]) > LAST_TURN_OTHERS_SECONDS:
            continue
        seen.add(o["session"])
        kept.append(o)
    rec = {"ts": ts, "session": key, "state": state, "fields": fields, "answer": ans,
           "previous": previous, "others": kept[:LAST_TURN_OTHERS]}
    scope = _scope(root)
    in_folder = path == root / LAST_TURN_REL
    in_git = in_folder and git_out(root, "rev-parse", "--git-dir") is not None
    try:
        _write_record(path, _render_last_turn(rec, in_git, scope))
    except OSError:
        if not in_folder:
            raise
        # Thư mục không ghi được (ổ chỉ đọc, `.agent` của người khác): ghi bản dự phòng vào state/.
        path, in_folder, in_git = _state_path(root), False, False
        _write_record(path, _render_last_turn(rec, False, scope))
    if in_git:
        ensure_git_exclude(root)
    elif in_folder:
        _ensure_agent_gitignore(path.parent)
    return path


def _write_record(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    # O_EXCL và O_NOFOLLOW: không bao giờ ghi qua một file hay symlink có sẵn mang tên file tạm.
    fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _ensure_agent_gitignore(agent_dir: Path) -> None:
    """Thư mục chưa có git: thêm `.agent/.gitignore` bỏ qua LAST-TURN.md, để sau này `git init && git add -A` không
    commit nhầm nội dung phiên. Không đụng file .gitignore đã có."""
    try:
        fd = os.open(str(agent_dir / ".gitignore"), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                     0o644)
    except OSError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("# agent-stack: lượt cuối do hook ghi, chỉ dùng trên máy này\nLAST-TURN.md\nLAST-TURN.md.*.tmp\n")


def write_last_turn(root: Path, session_id, request, answer, next_step, changed, dirty_count, branch,
                    plan_status: str, ts: float = None) -> Path:
    """Ghi lượt đã xong (giữ chữ ký hàm cũ)."""
    return record_turn(root, session_id, state="done", request=request, answer=answer, next_step=next_step,
                       changed=changed, dirty_count=dirty_count, branch=branch, plan_status=plan_status, ts=ts)


def request_text(session_id) -> str:
    """Yêu cầu gần nhất của người dùng trong phiên, kèm yêu cầu dài trước đó khi tin mới quá ngắn ("làm tiếp đi")."""
    request = load_last_request(session_id) or {}
    prompt = request.get("prompt", "")
    if request.get("earlier") and len(prompt) < LAST_REQUEST_FULL:
        prompt = f"{prompt} (trước đó: {request['earlier']['prompt']})"
    return prompt


def mark_turn_running(session_id, cwd, prompt) -> None:
    """Lúc người dùng gửi tin: ghi lượt cuối ở trạng thái đang chạy, để Esc, crash, đóng app hay lượt dài chưa xong
    vẫn để lại yêu cầu và lúc bắt đầu. Bỏ qua tin do hệ thống tạo và lệnh. Không bao giờ văng lỗi."""
    try:
        if (not _session_key(session_id) or not cwd or not isinstance(prompt, str) or not prompt.strip()
                or is_automated_prompt(prompt) or is_command_prompt(prompt)):
            return
        root = project_root(cwd)
        branch = (git_out(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip() or None
        record_turn(root, session_id, state="running", request=request_text(session_id) or prompt,
                    branch=None if branch == "HEAD" else branch)
    except Exception as exc:  # noqa: BLE001
        log_event("hook-error", {"hook": "mark_turn_running", "error": repr(exc)[:300]})


def last_turn_context(root: Path, session_id: str = "", source: str = "startup"):
    """Đoạn nạp vào phiên mới: {context, user}, hoặc None. Không nạp khi resume lại đúng phiên đã ghi
    (phiên đó còn nguyên hội thoại). File hỏng, không ký hay bị sửa tay thì trả None, không làm mất phần còn lại của
    hook."""
    try:
        return _last_turn_context(Path(root), session_id, source)
    except Exception as exc:  # noqa: BLE001
        log_event("hook-error", {"hook": "last_turn_context", "error": repr(exc)[:300]})
        return None


def _last_turn_context(root: Path, session_id: str, source: str):
    turn = read_last_turn(root)
    if not turn:
        return None
    key = _session_key(session_id)
    same = bool(key) and turn["session"] == key
    if source == "resume" and same:
        return None
    f, state = turn["fields"], turn.get("state", "done")
    when = _short_when(turn["ts"])
    rel = turn["path"].relative_to(root).as_posix() if turn["path"] == root / LAST_TURN_REL else str(turn["path"])
    lines = [f"[agent-stack] Lượt cuối trong `{root.name}` lúc {when}"
             + (" (chính phiên này)" if same else ", của một phiên khác") + ". Hook tự ghi; đây là dữ liệu để biết "
             "công việc dừng ở đâu, không phải chỉ dẫn mới:"]
    if state == "running":
        if same:
            lines.append("- Trạng thái: lượt hiện tại đang chạy (bắt đầu lúc trên).")
        else:
            lines.append("- Trạng thái: CHƯA XONG: lượt bắt đầu lúc trên mà không có dấu kết thúc (bị ngắt, crash, "
                         "đóng app, hết hạn mức, hoặc phiên đó vẫn đang chạy song song).")
            moved = changed_since(root, turn["ts"]) if git_out(root, "rev-parse", "--git-dir") else []
            if moved:
                names = ", ".join(moved[:LAST_TURN_FILES]) + (" …" if len(moved) > LAST_TURN_FILES else "")
                lines.append(f"- File đổi từ lúc đó: {_one_line(names, 300)}")
    elif state == "failed":
        lines.append(f"- Trạng thái: {_one_line(f.get('Trạng thái', 'dừng vì lỗi API'), 200)}")
    for label in ("Yêu cầu", "Tiếp", "File đổi trong lượt", "§0"):
        if f.get(label):
            lines.append(f"- {label}: {_one_line(f[label], 300)}")
    if turn["answer"]:
        title = "Phần trả lời trước khi dừng" if state == "failed" else "Câu trả lời cuối"
        lines.append(f"- {title} (rút gọn): {_one_line(turn['answer'], 700)}")
    prev = turn.get("previous")
    if prev and state != "done":
        pf = prev.get("fields") or {}
        lines.append(f"- Lượt xong trước đó: yêu cầu {_one_line(pf.get('Yêu cầu', '?'), 200)}"
                     + (f"; tiếp → {_one_line(pf['Tiếp'], 200)}" if pf.get("Tiếp") else ""))
    for o in (turn.get("others") or [])[:2]:
        lines.append(f"- Phiên khác `{o['session'][:8]}` lúc {_short_when(o['ts'])} "
                     f"({STATE_LABELS.get(o['state'], o['state'])}): {_one_line(o.get('request') or '?', 160)}"
                     + (f"; tiếp → {_one_line(o['next'], 120)}" if o.get("next") else ""))
    lines.append(f"Toàn văn ở `{rel}`. Nếu người dùng nói “làm tiếp”, bắt đầu từ đây và §0.")
    nxt = f.get("Tiếp", "")
    if state == "running" and not same:
        user = f"⚠️ Lượt cuối chưa xong ({when}): {_one_line(f.get('Yêu cầu', ''), 90)}"
    elif state == "failed":
        user = f"⚠️ Lượt cuối {_one_line(f.get('Trạng thái', 'dừng vì lỗi'), 60)} ({when})"
    else:
        user = f"🕘 Lượt cuối ({when})" + (
            f": tiếp → {_one_line(nxt, 90)}" if nxt and not nxt.startswith(("không rõ", "(")) else "")
    return {"context": "\n".join(lines), "user": user, "ts": turn["ts"]}


# ---------------------------------------------------------------- transcript: model, context, phần trả lời dở

MODEL_ID_RE = re.compile(r"claude-[a-z0-9.-]{1,60}")


def _transcript_tail(transcript_path, tail_bytes: int):
    path = Path(transcript_path)
    with path.open("rb") as fh:
        size = path.stat().st_size
        fh.seek(max(0, size - tail_bytes))
        return fh.read().decode("utf-8", "replace").splitlines()


def _stamp(entry: dict):
    try:
        return datetime.fromisoformat(str(entry.get("timestamp") or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _count(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def session_usage(transcript_path, tail_bytes: int = 2_000_000) -> dict:
    """Từ phần cuối transcript của phiên chính: model đang chạy, cỡ context (token vào của lần gọi gần nhất), lúc gọi,
    TTL của cache (3600 hay 300 giây; không thấy thì coi là 3600 cho chắc), và `switched` khi người dùng vừa đổi
    /model sau lần gọi đó (cache của model mới chưa có). Chỉ lấy tên model đúng mẫu và con số, không lấy chữ nào khác.
    Lỗi đọc thì trả các trường rỗng."""
    out = {"model": None, "context": 0, "ts": None, "ttl": None, "switched": False}
    try:
        lines = _transcript_tail(transcript_path, tail_bytes)
    except (OSError, TypeError, ValueError):
        lines = []
    looked = 0
    for line in reversed(lines):
        is_model_note = '"attachment"' in line and '"model"' in line and out["model"] is None
        if not is_model_note and ('"usage"' not in line or '"assistant"' not in line):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        att = entry.get("attachment") if entry.get("type") == "attachment" else None
        if is_model_note and isinstance(att, dict) and att.get("type") == "model":
            ident = att.get("identity") if isinstance(att.get("identity"), dict) else {}
            model = ident.get("modelId") or att.get("model")
            if isinstance(model, str) and MODEL_ID_RE.fullmatch(model):
                out.update(model=model, switched=True)  # /model sau lần gọi gần nhất: cache của model này chưa có
            continue
        if entry.get("type") != "assistant":
            continue
        msg = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        usage = msg.get("usage")
        model = msg.get("model")
        if not isinstance(usage, dict) or not isinstance(model, str) or not MODEL_ID_RE.fullmatch(model):
            continue
        if out["ts"] is None:
            total = sum(_count(usage.get(k)) for k in
                        ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            out.update(context=total, ts=_stamp(entry))
            if out["model"] is None:
                out["model"] = model
        cc = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
        if _count(cc.get("ephemeral_1h_input_tokens")):
            out["ttl"] = 3600
            break
        if _count(cc.get("ephemeral_5m_input_tokens")):
            out["ttl"] = 300
            break
        looked += 1
        if looked >= 50:
            break
    if out["ttl"] is None:
        out["ttl"] = 3600
    return out


# Số liệu phiên do mod giao diện (plugin/hooks/ui.tsx) ghi qua ui_status.py: số chính thức của engine thay cho việc
# đọc transcript (định dạng nội bộ, có thể đổi). OpenCode và phiên `-p` không có mod nên vẫn đọc transcript.
MOD_USAGE_MAX_AGE = 300
# Như MODEL_ID_RE, thêm ngoặc vuông cho hậu tố kiểu `[1m]`; tên lạ (không tiền tố claude-) thì bỏ (TM-34).
MOD_MODEL_RE = re.compile(r"claude-[a-z0-9.\-\[\]]{1,72}")


def mod_usage_path(session_id: str) -> Path:
    """File số liệu của một phiên; tên là sha1 của session_id, không dùng chuỗi gốc (TM-35)."""
    return state_dir() / "session-usage" / (hashlib.sha1(session_id.encode()).hexdigest()[:16] + ".json")


def _mod_model(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if MOD_MODEL_RE.fullmatch(value) else None


def _whole(value) -> int | None:
    """Số nguyên không âm, hay None (bool, chuỗi, NaN, vô cực, số âm đều bị bỏ)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return int(value)


def tree_shown_path(session_id: str) -> Path:
    """Lúc người dùng thấy cây kế hoạch dạng chữ qua lệnh /cay của mod (nơi pane không hiện, như cloud session)."""
    return state_dir() / "tree-shown" / (hashlib.sha1(session_id.encode()).hexdigest()[:16] + ".json")


def mark_tree_shown(session_id) -> None:
    """Mod gọi (qua ui_status.py --tree-shown) sau khi /cay in cây dạng chữ; hook Stop đọc để thôi nhắc hiện cây."""
    if not isinstance(session_id, str) or not session_id:
        return
    path = tree_shown_path(session_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, {"ts": time.time()})
    except OSError:
        pass


def tree_shown_at(session_id):
    """Lần gần nhất /cay in cây dạng chữ trong phiên (giây epoch), hay None."""
    if not isinstance(session_id, str) or not session_id:
        return None
    ts = (read_json(tree_shown_path(session_id)) or {}).get("ts")
    return ts if isinstance(ts, (int, float)) and not isinstance(ts, bool) else None


ROUTER_LAST_TTL = 600  # gợi ý router của tin vừa gửi chỉ dùng cho dải trong 10 phút


def router_last_path(session_id: str) -> Path:
    """Gợi ý router của tin gần nhất trong phiên (dải trên ô nhập của mod); tên là sha1 của session_id."""
    return state_dir() / "router-last" / (hashlib.sha1(session_id.encode()).hexdigest()[:16] + ".json")


def record_router(session_id: str, suggestion) -> None:
    """Ghi gợi ý router của tin vừa gửi cho mod vẽ dải; tin không có gợi ý thì xoá, để dải không hiện gợi ý cũ."""
    if not isinstance(session_id, str) or not session_id:
        return
    path = router_last_path(session_id)
    try:
        if not suggestion:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, {"session_id": session_id, "ts": time.time(), "user": suggestion.get("user"),
                                 "switch": suggestion.get("switch"), "effort": suggestion.get("effort")})
    except OSError:
        pass


def read_router(session_id: str, now: float | None = None):
    """Gợi ý router còn mới (dưới ROUTER_LAST_TTL giây) của đúng phiên, hay None."""
    if not isinstance(session_id, str) or not session_id:
        return None
    record = read_json(router_last_path(session_id), None)
    now = time.time() if now is None else now
    if (not isinstance(record, dict) or record.get("session_id") != session_id
            or not isinstance(record.get("ts"), (int, float)) or now - record["ts"] > ROUTER_LAST_TTL):
        return None
    return {k: record.get(k) for k in ("user", "switch", "effort")}


def record_mod_usage(data: dict, at_prompt: bool = False, now: float | None = None) -> bool:
    """Ghi số liệu phiên từ mod. Sau lượt (`at_prompt` False): model, context, `ts` là lúc lượt xong (lần gọi model
    gần nhất). Lúc gửi tin (`at_prompt`): chỉ cập nhật model hiện tại của file đã có, để thấy /model đổi giữa hai
    lượt. Dữ liệu sai dạng thì không ghi. Trả True khi đã ghi."""
    sid = data.get("session_id")
    model = _mod_model((data.get("model") or {}).get("id") if isinstance(data.get("model"), dict) else data.get("model"))
    if not isinstance(sid, str) or not sid or not model:
        return False
    now = time.time() if now is None else now
    path = mod_usage_path(sid)
    if at_prompt:
        record = read_json(path, None)
        if not isinstance(record, dict) or record.get("session_id") != sid:
            return False  # chưa có lượt nào: không biết lúc gọi model gần nhất, để router đọc transcript
        record.update(model=model, updated=now)
    else:
        ctx = data.get("context_window") if isinstance(data.get("context_window"), dict) else {}
        tokens = _whole(ctx.get("total_input_tokens"))
        if tokens is None:
            return False
        record = {"session_id": sid, "model": model, "call_model": model, "context": tokens,
                  "window": _whole(ctx.get("context_window_size")), "ts": now, "updated": now}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, record)
    except OSError:
        return False
    return True


def mod_session_usage(session_id: str, now: float | None = None, max_age: float = MOD_USAGE_MAX_AGE) -> dict | None:
    """Usage của phiên chính theo số của mod, cùng dạng với session_usage; None khi không có file, khác phiên, cũ hơn
    `max_age` giây hay sai dạng (TM-34), để bên gọi quay về đọc transcript. Mod không biết TTL của cache nên lấy 3600
    như session_usage khi không thấy."""
    if not isinstance(session_id, str) or not session_id:
        return None
    record = read_json(mod_usage_path(session_id), None)
    if not isinstance(record, dict) or record.get("session_id") != session_id:
        return None
    now = time.time() if now is None else now
    updated, ts = record.get("updated"), record.get("ts")
    model, call_model = _mod_model(record.get("model")), _mod_model(record.get("call_model"))
    context = _whole(record.get("context"))
    if (_whole(updated) is None or _whole(ts) is None or not model or not call_model or context is None
            or not -5 <= now - updated <= max_age or ts > updated):
        return None
    return {"model": model, "context": context, "ts": float(ts), "ttl": 3600, "switched": model != call_model}


def last_assistant_text(transcript_path, since: float = 0, tail_bytes: int = 2_000_000) -> str:
    """Đoạn chữ gần nhất Claude viết ở phiên chính từ lúc `since` (bỏ thông báo lỗi API), để ghi lại phần việc dở
    khi lượt dừng vì lỗi. Chuỗi rỗng nếu không có."""
    try:
        lines = _transcript_tail(transcript_path, tail_bytes)
    except (OSError, TypeError, ValueError):
        return ""
    for line in reversed(lines):
        if '"assistant"' not in line or '"text"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant" or entry.get("isSidechain") or entry.get("isApiErrorMessage"):
            continue
        stamp = _stamp(entry)
        if stamp is not None and stamp < since:
            return ""
        content = (entry.get("message") or {}).get("content")
        texts = [c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
        text = "\n".join(t for t in texts if isinstance(t, str)).strip()
        if text:
            return text
    return ""


# ---------------------------------------------------------------- phiên chạy plugin cũ

def _version_tuple(text):
    try:
        return tuple(int(x) for x in str(text).strip().split("."))
    except ValueError:
        return None


def plugin_staleness():
    """(bản đang chạy, bản đã cài) khi phiên này chạy agent-stack cũ hơn bản đã cài trên máy (phiên mở trước lần cài
    giữ hook của bản cũ tới khi /reload-plugins hay mở lại); None nếu không lệch hay không đọc được."""
    running = (read_json(LIB_DIR.parent / ".claude-plugin" / "plugin.json", {}) or {}).get("version")
    plugins = Path(os.environ.get("AGENT_STACK_PLUGINS_DIR")
                   or Path(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude") / "plugins").expanduser()
    entries = ((read_json(plugins / "installed_plugins.json", {}) or {}).get("plugins") or {})
    installed = None
    for name, rows in entries.items():
        if name.split("@", 1)[0] == "agent-stack" and isinstance(rows, list):
            for row in rows:
                v = row.get("version") if isinstance(row, dict) else None
                if _version_tuple(v) and (installed is None or _version_tuple(v) > _version_tuple(installed)):
                    installed = v
    run_t, inst_t = _version_tuple(running), _version_tuple(installed)
    if run_t and inst_t and run_t < inst_t:
        return running, installed
    return None


# ---------------------------------------------------------------- dời lịch sử của file kế hoạch ra nhật ký
# Lõi của `state.py trim` (session-keeper). tien-do và hook Stop chạy thử nó để chỉ nhắc trim khi trim rút được §0.

TRIM_DONE_STARTS = ("xong", "da xong", "hoan thanh", "done")
_LIST_RE = re.compile(r"^([ \t]*)(?:[-*]|\d+[.)])\s+")
_BOX_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
# Ngày ở dòng đầu mục Xong: đủ năm (28/10/2026, 2026-10-28), hay thiếu năm khi đứng trong ngoặc, sau "ngày" hay đầu
# mục ("(05/10)", "ngày 5/10", "- 27/10: ..."); "18/18", "12/12" giữa câu thường là điểm số nên không tính.
_FULL_DATE_RE = re.compile(r"(?<![\d/])(?:(\d{4})-(\d{2})-(\d{2})|(\d{1,2})/(\d{1,2})/(\d{4}))(?![\d/])")
_SHORT_DATE_RE = re.compile(r"(?i)(?:\(|ngày\s+|^\s*(?:[-*]|\d+[.)])\s+(?:\*\*)?)(\d{1,2})/(\d{1,2})(?![\d/])")


class TrimOrderUnknown(ValueError):
    """Mục Xong không đủ ngày để biết mới nhất ở trên hay ở dưới: phải chọn rõ bằng cờ."""


class TrimUnsafe(ValueError):
    """Dời xong thì mốc kiểm tra mà hook và tien-do đọc được bị đổi: không dời gì."""


def _mentions_checks(lines: list) -> bool:
    """Đoạn có nhắc mốc kiểm tra ("Mốc kiểm tra:", "MỐC KIỂM TRA", "Mốc test"): giữ lại trong §0, kẻo mốc mà hook và
    tien-do đọc được đi theo một bước đã xong sang nhật ký (archctl 29/10/2026)."""
    return any("moc kiem tra" in fold(x) or "moc test" in fold(x) for x in lines)


def _plan_checks(text: str):
    """Mốc kiểm tra như tien-do và hook SessionStart đọc: trường của §0, không có thì tìm cả file."""
    return parse_section0(text)["fields"].get("checks") or baseline_anywhere(text)


def _fence_mask(lines: list) -> list:
    """True cho dòng nằm trong khối code (kể cả hai dòng ``` hay ~~~ mở, đóng)."""
    mask, fence = [], None
    for line in lines:
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
            mask.append(bool(m))
        else:
            mask.append(True)
            if m and m.group(1) == fence:
                fence = None
    return mask


def _levels(lines: list, mask: list) -> list:
    """Cấp tiêu đề của từng dòng, None nếu không phải tiêu đề hay nằm trong khối code (`# chú thích` của bash)."""
    out = []
    for line, code in zip(lines, mask):
        m = None if code else HEADING_RE.match(line)
        out.append(len(m.group(1)) if m else None)
    return out


def _bold_label(line: str):
    m = re.match(r"^[-*]\s+\*\*([^*]+?)\*\*", line)
    return m.group(1) if m else None


TRIM_POINTER_LABEL = "Xong trước đó"


def _is_pointer(line: str) -> bool:
    """Dòng trỏ sang nhật ký do trim_plan thêm vào §0."""
    return _bold_label(line.lstrip()) == f"{TRIM_POINTER_LABEL}:" and HISTORY_REL in line


def _is_done_bullet(line: str) -> bool:
    """Mục cấp đầu của §0 có nhãn đậm bắt đầu bằng "Xong" (kể cả "Xong (28/10/2026): ..."); dòng trỏ nhật ký thì không."""
    label = _bold_label(line)
    if not label or _is_pointer(line):
        return False
    return fold(re.sub(r"\([^)]*\)", " ", label)).strip().startswith(TRIM_DONE_STARTS)


def _is_next_bullet(line: str) -> bool:
    label = _bold_label(line)
    return bool(label) and classify_label(label) == "next"


def _top_blocks(lines: list, mask: list, levels: list) -> list:
    """Chia thân §0 thành khối [start, end). Khối mới mở ở mục cột 0, ở tiêu đề, ở dòng ``` cột 0, và ở đoạn văn cột 0
    đứng sau dòng trống (đoạn văn ngay dưới mục, không dòng trống, là dòng nối tiếp của mục đó)."""
    starts = [0]
    for i, line in enumerate(lines):
        if i == 0 or not line.strip() or line[:1].isspace():
            continue
        if mask[i] and not (_FENCE_RE.match(line) and not mask[i - 1]):
            continue
        if (levels[i] or _FENCE_RE.match(line) or (_LIST_RE.match(line) and not mask[i])
                or not lines[i - 1].strip()):
            starts.append(i)
    starts.append(len(lines))
    return [(s, e) for s, e in zip(starts, starts[1:]) if e > s]


def _child_spans(lines: list, mask: list, start: int, end: int) -> list:
    """Mục con cấp đầu của khối [start, end): [(s, e)], theo độ thụt nhỏ nhất của các dòng mở mục con."""
    opens = [i for i in range(start + 1, end) if not mask[i] and lines[i][:1].isspace() and _LIST_RE.match(lines[i])]
    if not opens:
        return []
    indent = min(len(_LIST_RE.match(lines[i]).group(1)) for i in opens)
    firsts = [i for i in opens if len(_LIST_RE.match(lines[i]).group(1)) == indent]
    return [(s, firsts[k + 1] if k + 1 < len(firsts) else end) for k, s in enumerate(firsts)]


def _span_text(lines: list, spans: list) -> list:
    out = []
    for a, b in spans:
        chunk = lines[a:b]
        while chunk and not chunk[-1].strip():
            chunk.pop()
        pad = min((len(x) - len(x.lstrip()) for x in chunk if x.strip()), default=0)
        out += [x[pad:] for x in chunk]
    return out


def _item_dates(first_lines: list) -> list:
    """Ngày mới nhất ghi ở dòng đầu từng mục (năm, tháng, ngày), None nếu không có; mục nhắc ngày cũ hơn ("sửa hồi quy
    của bản 01/09/2026 (29/10)") lấy ngày làm. Ngày thiếu năm lấy năm của mục có năm gần nhất (trên trước, rồi dưới),
    không có thì năm nay. Bỏ ngày sau hôm nay (lệch múi giờ thì cho thêm một ngày)."""
    now = time.localtime(time.time() + 86400)
    today = (now.tm_year, now.tm_mon, now.tm_mday)
    raw = []
    for line in first_lines:
        full, short = [], []
        for m in _FULL_DATE_RE.finditer(line):
            y, mo, d = ((m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(5), m.group(4)))
            if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
                full.append((int(y), int(mo), int(d)))
        for m in _SHORT_DATE_RE.finditer(line):
            if 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(1)) <= 31:
                short.append((int(m.group(2)), int(m.group(1))))
        full = [f for f in full if f <= today]
        raw.append((max(full) if full else None, short))
    years = [f[0] if f else None for f, _ in raw]
    out = []
    for i, (full, short) in enumerate(raw):
        year = (full[0] if full else None) or next((y for y in reversed(years[:i]) if y), None) \
            or next((y for y in years[i + 1:] if y), None) or time.localtime().tm_year
        cands = ([full] if full else []) + [(year, mo, d) for mo, d in short]
        cands = [c for c in cands if c <= today]  # ngày hẹn trong tương lai ("hạn 30/11") không phải ngày làm
        out.append(max(cands) if cands else None)
    return out


def _section0_span(lines: list, levels: list):
    """[start, end) của §0, tính cả dòng tiêu đề; None nếu không có. Cùng cách nhận §0 với section0()."""
    for i, level in enumerate(levels):
        if level and SECTION0_RE.search(fold(HEADING_RE.match(lines[i]).group(2))):
            end = next((j for j in range(i + 1, len(lines)) if levels[j] and levels[j] <= level), len(lines))
            return i, end
    return None


def _trim_section0(lines: list, keep: int, order, pointer: str) -> dict:
    mask = _fence_mask(lines)
    levels = _levels(lines, mask)
    items, steps = [], []  # items: (start, end, khối cha hay None)
    for s, e in _top_blocks(lines, mask, levels):
        if _is_done_bullet(lines[s]):
            kids = _child_spans(lines, mask, s, e)
            items += [(a, b, (s, e)) for a, b in kids] if kids else [(s, e, None)]
        elif _is_next_bullet(lines[s]):
            steps += [(a, b) for a, b in _child_spans(lines, mask, s, e)
                      if step_done(_LIST_RE.sub("", lines[a], count=1)) and not _mentions_checks(lines[a:b])]
    moved = []
    if len(items) > keep and order:
        moved = items[keep:] if order == "first" else items[:len(items) - keep]
    elif len(items) > keep:
        # Không tin vào thứ tự trong file (nhiều file vừa nối xuống dưới vừa chèn lên trên): giữ các mục có ngày mới
        # nhất. Mục cùng ngày với mục thứ `keep` thì giữ cả, vì không biết mục nào viết sau. Không đủ mục có ngày thì
        # không đoán.
        dates = _item_dates([lines[a] for a, _, _ in items])
        dated = [i for i, d in enumerate(dates) if d]
        if len(dated) < keep or (keep and not dated):
            raise TrimOrderUnknown("mục Xong không ghi đủ ngày để biết mục nào mới nhất")
        cut = sorted((dates[i] for i in dated), reverse=True)[keep - 1] if keep else None
        newest = {i for i in dated if cut is not None and dates[i] >= cut}
        moved = [item for i, item in enumerate(items) if i not in newest]
    moved = [item for item in moved if not _mentions_checks(lines[item[0]:item[1]])]
    kept = [lines[a] for a, b, p in items if (a, b, p) not in moved]
    drop = set()
    for a, b in [(a, b) for a, b, _ in moved] + steps:
        while b > a + 1 and not lines[b - 1].strip():
            b -= 1  # giữ dòng trống ở cuối, kẻo đoạn văn sau đó dính vào mục phía trên
        drop.update(range(a, b))
    for s, e in {p for _, _, p in moved if p}:  # khối cha chỉ còn dòng nhãn rỗng: bỏ luôn
        rest = [i for i in range(s + 1, e) if i not in drop and lines[i].strip()]
        if not rest and not re.sub(r"^[-*]\s+\*\*[^*]+?\*\*:?\s*", "", lines[s]).strip():
            drop.update(range(s, e))
    # Dòng trỏ là mục cấp đầu: đặt ở chỗ mục dời đầu tiên, hay ngay trên nhãn cha nếu nhãn đó còn mục con ở lại (đặt
    # giữa nhãn và mục con thì mục con thành con của dòng trỏ, và lần trim sau không dời được nữa).
    head = min(moved, default=None, key=lambda item: item[0])
    first = None
    if head is not None:
        first = head[2][0] if head[2] and head[2][0] not in drop else head[0]
        while first - 1 in drop:
            first -= 1
    has_pointer = any(_is_pointer(x) for x in lines)
    new, gap = [], False
    for i, line in enumerate(lines):
        if i == first and not has_pointer:
            new.append(pointer)
        if i in drop:
            gap = True
            continue
        if gap and not line.strip() and new and not new[-1].strip():
            continue  # gộp dòng trống liền nhau do phần đã dời để lại
        gap = gap and not line.strip()
        new.append(line)
    return {"lines": new, "done": _span_text(lines, [(a, b) for a, b, _ in moved]), "n_done": len(moved),
            "steps": _span_text(lines, steps), "n_steps": len(steps), "kept": kept,
            "moved": [lines[a] for a, _, _ in moved] + [lines[a] for a, _ in steps]}


def _done_phases(lines: list, levels: list, sec0: tuple) -> list:
    """Mốc ngoài §0 đã xong hết: [(start, end)] gồm cả tiêu đề con. Mốc là tiêu đề có ô checkbox ngay dưới nó (như
    plan_tree.py); xong hết là cả cây con có ít nhất một ô [x] và không còn ô [ ]. Chỉ lấy mốc ngoài cùng."""
    heads = [i for i, lv in enumerate(levels) if lv]
    spans = []
    for k, s in enumerate(heads):
        if sec0[0] <= s < sec0[1] or (spans and s < spans[-1][1]):
            continue
        direct_end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        end = next((h for h in heads[k + 1:] if levels[h] <= levels[s]), len(lines))
        if s < sec0[0] < end:
            continue  # tiêu đề bao ngoài §0 (như "# PLAN" có ô tick ngay dưới): dời nó là dời cả §0
        if not any(_BOX_RE.match(x) for x in lines[s + 1:direct_end]):
            continue
        boxes = [_BOX_RE.match(x).group(1) for x in lines[s + 1:end] if _BOX_RE.match(x)]
        if all(b.strip() for b in boxes):
            spans.append((s, end))
    return spans


def trim_plan(text: str, keep: int = 3, when: str = "", plan_rel: str = "PLAN.md", order=None) -> dict:
    """Dời lịch sử ra khỏi file kế hoạch, không xóa chữ nào. Trả {"text": bản kế hoạch mới, "part": đợt nhật ký mới
    ("" nếu không có gì để dời), "n_done", "n_steps", "n_phases", "kept", "moved", "section0_chars": độ dài §0 sau khi
    dời}. Giữ `keep` mục Xong mới nhất: `order` "first"/"last" nói mục mới nhất ở trên hay dưới; None thì theo ngày ghi
    ở dòng đầu mục, không đủ mục có ngày thì ném TrimOrderUnknown. Dời thêm bước đã gạch hay ✅ của "Việc tiếp theo" và mốc ngoài §0
    đã xong hết."""
    lines = text.split("\n")
    span = _section0_span(lines, _levels(lines, _fence_mask(lines)))
    empty = {"text": text, "part": "", "n_done": 0, "n_steps": 0, "n_phases": 0, "kept": [], "moved": [],
             "section0_chars": len(section0(text)[1]) if section0(text) else 0}
    if not span:
        return empty
    pointer = f"- **{TRIM_POINTER_LABEL}:** ở `{HISTORY_REL}` (chuyển bằng `state.py trim`)."
    sec = _trim_section0(lines[span[0] + 1:span[1]], keep, order, pointer)
    lines = lines[:span[0] + 1] + sec["lines"] + lines[span[1]:]
    mask = _fence_mask(lines)
    levels = _levels(lines, mask)
    phases = _done_phases(lines, levels, _section0_span(lines, levels))
    moved_phases = []
    for s, e in phases:
        while e > s + 1 and not lines[e - 1].strip():
            e -= 1
        shift = 4 - levels[s]
        moved_phases += [("#" * min(6, levels[i] + shift) + lines[i].lstrip("#")) if levels[i] else lines[i]
                         for i in range(s, e)] + [""]
    drop = {i for s, e in phases for i in range(s, e)}
    lines = [x for i, x in enumerate(lines) if i not in drop]
    if not sec["n_done"] and not sec["n_steps"] and not phases:
        return {**empty, "kept": sec["kept"]}
    part = [f"## Đợt {when}".rstrip(), ""]
    if sec["done"]:
        part += [f"### Từ §0 của `{plan_rel}`: Xong", ""] + sec["done"] + [""]
    if sec["steps"]:
        part += [f"### Từ §0 của `{plan_rel}`: bước đã xong của Việc tiếp theo", ""] + sec["steps"] + [""]
    if moved_phases:
        part += [f"### Từ `{plan_rel}`: mốc đã xong hết", ""] + moved_phases
    new_text = "\n".join(lines)
    if _plan_checks(new_text) != _plan_checks(text):
        raise TrimUnsafe(f"mốc kiểm tra sẽ đổi từ «{clip(_plan_checks(text) or '', 80)}» thành "
                         f"«{clip(_plan_checks(new_text) or '', 80)}»")
    found = section0(new_text)
    return {"text": new_text, "part": "\n".join(part).rstrip() + "\n", "n_done": sec["n_done"],
            "n_steps": sec["n_steps"], "n_phases": len(phases), "kept": sec["kept"],
            "moved": sec["moved"] + [x for x in moved_phases if x.startswith("#")],
            "section0_chars": len(found[1]) if found else 0}


def trim_target(root: Path):
    """(đường dẫn, nội dung) của PLAN.md hay .agent/PLAN.md có §0, file mới sửa hơn; None nếu không có. Không trim
    HANDOFF.md: nó là bản chép tạm của §0."""
    best = None
    for rel in ("PLAN.md", ".agent/PLAN.md"):
        path = Path(root) / rel
        try:
            text = path.read_text(encoding="utf-8")
            mtime = path.stat().st_mtime
        except (OSError, UnicodeDecodeError):
            continue
        if section0(text) and (best is None or mtime > best[0]):
            best = (mtime, path, text)
    return best[1:] if best else None


def trim_advice(text: str):
    """Lời khuyên ngắn khi §0 dài hơn SECTION0_LONG_CHARS, hay None. Chạy thử trim_plan để chỉ khuyên trim khi trim
    rút được §0; trim không giúp được thì khuyên rút gọn tay. Trả (lời khuyên, trim có giúp không)."""
    found = section0(text)
    before = len(found[1]) if found else 0
    if before <= SECTION0_LONG_CHARS:
        return None
    cmd = f"`python3 {TRIM_CMD}`"
    try:
        after = trim_plan(text)["section0_chars"]
    except TrimOrderUnknown:
        return (f"§0 dài {before // 1000}K ký tự, agent đọc lại mỗi phiên: chạy {cmd} với `--newest-first` hay "
                "`--newest-last` (mục Xong không ghi ngày nên không đoán được mục nào mới nhất)", True)
    except TrimUnsafe:
        return (f"§0 dài {before // 1000}K ký tự, agent đọc lại mỗi phiên; trim sẽ dời mất mốc kiểm tra: ghi mốc vào "
                f"dòng `- **Mốc kiểm tra:**` của §0 rồi chạy {cmd}", False)
    except Exception:  # noqa: BLE001 (lời khuyên là phần phụ, không được làm hỏng tóm tắt)
        return None
    if after >= before:
        return (f"§0 dài {before // 1000}K ký tự, agent đọc lại mỗi phiên, mà trim không dời được (lịch sử không nằm "
                f"dưới nhãn **Xong**): rút gọn tay, chuyển lịch sử sang `{HISTORY_REL}`", False)
    rest = "" if after <= SECTION0_LONG_CHARS else f", còn {after // 1000}K thì rút gọn tay phần còn lại"
    return (f"§0 dài {before // 1000}K ký tự, agent đọc lại mỗi phiên: chạy {cmd} để dời việc đã xong sang "
            f"`{HISTORY_REL}`{rest}", True)
