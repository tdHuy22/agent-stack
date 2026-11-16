"""Spec theo lát (GĐ6, 16/11/2026): file spec của từng lát việc và sổ duyệt spec.

File spec: `.agent/spec/<slug>.txt` trong repo, mỗi dòng `Sn: Khi|Nếu|Trong khi … thì …` (dòng `#` là chú thích), số
thứ tự tăng dần. Chỉ ghi thêm ở cuối: sửa dòng có sẵn là nới (bánh cóc của done-gate, sổ khóa test). Test gắn với dòng
spec bằng dấu `spec:<slug>#Sn` viết trong chính test.

Sổ duyệt `state/spec-approvals.json` (ngoài repo, TM-128): chỉ hook ghi. `prompt_submit` ghi khi chính người dùng nhắn
"duyệt spec <mã>" (mã là đầu sha256 của đúng một file spec), `plan_exit` ghi khi người dùng duyệt kế hoạch có mục
`## Spec`. Bản duyệt là dấu băm từng dòng (số thứ tự + chữ), nên sửa chữ một dòng thì dòng đó hết được duyệt.
Chạy được trên Python 3.9 như mọi file trong plugin/lib.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path

import agentstack as A

SPEC_DIR = ".agent/spec"
APPROVALS = "spec-approvals.json"
MAX_SPEC_BYTES = 64_000
MAX_TEST_BYTES = 1_000_000
MAX_RECORDS = 500
SOURCES = ("duyet-spec", "ke-hoach")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LINE_RE = re.compile(r"^S(\d{1,4}):\s*(\S.*)$")
TEXT_RE = re.compile(r"^(khi|nếu|trong khi)\s.*?\sthì\s+\S", re.I)
TEST_PATH_RE = re.compile(r"(^|/)(tests?|spec|__tests__)/|(^|/)(test_[^/]*|[^/]*_test\.\w+|[^/]*\.(test|spec)\.\w+)$")
CODE_RE = re.compile(r"^[0-9a-f]{8,64}$")
# Tin đầu của phiên do phiên khác mở (brief do agent viết) và khối hệ thống chèn vào không phải lời người dùng (TM-128).
SPAWN_RE = re.compile(r"\(from the session that started this one\)", re.I)  # "Background (…)" và "Task (…)"
# Tin nhắc số dòng spec (S3) là góp ý hay điều kiện: không phải lời duyệt cả file.
LINE_ID_RE = re.compile(r"(?<![\w-])s\d{1,4}(?![\w-])")
MENTION_RE = re.compile(r"duyet\s+spec\s+[0-9a-f]{8,64}")
REMINDER_RE = re.compile(r"<system-reminder\b[^>]*>.*?(?:</system-reminder>|\Z)", re.S | re.I)
# Từ được đứng sau mã trong câu duyệt (đã bỏ dấu); từ khác thì câu có điều kiện, không tính là lời duyệt.
_TAIL_OK = {"nhe", "nha", "di", "luon", "nay", "do", "va", "and", "file", "ok", "giup", "gium", "cho", "toi",
            "minh", "spec", "ma", "nhe!", "a", "nhen", "nghen", "nhá", "nha!"}
_NEG_WORDS = {"không", "đừng", "chưa", "trừ", "chẳng", "khỏi", "not", "no", "don't", "never", "without", "except"}
_THEN_WORDS = {"roi", "then"}  # sau mã: "rồi lưu trang" là việc kế tiếp; "sau khi …", "xong thì …" là điều kiện


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text or "").split())


def line_hash(sid: str, text: str) -> str:
    """Dấu một dòng spec: số thứ tự và chữ (bỏ khoảng trắng thừa), 16 ký tự hex."""
    return hashlib.sha256(f"{sid}: {norm(text)}".encode()).hexdigest()[:16]


def parse(text: str) -> dict:
    """{"lines": [{"id", "n", "text", "lineno"}], "errors": [{"lineno", "msg"}]} của một file spec."""
    lines, errors, seen, last = [], [], set(), 0
    for lineno, raw in enumerate(unicodedata.normalize("NFC", text or "").splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = LINE_RE.match(s)
        if not m:
            errors.append({"lineno": lineno, "msg": "dòng không theo mẫu `Sn: Khi|Nếu|Trong khi … thì …`"})
            continue
        n, body = int(m.group(1)), m.group(2).strip()
        sid = f"S{n}"
        if any(unicodedata.category(ch) in ("Cc", "Cf") for ch in s):
            errors.append({"lineno": lineno, "msg": f"{sid} có ký tự ẩn hay điều khiển (đảo chiều, độ rộng 0): trang "
                                                    "có thể hiện chữ khác nội dung được duyệt (TM-131)"})
            seen.add(sid)
            last = max(last, n)
            continue
        if sid in seen:
            errors.append({"lineno": lineno, "msg": f"{sid} trùng số thứ tự với dòng trước"})
            continue
        if n < last:
            errors.append({"lineno": lineno, "msg": f"{sid} lùi số thứ tự (sau S{last}); dòng mới ghi thêm ở cuối"})
            seen.add(sid)
            continue
        seen.add(sid)
        last = n
        if not TEXT_RE.match(body):
            errors.append({"lineno": lineno, "msg": f"{sid} phải bắt đầu bằng Khi, Nếu hay Trong khi và có vế thì"})
            continue
        lines.append({"id": sid, "n": n, "text": body, "lineno": lineno})
    return {"lines": lines, "errors": errors}


def git_top(path):
    try:
        out = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def spec_files(top) -> list:
    """File spec của repo (bỏ symlink và file quá lớn), sắp theo tên."""
    folder = Path(top) / SPEC_DIR
    try:
        return sorted(p for p in folder.glob("*.txt")
                      if p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_SPEC_BYTES)
    except OSError:
        return []


def listed_files(top) -> list:
    """File git theo dõi và file mới chưa bị ignore (đường dẫn tương đối); không phải git repo thì rỗng."""
    try:
        out = subprocess.run(["git", "-C", str(top), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return sorted({p.decode("utf-8", "surrogateescape") for p in out.stdout.split(b"\0") if p})


def markers(top, slug: str) -> dict:
    """{"S1": [file test mang dấu `spec:<slug>#S1`]}: chỉ xét file có đường dẫn kiểu test, bỏ `.agent/`."""
    pattern = re.compile(r"(?<![\w-])spec:" + re.escape(slug) + r"#S(\d{1,4})(?!\d)")
    found: dict = {}
    for rel in listed_files(top):
        if rel.startswith(".agent/") or not TEST_PATH_RE.search(rel):
            continue
        path = Path(top) / rel
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TEST_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n in sorted({int(x) for x in pattern.findall(text)}):
            found.setdefault(f"S{n}", []).append(rel)
    return found


# --- sổ duyệt -----------------------------------------------------------------------------------------------------

def book_path() -> Path:
    return A.state_dir() / APPROVALS


def load_approvals() -> list:
    data = A.read_json(book_path(), [])
    return [r for r in data if isinstance(r, dict) and r.get("source") in SOURCES
            and isinstance(r.get("lines"), list)] if isinstance(data, list) else []


def add_record(rec: dict) -> None:
    rows = (load_approvals() + [rec])[-MAX_RECORDS:]
    path = book_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    A.write_json_atomic(path, rows)


def approved(top) -> dict:
    """{dấu dòng: {nguồn}} đã duyệt cho repo `top`."""
    here = str(Path(top).resolve())
    out: dict = {}
    for r in load_approvals():
        try:
            same = str(Path(str(r.get("top"))).resolve()) == here
        except (OSError, RuntimeError, ValueError):
            same = False
        if same:
            for h in r["lines"]:
                if isinstance(h, str):
                    out.setdefault(h, set()).add(r["source"])
    return out


def _record(top, source: str, path, sha, pairs) -> dict:
    return {"top": str(Path(top).resolve()), "path": path, "sha256": sha,
            "lines": [line_hash(sid, text) for sid, text in pairs], "source": source,
            "ts": datetime.now().astimezone().isoformat(timespec="seconds")}


def codes_in(text: str) -> list:
    """Mã trong lời duyệt của chính người dùng (đã bỏ phần dán, khối code, dòng trích), luật chặt (bạn chọn 16/11/2026):
    một câu (tách ở `.`, `!`, `?`, xuống dòng) chỉ gồm từ đồng ý + "duyệt spec" + mã + từ đệm, có thể nối "rồi"/"then" +
    việc kế tiếp; câu không là câu hỏi, không có từ phủ định; cả tin không nhắc số dòng `Sn` (nhắc dòng là góp ý hay điều
    kiện, không phải duyệt cả file). Không khớp thì không ghi, hook báo để người dùng nhắn lại."""
    codes = []
    text = unicodedata.normalize("NFC", text or "").lower()
    if LINE_ID_RE.search(text):
        return []
    for clause, end in re.findall(r"((?:[^.!?\n]|\.(?!\s|$))+)([.!?\n]?)", text):
        if "?" in end:
            continue
        words = [w.strip(A._CONSENT_STRIP + ",;") for w in clause.split()]
        words = [w for w in words if w]
        folded = [A.fold(w) for w in words]
        at = next((i for i in range(len(folded) - 1) if folded[i] == "duyet" and folded[i + 1] == "spec"), None)
        if at is None or any(w in _NEG_WORDS for w in words):  # so chữ còn dấu: "trữ", "dùng" không phải phủ định
            continue
        if any(w not in A._CONSENT_LEAD and w not in A._APPROVE_LEAD for w in words[:at]):
            continue
        tail = folded[at + 2:]
        cut = next((i for i, w in enumerate(tail) if w in _THEN_WORDS), len(tail))  # "rồi lưu trang": việc kế tiếp
        tail = tail[:cut]
        found = [w for w in tail if CODE_RE.match(w)]
        if found and all(CODE_RE.match(w) or w in _TAIL_OK for w in tail):
            codes += found
    return list(dict.fromkeys(codes))


def mentions_approval(text: str) -> bool:
    """Tin có cụm "duyệt spec <mã>" (dù có được tính là lời duyệt hay không), để hook báo khi không ghi."""
    return bool(MENTION_RE.search(A.fold(unicodedata.normalize("NFC", text or ""))))


def approve_code(top, code: str):
    """Ghi bản duyệt file spec có sha256 bắt đầu bằng `code` (8–64 ký tự hex); không khớp hay khớp nhiều file thì
    None (TM-131)."""
    if not CODE_RE.match(code or ""):
        return None
    hits = []
    for path in spec_files(top):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        sha = hashlib.sha256(data).hexdigest()
        if sha.startswith(code):
            hits.append((path, data, sha))
    if len(hits) != 1:
        return None
    path, data, sha = hits[0]
    pairs = [(x["id"], x["text"]) for x in parse(data.decode("utf-8", "replace"))["lines"]]
    rec = _record(top, "duyet-spec", path.relative_to(Path(top)).as_posix(), sha, pairs)
    add_record(rec)
    rec["texts"] = pairs  # chỉ để hook hiện cho người dùng, không ghi vào sổ
    return rec


def shown_line(sid: str, text: str, limit: int = 200) -> str:
    """Một dòng spec để hiện cho người dùng: bỏ ký tự điều khiển, cắt ngắn."""
    clean = "".join(ch for ch in f"{sid}: {text}" if unicodedata.category(ch) not in ("Cc", "Cf"))
    return clean if len(clean) <= limit else clean[:limit - 1] + "…"


def approval_text(prompt) -> str:
    """Phần chữ được đọc lời duyệt spec: rỗng khi tin là brief của phiên do phiên khác mở; bỏ khối hệ thống chèn vào,
    thẻ <ide_*>, phần dán, khối code, dòng trích (TM-128)."""
    if not isinstance(prompt, str) or SPAWN_RE.search(prompt):
        return ""
    return A.own_words(REMINDER_RE.sub(" ", A.routable_text(prompt)))


def approve_from_prompt(own_words: str, cwd) -> list:
    """[(mã, bản ghi hay None)] cho mỗi mã duyệt trong lời người dùng (đã lọc bằng approval_text); rỗng khi tin không
    có lời duyệt spec."""
    if "spec" not in (own_words or "").lower():
        return []
    codes = codes_in(own_words)
    top = git_top(cwd) if codes and cwd else None
    if top is None:
        return [(c, None) for c in codes]
    return [(c, approve_code(top, c)) for c in codes]


def plan_lines(body) -> list:
    """[(id, chữ)] từ thân mục `## Spec` của kế hoạch: gạch đầu dòng `- Sn: …`."""
    out = []
    for line in body or []:
        m = re.match(r"^\s*[-*•]\s+S(\d{1,4}):\s*(\S.*)$", line)
        if m:
            out.append((f"S{int(m.group(1))}", m.group(2).strip()))
    return out


def approve_plan(cwd, body):
    """Ghi các dòng `## Spec` của kế hoạch vừa được người dùng duyệt (nguồn "ke-hoach"); không có dòng nào thì None."""
    pairs = plan_lines(body)
    top = git_top(cwd) if pairs else None
    if top is None:
        return None
    rec = _record(top, "ke-hoach", None, None, pairs)
    add_record(rec)
    return rec
