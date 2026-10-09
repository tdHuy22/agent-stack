#!/usr/bin/env python3
"""Chấm mức rủi ro của thay đổi chưa commit, để quyết review sâu tới đâu.

  python3 risk.py [thư mục] [--base REF] [--json]

Chỉ đọc. In mức (thấp, vừa, cao), lý do, file nên đọc kỹ và cách review đề nghị.
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


# Ranh giới tin cậy: (tên, mẫu đường dẫn, mẫu nội dung dòng thêm vào ở file code). Đụng ranh giới thì ít nhất mức vừa,
# và chot-viec cần một mục trong .agent/threat-model.md (skill mo-hinh-de-doa) để reviewer kiểm từng chốt chặn.
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


def boundaries(changes: list) -> list:
    """[(tên ranh giới, [đường dẫn])]: file đổi khớp đường dẫn, hay file code có dòng thêm vào khớp nội dung."""
    out = []
    for name, path_re, text_re in BOUNDARY_RULES:
        paths = [c["path"] for c in changes
                 if (path_re and kind(c["path"]) != "test" and path_re.search(c["path"].lower()))
                 or (text_re and kind(c["path"]) == "code" and Path(c["path"]).suffix.lower() in SOURCE_EXT
                     and text_re.search(c.get("text") or ""))]
        if paths:
            out.append((name, paths))
    return out


class NotARepo(Exception):
    pass


class GitError(Exception):
    pass


def kind(path: str) -> str:
    """Phân loại file: code, test, doc hay instr (chỉ dẫn cho agent)."""
    p = path.lower()
    name = p.rsplit("/", 1)[-1]
    if re.search(r"(^|/)(tests?|spec|__tests__)/", p) or re.match(r"(test_.*|.*_test|.*\.(test|spec))\.\w+$", name):
        return "test"
    if INSTR_RE.search(p):
        return "instr"
    if Path(name).suffix in DOC_EXT or re.search(r"(^|/)docs?/", p):
        return "doc"
    return "code"


def assess(changes: list) -> dict:
    """Chấm điểm từ danh sách {path, added, deleted, text}. added là None với file nhị phân."""
    result = {"level": "thap", "score": 0, "files": len(changes), "added": 0, "deleted": 0,
              "by_kind": {k: 0 for k in KIND_NAMES}, "reasons": [], "hotspots": [], "empty": not changes}
    if not changes:
        result["review"] = review_hint("thap")
        return result
    score, reasons, hot = 0, [], {}
    test_add = test_del = 0

    def hit(points, reason, paths):
        nonlocal score
        score += points
        shown = ", ".join(paths[:3]) + (f" và {len(paths) - 3} file khác" if len(paths) > 3 else "")
        reasons.append(f"{reason}: {shown}" if shown else reason)
        for p in paths:
            hot.setdefault(p, [0, []])
            hot[p][0] += points
            hot[p][1].append(reason)

    for c in changes:
        k = kind(c["path"])
        added, deleted = c.get("added") or 0, c.get("deleted") or 0
        result["added"] += added
        result["deleted"] += deleted
        result["by_kind"][k] += added + deleted
        if k == "test":
            test_add, test_del = test_add + added, test_del + deleted

    for pattern, points, reason in PATH_RULES:
        paths = [c["path"] for c in changes if pattern.search(c["path"].lower())]
        if paths:
            hit(points, reason, paths)
    secret_paths = [c["path"] for c in changes if any(r.search(c.get("text") or "") for r in SECRET_RULES)]
    if secret_paths:
        hit(4, "có thể lộ secret trong dòng thêm vào", secret_paths)
    for pattern, points, reason in CODE_RULES:
        paths = [c["path"] for c in changes if kind(c["path"]) == "code" and pattern.search(c.get("text") or "")]
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
    binary = [c["path"] for c in changes if c.get("added") is None]
    if binary:
        reasons.append("có file nhị phân, không đọc được nội dung: " + ", ".join(binary[:3]))

    level = "cao" if score >= 4 else "vua" if score >= 2 else "thap"
    crossed = boundaries(changes)
    if crossed and level == "thap":
        level = "vua"
        reasons.append("đụng ranh giới tin cậy: " + ", ".join(name for name, _ in crossed))
    result.update(boundaries=[{"kind": name, "paths": paths} for name, paths in crossed],
                  threat_model_updated=any(c["path"] == THREAT_MODEL_REL or c["path"].endswith("/" + THREAT_MODEL_REL)
                                           for c in changes))
    result.update(level=level, score=score, reasons=reasons, review=review_hint(level),
                  hotspots=[(p, v[1]) for p, v in sorted(hot.items(), key=lambda kv: (-kv[1][0], kv[0]))])
    return result


def review_hint(level: str) -> str:
    return {
        "thap": "tự rà `git diff` một lượt, không cần subagent; người dùng không cần đọc diff.",
        "vua": "giao `agent-stack:reviewer` trong context mới, chọn model sonnet; "
               "người dùng đọc lướt các file nên đọc kỹ.",
        "cao": "giao `agent-stack:reviewer` trong context mới (mặc định opus · high); "
               "người dùng nên đọc kỹ các file nên đọc kỹ trước khi commit.",
    }[level]


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "--no-optional-locks", "-c", "core.quotePath=false", "-C", str(root), *args],
                          capture_output=True, text=True, errors="replace")


def added_text(patch: str) -> dict:
    """Gom các dòng thêm vào theo file từ một patch -U0."""
    texts, current = {}, None
    for line in patch.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = None if target == "/dev/null" else (target[2:] if target.startswith("b/") else target)
        elif line.startswith("+") and current is not None:
            texts.setdefault(current, []).append(line[1:])
    return {k: "\n".join(v)[:MAX_TEXT] for k, v in texts.items()}


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
    numstat = checked(root, "diff", ref, "--numstat", "--no-renames", "-z")
    texts = added_text(checked(root, "diff", ref, "-U0", "--no-color", "--no-renames"))
    changes = []
    for record in numstat.split("\0"):
        parts = record.split("\t", 2)
        if len(parts) != 3:
            continue
        a, d, path = parts
        changes.append({"path": path, "added": None if a == "-" else int(a), "deleted": 0 if d == "-" else int(d),
                         "text": texts.get(path, "")})
    for path in git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\0"):
        if not path:
            continue
        try:
            size = (root / path).stat().st_size
            data = (root / path).read_bytes() if size <= MAX_UNTRACKED_BYTES else b""
        except OSError:
            continue
        if size > MAX_UNTRACKED_BYTES or b"\0" in data[:8192]:
            changes.append({"path": path, "added": None, "deleted": 0, "text": ""})
            continue
        text = data.decode("utf-8", errors="replace")
        changes.append({"path": path, "added": len(text.splitlines()), "deleted": 0, "text": text[:MAX_TEXT]})
    return sorted(changes, key=lambda c: c["path"])


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
                                                "; nếu chưa có mục cho việc này, chạy skill mo-hinh-de-doa trước bước review")
                     + ", rồi đưa các mục cho reviewer kiểm từng chốt chặn.")
    lines.append(f"Review đề nghị: {r['review']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chấm mức rủi ro của thay đổi chưa commit (chỉ đọc).")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--base", help="so với ref này thay vì HEAD, ví dụ main")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        result = assess(collect(args.root, args.base))
    except NotARepo:
        print(f"Không phải git repo: {args.root}. Script cần git để đọc thay đổi.")
        return 2
    except GitError as exc:
        print(f"Không chấm được: {exc}. Kiểm lại --base hoặc trạng thái repo.")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(render(result, args.base or "HEAD"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
