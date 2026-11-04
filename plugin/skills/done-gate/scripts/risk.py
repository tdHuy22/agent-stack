#!/usr/bin/env python3
"""Chấm mức rủi ro của thay đổi chưa commit, để quyết review sâu tới đâu.

  python3 risk.py [thư mục] [--base REF] [--new] [--writer opus|sonnet] [--json]

Chỉ đọc. In mức (thấp, vừa, cao), lý do, file nên đọc kỹ và cách review đề nghị: reviewer nào (model, effort) theo
mức rủi ro và model người viết, và có phải hỏi người dùng trước vì hạn mức hay diff lớn không.
Mức là gợi ý thô dựa trên đường dẫn và các dòng thêm vào; nó không thay review.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

LEVEL_NAMES = {"thap": "thấp", "vua": "vừa", "cao": "cao"}
KIND_NAMES = {"code": "code", "test": "test", "doc": "tài liệu", "instr": "chỉ dẫn cho agent"}
DOC_EXT = {".md", ".txt", ".rst", ".adoc"}
# HTML mặc định là code (trang của web app, template). Trang cho người đọc (luật chung: báo cáo, kế hoạch viết bằng
# .html) là tài liệu khi nằm trong .agent/ hay docs/, hoặc mang dấu của skill reader-page trong nội dung file.
PAGE_EXT = {".html", ".htm"}
READER_PAGE_RE = re.compile(r"<main\b[^>]*\bdata-loai=|\bdata-phan=[\"']tom-tat[\"']")
MAX_UNTRACKED_BYTES = 1_000_000
MAX_TEXT = 200_000

# File chỉ dẫn cho agent: đổi nó là đổi hành vi của agent, dù đuôi là .md.
INSTR_RE = re.compile(r"(^|/)(skill|claude|agents)(\.global)?\.md$|(^|/)agents/[^/]+\.md$")
DEP_FILES_RE = re.compile(r"(^|/)(requirements[^/]*\.txt|pyproject\.toml|setup\.cfg|package(-lock)?\.json|yarn\.lock|"
                          r"pnpm-lock\.yaml|poetry\.lock|uv\.lock|cargo\.(toml|lock)|go\.(mod|sum)|gemfile(\.lock)?)$")
# Luật theo đường dẫn: (mẫu, điểm, lý do). Mỗi luật chỉ cộng điểm một lần dù khớp nhiều file.
PATH_RULES = [
    (re.compile(r"(^|[/_.-])(auth\w*|oauth|login|passw\w*|credentials?|secrets?|tokens?|crypto\w*|encrypt\w*|"
                r"decrypt\w*|cipher|payments?|billing|permissions?|acl|sandbox)([/_.-]|$)"),
     3, "đụng phần nhạy cảm (xác thực, secret, mã hóa, thanh toán, quyền, sandbox)"),
    (re.compile(r"(^|/)(migrations?|schema)([/._-]|$)|\.sql$"), 3, "đổi schema hoặc migration dữ liệu"),
    (re.compile(r"(^|/)hooks?/"), 2, "hook chạy tự động trong mọi phiên"),
    (re.compile(r"(^|/)(install|setup|bootstrap|deploy)[^/]*\.(sh|py|ps1)$|(^|/)\.github/workflows/|"
                r"(^|/)dockerfile|(^|/)makefile$"), 2, "cài đặt, triển khai hoặc CI"),
    (DEP_FILES_RE, 2, "đổi phụ thuộc"),
    (re.compile(r"(^|/)\.env|(^|/)settings(\.local)?\.json$|\.(pem|key)$"), 2, "cấu hình hoặc khóa"),
    (INSTR_RE, 1, "chỉ dẫn cho agent (đổi hành vi của agent)"),
]

# Luật theo nội dung dòng thêm vào: (mẫu, điểm, lý do, áp cho loại file nào).
SECRET_RULES = [
    re.compile(r"""(?i)\b(api[_-]?key|secret|password|passwd|token|private[_-]?key)\b\s*[:=]\s*['"][^'"\s]{8,}['"]"""),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"),
]
CODE_RULES = [
    (re.compile(r"shell\s*=\s*True|\bos\.system\(|(?<![\w.])eval\(|(?<![\w.])exec\(|pickle\.loads?\(|"
                r"yaml\.load\((?![^)]*Loader=yaml\.SafeLoader)"),
     2, "chạy lệnh qua shell hoặc mã động (os.system, eval, exec, pickle)"),
    (re.compile(r"shutil\.rmtree|os\.remove\(|os\.unlink\(|\.unlink\(|\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*f|"
                r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*[rR]|git\s+(reset\s+--hard|clean\s+-[a-z]*f|push\s+(-f|--force))"),
     2, "xóa file hoặc thao tác git không đảo ngược"),
    (re.compile(r"(curl|wget)[^|\n]*\|\s*(ba|z)?sh\b"), 3, "tải mã từ mạng rồi chạy luôn"),
    (re.compile(r"""(?i)execute\(\s*f["']|["']\s*(select|insert|update|delete)\b[^"'\n]*["']\s*(\+|%)"""),
     3, "SQL ghép chuỗi"),
]
# Lý do thuộc phần bảo mật (xác thực, mã hóa, secret, chạy lệnh, SQL): mức cao kèm một trong số này thì review kép.
SECURITY_REASONS = {PATH_RULES[0][2], "có thể lộ secret trong dòng thêm vào", CODE_RULES[0][2], CODE_RULES[2][2],
                    CODE_RULES[3][2]}
# Ranh giới tin cậy tính là đụng bảo mật (done-gate bước 5: xác thực, mã hóa, input, chạy lệnh, dữ liệu nhạy cảm).
# "Gọi ra ngoài" và "thêm dependency" không kéo review kép, để tiết kiệm hạn mức.
SECURITY_BOUNDARIES = {"input từ bên ngoài", "xác thực, phân quyền", "dữ liệu nhạy cảm",
                       "chạy mã, lệnh hay đường dẫn từ input"}

# Nới test, hay gặp ở vòng sửa cho test đạt: assert chặt (so bằng, so đúng đối tượng, đòi lỗi) đổi thành dạng lỏng
# hơn, bớt assert, thêm skip. Chỉ xét file test, bỏ dòng chú thích (comment một assert là bỏ nó).
COMMENT_LINE_RE = re.compile(r"^\s*(#(?!\[)|//|/\*|\*|--)")
ASSERT_RE = re.compile(r"\bassert\w*\s*\(|\bassert\s|\bassert_\w*!|\bexpect\s*\(|\bpytest\.raises\b|"
                       r"\bassert\.\w+\s*\(")
STRICT_ASSERT_RE = re.compile(
    r"\bassert(Equals?|Is|IsNone|Raises|RaisesRegex|Warns|WarnsRegex|AlmostEqual|CountEqual|DictEqual|ListEqual|"
    r"TupleEqual|SetEqual|SequenceEqual|MultiLineEqual|_called_once_with|_called_with)\s*\(|"
    r"\bassert\s[^\n]*(==|\bis\s+(?!not\b))|\bassert_eq!|\bpytest\.raises\b|"
    r"\.to(Be|Equal|StrictEqual|Throw|BeNull|HaveLength)\s*\(|"
    r"\bassert\.(equal|strictEqual|deepEqual|deepStrictEqual|throws|rejects)\s*\(")
# Neo ở đầu dòng: decorator hay lời gọi skip đứng thành câu lệnh, không phải chuỗi mẫu nằm trong dữ liệu của test.
SKIP_RE = re.compile(r"^\s*(@(unittest\.)?skip(If|Unless)?\b|@pytest\.mark\.(skip|skipif|xfail)\b|(self\.)?skipTest\(|"
                     r"pytest\.(skip|xfail)\(|(it|test|describe)\.(skip|todo)\(|x(it|test|describe)\(|"
                     r"t\.Skip(Now|f)?\(|#\[ignore\])")

# Cấu hình review (bạn chốt 04/11/2026): reviewer khác model người viết, để giảm điểm mù chung của một model.
# Fable mạnh hơn Opus nên xếp như Opus viết; Haiku yếu hơn Sonnet nên xếp như Sonnet viết (reviewer là Opus).
WRITER_SIDE = {"opus": "opus", "fable": "opus", "sonnet": "sonnet", "haiku": "sonnet"}
WRITER_NAMES = {"opus": "Opus", "sonnet": "Sonnet"}
# Phần nhạy cảm cần Opus effort xhigh khi review mức cao (bảng router: mã hóa, token, thanh toán, sandbox).
CRYPTO_RE = re.compile(r"(^|[/_.-])(crypto\w*|encrypt\w*|decrypt\w*|cipher|signing|signatures?|tokens?|jwt|"
                       r"payments?|billing|sandbox)([/_.-]|$)")
# Trước review kép hay review có Opus: hỏi người dùng khi hạn mức tuần, 5 giờ chạm ngưỡng, hay diff mức cao quá lớn.
ASK_WEEK, ASK_FIVE_HOUR, ASK_CODE_LINES = 80, 90, 800


def assert_lines(text: str) -> list:
    """[(dòng, có chặt không)] cho các dòng assert không nằm trong chú thích."""
    return [(line, bool(STRICT_ASSERT_RE.search(line))) for line in text.splitlines()
            if not COMMENT_LINE_RE.match(line) and ASSERT_RE.search(line)]


def has_skip(text: str) -> bool:
    return any(SKIP_RE.search(line) for line in text.splitlines() if not COMMENT_LINE_RE.match(line))


# Ranh giới tin cậy: (tên, mẫu đường dẫn, mẫu nội dung dòng thêm vào ở file code). Đụng ranh giới thì ít nhất mức vừa,
# và done-gate cần một mục trong .agent/threat-model.md (skill threat-model) để reviewer kiểm từng chốt chặn.
BOUNDARY_RULES = [
    ("input từ bên ngoài", None,
     re.compile(r"@(app|router|bp|blueprint|api)\.(get|post|put|patch|delete|route|websocket)\(|"
                r"\brequest\.(args|form|json|files|get_json|query_params|body|cookies)\b|"
                r"\b(app|router)\.(get|post|put|patch|delete|all)\(\s*['\"]/|\b(FastAPI|APIRouter|Flask)\(|"
                r"\bexpress\(\)|\bmulter\(|\bUploadFile\b|BaseHTTPRequestHandler|\bcreateServer\(|"
                r"\bsocket\.(bind|listen)\(")),
    ("xác thực, phân quyền", re.compile(r"(^|[/_.-])(auth\w*|oauth|login|passw\w*|permissions?|acl)([/_.-]|$)"),
     re.compile(r"\b(login|logout|authenticate|authorize|login_required|permission_required|is_authenticated|"
                r"jwt|oauth2?|set_cookie|verify_password|check_password|bcrypt|passlib|getServerSession)\b|"
                r"\bsession\[")),
    ("gọi ra ngoài", None,
     re.compile(r"\brequests\.(get|post|put|patch|delete|request|Session)\b|\bhttpx\.|\burllib\.request\b|"
                r"\burlopen\(|\baiohttp\.|(?<![\w.])fetch\(|\baxios\.|\bsmtplib\b|\bboto3\.|"
                r"\bsocket\.(connect|create_connection)\(")),
    ("dữ liệu nhạy cảm", re.compile(r"(^|[/_.-])(payments?|billing|secrets?|credentials?|pii)([/_.-]|$)"),
     re.compile(r"(?i)\b(ssn|credit_?card|card_?number|cvv|iban|cccd|date_of_birth|phone_?number|so_dien_thoai)\b")),
    ("thêm dependency", DEP_FILES_RE, None),
    ("chạy mã, lệnh hay đường dẫn từ input", None,
     re.compile(r"\bsubprocess\.|\bos\.(system|popen|exec\w*)\(|(?<![\w.])(eval|exec)\(|\bpickle\.loads?\(|"
                r"\byaml\.load\(|\bchild_process\b|\bsend_file\(|\bsend_from_directory\(|\.extractall\(")),
]
THREAT_MODEL_REL = ".agent/threat-model.md"
# Chỉ soi nội dung ranh giới trong file mã nguồn: file dữ liệu (JSON, YAML) hay liệt kê từ khóa như "login" mà không chạy gì.
SOURCE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java", ".kt", ".php", ".rs", ".c",
              ".cc", ".cpp", ".h", ".hpp", ".cs", ".swift", ".scala", ".sh", ".bash", ".zsh", ".ps1", ".lua", ".pl"}


def boundaries(changes: list, reviewed=frozenset()) -> list:
    """[(tên ranh giới, [đường dẫn])]: file đổi khớp đường dẫn, hay file code có dòng thêm vào khớp nội dung.
    File trong `reviewed` (đã qua chốt việc) chỉ xét nội dung dòng mới, không xét đường dẫn."""
    out = []
    for name, path_re, text_re in BOUNDARY_RULES:
        paths = [c["path"] for c in changes
                 if (path_re and c["path"] not in reviewed and change_kind(c) != "test"
                     and path_re.search(c["path"].lower()))
                 or (text_re and change_kind(c) == "code" and Path(c["path"]).suffix.lower() in SOURCE_EXT
                     and text_re.search(c.get("text") or ""))]
        if paths:
            out.append((name, paths))
    return out


class NotARepo(Exception):
    pass


class GitError(Exception):
    pass


def kind(path: str, page: bool = False) -> str:
    """Phân loại file: code, test, doc hay instr (chỉ dẫn cho agent). page: file HTML mang dấu trang cho người đọc."""
    p = path.lower()
    name = p.rsplit("/", 1)[-1]
    if re.search(r"(^|/)(tests?|spec|__tests__)/", p) or re.match(r"(test_.*|.*_test|.*\.(test|spec))\.\w+$", name):
        return "test"
    if INSTR_RE.search(p):
        return "instr"
    if Path(name).suffix in DOC_EXT or re.search(r"(^|/)docs?/", p):
        return "doc"
    if Path(name).suffix in PAGE_EXT and (page or re.search(r"(^|/)\.agent/", p)):
        return "doc"
    return "code"


# Tài liệu mà sửa sau bước kiểm chứng không làm cũ biên nhận: hẹp hơn kind() == "doc", vì nhắc thừa một lần còn hơn
# bỏ sót. Không tính .txt (requirements.txt), file code trong docs/, và file trong thư mục mà test hay build hay đọc.
RECEIPT_DOC_EXT = {".md", ".rst", ".adoc"} | PAGE_EXT
FIXTURE_DIR_RE = re.compile(r"(^|/)(tests?|spec|__tests__|samples?|fixtures?|testdata|examples?|references?|"
                            r"templates?)/")


def doc_only(path: str, top: Path = None) -> bool:
    """File chỉ là tài liệu: sửa nó sau bước kiểm chứng không làm cũ biên nhận (receipt.py, hook Stop). `top`: gốc
    repo, để đọc dấu trang cho người đọc của file HTML nằm ngoài .agent/, docs/ (như HUONG-DAN.html ở gốc repo)."""
    if Path(path).suffix.lower() not in RECEIPT_DOC_EXT or FIXTURE_DIR_RE.search(path.lower()):
        return False
    return kind(path, bool(top) and reader_page(Path(top) / path)) == "doc"


def doc_filter(root):
    """doc_only cho đường dẫn tính từ gốc repo chứa `root` (khóa của agentstack.tree_blobs)."""
    out = git(Path(root), "rev-parse", "--show-toplevel")
    top = Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
    return lambda path: doc_only(path, top)


def change_kind(c: dict) -> str:
    """Loại của một thay đổi: dấu trang cho người đọc lấy từ cờ page (collect đọc cả file) hay từ dòng thêm vào."""
    page = Path(c["path"]).suffix.lower() in PAGE_EXT and (c.get("page") or READER_PAGE_RE.search(c.get("text") or ""))
    return kind(c["path"], bool(page))


def assess(changes: list, reviewed=frozenset(), writer=None, rereview=False, limits=None,
           writer_guessed=False) -> dict:
    """Chấm điểm từ danh sách {path, added, deleted, text}. added là None với file nhị phân. File trong `reviewed`
    đã qua chốt việc, `text` chỉ còn dòng mới: bỏ luật theo đường dẫn cho chúng (hook Stop dùng).
    writer, rereview, limits: để chọn reviewer (xem review_plan)."""
    result = {"level": "thap", "score": 0, "files": len(changes), "added": 0, "deleted": 0,
              "by_kind": {k: 0 for k in KIND_NAMES}, "reasons": [], "hotspots": [], "empty": not changes}
    if not changes:
        result.update(review_plan("thap", writer, rereview=rereview, limits=limits))
        return result
    score, reasons, hot = 0, [], {}
    test_add = test_del = 0
    security = []  # lý do thuộc phần bảo mật, để mức cao giao cả hai reviewer

    def hit(points, reason, paths):
        nonlocal score
        if reason in SECURITY_REASONS:
            security.append(reason)
        score += points
        shown = ", ".join(paths[:3]) + (f" và {len(paths) - 3} file khác" if len(paths) > 3 else "")
        reasons.append(f"{reason}: {shown}" if shown else reason)
        for p in paths:
            hot.setdefault(p, [0, []])
            hot[p][0] += points
            hot[p][1].append(reason)

    for c in changes:
        k = change_kind(c)
        added, deleted = c.get("added") or 0, c.get("deleted") or 0
        result["added"] += added
        result["deleted"] += deleted
        result["by_kind"][k] += added + deleted
        if k == "test":
            test_add, test_del = test_add + added, test_del + deleted

    for pattern, points, reason in PATH_RULES:
        paths = [c["path"] for c in changes if c["path"] not in reviewed and pattern.search(c["path"].lower())]
        if paths:
            hit(points, reason, paths)
    secret_paths = [c["path"] for c in changes if any(r.search(c.get("text") or "") for r in SECRET_RULES)]
    if secret_paths:
        hit(4, "có thể lộ secret trong dòng thêm vào", secret_paths)
    for pattern, points, reason in CODE_RULES:
        paths = [c["path"] for c in changes if change_kind(c) == "code" and pattern.search(c.get("text") or "")]
        if paths:
            hit(points, reason, paths)

    code_lines = result["by_kind"]["code"]
    if code_lines > 400:
        score += 2
        reasons.append(f"thay đổi lớn ({code_lines} dòng code)")
    elif code_lines > 150:
        score += 1
        reasons.append(f"thay đổi khá lớn ({code_lines} dòng code)")
    if len(changes) > 15:
        score += 1
        reasons.append(f"nhiều file ({len(changes)})")
    if code_lines > 20 and result["by_kind"]["test"] == 0:
        score += 1
        reasons.append("đổi code mà không đổi test")
    if test_del > test_add and test_del >= 10:
        score += 2
        reasons.append(f"bớt test (+{test_add}/−{test_del} dòng test)")
    weakening(changes, hit)
    binary =[c["path"] for c in changes if c.get("added") is None]
    if binary:
        reasons.append("có file nhị phân, không đọc được nội dung: " + ", ".join(binary[:3]))

    level = "cao" if score >= 4 else "vua" if score >= 2 else "thap"
    crossed = boundaries(changes, reviewed)
    if crossed and level == "thap":
        level = "vua"
        reasons.append("đụng ranh giới tin cậy: " + ", ".join(name for name, _ in crossed))
    result.update(boundaries=[{"kind": name, "paths": paths} for name, paths in crossed],
                  threat_model_updated=any(c["path"] == THREAT_MODEL_REL or c["path"].endswith("/" + THREAT_MODEL_REL)
                                           for c in changes))
    crypto = [c["path"] for c in changes
              if c["path"] not in reviewed and change_kind(c) != "test" and CRYPTO_RE.search(c["path"].lower())]
    secure = bool(security or crypto or any(name in SECURITY_BOUNDARIES for name, _ in crossed))
    result.update(review_plan(level, writer, security=secure, crypto=bool(crypto), rereview=rereview,
                              code_lines=code_lines, limits=limits, writer_guessed=writer_guessed))
    result.update(level=level, score=score, reasons=reasons,
                  hotspots=[(p, v[1]) for p, v in sorted(hot.items(), key=lambda kv: (-kv[1][0], kv[0]))])
    return result


def weakening(changes: list, hit) -> None:
    """Luật nới test. Đếm gộp mọi file test (đổi tên file test không bị tính là bớt assert), nhưng chỉ ghi tên file
    có assert bị bớt hay bị nới. `vanished`: assert đã qua chốt việc rồi biến mất khỏi dòng thêm vào (fresh_changes)."""
    totals = [0, 0, 0, 0]  # thêm, thêm chặt, bớt, bớt chặt
    loosened, fewer, skipped = [], [], []
    for c in changes:
        if change_kind(c) != "test":
            continue
        added = assert_lines(c.get("text") or "")
        gone = [strict for _, strict in assert_lines(c.get("removed") or "")] + list(c.get("vanished") or [])
        counts = (len(added), sum(s for _, s in added), len(gone), sum(1 for s in gone if s))
        totals = [a + b for a, b in zip(totals, counts)]
        if counts[3] > counts[1]:
            loosened.append(c["path"])
        elif counts[2] > counts[0]:
            fewer.append(c["path"])
        if has_skip(c.get("text") or ""):
            skipped.append(c["path"])
    add, add_strict, rem, rem_strict = totals
    if rem_strict > add_strict and add >= rem:
        hit(2, "nới assert (assert chặt như so bằng đổi thành dạng lỏng hơn)", loosened)
    elif rem > add:
        hit(1, f"bớt assert (+{add}/−{rem} dòng assert)", loosened + fewer)
    if skipped:
        hit(2, "thêm skip hay xfail trong test", skipped)


def writer_side(writer) -> str:
    """Họ model người viết ("opus", "sonnet") từ tên ngắn hay id model ("claude-opus-5-5"); chưa rõ thì chuỗi rỗng."""
    text = str(writer or "").lower()
    return next((side for name, side in WRITER_SIDE.items() if name in text), "")


def reviewers_for(level: str, side: str, security=False, crypto=False, rereview=False) -> list:
    """[(model, effort)] cho một mức rủi ro và họ model người viết, theo cấu hình bạn chốt 04/11/2026:
    vừa: Opus viết → sonnet·high, Sonnet viết → opus·medium; cao: Opus viết → opus·high và sonnet·high, Sonnet viết →
    opus·high; cao và đụng bảo mật → cả hai; mã hóa, token, thanh toán, sandbox → opus·xhigh. Review lại phần sửa
    (`--new`): một sonnet·high bất kể ai viết, lên opus khi chính phần sửa ở mức cao."""
    if level == "thap":
        return []
    opus = ("opus", "xhigh" if crypto else "high")
    if rereview:
        return [opus] if level == "cao" else [("sonnet", "high")]
    if level == "vua":
        return [("sonnet", "high")] if side == "opus" else [("opus", "medium")]
    return [opus, ("sonnet", "high")] if side == "opus" or security else [opus]


def window_pct(limits, window: str, now: float):
    """Phần trăm đã dùng của một cửa sổ hạn mức trong state/limits.json, hay None (không có, hay đã qua giờ reset:
    số cũ hơn lúc reset không còn đúng). Trước giờ reset, số cũ là cận dưới nên vẫn dùng được để so ngưỡng."""
    windows = limits.get("rate_limits") if isinstance(limits, dict) else None
    info = windows.get(window) if isinstance(windows, dict) else None
    if not isinstance(info, dict):
        return None
    pct, resets = info.get("used_percentage"), info.get("resets_at")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        return None
    if isinstance(resets, (int, float)) and resets < now:
        return None
    return float(pct)


def budget_asks(reviewers: list, level: str, code_lines: int, limits, now=None) -> list:
    """Lý do phải hỏi người dùng trước khi giao review kép hay review có Opus (đề xuất b, 04/11/2026)."""
    import time
    if len(reviewers) < 2 and not any(model == "opus" for model, _ in reviewers):
        return []
    now = time.time() if now is None else now
    asks = []
    week, five = window_pct(limits, "seven_day", now), window_pct(limits, "five_hour", now)
    if week is not None and week >= ASK_WEEK:
        asks.append(f"hạn mức tuần đã dùng {week:.0f}% (từ {ASK_WEEK}%)")
    if five is not None and five >= ASK_FIVE_HOUR:
        asks.append(f"hạn mức 5 giờ đã dùng {five:.0f}% (từ {ASK_FIVE_HOUR}%)")
    if level == "cao" and code_lines > ASK_CODE_LINES:
        asks.append(f"diff lớn ({code_lines} dòng code, trên {ASK_CODE_LINES})")
    return asks


def describe(reviewers: list) -> str:
    names = [f"{model}·{effort}" for model, effort in reviewers]
    if len(names) == 1:
        return f"giao `agent-stack:reviewer` trong context mới, model {reviewers[0][0]}, effort {reviewers[0][1]}"
    return (f"giao song song {len(names)} `agent-stack:reviewer` trong context mới, cùng một prompt: "
            f"{' và '.join(names)}; gộp lỗi trùng rồi ghi lỗi nào do reviewer nào tìm bằng `review_log.py add`")


def review_plan(level: str, writer=None, security=False, crypto=False, rereview=False, code_lines=0,
                limits=None, writer_guessed=False) -> dict:
    """{review: câu đề nghị, reviewers: [{model, effort}] (rỗng khi chưa rõ người viết hay mức thấp), ask: [lý do hỏi
    người dùng trước]}. Chưa rõ người viết thì câu đề nghị nêu cả hai trường hợp. writer_guessed: người viết suy từ
    state/limits.json (có thể của phiên khác), nên câu đề nghị nói rõ."""
    if level == "thap":
        return {"review": "tự rà `git diff` một lượt, không cần subagent; người dùng không cần đọc diff.",
                "reviewers": [], "ask": []}
    side = writer_side(writer)
    tail = ("người dùng nên đọc kỹ các file nên đọc kỹ trước khi commit." if level == "cao" and not rereview
            else "người dùng đọc lướt các file nên đọc kỹ.")
    if level == "cao" and security and not rereview:
        tail = "chạy differential-review trước nếu có (bước 5); " + tail
    sides = [side] if side else ["opus", "sonnet"]
    plans = {s: reviewers_for(level, s, security, crypto, rereview) for s in sides}
    if side:
        reviewers = plans[side]
        source = ", suy từ state/limits.json, có thể của phiên khác: truyền --writer cho chắc" if writer_guessed else ""
        text = f"{describe(reviewers)} (người viết: {WRITER_NAMES[side]}{source}); {tail}"
        asks = budget_asks(reviewers, level, code_lines, limits)
    else:
        if plans["opus"] == plans["sonnet"]:
            text = f"{describe(plans['opus'])}; {tail}"
        else:
            text = (f"Opus viết: {describe(plans['opus'])}. Sonnet viết: {describe(plans['sonnet'])}. "
                    f"Truyền --writer opus|sonnet để chọn sẵn; {tail}")
        reviewers = plans["opus"] if plans["opus"] == plans["sonnet"] else []
        asks = budget_asks(plans["opus"] + plans["sonnet"], level, code_lines, limits)
    return {"review": text, "reviewers": [{"model": m, "effort": e} for m, e in reviewers], "ask": asks}


def review_hint(level: str, writer=None) -> str:
    """Câu đề nghị review cho một mức (giữ cho nơi gọi cũ)."""
    return review_plan(level, writer)["review"]


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # core.fsmonitor=false: repo lạ có thể đặt nó thành lệnh bất kỳ mà git diff, git status sẽ chạy (hook Stop gọi hàm này).
    return subprocess.run(["git", "--no-optional-locks", "-c", "core.quotePath=false", "-c", "core.fsmonitor=false",
                           "-C", str(root), *args],
                          capture_output=True, text=True, errors="replace")


def diff_lines(patch: str):
    """(dòng thêm vào, dòng bị xóa) theo file từ một patch -U0. Tiêu đề `--- a/…`, `+++ b/…` chỉ được hiểu là tiêu đề
    khi chưa vào hunk, để dòng nội dung bắt đầu bằng "--" hay "++" không bị nhầm. File bị xóa ghi theo đường dẫn cũ."""
    added, removed = {}, {}
    old = current = None
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            in_hunk, old, current = False, None, None
        elif not in_hunk and line.startswith("--- "):
            old = patch_path(line[4:])
        elif not in_hunk and line.startswith("+++ "):
            current = patch_path(line[4:]) or old
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and current is not None and line[:1] in ("+", "-"):
            (added if line[0] == "+" else removed).setdefault(current, []).append(line[1:])
    return ({k: "\n".join(v)[:MAX_TEXT] for k, v in added.items()},
            {k: "\n".join(v)[:MAX_TEXT] for k, v in removed.items()})


def patch_path(value: str):
    value = value.strip()
    if value == "/dev/null":
        return None
    return value[2:] if value[:2] in ("a/", "b/") else value


def checked(root: Path, *args: str) -> str:
    out = git(root, *args)
    if out.returncode != 0:
        raise GitError(f"git {' '.join(args[:2])} lỗi: {out.stderr.strip()[:300]}")
    return out.stdout


def collect(root, base: str = None) -> list:
    """Đọc thay đổi so với base (mặc định HEAD), kể cả file chưa được git theo dõi."""
    root = Path(root)
    if git(root, "rev-parse", "--is-inside-work-tree").returncode != 0:
        raise NotARepo(str(root))
    if base:
        if git(root, "rev-parse", "--verify", "-q", base + "^{commit}").returncode != 0:
            raise GitError(f"không tìm thấy ref {base}")
        ref = base
    elif git(root, "rev-parse", "--verify", "-q", "HEAD").returncode == 0:
        ref = "HEAD"
    else:
        # Repo chưa có commit: so cây làm việc với cây rỗng, gồm cả phần đã add lẫn phần sửa sau đó.
        ref = checked(root, "hash-object", "-t", "tree", "/dev/null").strip()
    # --no-ext-diff, --no-textconv: không chạy lệnh diff ngoài hay textconv do config đặt (repo lạ có thể đặt lệnh
    # bất kỳ; diff.external toàn cục như difftastic còn làm mất các dòng thêm vào cần chấm).
    numstat = checked(root, "diff", ref, "--numstat", "--no-renames", "--no-ext-diff", "--no-textconv", "-z")
    # Tiền tố a/, b/ đặt rõ: config diff.noprefix hay diff.mnemonicPrefix của người dùng làm sai đường dẫn.
    texts, removed = diff_lines(checked(root, "diff", ref, "-U0", "--no-color", "--no-renames", "--no-ext-diff",
                                        "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/"))
    # --full-name: đường dẫn tính từ gốc repo như của git diff, để dấu đã chấm khớp dù chạy từ thư mục con.
    top = Path(checked(root, "rev-parse", "--show-toplevel").strip())
    changes = []
    for record in numstat.split("\0"):
        parts = record.split("\t", 2)
        if len(parts) != 3:
            continue
        a, d, path = parts
        changes.append({"path": path, "added": None if a == "-" else int(a), "deleted": 0 if d == "-" else int(d),
                         "text": texts.get(path, ""), "removed": removed.get(path, ""),
                         "page": reader_page(top / path), "content": test_content(top / path)})
    for path in git(root, "ls-files", "--others", "--exclude-standard", "--full-name", "-z").stdout.split("\0"):
        if not path:
            continue
        try:
            size = (top / path).stat().st_size
            data = (top / path).read_bytes() if size <= MAX_UNTRACKED_BYTES else b""
        except OSError:
            continue
        if size > MAX_UNTRACKED_BYTES or b"\0" in data[:8192]:
            changes.append({"path": path, "added": None, "deleted": 0, "text": ""})
            continue
        text = data.decode("utf-8", errors="replace")
        # dấu trang tính trên cả file: fresh_changes cắt text còn dòng mới, dấu ở dòng cũ sẽ mất
        changes.append({"path": path, "added": len(text.splitlines()), "deleted": 0, "text": text[:MAX_TEXT],
                        "page": Path(path).suffix.lower() in PAGE_EXT and bool(READER_PAGE_RE.search(text)),
                        "content": text if kind(path) == "test" else None})
    return sorted(changes, key=lambda c: c["path"])


def test_content(path: Path):
    """Nội dung hiện tại của file test (để biết assert đã qua chốt việc còn trong file không, kể cả sau commit, khi nó
    không còn là dòng thêm vào); None với file khác, file quá lớn hay đã bị xóa."""
    if kind(path.as_posix()) != "test":
        return None
    try:
        if path.stat().st_size > MAX_UNTRACKED_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "" if not path.exists() else None


def reader_page(path: Path) -> bool:
    """File HTML đã theo dõi mang dấu trang cho người đọc: diff chỉ có dòng thêm vào, dấu thường nằm ở phần không đổi."""
    if path.suffix.lower() not in PAGE_EXT:
        return False
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            return bool(READER_PAGE_RE.search(f.read(MAX_UNTRACKED_BYTES)))
    except OSError:
        return False


def render(r: dict, base: str = "HEAD") -> str:
    if r["empty"]:
        return f"Không có thay đổi nào so với {base}."
    sizes = ", ".join(f"{KIND_NAMES[k]} {v}" for k, v in r["by_kind"].items() if v)
    lines = [f"Mức rủi ro: {LEVEL_NAMES[r['level']]} (điểm {r['score']}) · {r['files']} file, "
             f"+{r['added']}/−{r['deleted']} dòng ({sizes or 'không đếm được dòng'})"]
    if r["reasons"]:
        lines.append("Lý do:")
        lines += [f"- {x}" for x in r["reasons"]]
    else:
        lines.append("Lý do: không thấy dấu hiệu rủi ro nào theo đường dẫn hay nội dung.")
    if r["hotspots"]:
        lines.append("File nên đọc kỹ:")
        lines += [f"- {p}: {'; '.join(why)}" for p, why in r["hotspots"][:8]]
    if r.get("boundaries"):
        lines.append("Ranh giới tin cậy bị đụng:")
        lines += [f"- {b['kind']}: {', '.join(b['paths'][:3])}" + (f" và {len(b['paths']) - 3} file khác"
                                                                    if len(b["paths"]) > 3 else "")
                  for b in r["boundaries"]]
        lines.append(f"Threat model: {'có mục mới trong' if r.get('threat_model_updated') else 'chưa có mục mới trong'} "
                     f"`{THREAT_MODEL_REL}`" + ("" if r.get("threat_model_updated") else
                                                "; nếu chưa có mục cho việc này, chạy skill threat-model trước bước review")
                     + ", rồi đưa các mục cho reviewer kiểm từng chốt chặn.")
    lines.append(f"Review đề nghị: {r['review']}")
    if r.get("ask"):
        lines.append("Hỏi người dùng trước khi giao review này: " + "; ".join(r["ask"])
                     + ". Cho họ chọn chỉ một reviewer sonnet·high (rẻ hơn), trừ khi họ đã chọn cho việc này.")
    return "\n".join(lines)


def fresh_changes(changes, seen: dict, removed_seen: dict = None, asserts_seen: dict = None):
    """Bỏ các dòng đã qua lần chấm trước (dấu băm trong `seen`, theo file). File đã có dấu chỉ giữ dòng mới và
    nằm trong tập trả về thứ hai, để `assess` không tính lại luật theo đường dẫn; file chưa có dấu giữ nguyên.
    `removed_seen`: dấu dòng bị xóa lúc chấm trước; dấu cũ không có mục này thì coi mọi dòng bị xóa là đã chấm.
    `asserts_seen`: assert của file test lúc chấm trước; assert không còn trong file (`content`, thiếu thì dòng thêm
    vào) và không nằm trong dòng bị xóa (đã đếm ở đó) thì vào `vanished` (có chặt không), để `assess` thấy assert đã
    qua chốt việc bị sửa lỏng hay bị xóa."""
    picked, reviewed = [], set()
    for c in changes:
        known = seen.get(c["path"])
        if isinstance(known, list):
            known = set(known)
            text = c.get("text") or ""
            fresh = [line for line in text.splitlines() if line.strip() and line_hashes(line)[0] not in known]
            removed = []
            if isinstance(removed_seen, dict):
                gone = set(removed_seen.get(c["path"]) or [])
                removed = [line for line in (c.get("removed") or "").splitlines()
                           if line.strip() and line_hashes(line)[0] not in gone]
            # So với cả file khi có (dòng đã commit không còn là dòng thêm vào); file quá lớn thì không xét.
            content = c.get("content", text)
            now = set(line_hashes(content)) | set(line_hashes("\n".join(removed))) if content is not None else None
            vanished = [] if now is None else [bool(p[1]) for p in (asserts_seen or {}).get(c["path"]) or []
                                               if isinstance(p, list) and len(p) == 2 and p[0] not in now]
            if not fresh and not removed and not vanished:
                continue
            c = dict(c, text="\n".join(fresh), added=len(fresh), deleted=len(removed), removed="\n".join(removed),
                     vanished=vanished)
            reviewed.add(c["path"])
        picked.append(c)
    return picked, frozenset(reviewed)


def fresh_since_mark(changes, mark: dict):
    """fresh_changes theo dấu của lần chốt việc trước (dict của agentstack.done_gate_mark)."""
    return fresh_changes(changes, mark.get("files") or {}, mark.get("removed"), mark.get("asserts"))


def previous_mark(root) -> dict:
    """Dấu của lần chạy trước; thiếu thư viện agent-stack hay chưa chạy lần nào thì rỗng."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
        import agentstack
        return agentstack.done_gate_mark(agentstack.project_root(Path(root).resolve()))
    except Exception:  # noqa: BLE001
        return {}


def load_limits() -> dict:
    """state/limits.json (hạn mức, model của phiên ghi gần nhất); thiếu thư viện agent-stack hay file thì rỗng."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
        import agentstack
        data = agentstack.read_json(agentstack.state_dir() / "limits.json", {})
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chấm mức rủi ro của thay đổi chưa commit (chỉ đọc).")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--base", help="so với ref này thay vì HEAD, ví dụ main")
    ap.add_argument("--new", action="store_true",
                    help="chỉ chấm dòng thêm sau lần chạy trước, ví dụ phần sửa theo review")
    ap.add_argument("--writer", help="model của phiên viết code (opus, sonnet, haiku, fable hay id model), để chọn "
                                     "reviewer khác model; thiếu thì lấy từ state/limits.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    limits = load_limits()
    writer = args.writer or ((limits.get("model") or {}).get("id") if isinstance(limits.get("model"), dict) else None)
    guessed = bool(writer) and not args.writer
    try:
        changes = collect(args.root, args.base)
        options = {"writer": writer, "rereview": args.new, "limits": limits, "writer_guessed": guessed}
        result = (assess(*fresh_since_mark(changes, previous_mark(args.root)), **options) if args.new
                  else assess(changes, **options))
    except NotARepo:
        print(f"Không phải git repo: {args.root}. Script cần git để đọc thay đổi.")
        return 2
    except GitError as exc:
        print(f"Không chấm được: {exc}. Kiểm lại --base hoặc trạng thái repo.")
        return 2
    # Diff rỗng (thường do quên --base sau khi commit) thì không ghi dấu: dấu rỗng sẽ làm hook Stop tưởng đã chốt việc.
    if changes:
        mark_ran(args.root, changes, result["level"])
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(render(result, args.base or "HEAD"))
    return 0


def line_hashes(text: str) -> list:
    """Dấu băm ngắn của từng dòng thêm vào (bỏ khoảng trắng hai đầu), để biết dòng nào đã qua chốt việc."""
    import hashlib
    return sorted({hashlib.sha1(line.strip().encode("utf-8", "replace")).hexdigest()[:12]
                   for line in text.splitlines() if line.strip()})


def mark_ran(root, changes=(), level=None) -> None:
    """Ghi dấu "đã chốt việc" cho project, kèm mức vừa chấm và dấu băm các dòng thêm vào, dòng bị xóa và assert của
    file test lúc đó theo từng file, để hook Stop chỉ chấm phần mới ở lượt sau và biết lượt cần bằng chứng tới đâu.
    Thiếu thư viện agent-stack thì bỏ qua."""
    asserts = {}
    for c in changes:
        if change_kind(c) == "test":
            pairs = [[line_hashes(line)[0], strict] for line, strict in assert_lines(c.get("text") or "")]
            if pairs:
                asserts[c["path"]] = pairs
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
        import agentstack
        agentstack.mark_done_gate(
            Path(root).resolve(), {c["path"]: line_hashes(c.get("text") or "") for c in changes}, level=level,
            removed={c["path"]: line_hashes(c["removed"]) for c in changes if c.get("removed")}, asserts=asserts)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    sys.exit(main())
