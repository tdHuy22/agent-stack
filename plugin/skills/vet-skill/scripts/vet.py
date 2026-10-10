#!/usr/bin/env python3
"""Kiểm duyệt bảo mật skill, plugin hoặc MCP của bên thứ ba trước khi cài.

Lệnh scan chỉ đọc: tải mã nguồn về thư mục cache, KHÔNG chạy bất kỳ mã nào của đối tượng.
Chỉ lệnh `dynamic` (tùy chọn, mặc định không dùng) chạy mã, và chỉ trong sandbox-runtime: không mạng, chỉ đọc ghi trong bản chép tạm.

Lệnh:
  vet.py scan <đích> [--name KHÓA] [--no-scanner] [--json]
  vet.py approve <khóa> --note "..."     ghi xác nhận của người duyệt vào vetted.lock
  vet.py reject  <khóa> --note "..."
  vet.py list
  vet.py drift [--plugins-dir DIR] [--quiet] [--json] [--remote]
                                         so plugin đã cài với bản đã kiểm trong .vet-cache (0 = ổn, 1 = có lệch);
                                         --remote: thêm MCP từ xa, lấy lại định nghĩa tool qua mạng và so hash đã duyệt
  vet.py dynamic --setup                 cài cô lập sandbox-runtime (tùy chọn, một lần)
  vet.py dynamic <khóa|thư mục> [--timeout GIÂY] [--allow-read ĐƯỜNG_DẪN] [--keep] [--json] -- <lệnh...>
                                         chạy MỘT lệnh của đối tượng trong sandbox rồi báo nó cố làm gì

<đích> là owner/repo[@ref][:thư/mục/con] trên GitHub, đường dẫn thư mục cục bộ, hoặc URL https của một
MCP server từ xa (streamable HTTP; xem mcp_remote.py: chụp instructions và định nghĩa tool, quét, ghim sha256,
không bao giờ tự PASS).
Mã thoát của scan: 0 = PASS, 1 = REVIEW (cần người đọc), 2 = FAIL, 3 = lỗi.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redflags import RISKY_ALLOWED, SEVERITIES, SHADOWED_COMMANDS, hidden_chars, is_comment, scan_text  # noqa: E402

TOOL_VERSION = "vet.py/1"
MD_EXT = {".md", ".mdc", ".markdown"}
CODE_EXT = {".sh", ".bash", ".zsh", ".fish", ".py", ".js", ".mjs", ".cjs", ".ts", ".mts", ".rb", ".pl",
            ".ps1", ".bat", ".cmd", ".go", ".rs", ".php", ".lua", ".applescript", ".scpt"}
CONFIG_NAMES = {"hooks.json", ".mcp.json", "plugin.json", "marketplace.json", "settings.json",
                "package.json", "monitors.json", ".lsp.json"}
MAX_SCAN_BYTES = 2_000_000
# Nhóm phát hiện của skill-scanner cho thấy ý đồ độc hại (khác với mẫu lỗ hổng như
# command_injection hay path traversal, vốn hay báo nhầm trên code phòng thủ).
MALICIOUS_CATEGORIES = {"data_exfiltration", "obfuscation", "malware", "backdoor", "credential_access",
                        "credential_theft", "persistence", "supply_chain"}
LICENSE_GUESS = [("apache license", "Apache-2.0"), ("mit license", "MIT"), ("permission is hereby granted", "MIT"),
                 ("bsd", "BSD"), ("mozilla public license", "MPL-2.0"), ("gnu affero", "AGPL"),
                 ("gnu lesser", "LGPL"), ("gnu general public", "GPL"), ("creative commons", "CC"),
                 ("unlicense", "Unlicense"), ("all rights reserved", "độc quyền (all rights reserved)")]
STALE_DAYS = 180
MIN_STARS = 500


# ---------------------------------------------------------------- vị trí

def find_home() -> Path:
    env = os.environ.get("AGENT_STACK_HOME")
    if env:
        return Path(env).expanduser()
    for parent in Path(__file__).resolve().parents:
        if (parent / ".agent-stack-root").exists():
            return parent
    default = Path("~/Documents/Claude/agent-stack").expanduser()
    return default if (default / ".agent-stack-root").exists() else Path.cwd()


# ---------------------------------------------------------------- đích

TARGET_RE = re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?:@(?P<ref>[^:\s]+))?(?::(?P<sub>\S+))?$")


def parse_target(value: str) -> dict:
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value.strip()):
        import mcp_remote
        return {"kind": "mcp-remote", "url": mcp_remote.check_url(value.strip())}
    local = Path(value).expanduser()
    if local.is_dir():
        return {"kind": "local", "path": local.resolve()}
    m = TARGET_RE.match(value.strip())
    if not m:
        raise ValueError(f"Không hiểu đích '{value}'. Dùng owner/repo[@ref][:thư/mục], đường dẫn thư mục hoặc URL https của MCP từ xa.")
    sub = (m.group("sub") or "").strip("/")
    if ".." in Path(sub).parts:
        raise ValueError("Thư mục con không được chứa '..'.")
    return {"kind": "github", "owner": m.group("owner"), "repo": m.group("repo").removesuffix(".git"),
            "ref": m.group("ref"), "subpath": sub}


# ---------------------------------------------------------------- GitHub

def gh_json(api_path: str):
    """Gọi GitHub API qua `gh` (đã đăng nhập); không có `gh` thì gọi thẳng API công khai."""
    if shutil.which("gh"):
        out = subprocess.run(["gh", "api", api_path], capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            return json.loads(out.stdout)
    req = urllib.request.Request(f"https://api.github.com/{api_path}",
                                 headers={"User-Agent": "agent-stack-vet", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (URL cố định tới api.github.com)
        return json.loads(resp.read().decode("utf-8"))


def repo_meta(owner: str, repo: str) -> dict:
    d = gh_json(f"repos/{owner}/{repo}")
    return {
        "full_name": d.get("full_name"),
        "stars": d.get("stargazers_count", 0),
        "pushed_at": (d.get("pushed_at") or "")[:10],
        "archived": bool(d.get("archived")),
        "license": (d.get("license") or {}).get("spdx_id") or "none",
        "default_branch": d.get("default_branch") or "main",
        "owner_type": (d.get("owner") or {}).get("type"),
        "fork": bool(d.get("fork")),
    }


def resolve_sha(owner: str, repo: str, ref: str) -> str:
    return gh_json(f"repos/{owner}/{repo}/commits/{ref}")["sha"]


def git(*args: str, cwd: Path) -> None:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    subprocess.run(["git", "-c", "advice.detachedHead=false", "-c", "core.hooksPath=/dev/null", *args],
                   cwd=str(cwd), check=True, capture_output=True, text=True, timeout=600, env=env)


def fetch(owner: str, repo: str, sha: str, subpath: str, cache_root: Path) -> Path:
    """Tải đúng commit `sha` (chỉ thư mục con nếu có) vào cache; dùng lại nếu đã tải."""
    slug = f"{owner}__{repo}" + (f"__{re.sub(r'[^A-Za-z0-9._-]+', '-', subpath)}" if subpath else "")
    dest = cache_root / f"{slug}@{sha[:12]}"
    if (dest / ".vet-complete").exists():
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git("init", "-q", cwd=dest)
    git("remote", "add", "origin", f"https://github.com/{owner}/{repo}.git", cwd=dest)
    git("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", sha, cwd=dest)
    if subpath:
        git("sparse-checkout", "set", subpath, cwd=dest)
    git("checkout", "-q", "FETCH_HEAD", cwd=dest)
    (dest / ".vet-complete").write_text(sha + "\n")
    return dest


def license_files(*dirs: Path) -> list:
    """Tìm file giấy phép ở các thư mục cho trước và đoán loại giấy phép."""
    found = []
    for d in dirs:
        for path in sorted(d.glob("*")):
            if path.is_file() and re.match(r"(?i)^(license|licence|copying)(\.[a-z]+)?$", path.name):
                head = path.read_text(encoding="utf-8", errors="replace")[:2000].lower()
                guess = next((spdx for needle, spdx in LICENSE_GUESS if needle in head), "không rõ loại")
                found.append(f"{path.name}: {guess}")
    return found


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
        h.update(str(path.relative_to(root)).encode())
        h.update(path.read_bytes()[:MAX_SCAN_BYTES])
    return h.hexdigest()


# ---------------------------------------------------------------- thống kê file

MAGIC = {b"\xcf\xfa\xed\xfe": "Mach-O", b"\xce\xfa\xed\xfe": "Mach-O", b"\xca\xfe\xba\xbe": "Mach-O universal",
         b"\x7fELF": "ELF", b"MZ": "PE/Windows"}


def classify(path: Path, head: bytes) -> str:
    for magic, _ in MAGIC.items():
        if head.startswith(magic):
            return "binary"
    if b"\x00" in head:
        return "binary"
    name, ext = path.name, path.suffix.lower()
    if ext in MD_EXT:
        return "md"
    if ext in CODE_EXT or head.startswith(b"#!") or "bin" in path.parts:
        return "code"
    if name in CONFIG_NAMES or ext in {".json", ".yaml", ".yml", ".toml"}:
        return "code" if name in CONFIG_NAMES else "other"
    return "other"


def inventory(root: Path) -> list:
    files = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            path = Path(dirpath) / name
            if name == ".vet-complete":
                continue
            rel = path.relative_to(root)
            item = {"rel": str(rel), "path": path, "size": 0, "kind": "other", "symlink": None, "exec": False}
            if path.is_symlink():
                target = os.path.realpath(path)
                item["symlink"] = target
                item["escapes"] = not target.startswith(str(root.resolve()))
                files.append(item)
                continue
            try:
                st = path.stat()
                with path.open("rb") as fh:
                    head = fh.read(8192)
            except OSError:
                continue
            item["size"] = st.st_size
            item["exec"] = bool(st.st_mode & 0o111)
            item["kind"] = classify(rel, head)
            if item["kind"] == "binary":
                item["magic"] = next((v for k, v in MAGIC.items() if head.startswith(k)), "binary")
            files.append(item)
    return files


# ---------------------------------------------------------------- thành phần tự chạy

def frontmatter(text: str) -> dict:
    """Đọc phần frontmatter YAML đơn giản (key: value, danh sách, khối nhiều dòng)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    data, key = {}, None
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            key, value = m.group(1), m.group(2).strip()
            data[key] = "" if value in ("|", ">", "|-", ">-") else value.strip("'\"")
        elif key:
            piece = line.strip()
            data[key] = (data[key] + " " + piece.lstrip("- ")).strip()
    return data


# Khóa trong settings.json khiến Claude Code tự chạy một lệnh (statusline, lấy khóa API, lấy credential...).
COMMAND_SETTINGS = ("statusLine", "subagentStatusLine", "apiKeyHelper", "awsAuthRefresh", "awsCredentialExport",
                    "otelHeadersHelper", "fileSuggestion")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def hook_commands(hooks_obj) -> list:
    """Trích danh sách lệnh từ cấu hình hook dạng settings.json/hooks.json."""
    out = []
    if isinstance(hooks_obj, dict) and "hooks" in hooks_obj and isinstance(hooks_obj["hooks"], dict):
        hooks_obj = hooks_obj["hooks"]
    if not isinstance(hooks_obj, dict):
        return out
    for event, groups in hooks_obj.items():
        for group in groups if isinstance(groups, list) else []:
            for h in (group.get("hooks") or []) if isinstance(group, dict) else []:
                if not isinstance(h, dict):
                    continue
                cmd = h.get("command") or h.get("url") or h.get("prompt") or h.get("tool") or ""
                if h.get("args"):
                    cmd = f"{cmd} {' '.join(map(str, h['args']))}"
                out.append({"event": event, "matcher": group.get("matcher", ""), "type": h.get("type"), "command": cmd})
    return out


def components(root: Path, files: list) -> dict:
    comp = {"skills": [], "agents": [], "hooks": [], "mcp": [], "monitors": [], "bin": [], "lifecycle": [],
            "marketplace_sources": [], "statusline": []}
    for f in files:
        rel, path = Path(f["rel"]), f["path"]
        name = rel.name
        if f["symlink"]:
            continue
        if name == "SKILL.md":
            text = path.read_text(encoding="utf-8", errors="replace")
            fm = frontmatter(text)
            dynamic = [ln.strip()[:120] for ln in text.splitlines() if re.search(r"(^|\s)!`|^```!", ln)]
            comp["skills"].append({"path": str(rel.parent) or ".", "name": fm.get("name", ""),
                                   "description_len": len(fm.get("description", "")),
                                   "allowed_tools": fm.get("allowed-tools", ""), "hooks": "hooks" in fm,
                                   "model": fm.get("model", ""), "context": fm.get("context", ""),
                                   "dynamic_shell": dynamic})
        elif rel.parts[:1] == ("agents",) and rel.suffix == ".md":
            fm = frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            comp["agents"].append({"path": str(rel), "tools": fm.get("tools", "(tất cả)"),
                                   "hooks": "hooks" in fm, "mcpServers": "mcpServers" in fm,
                                   "permissionMode": fm.get("permissionMode", "")})
        elif name in ("hooks.json", "settings.json", "plugin.json"):
            data = load_json(path)
            if isinstance(data, dict):
                for h in hook_commands(data.get("hooks") if name != "hooks.json" else data):
                    comp["hooks"].append(dict(h, file=str(rel)))
                if name == "plugin.json":
                    mcp = data.get("mcpServers")
                    if isinstance(mcp, dict):
                        for srv, cfg in mcp.items():
                            comp["mcp"].append({"file": str(rel), "server": srv, "spec": json.dumps(cfg)[:200]})
                    mon = (data.get("experimental") or {}).get("monitors") or data.get("monitors")
                    if mon:
                        comp["monitors"].append({"file": str(rel), "spec": json.dumps(mon)[:200]})
                if name == "settings.json":
                    for key in COMMAND_SETTINGS:
                        if data.get(key):
                            comp["statusline"].append({"file": str(rel), "key": key,
                                                       "spec": json.dumps(data[key])[:200]})
        elif name == ".mcp.json":
            data = load_json(path) or {}
            servers = data.get("mcpServers", data) if isinstance(data, dict) else {}
            for srv, cfg in (servers.items() if isinstance(servers, dict) else []):
                comp["mcp"].append({"file": str(rel), "server": srv, "spec": json.dumps(cfg)[:200]})
        elif name == "monitors.json":
            comp["monitors"].append({"file": str(rel), "spec": (path.read_text(errors="replace"))[:200]})
        elif name == "package.json":
            data = load_json(path) or {}
            for script_name, cmd in (data.get("scripts") or {}).items():
                if re.match(r"^(pre|post)?install$|^prepare$", script_name):
                    comp["lifecycle"].append({"file": str(rel), "script": script_name, "command": str(cmd)[:160]})
        elif name == "marketplace.json":
            data = load_json(path) or {}
            for plugin in data.get("plugins", []) if isinstance(data, dict) else []:
                src = plugin.get("source") if isinstance(plugin, dict) else None
                if src and not (isinstance(src, str) and src.startswith("./")):
                    comp["marketplace_sources"].append({"plugin": plugin.get("name"), "source": json.dumps(src)[:160]})
        if "bin" in rel.parts[:-1] and f.get("exec"):
            comp["bin"].append({"path": str(rel), "shadows": name in SHADOWED_COMMANDS})
    return comp


# ---------------------------------------------------------------- dò dấu hiệu

CI_WORKFLOW_RE = re.compile(r"\.github/workflows/[^/]+\.ya?ml$")


def run_redflags(files: list, ci_root: bool = False) -> list:
    """Quét dấu hiệu theo luật. `ci_root` chỉ đúng khi gốc quét là gốc một repo GitHub (không có thư mục con): lúc đó
    workflow `.github/workflows/*.yml` mới là CI chạy trên máy chủ của tác giả. Ở thư mục con hay thư mục cục bộ, một
    `.github/` có thể là thứ plugin tự gọi, nên không hạ bậc."""
    findings = []
    for f in files:
        if f["symlink"] or f["kind"] in ("binary",) or f["size"] > MAX_SCAN_BYTES:
            continue
        try:
            text = f["path"].read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        kind = f["kind"] if f["kind"] in ("md", "code") else "other"
        lines = text.splitlines()
        for rule, line_no, excerpt in scan_text(text, kind):
            sev, why = rule.severity, rule.why
            if kind == "code" and is_comment(lines[line_no - 1]):
                # Mẫu nằm trong chú thích thì không chạy: hạ một bậc và ghi chú lại.
                sev = SEVERITIES[min(SEVERITIES.index(sev) + 1, len(SEVERITIES) - 1)]
                why += " (trong chú thích)"
            if ci_root and CI_WORKFLOW_RE.fullmatch(f["rel"]):
                # Workflow CI chạy trên máy chủ CI của tác giả, không chạy khi người dùng cài: hạ một bậc.
                sev = SEVERITIES[min(SEVERITIES.index(sev) + 1, len(SEVERITIES) - 1)]
                why += " (trong CI, không chạy khi cài)"
            findings.append({"rule": rule.id, "severity": sev, "why": why, "file": f["rel"],
                             "line": line_no, "excerpt": excerpt, "kind": kind})
        for line_no, cps, benign in hidden_chars(text):
            if benign:
                sev, why = "low", "U+200B đứng trước backtick (mẹo hiển thị code fence lồng nhau)"
            elif kind == "md":
                sev, why = "critical", "Ký tự vô hình hoặc đảo chiều: " + ", ".join(cps)
            else:
                sev = "medium" if cps == ["U+FEFF"] else "high"
                why = "Ký tự vô hình hoặc đảo chiều: " + ", ".join(cps)
            findings.append({"rule": "hidden-unicode", "severity": sev, "why": why, "file": f["rel"],
                             "line": line_no, "excerpt": "(không in để tránh ký tự ẩn)", "kind": kind})
    return findings


# ---------------------------------------------------------------- skill-scanner

def scanner_bin(home: Path):
    local = home / ".venv" / "bin" / "skill-scanner"
    if local.exists():
        return str(local)
    return shutil.which("skill-scanner")


def run_scanner(home: Path, root: Path, skills: list):
    exe = scanner_bin(home)
    if not exe:
        return {"status": "không có skill-scanner"}
    if not skills:
        return {"status": "bỏ qua (không có SKILL.md)"}
    single = len(skills) == 1 and skills[0]["path"] in ("", ".")
    cmd = [exe, "scan", str(root)] if single else [exe, "scan-all", str(root), "--recursive"]
    cmd += ["--use-behavioral", "--format", "json", "--compact"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        data = json.loads(out.stdout)
    except (subprocess.TimeoutExpired, ValueError) as exc:
        return {"status": f"lỗi: {exc.__class__.__name__}"}
    results = [data] if single else data.get("results", [])
    counts = {s: 0 for s in SEVERITIES}
    top = []
    for res in results:
        base = Path(res.get("skill_path") or root)
        for item in res.get("findings", []):
            sev = str(item.get("severity", "info")).lower()
            counts[sev] = counts.get(sev, 0) + 1
            file_abs = base / (item.get("file_path") or "")
            try:
                rel = str(file_abs.resolve().relative_to(root.resolve()))
            except ValueError:
                rel = item.get("file_path") or ""
            top.append({"severity": sev, "rule": item.get("rule_id"), "title": item.get("title"), "file": rel,
                        "line": item.get("line_number"), "category": item.get("category") or ""})
    order = {s: i for i, s in enumerate(SEVERITIES)}
    top.sort(key=lambda x: order.get(x["severity"], 9))
    version = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip().split()[-1:]
    return {"status": "ok", "version": version[0] if version else "?", "counts": counts, "findings": top[:200]}


# ---------------------------------------------------------------- phán quyết

def verdict(meta: dict, files: list, comp: dict, flags: list, scanner: dict, spector: dict = None):
    fail, review = [], []
    if meta.get("archived"):
        fail.append("Repo đã archived, không còn được bảo trì.")
    for f in flags:
        where = f"{f['file']}:{f['line']}"
        if f["severity"] == "critical" and (f["kind"] == "code" or f["rule"] == "hidden-unicode"):
            fail.append(f"[{f['rule']}] {f['why']} ({where})")
        elif f["severity"] in ("critical", "high"):
            note = " (trong tài liệu, có thể chỉ là ví dụ)" if f["kind"] == "md" else ""
            review.append(f"[{f['rule']}] {f['why']}{note} ({where})")
    for item in files:
        if item["symlink"] and item.get("escapes"):
            fail.append(f"Symlink trỏ ra ngoài repo: {item['rel']} → {item['symlink']}")
        if item["kind"] == "binary" and item.get("magic") not in (None, "binary"):
            review.append(f"File thực thi nhị phân {item.get('magic')}: {item['rel']}")
    for b in comp["bin"]:
        (fail if b["shadows"] else review).append(
            f"bin/ đưa file lên PATH{' và giả mạo lệnh hệ thống' if b['shadows'] else ''}: {b['path']}")
    if scanner.get("status") == "ok":
        for item in scanner["findings"]:
            if item["severity"] in ("critical", "high"):
                is_doc = Path(item["file"] or "x.md").suffix.lower() in MD_EXT
                malicious = item.get("category") in MALICIOUS_CATEGORIES
                target = fail if (item["severity"] == "critical" and malicious and not is_doc) else review
                kind = "mã độc" if malicious else "mẫu lỗ hổng, có thể báo nhầm"
                target.append(f"[skill-scanner {item['rule']}] {item['title']} ({kind}) ({item['file']}:{item['line']})")
    if (spector or {}).get("status") == "ok":
        # Máy quét thứ hai, điều kiện khi duyệt: chỉ đẩy lên REVIEW cho tới khi đo được trên bộ mẫu của mình.
        for item in spector["findings"]:
            if item["severity"] in ("critical", "high"):
                review.append(f"[SkillSpector {item['rule']}] {item['title']} ({item['severity']}) "
                              f"({item['file']}:{item['line']})")
    if comp["hooks"]:
        review.append(f"Có {len(comp['hooks'])} hook tự chạy khi dùng.")
    if comp["mcp"]:
        review.append(f"Khai báo {len(comp['mcp'])} MCP server.")
    if comp["monitors"]:
        review.append("Có monitor chạy nền suốt phiên.")
    if comp["statusline"]:
        keys = ", ".join(sorted({s.get("key", "subagentStatusLine") for s in comp["statusline"]}))
        review.append(f"settings.json có khóa tự chạy lệnh ({keys}); đọc lệnh trước khi duyệt.")
    if comp["lifecycle"]:
        review.append("package.json có script tự chạy khi cài.")
    if comp["marketplace_sources"]:
        review.append("Marketplace kéo plugin từ nguồn khác; phải kiểm từng nguồn.")
    if any(s["dynamic_shell"] for s in comp["skills"]):
        review.append("SKILL.md có lệnh shell chạy ngay khi gọi skill (cú pháp !`...`).")
    if any(re.search(r"(^|[\s,])Bash($|[\s,])|Bash\(\*\)", s["allowed_tools"]) for s in comp["skills"]):
        review.append("allowed-tools cấp Bash không giới hạn.")
    for s in comp["skills"]:
        for m in RISKY_ALLOWED.finditer(s["allowed_tools"]):
            review.append(f"[allowed-tools] Skill tự duyệt sẵn lệnh tải-rồi-chạy hoặc tới host bất kỳ: "
                          f"`{m.group(0)[:100]}` ({s['path']}/SKILL.md)")
    code_files = [f for f in files if f["kind"] == "code"]
    if code_files:
        review.append(f"Có {len(code_files)} file mã hoặc cấu hình chạy được; cần đọc trước khi cài.")
    if meta.get("stars") is not None and meta.get("kind") == "github":
        if meta["stars"] < MIN_STARS:
            review.append(f"Ít sao ({meta['stars']} < {MIN_STARS}).")
        if meta.get("pushed_at"):
            age = (date.today() - date.fromisoformat(meta["pushed_at"])).days
            if age > STALE_DAYS:
                review.append(f"Không cập nhật {age} ngày.")
    if meta.get("kind") == "github" and meta.get("license") in ("none", None, "NOASSERTION") \
            and not meta.get("license_files"):
        review.append("Không thấy giấy phép: không được phép tái phân phối.")
    result = "FAIL" if fail else ("REVIEW" if review else "PASS")
    return result, collapse(fail), collapse(review)


def collapse(reasons: list) -> list:
    """Gộp các lý do giống nhau (khác vị trí) thành một dòng kèm số lần."""
    groups, order = {}, []
    for r in reasons:
        m = re.match(r"^(.*) \(([^()]*)\)$", r)
        head, where = (m.group(1), m.group(2)) if m else (r, "")
        if head not in groups:
            groups[head] = []
            order.append(head)
        if where:
            groups[head].append(where)
    out = []
    for head in order:
        where = groups[head]
        if len(where) > 1:
            out.append(f"{head} (×{len(where)}, ví dụ {where[0]})")
        else:
            out.append(f"{head} ({where[0]})" if where else head)
    return out


# ---------------------------------------------------------------- báo cáo

def must_read(files: list, comp: dict, flags: list, scanner: dict, spector: dict = None) -> list:
    paths = {f["rel"] for f in files if f["kind"] == "code"}
    paths |= {s["path"].rstrip("/") + "/SKILL.md" if s["path"] not in ("", ".") else "SKILL.md" for s in comp["skills"]}
    paths |= {a["path"] for a in comp["agents"]}
    paths |= {f["file"] for f in flags if f["severity"] in ("critical", "high")}
    for found in (scanner, spector or {}):
        if found.get("status") == "ok":
            paths |= {x["file"] for x in found["findings"] if x["severity"] in ("critical", "high") and x["file"]}
    return sorted(p for p in paths if p)


def render_reviews(reviews: list) -> list:
    L = []
    for r in reviews:
        L += ["", f"## Nhận xét đọc tay của {r['by']} ({r['at'][:10]}, khuyến nghị: {r['recommend']})", "", r["text"]]
    return L


def render_report(key: str, meta: dict, files: list, comp: dict, flags: list, scanner: dict,
                  result: str, fail: list, review: list, reviews: list = (), spector: dict = None) -> str:
    spector = spector or {"status": "không chạy"}
    L = [f"# Kiểm duyệt: {key}", "",
         f"- Ngày: {date.today()} · Công cụ: {TOOL_VERSION}" +
         (f" + skill-scanner {scanner.get('version')}" if scanner.get("status") == "ok" else "") +
         (f" + SkillSpector {spector.get('version')}" if spector.get("status") == "ok" else ""),
         f"- Nguồn: {meta.get('source')} · Commit: `{meta.get('sha', '')}`",
         f"- **Phán quyết: {result}**", ""]
    if meta.get("kind") == "github":
        L += ["## Repo", "", "| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |", "|---:|---|---|---|---|",
              f"| {meta['stars']} | {meta['pushed_at']} | {meta['archived']} | {meta['license']} | {meta.get('owner_type')} |", ""]
    if meta.get("license_files"):
        L += ["File giấy phép: " + "; ".join(meta["license_files"]), ""]
    kinds = {}
    for f in files:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    L += ["## Thống kê file", "", ", ".join(f"{k}: {v}" for k, v in sorted(kinds.items())) +
          f" · tổng {sum(f['size'] for f in files) / 1024:.0f} KB", ""]
    L += ["## Lý do", ""]
    L += [f"- ❌ {x}" for x in fail] + [f"- ⚠️ {x}" for x in review] or ["- Không có dấu hiệu nào."]
    L += ["", "## Thành phần tự chạy hoặc có quyền", ""]
    for label, items, fmt in (
        ("Hook", comp["hooks"], lambda h: f"`{h['event']}` [{h['matcher']}] {h['type']}: `{h['command'][:140]}` ({h['file']})"),
        ("MCP", comp["mcp"], lambda m: f"`{m['server']}`: `{m['spec']}` ({m['file']})"),
        ("Monitor", comp["monitors"], lambda m: f"`{m['spec']}` ({m['file']})"),
        ("bin/ trên PATH", comp["bin"], lambda b: f"`{b['path']}`" + (" ⚠️ trùng tên lệnh hệ thống" if b["shadows"] else "")),
        ("Script khi cài", comp["lifecycle"], lambda s: f"`{s['script']}`: `{s['command']}`"),
        ("Nguồn plugin bên ngoài", comp["marketplace_sources"], lambda s: f"{s['plugin']}: `{s['source']}`"),
    ):
        L.append(f"- **{label}:** " + ("không có" if not items else ""))
        L += [f"  - {fmt(i)}" for i in items]
    L += ["", "## Skill và agent", ""]
    for s in comp["skills"]:
        L.append(f"- `{s['path']}`: name=`{s['name']}`, mô tả {s['description_len']} ký tự"
                 + (f", allowed-tools=`{s['allowed_tools']}`" if s["allowed_tools"] else "")
                 + (", **có hook**" if s["hooks"] else "") + (f", context={s['context']}" if s["context"] else ""))
        L += [f"  - lệnh shell khi gọi: `{d}`" for d in s["dynamic_shell"]]
    L += [f"- agent `{a['path']}`: tools={a['tools']}" + (" **có hook**" if a["hooks"] else "")
          + (" **có MCP**" if a["mcpServers"] else "") for a in comp["agents"]]
    if not comp["skills"] and not comp["agents"]:
        L.append("- Không có SKILL.md hay agent.")
    L += ["", "## Dấu hiệu (luật riêng)", ""]
    if flags:
        L += ["| Mức | Luật | Vị trí | Loại file | Trích |", "|---|---|---|---|---|"]
        order = {s: i for i, s in enumerate(SEVERITIES)}
        for f in sorted(flags, key=lambda x: order[x["severity"]])[:60]:
            excerpt = f["excerpt"].replace("|", "\\|").replace("`", "'")
            L.append(f"| {f['severity']} | {f['rule']} | {f['file']}:{f['line']} | {f['kind']} | `{excerpt}` |")
    else:
        L.append("Không có.")
    L += ["", "## skill-scanner", ""]
    if scanner.get("status") == "ok":
        L.append("Đếm theo mức: " + (", ".join(f"{k}={v}" for k, v in scanner["counts"].items() if v) or "không có"))
        L += [f"- {x['severity']} · {x['rule']} · {x['title']} ({x['file']}:{x['line']})"
              for x in scanner["findings"] if x["severity"] != "info"][:25]
    else:
        L.append(f"Không chạy: {scanner.get('status')}")
    L += ["", "## SkillSpector (máy quét thứ hai, chỉ đẩy lên REVIEW)", ""]
    if spector.get("status") == "ok":
        L.append(f"Điểm rủi ro cao nhất: {spector.get('score')} · mạng: {spector.get('network')} · đếm theo mức: " +
                 (", ".join(f"{k}={v}" for k, v in spector["counts"].items() if v) or "không có"))
        L += [f"- {x['severity']} · {x['rule']} · {x['title']} ({x['file']}:{x['line']})"
              for x in spector["findings"] if x["severity"] != "info"][:25]
        L += [f"- lỗi khi quét: {e}" for e in spector.get("errors", [])[:5]]
    else:
        L.append(f"Không chạy: {spector.get('status')}")
    L += ["", "## Cần đọc tay trước khi duyệt", "",
          "Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.", ""]
    L += [f"- [ ] `{p}`" for p in must_read(files, comp, flags, scanner, spector)] or ["- (không có)"]
    L += ["", "Duyệt xong thì ghi lại: `vet.py approve <khóa> --note \"...\"` (hoặc `reject`)."]
    L += render_reviews(list(reviews))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- vetted.lock

def lock_path(home: Path) -> Path:
    return home / "vetted.lock"


def load_lock(home: Path) -> dict:
    data = load_json(lock_path(home))
    return data if isinstance(data, dict) and "entries" in data else {"version": 1, "entries": {}}


def save_lock(home: Path, data: dict) -> None:
    path = lock_path(home)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- lệnh

def cmd_scan(args, home: Path) -> int:
    target = parse_target(args.target)
    if target["kind"] == "mcp-remote":
        import mcp_remote
        return mcp_remote.scan_cmd(args, home, target["url"], (load_lock, save_lock, TOOL_VERSION))
    cache = home / ".vet-cache"
    if target["kind"] == "github":
        meta = repo_meta(target["owner"], target["repo"])
        ref = target["ref"] or meta["default_branch"]
        sha = resolve_sha(target["owner"], target["repo"], ref)
        checkout = fetch(target["owner"], target["repo"], sha, target["subpath"], cache)
        root = checkout / target["subpath"] if target["subpath"] else checkout
        if not root.is_dir():
            raise ValueError(f"Không có thư mục '{target['subpath']}' trong commit {sha[:12]}.")
        key = args.name or f"{target['owner']}/{target['repo']}" + (f":{target['subpath']}" if target["subpath"] else "")
        meta.update(kind="github", source=f"github:{target['owner']}/{target['repo']}", ref=ref, sha=sha,
                    subpath=target["subpath"])
        slug = f"{target['owner']}__{target['repo']}" + (f"__{re.sub(r'[^A-Za-z0-9._-]+', '-', target['subpath'])}" if target["subpath"] else "")
    else:
        root = target["path"]
        sha = tree_hash(root)
        key = args.name or f"local:{root}"
        meta = {"kind": "local", "source": f"local:{root}", "sha": sha, "ref": None, "subpath": ""}
        slug = "local__" + re.sub(r"[^A-Za-z0-9._-]+", "-", root.name)

    files = inventory(root)
    lic_dirs = [root] + ([checkout] if target["kind"] == "github" and target["subpath"] else [])
    meta["license_files"] = license_files(*lic_dirs)
    comp = components(root, files)
    flags = run_redflags(files, ci_root=target["kind"] == "github" and not target["subpath"])
    scanner = {"status": "tắt bằng --no-scanner"} if args.no_scanner else run_scanner(home, root, comp["skills"])
    if args.no_spector:
        second = {"status": "tắt bằng --no-spector"}
    else:
        import spector
        second = spector.run(home, root, comp["skills"], local=target["kind"] == "local")
    result, fail, review = verdict(meta, files, comp, flags, scanner, second)

    reports = home / "vet-reports"
    reports.mkdir(exist_ok=True)
    report_path = reports / f"{slug}@{meta['sha'][:12]}.md"

    lock = load_lock(home)
    old = lock["entries"].get(key, {})
    same_sha = old.get("sha") == meta["sha"]
    # Nhận xét đọc tay chỉ còn giá trị khi nội dung (commit) không đổi.
    reviews = [r for r in old.get("reviews", []) if r.get("sha") == meta["sha"]]
    report_path.write_text(render_report(key, meta, files, comp, flags, scanner, result, fail, review, reviews, second),
                           encoding="utf-8")
    counts = {s: 0 for s in SEVERITIES}
    for f in flags:
        counts[f["severity"]] += 1
    lock["entries"][key] = {
        "source": meta["source"], "subpath": meta.get("subpath") or "", "ref": meta.get("ref"), "sha": meta["sha"],
        "verdict": result, "vetted_at": str(date.today()), "tool": TOOL_VERSION,
        "stars": meta.get("stars"), "pushed_at": meta.get("pushed_at"), "license": meta.get("license"),
        "license_files": meta.get("license_files") or [],
        "archived": meta.get("archived"),
        "redflags": {k: v for k, v in counts.items() if v},
        "scanner": {k: scanner.get(k) for k in ("status", "version")} |
                   ({"counts": {k: v for k, v in scanner["counts"].items() if v}} if scanner.get("status") == "ok" else {}),
        "spector": {k: second.get(k) for k in ("status", "version", "score")} |
                   ({"counts": {k: v for k, v in second["counts"].items() if v}} if second.get("status") == "ok" else {}),
        "report": str(report_path.relative_to(home)),
        # Xác nhận của người duyệt chỉ giữ khi commit không đổi.
        "human_review": old.get("human_review") if same_sha and old.get("human_review") else
                        {"status": "pending", "at": None, "note": None},
        "reviews": reviews,
    }
    # Bản vá cục bộ đã duyệt gắn với đúng commit này: vet lại cùng commit thì giữ. Commit khác thì bỏ, và ghi lại
    # (lock, báo cáo, tóm tắt) để người duyệt kiểm upstream đã sửa chưa, kẻo lỗi cũ quay lại mà không ai biết.
    dropped = []
    if same_sha:
        for field in ("local_patches", "dropped_patches"):
            if old.get(field):
                lock["entries"][key][field] = old[field]
    elif old.get("local_patches"):
        dropped = [{k: p.get(k) for k in ("path", "why", "upstream")} for p in old["local_patches"]]
        lock["entries"][key]["dropped_patches"] = dropped
        with report_path.open("a", encoding="utf-8") as fh:
            fh.write("\n## Bản vá cục bộ bị bỏ khi đổi commit\n\n" + "".join(
                f"- `{d['path']}`: {d['why']} Upstream: {d['upstream']}\n" for d in dropped) +
                "\nKiểm upstream đã sửa lỗi này ở commit mới chưa; chưa thì làm lại bản vá cho commit mới và duyệt lại.\n")
    save_lock(home, lock)

    summary = {"key": key, "verdict": result, "sha": meta["sha"], "report": str(report_path),
               "fail": fail, "review": review[:20], "must_read": must_read(files, comp, flags, scanner, second)}
    if dropped:
        summary["dropped_patches"] = dropped
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"{result}  {key}  @{meta['sha'][:12]}")
        for x in fail:
            print(f"  ❌ {x}")
        for x in review[:12]:
            print(f"  ⚠️  {x}")
        if len(review) > 12:
            print(f"  … và {len(review) - 12} lý do khác trong báo cáo")
        for d in dropped:
            print(f"  ⚠️  Bỏ bản vá cục bộ {d['path']} vì commit đổi ({d['upstream']}): kiểm upstream đã sửa chưa, "
                  "chưa thì làm lại bản vá rồi duyệt lại")
        print(f"  Báo cáo: {report_path}")
    return {"PASS": 0, "REVIEW": 1, "FAIL": 2}[result]


def cmd_review(args, home: Path, status: str) -> int:
    lock = load_lock(home)
    if args.key not in lock["entries"]:
        print(f"Không có khóa '{args.key}' trong vetted.lock.", file=sys.stderr)
        return 3
    lock["entries"][args.key]["human_review"] = {
        "status": status, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "note": args.note}
    save_lock(home, lock)
    print(f"Đã ghi {status} cho {args.key}.")
    for d in lock["entries"][args.key].get("dropped_patches") or []:
        print(f"⚠️  Commit này không còn bản vá cục bộ {d.get('path')} ({d.get('upstream')}); "
              "nếu upstream chưa sửa thì lỗi cũ quay lại.")
    return 0


def cmd_note(args, home: Path) -> int:
    """Ghi nhận xét đọc tay (của Claude hoặc người) vào vetted.lock và vào báo cáo."""
    lock = load_lock(home)
    entry = lock["entries"].get(args.key)
    if not entry:
        print(f"Không có khóa '{args.key}' trong vetted.lock.", file=sys.stderr)
        return 3
    note = {"by": args.by, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sha": entry["sha"],
            "recommend": args.recommend, "text": args.text.strip()}
    entry.setdefault("reviews", [])
    entry["reviews"] = [r for r in entry["reviews"] if r.get("by") != args.by or r.get("sha") != entry["sha"]] + [note]
    save_lock(home, lock)
    report = home / entry["report"]
    if report.exists():
        text = report.read_text(encoding="utf-8")
        marker = f"\n## Nhận xét đọc tay của {args.by} "
        if marker in text:
            text = text[: text.index(marker)]
        others = [r for r in entry["reviews"] if r["by"] != args.by]
        text = text.rstrip("\n") + "\n" + "\n".join(render_reviews(others + [note])) + "\n"
        report.write_text(text, encoding="utf-8")
    print(f"Đã ghi nhận xét của {args.by} cho {args.key} (khuyến nghị: {args.recommend}).")
    return 0


def cmd_list(home: Path) -> int:
    for key, e in sorted(load_lock(home)["entries"].items()):
        human = (e.get("human_review") or {}).get("status", "pending")
        print(f"{e['verdict']:<7} {human:<9} {e['sha'][:12]}  {key}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm duyệt skill/plugin/MCP của bên thứ ba.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="kiểm duyệt một đích")
    s.add_argument("target")
    s.add_argument("--name", help="khóa ghi vào vetted.lock (mặc định suy từ đích)")
    s.add_argument("--no-scanner", action="store_true", help="không chạy skill-scanner")
    s.add_argument("--no-spector", action="store_true", help="không chạy SkillSpector (máy quét thứ hai)")
    s.add_argument("--json", action="store_true")
    for name in ("approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("key")
        p.add_argument("--note", required=True)
    n = sub.add_parser("note", help="ghi nhận xét đọc tay")
    n.add_argument("key")
    n.add_argument("--by", default="claude")
    n.add_argument("--recommend", required=True, choices=["cài", "có-điều-kiện", "thử-1-project", "không-cài"])
    n.add_argument("--text", required=True)
    sub.add_parser("list")
    sp = sub.add_parser("spector", help="SkillSpector, máy quét thứ hai: xem trạng thái hoặc cài (--setup)")
    sp.add_argument("--setup", action="store_true", help="cài .venv-skillspector từ đúng bản đã duyệt (cần mạng)")
    dr = sub.add_parser("drift", help="so plugin đã cài với bản đã kiểm duyệt")
    dr.add_argument("--plugins-dir", help="thư mục plugin của Claude Code (mặc định ~/.claude/plugins)")
    dr.add_argument("--quiet", action="store_true", help="không in gì khi mọi plugin đều khớp")
    dr.add_argument("--json", action="store_true")
    dr.add_argument("--remote", action="store_true",
                    help="kiểm cả MCP từ xa trong catalog: lấy lại định nghĩa tool qua mạng, so với hash đã duyệt")
    dr.add_argument("--claude-json", help="cấu hình MCP scope user (mặc định ~/.claude.json)")
    d = sub.add_parser("dynamic", help="chạy một lệnh của đối tượng trong sandbox (tùy chọn)")
    d.add_argument("key", nargs="?", help="khóa trong vetted.lock hoặc thư mục cục bộ")
    d.add_argument("--setup", action="store_true", help="cài sandbox-runtime vào .cache/srt")
    d.add_argument("--timeout", type=int, default=60, help="giây tối đa cho lệnh (mặc định 60)")
    d.add_argument("--allow-read", action="append", default=[], help="cho đọc thêm một đường dẫn (lặp được)")
    d.add_argument("--allow-domain", action="append", default=[], help="cho phép một tên miền (mặc định không mạng)")
    d.add_argument("--keep", action="store_true", help="giữ bản chép tạm để soi")
    d.add_argument("--real-home", action="store_true",
                   help="giữ HOME thật (bị chặn đọc) thay vì HOME giả có file mồi; chỉ còn log để phát hiện")
    d.add_argument("--json", action="store_true")
    # Lệnh cần chạy đứng sau `--`; tách trước để các tùy chọn đứng sau khóa vẫn được nhận.
    argv = list(sys.argv[1:] if argv is None else argv)
    command = []
    if argv and argv[0] == "dynamic" and "--" in argv:
        cut = argv.index("--")
        argv, command = argv[:cut], argv[cut + 1:]
    args = ap.parse_args(argv)
    if args.cmd == "dynamic":
        args.command = command
    home = find_home()
    try:
        if args.cmd == "scan":
            return cmd_scan(args, home)
        if args.cmd in ("approve", "reject"):
            return cmd_review(args, home, "approved" if args.cmd == "approve" else "rejected")
        if args.cmd == "note":
            return cmd_note(args, home)
        if args.cmd == "drift":
            import drift
            return drift.main_cli(args, home)
        if args.cmd == "dynamic":
            import dynamic  # chỉ nạp khi dùng, để scan không phụ thuộc Node
            return dynamic.main_cli(args, home)
        if args.cmd == "spector":
            import spector
            return spector.main_cli(args, home)
        return cmd_list(home)
    except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        detail = getattr(exc, "stderr", "") or ""
        print(f"Lỗi: {exc} {detail}".strip(), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
