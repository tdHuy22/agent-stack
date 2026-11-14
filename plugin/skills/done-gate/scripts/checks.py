#!/usr/bin/env python3
"""Bộ chạy kiểm tĩnh cho project bất kỳ (done-gate bước 4; hook post_edit dùng phần kiểm nhanh).

Nhận ngôn ngữ từ các file vừa đổi, chọn lệnh theo thứ tự: lệnh trong "Mốc kiểm tra" của project (không chạy lại,
done-gate bước 4 chạy) → script sẵn của project (package.json, cấu hình ruff/mypy, pre-commit, Makefile) → công cụ gốc
của ngôn ngữ. Chỉ báo phát hiện ở dòng vừa đổi (`git diff -U0`); riêng lỗi kiểu, biên dịch, cú pháp thì báo cả ngoài
dòng đổi, vì đổi chữ ký hàm làm hỏng chỗ gọi ở dòng không đổi.

Lỗi thật chặn chốt việc; luật phong cách chỉ báo, trừ khi project tự bắt buộc công cụ đó (có file cấu hình, hay tên
công cụ nằm trong Mốc kiểm tra, CI, pre-commit, Makefile, script package.json). Thiếu công cụ thì báo
"chưa kiểm X vì thiếu Y", không bao giờ báo đạt.

Mã thoát: 0 không có lỗi chặn và mọi kiểm cần chạy đều đã chạy; 1 có lỗi chặn; 2 không có lỗi chặn nhưng có kiểm chưa
chạy được (thiếu công cụ, lệnh hỏng, hết giờ); 3 sai cách gọi hay không phải git repo.

    python3 checks.py [--root DIR] [--base REF] [--list] [--json] [--offline] [--all]
"""
import argparse
import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- bảng ngôn ngữ

LANGS = {
    "python": ("Python", {".py", ".pyi"}),
    "ts": ("TS/JS", {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"}),
    "swift": ("Swift", {".swift"}),
    "rust": ("Rust", {".rs"}),
    "shell": ("Shell", {".sh", ".bash", ".zsh", ".ksh"}),
    "c_cpp": ("C/C++", {".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"}),
    "go": ("Go", {".go"}),
    "java": ("Java", {".java"}),
    "kotlin": ("Kotlin", {".kt", ".kts"}),
    "csharp": ("C#", {".cs"}),
    "ruby": ("Ruby", {".rb", ".rake", ".gemspec"}),
    "php": ("PHP", {".php"}),
    "dart": ("Dart", {".dart"}),
    "lua": ("Lua", {".lua"}),
}
CONFIG_LABELS = {"docker": "Dockerfile", "actions": "GitHub Actions", "yaml": "YAML", "json": "JSON", "toml": "TOML",
                 "*": "mọi file"}
# Ngôn ngữ agent-stack chưa có công cụ kiểm: tên và công cụ nên tìm hiểu (gợi ý cho project lạ).
UNSUPPORTED = {
    ".scala": ("Scala", "scalac, scalafmt"), ".sc": ("Scala", "scalac, scalafmt"),
    ".ex": ("Elixir", "mix compile --warnings-as-errors, credo"), ".exs": ("Elixir", "mix compile, credo"),
    ".hs": ("Haskell", "ghc -fno-code, hlint"), ".ml": ("OCaml", "dune build"), ".r": ("R", "lintr"),
    ".jl": ("Julia", "JET.jl"), ".zig": ("Zig", "zig ast-check"), ".nim": ("Nim", "nim check"),
    ".v": ("Verilog", "verilator --lint-only"), ".sv": ("SystemVerilog", "verilator --lint-only, verible-verilog-lint"),
    ".vhd": ("VHDL", "ghdl -s"), ".vhdl": ("VHDL", "ghdl -s"), ".clj": ("Clojure", "clj-kondo"),
    ".erl": ("Erlang", "erlc, elvis"), ".fs": ("F#", "dotnet build, fantomas"), ".pl": ("Perl", "perl -c, perlcritic"),
    ".pm": ("Perl", "perl -c, perlcritic"), ".ps1": ("PowerShell", "PSScriptAnalyzer"),
    ".groovy": ("Groovy", "CodeNarc"), ".sol": ("Solidity", "solhint, slither"),
    ".m": ("Objective-C", "clang -fsyntax-only, clang-tidy"), ".mm": ("Objective-C++", "clang-tidy"),
    ".cu": ("CUDA", "nvcc, clang-tidy"), ".f90": ("Fortran", "gfortran -fsyntax-only"),
    ".tf": ("Terraform", "terraform validate, tflint"), ".proto": ("Protobuf", "buf lint"),
    ".sql": ("SQL", "sqlfluff"), ".elm": ("Elm", "elm make, elm-review"),
}
# Cách cài công cụ hay gặp (gợi ý; agent không tự cài, cài toàn cục chỉ qua install.sh khi người dùng duyệt).
INSTALL = {
    "ruff": "brew install ruff", "shellcheck": "brew install shellcheck", "swiftlint": "brew install swiftlint",
    "cargo-clippy": "rustup component add clippy", "cargo-fmt": "rustup component add rustfmt",
    "go": "brew install go", "golangci-lint": "brew install golangci-lint", "cppcheck": "brew install cppcheck",
    "javac": "brew install openjdk", "mvn": "brew install maven", "ktlint": "brew install ktlint",
    "dotnet": "brew install --cask dotnet-sdk", "rubocop": "gem install rubocop (hay thêm vào Gemfile)",
    "php": "brew install php", "phpstan": "composer require --dev phpstan/phpstan", "dart": "brew install dart-sdk",
    "luacheck": "luarocks install luacheck", "hadolint": "brew install hadolint", "actionlint": "brew install actionlint",
    "yamllint": "brew install yamllint", "gitleaks": "brew install gitleaks", "osv-scanner": "brew install osv-scanner",
    "semgrep": "brew install semgrep", "tsc": "npm install --save-dev typescript (trong project)",
    "eslint": "npm install --save-dev eslint (trong project)", "prettier": "npm install --save-dev prettier (trong project)",
    "biome": "npm install --save-dev @biomejs/biome (trong project)", "node": "brew install node",
    "swiftc": "xcode-select --install", "mypy": "pip install mypy (trong venv của project)",
    "pyright": "brew install pyright", "shfmt": "brew install shfmt", "clang-tidy": "brew install llvm",
    "clang-format": "brew install clang-format", "ruby": "brew install ruby", "pre-commit": "brew install pre-commit",
    "archctl": "./install.sh --only tools của agent-stack (mục cargo:archctl, cần bạn duyệt trong vetted.lock)",
}
SKIP_DIRS = ("node_modules/", "vendor/", "dist/", "build/", ".venv/", "venv/", "target/", "third_party/", ".git/",
             "__pycache__/", "Pods/", ".build/", "DerivedData/")
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "Cargo.lock", "poetry.lock", "uv.lock",
             "Pipfile.lock", "go.sum", "Gemfile.lock", "composer.lock", "pubspec.lock", "gradle.lockfile",
             "packages.lock.json", "mix.lock", "requirements.txt"}
JSONC_NAMES = re.compile(r"(^|/)(tsconfig[^/]*|jsconfig[^/]*|\.eslintrc|\.babelrc|devcontainer|\.swcrc|turbo|biome|deno|"
                         r"renovate|wrangler|tslint|nx|project|nest-cli|angular|cspell|\.markdownlint|\.jshintrc)\.json$"
                         r"|(^|/)\.vscode/|\.jsonc$")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
KIND_LABEL = {"lint": "lint", "type": "kiểu/biên dịch", "format": "định dạng", "syntax": "cú pháp",
              "security": "bảo mật (semgrep)", "secrets": "khóa lộ", "deps": "thư viện có lỗ hổng", "config": "cấu hình",
              "arch": "luật kiến trúc (archctl)"}


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt, để so khớp."""
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").lower()


def lang_of(path: str):
    """Mã ngôn ngữ hay loại file cấu hình của một đường dẫn tương đối; None nếu không kiểm."""
    name = os.path.basename(path)
    low = name.lower()
    ext = os.path.splitext(low)[1]
    if low.startswith(("dockerfile", "containerfile")) or ext == ".dockerfile":
        return "docker"
    if re.match(r"(^|.*/)\.github/workflows/[^/]+\.ya?ml$", path):
        return "actions"
    for code, (_, exts) in LANGS.items():
        if ext in exts:
            return code
    if name in ("Gemfile", "Rakefile"):
        return "ruby"
    if ext in (".yml", ".yaml"):
        return "yaml"
    if ext == ".json":
        return "json"
    if ext == ".toml":
        return "toml"
    return None


# ---------------------------------------------------------------- git: dòng vừa đổi

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def git(root: Path, *args: str, timeout: float = 30):
    try:
        out = subprocess.run(["git", "--no-optional-locks", "-c", "core.quotePath=false", *args], cwd=root,
                             capture_output=True, text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def parse_diff(text: str) -> dict:
    """{đường dẫn: tập dòng đã thêm hay sửa} từ `git diff -U0`. Hunk chỉ xóa thì lấy dòng ngay sau chỗ xóa."""
    changed, path = {}, None
    for line in text.splitlines():
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else (target.removeprefix("b/"))
            if path:
                changed.setdefault(path, set())
        elif line.startswith("@@") and path:
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if not m:
                continue
            start, count = int(m.group(1)), int(m.group(2)) if m.group(2) is not None else 1
            changed[path].update(range(start, start + count) if count else {max(start, 1), start + 1})
    return {p: lines for p, lines in changed.items() if lines}


def changed_lines(root: Path, base: str = "HEAD", all_files: bool = False):
    """{đường dẫn tương đối: tập dòng đổi, hay None nếu cả file là mới}. None nếu git lỗi."""
    if all_files:
        listing = git(root, "ls-files", "-z")
        if listing is None:
            return None
        files = {f: None for f in listing.split("\0") if f}
    else:
        ref = base
        if git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}") is None:
            if base != "HEAD":
                return None
            ref = EMPTY_TREE  # repo chưa có commit: mọi file là mới
        diff = git(root, "diff", "-U0", "--no-color", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/", ref, "--")
        if diff is None:
            return None
        files = parse_diff(diff)
        others = git(root, "ls-files", "--others", "--exclude-standard", "-z")
        for f in (others or "").split("\0"):
            if f:
                files[f] = None
    return {f: lines for f, lines in files.items()
            if not any(f.startswith(d) or f"/{d}" in f for d in SKIP_DIRS) and (root / f).is_file()}


# ---------------------------------------------------------------- Mốc kiểm tra và dấu hiệu bắt buộc

MOC_FILES = ("PLAN.md", ".agent/PLAN.md", ".agent/HANDOFF.md", "CLAUDE.md", "AGENTS.md")
MOC_START = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?\s*moc (?:kiem tra|test)")
HEADING = re.compile(r"^(#+)\s")


def read_text(path: Path, limit: int = 400_000) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def moc_text(root: Path) -> str:
    """Các đoạn "Mốc kiểm tra" (tiêu đề và phần dưới nó, hay gạch đầu dòng bắt đầu bằng nhãn đó và các dòng con)."""
    parts = []
    for name in MOC_FILES:
        lines = read_text(root / name).splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            head = HEADING.match(line)
            label = fold(line[head.end():] if head else line)
            if (head and ("moc kiem tra" in label or "moc test" in label)) or (not head and MOC_START.match(label)):
                j = i + 1
                if head:
                    while j < len(lines) and not (HEADING.match(lines[j]) and
                                                  len(HEADING.match(lines[j]).group(1)) <= len(head.group(1))):
                        j += 1
                else:
                    indent = len(line) - len(line.lstrip())
                    while j < len(lines) and lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) > indent:
                        j += 1
                parts.append("\n".join(lines[i:j]))
                i = j
                continue
            i += 1
    return "\n".join(parts)


def moc_commands(text: str) -> list:
    return [c.strip() for c in re.findall(r"`([^`\n]+)`", text) if c.strip()]


# (mẫu, ngôn ngữ, loại kiểm): lệnh trong Mốc kiểm tra đã phủ loại kiểm đó, bộ chạy không chạy lại.
COVER = [
    (r"\bcargo\s+(?:\+\S+\s+)?clippy\b", "rust", ("lint", "type")),
    (r"\bcargo\s+(?:\+\S+\s+)?(?:check|build)\b", "rust", ("type",)),
    (r"\bcargo\s+(?:\+\S+\s+)?fmt\b|\brustfmt\b", "rust", ("format",)),
    (r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:typecheck|type-check|check-types|tsc)\b|\b(?:vue-)?tsc\b", "ts", ("type",)),
    (r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?lint\b|\beslint\b|\bbiome\s+(?:check|lint|ci)\b", "ts", ("lint",)),
    (r"\bprettier\b|\bbiome\s+(?:format|check|ci)\b", "ts", ("format",)),
    (r"\bruff\s+check\b|\bruff\s+(?!format)\S|\bflake8\b|\bpylint\b", "python", ("lint",)),
    (r"\bruff\s+format\b|\bblack\b", "python", ("format",)),
    (r"\bmypy\b|\b(?:based)?pyright\b", "python", ("type",)),
    (r"\bshellcheck\b", "shell", ("lint",)),
    (r"\bswiftlint\b", "swift", ("lint",)),
    (r"\bswift\s+build\b|\bxcodebuild\b", "swift", ("type",)),
    (r"\bswiftformat\b|\bswift-format\b", "swift", ("format",)),
    (r"\bgo\s+vet\b|\bgolangci-lint\b|\bstaticcheck\b", "go", ("lint", "type")),
    (r"\bgo\s+build\b", "go", ("type",)),
    (r"\bgofmt\b|\bgo\s+fmt\b|\bgofumpt\b", "go", ("format",)),
    (r"\bgradlew?\b|\bmvn\b", "java", ("type",)),
    (r"\bgradlew?\b", "kotlin", ("type",)),
    (r"\bktlint\b|\bdetekt\b", "kotlin", ("lint",)),
    (r"\bdotnet\s+build\b", "csharp", ("type",)),
    (r"\bdotnet\s+format\b", "csharp", ("format",)),
    (r"\brubocop\b|\bstandardrb\b", "ruby", ("lint",)),
    (r"\bphpstan\b|\bpsalm\b", "php", ("lint",)),
    (r"\bdart\s+analyze\b|\bflutter\s+analyze\b", "dart", ("lint", "type")),
    (r"\bdart\s+format\b", "dart", ("format",)),
    (r"\bluacheck\b|\bselene\b", "lua", ("lint",)),
    (r"\bcppcheck\b|\bclang-tidy\b", "c_cpp", ("lint",)),
    (r"\bclang-format\b", "c_cpp", ("format",)),
    (r"\bhadolint\b", "docker", ("lint",)),
    (r"\bactionlint\b", "actions", ("lint",)),
    (r"\byamllint\b", "yaml", ("lint",)),
    (r"\bsemgrep\b", "*", ("security",)),
    (r"\bgitleaks\b|\btrufflehog\b", "*", ("secrets",)),
    (r"\bosv-scanner\b", "*", ("deps",)),
    (r"\barchctl\s+(?:\S+\s+)*?check\b[^`\n]*--strict", "*", ("arch",)),
    (r"\bmake\s+lint\b", "*", ("lint",)),
    (r"\bmake\s+(?:typecheck|type-check)\b", "*", ("type",)),
]


def coverage(commands: list) -> dict:
    """{(ngôn ngữ, loại): lệnh} mà Mốc kiểm tra đã phủ; ngôn ngữ "*" là mọi ngôn ngữ."""
    out = {}
    for cmd in commands:
        low = cmd.lower()
        for pattern, lang, kinds in COVER:
            if re.search(pattern, low):
                for kind in kinds:
                    out.setdefault((lang, kind), cmd)
    return out


def enforcement_corpus(root: Path, moc: str, pkg: dict) -> str:
    """Chữ của những nơi project tự bắt buộc công cụ: Mốc kiểm tra, CI, pre-commit, Makefile, script package.json."""
    texts = [moc, json.dumps((pkg or {}).get("scripts") or {})]
    for name in (".pre-commit-config.yaml", "Makefile", "makefile", "justfile", "tox.ini", "noxfile.py",
                 ".gitlab-ci.yml", "lefthook.yml", "Taskfile.yml"):
        texts.append(read_text(root / name, 100_000))
    for folder in (root / ".github" / "workflows", root / ".husky"):
        try:
            for f in sorted(folder.iterdir())[:30]:
                texts.append(read_text(f, 100_000))
        except OSError:
            pass
    return "\n".join(texts).lower()


# ---------------------------------------------------------------- phát hiện và lệnh kiểm

@dataclass
class Diag:
    path: object  # đường dẫn tương đối gốc repo, hay None khi lệnh trượt mà không rõ vị trí
    line: object
    col: object = None
    code: str = ""
    msg: str = ""
    level: str = "error"  # error | warning | info | style
    span: int = 1
    outside: bool = False
    syntax: bool = False  # lỗi cú pháp: chặn ở mọi dòng (file hỏng thì hỏng cả file)


@dataclass
class Check:
    lang: str
    kind: str
    tool: str
    argv: list = field(default_factory=list)
    cwd: object = None
    parse: object = None
    block: object = None  # (diag, enforced) -> chặn hay không
    enforced: bool = False
    source: str = "công cụ gốc"
    anywhere: bool = False  # lỗi (mức error) ngoài dòng đổi vẫn chặn: kiểu, biên dịch, cú pháp
    ok_codes: tuple = (0,)
    timeout: int = 300
    per_file: list = None  # chạy argv + [file] cho từng file
    inproc: object = None  # hàm kiểm ngay trong tiến trình: () -> list[Diag]
    missing_if: tuple = ()  # chuỗi trong output cho biết công cụ (thành phần) chưa cài


@dataclass
class Result:
    check: Check
    status: str = "ran"  # ran | error | timeout | missing
    block: list = field(default_factory=list)
    warn: list = field(default_factory=list)
    dropped: int = 0
    note: str = ""
    seconds: float = 0.0
    exit: object = None


def block_all(d, enforced):
    return True


def block_none(d, enforced):
    return False


def block_if_enforced(d, enforced):
    return enforced


def block_errors(d, enforced):
    return d.level == "error"


def block_errors_or_enforced(d, enforced):
    return d.level == "error" or enforced


def block_errors_warnings(d, enforced):
    return d.level in ("error", "warning") or enforced


# Mã ruff coi là lỗi thật khi project không tự cấu hình ruff. Nhóm B chỉ lấy mã bắt bug, bỏ thói quen như B007, B028,
# và B008 (FastAPI `Depends()` là cách viết chuẩn), B017 (`pytest.raises(Exception)`).
RUFF_REAL = ("E9", "F5", "F6", "F7", "F82", "PLE", "B002", "B003", "B006", "B012", "B015", "B016",
             "B018", "B020", "B021", "B023", "B025", "B026", "B029", "B030", "B031", "B032", "B033", "B035")
RULE_CODE = re.compile(r"^[A-Z]+\d+$")


def block_ruff(d, enforced):
    return enforced or d.syntax or not RULE_CODE.match(d.code or "") or d.code.startswith(RUFF_REAL)


def block_rubocop(d, enforced):
    return enforced or d.level == "error" or d.code.startswith("Lint/")


def block_luacheck(d, enforced):
    return enforced or d.code.startswith("E") or d.code in ("W113", "W121", "W122")


def block_actionlint(d, enforced):
    return enforced or d.code != "shellcheck"


def block_semgrep(d, enforced):
    return d.level == "error" or (enforced and d.level == "warning")


# ---------------------------------------------------------------- đọc output

GEN_RE = re.compile(r"^(?P<path>[^\s:][^:]*?):(?P<line>\d+)(?::(?P<col>\d+))?:\s*"
                    r"(?:(?P<level>fatal error|error|warning|note|info|information|style|performance|portability|remark)"
                    r"(?:\[(?P<code>[^\]]+)\])?\s*:\s*)?(?P<msg>.*)$")
TSC_RE = re.compile(r"^(?P<path>[^\s(][^(]*?)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<level>error|warning)\s+"
                    r"(?P<code>[A-Z]+\d+):\s*(?P<msg>.*?)(?:\s+\[[^\]]+\])?$")
MAVEN_RE = re.compile(r"^\[(?P<level>ERROR|WARNING)\]\s+(?P<path>/[^:\[]+?):\[(?P<line>\d+),(?P<col>\d+)\]\s*(?P<msg>.*)$")
TAIL_CODE = re.compile(r"\s*[\[(](?P<code>[A-Za-z][\w./:-]*)[\])]\s*$")
LEVELS = {"fatal error": "error", "error": "error", "warning": "warning", "note": "info", "info": "info",
          "information": "info", "remark": "info", "style": "style", "performance": "warning",
          "portability": "warning"}


def level_of(text, default="error") -> str:
    return LEVELS.get((text or "").lower(), default) if text else default


def parse_generic(out: str, err: str, default_level: str = "error") -> list:
    """Dạng `file:dòng[:cột]: [mức[mã]:] lời` (gcc, cargo --message-format=short, go vet, shellcheck -f gcc,
    swiftlint, actionlint, yamllint parsable, clang-tidy, javac), kèm dạng tsc/dotnet và Maven."""
    diags = []
    for raw in (out + "\n" + err).splitlines():
        line = re.sub(r"^vet:\s+", "", raw.rstrip())  # go vet in lỗi biên dịch kèm tiền tố "vet: "
        m = TSC_RE.match(line) or MAVEN_RE.match(line)
        if m:
            g = m.groupdict()
            diags.append(Diag(g["path"].strip(), int(g["line"]), int(g["col"]), g.get("code") or "", g["msg"].strip(),
                              level_of(g["level"].lower())))
            continue
        m = GEN_RE.match(line)
        if not m or m.group("path").startswith(("http", "warning", "error", "note")):
            continue
        msg, code = m.group("msg").strip(), m.group("code") or ""
        level = level_of(m.group("level"), default_level)
        y = re.match(r"^\[(error|warning)\]\s*(.*)$", msg)  # yamllint -f parsable
        if y:
            level, msg = y.group(1), y.group(2)
        t = TAIL_CODE.search(msg)
        if t and not code:
            code, msg = t.group("code"), msg[:t.start()].rstrip()
        diags.append(Diag(m.group("path"), int(m.group("line")), int(m.group("col")) if m.group("col") else None,
                          code, msg, level))
    return diags


def parse_ruff(out: str, err: str) -> list:
    try:
        items = json.loads(out or "[]")
    except ValueError:
        return []
    diags = []
    for it in items:
        loc = it.get("location") or {}
        code = it.get("code") or ""
        # ruff mới gắn mã `invalid-syntax` (cũ: không mã, hay E999) cho lỗi cú pháp
        syntax = not RULE_CODE.match(code) or code == "E999"
        diags.append(Diag(it.get("filename"), loc.get("row"), loc.get("column"), code or "invalid-syntax",
                          it.get("message", ""), "error", syntax=syntax))
    return diags


def parse_eslint(out: str, err: str) -> list:
    try:
        files = json.loads(out or "[]")
    except ValueError:
        return parse_stylish(out, err)
    diags = []
    for f in files:
        for m in f.get("messages") or []:
            diags.append(Diag(f.get("filePath"), m.get("line"), m.get("column"), m.get("ruleId") or "",
                              m.get("message", ""), "error" if m.get("severity") == 2 or m.get("fatal") else "warning"))
    return diags


def parse_stylish(out: str, err: str) -> list:
    """Định dạng mặc định của eslint: dòng tên file, rồi các dòng `  10:5  error  lời  luật`."""
    diags, current = [], None
    for line in (out + "\n" + err).splitlines():
        if line and not line[0].isspace() and ("/" in line or "." in line) and not line.startswith(("✖", ">")):
            current = line.strip()
            continue
        m = re.match(r"^\s+(\d+):(\d+)\s+(error|warning)\s+(.*?)(?:\s{2,}(\S+))?\s*$", line)
        if m and current:
            diags.append(Diag(current, int(m.group(1)), int(m.group(2)), m.group(5) or "", m.group(4), m.group(3)))
    return diags


def parse_script(out: str, err: str) -> list:
    """Output của script project (npm run lint, typecheck): thử tsc, gcc, rồi eslint stylish."""
    return parse_generic(out, err) or parse_stylish(out, err)


def parse_biome(out: str, err: str) -> list:
    diags = []
    for line in (out + "\n" + err).splitlines():
        m = re.match(r"^::(error|warning|notice)\s+(.*?)::(.*)$", line.strip())
        if not m:
            continue
        params = dict(p.split("=", 1) for p in m.group(2).split(",") if "=" in p)
        if params.get("file") and params.get("line"):
            diags.append(Diag(params["file"], int(params["line"]), int(params.get("col") or 0) or None,
                              params.get("title", ""), m.group(3), "error" if m.group(1) == "error" else "warning"))
    return diags


def parse_udiff(out: str, err: str) -> list:
    """Diff hợp nhất của công cụ định dạng (ruff format --diff, shfmt -d): mỗi hunk một phát hiện, theo dòng gốc."""
    diags, current = [], None
    for line in out.splitlines():
        if line.startswith("--- "):
            p = line[4:].split("\t")[0].strip()
            p = p.removeprefix("a/")
            current = None if p == "/dev/null" else re.sub(r"\.orig$", "", p)
        elif line.startswith("@@") and current:
            m = re.match(r"@@ -(\d+)(?:,(\d+))?", line)
            if m:
                start, count = int(m.group(1)), int(m.group(2)) if m.group(2) is not None else 1
                diags.append(Diag(current, max(start, 1), None, "format", "định dạng khác chuẩn của công cụ", "style",
                                  span=max(count, 1)))
    return diags


def parse_cargo_fmt(out: str, err: str) -> list:
    diags = []
    for line in (out + "\n" + err).splitlines():
        m = re.match(r"^Diff in (.+?)(?::(\d+):| at line (\d+):)\s*$", line.strip())
        if m:
            diags.append(Diag(m.group(1), int(m.group(2) or m.group(3)), None, "rustfmt", "định dạng khác rustfmt",
                              "style", span=3))
    return diags


def parse_file_list(prefix: str = ""):
    """Công cụ chỉ in tên file cần định dạng lại (gofmt -l, prettier --check, dart format)."""
    def parse(out: str, err: str) -> list:
        diags = []
        for line in (out + "\n" + err).splitlines():
            line = line.strip()
            if prefix:
                if not line.startswith(prefix):
                    continue
                line = line[len(prefix):].strip()
            if line and not line.startswith(("Checking", "Code style", "All matched", "Formatted")) and " " not in line:
                diags.append(Diag(line, None, None, "format", "định dạng khác chuẩn của công cụ", "style"))
        return diags
    return parse


def parse_gitleaks(out: str, err: str) -> list:
    try:
        items = json.loads(out or "[]")
    except ValueError:
        return []
    return [Diag(it.get("File"), it.get("StartLine"), it.get("StartColumn"), it.get("RuleID", ""),
                 f"có thể lộ khóa: {it.get('Description', '')} (giá trị đã che)", "error") for it in items or []]


def parse_semgrep(out: str, err: str) -> list:
    try:
        data = json.loads(out or "{}")
    except ValueError:
        return []
    sev = {"ERROR": "error", "WARNING": "warning", "INFO": "info"}
    diags = []
    for r in data.get("results") or []:
        extra = r.get("extra") or {}
        level = sev.get(extra.get("severity"), "warning")
        # Luật tương thích phiên bản cũ, thói quen, hiệu năng: báo nhưng không coi là lỗi thật.
        if level == "error" and (extra.get("metadata") or {}).get("category") in SEMGREP_SOFT:
            level = "warning"
        diags.append(Diag(r.get("path"), (r.get("start") or {}).get("line"), (r.get("start") or {}).get("col"),
                          r.get("check_id", "").split(".")[-1], (extra.get("message") or "").strip().splitlines()[0]
                          if extra.get("message") else "", level))
    return diags


SEMGREP_SOFT = {"compatibility", "best-practice", "maintainability", "performance", "portability", "style"}


def parse_osv(out: str, err: str) -> list:
    try:
        data = json.loads(out or "{}")
    except ValueError:
        return []
    diags = []
    for res in data.get("results") or []:
        path = (res.get("source") or {}).get("path")
        for pkg in res.get("packages") or []:
            info = pkg.get("package") or {}
            vulns = {v.get("id"): v for v in pkg.get("vulnerabilities") or [] if isinstance(v, dict)}
            # Một lỗ hổng thường có nhiều mục là bí danh của nhau (PYSEC và GHSA): gộp theo `groups`, mỗi nhóm báo một lần.
            groups = [g for g in pkg.get("groups") or [] if isinstance(g, dict) and g.get("ids")]
            seen = {i for g in groups for i in g["ids"]}
            groups += [{"ids": [i]} for i in vulns if i not in seen]
            for g in groups:
                members = [vulns[i] for i in g["ids"] if i in vulns] or [{"id": g["ids"][0]}]
                best = next((v for v in members if v.get("summary")), members[0])
                text = best.get("summary") or (best.get("details") or "").strip().split("\n")[0][:160] or "có lỗ hổng"
                cve = next((a for a in g.get("aliases") or best.get("aliases") or [] if str(a).startswith("CVE-")), "")
                sev = f", mức {g['max_severity']}" if g.get("max_severity") else ""
                extra = f" ({cve}{sev})" if cve else (f" ({sev[2:]})" if sev else "")
                diags.append(Diag(path, None, None, best.get("id", ""),
                                  f"{info.get('name')}@{info.get('version')}: {text}{extra}", "warning"))
    return diags


def parse_pyright(out: str, err: str) -> list:
    try:
        data = json.loads(out or "{}")
    except ValueError:
        return []
    return [Diag(d.get("file"), ((d.get("range") or {}).get("start") or {}).get("line", 0) + 1,
                 ((d.get("range") or {}).get("start") or {}).get("character", 0) + 1, d.get("rule") or "",
                 d.get("message", ""), "error" if d.get("severity") == "error" else "warning")
            for d in data.get("generalDiagnostics") or []]


def parse_dart(out: str, err: str) -> list:
    diags = []
    for line in (out + "\n" + err).splitlines():
        parts = line.split("|")
        if len(parts) >= 8 and parts[4].isdigit():
            level = {"ERROR": "error", "WARNING": "warning"}.get(parts[0], "info")
            diags.append(Diag(parts[3], int(parts[4]), int(parts[5]), parts[2], "|".join(parts[7:]), level))
    return diags


def parse_hadolint(out: str, err: str) -> list:
    diags = []
    for line in (out + "\n" + err).splitlines():
        m = re.match(r"^(?P<path>\S+?):(?P<line>\d+)\s+(?P<code>\S+)\s+(?P<level>error|warning|info|style):\s*(?P<msg>.*)$",
                     line.strip())
        if m:
            diags.append(Diag(m["path"], int(m["line"]), None, m["code"], m["msg"], level_of(m["level"])))
    return diags or parse_generic(out, err)


def parse_rubocop(out: str, err: str) -> list:
    diags = []
    for d in parse_generic(out, err):
        m = re.match(r"^(?P<lv>[FEWCR]):\s*(?:\[Correctable\]\s*)?(?:(?P<code>[A-Z]\w+/\w+):\s*)?(?P<msg>.*)$", d.msg)
        if m:
            d.level = {"F": "error", "E": "error", "W": "warning"}.get(m["lv"], "style")
            d.code, d.msg = m["code"] or "", m["msg"]
        diags.append(d)
    return diags


def parse_luacheck(out: str, err: str) -> list:
    diags = []
    for d in parse_generic(out, err, "warning"):
        m = re.match(r"^\((?P<code>[EW]\d{3})\)\s*(?P<msg>.*)$", d.msg)
        if m:
            d.code, d.msg = m["code"], m["msg"]
            d.level = "error" if d.code.startswith("E") else "warning"
        diags.append(d)
    return diags


def parse_php_lint(out: str, err: str) -> list:
    diags = []
    for line in (out + "\n" + err).splitlines():
        m = re.search(r"(?:PHP\s+)?(?:Parse|Fatal) error:\s*(?P<msg>.*?) in (?P<path>\S+) on line (?P<line>\d+)", line)
        if m:
            diags.append(Diag(m["path"], int(m["line"]), None, "php-l", m["msg"], "error", syntax=True))
    return diags


def parse_ruby_wc(out: str, err: str) -> list:
    diags = []
    for line in (out + "\n" + err).splitlines():
        m = re.match(r"^(?P<path>[^:]+):(?P<line>\d+):\s*(?P<msg>.*)$", line.strip())
        if m:
            level = "warning" if m["msg"].startswith("warning") else "error"
            diags.append(Diag(m["path"], int(m["line"]), None, "ruby -wc", m["msg"], level))
    return diags


def parse_shell_n(out: str, err: str) -> list:
    """`bash -n f`: `f: line 3: syntax error ...`; `zsh -n f`: `f:3: parse error ...`."""
    diags = []
    for line in (out + "\n" + err).splitlines():
        m = re.match(r"^(?P<path>[^:]+):(?: line)? ?(?P<line>\d+):\s*(?P<msg>.*)$", line.strip())
        if m:
            diags.append(Diag(m["path"], int(m["line"]), None, "syntax", m["msg"], "error", syntax=True))
    return diags


def parse_node_check(out: str, err: str) -> list:
    """`node --check f`: dòng đầu `f:3`, cuối có `SyntaxError: ...`."""
    m = re.search(r"^(?P<path>/[^\n:]+):(?P<line>\d+)\s*$", out + "\n" + err, re.M)
    s = re.search(r"^(SyntaxError: .*)$", out + "\n" + err, re.M)
    if m and s:
        return [Diag(m["path"], int(m["line"]), None, "syntax", s.group(1), "error")]
    return []


# ---------------------------------------------------------------- kiểm trong tiến trình

def check_python_syntax(root: Path, files: list):
    def run():
        diags = []
        for f in files:
            try:
                compile(read_text(root / f, 10_000_000), f, "exec", dont_inherit=True)
            except SyntaxError as exc:
                diags.append(Diag(f, exc.lineno, exc.offset, "syntax", exc.msg, "error", syntax=True))
            except ValueError as exc:
                diags.append(Diag(f, None, None, "syntax", str(exc), "error", syntax=True))
        return diags
    return run


def check_json(root: Path, files: list):
    def run():
        diags = []
        for f in files:
            text = read_text(root / f, 20_000_000)
            try:
                json.loads(text or "null")
            except ValueError as exc:
                if re.search(r"^\s*(//|/\*)", text, re.M):  # JSON có chú thích (JSONC): không phải lỗi, chưa kiểm
                    continue
                diags.append(Diag(f, getattr(exc, "lineno", None), getattr(exc, "colno", None), "json",
                                  getattr(exc, "msg", str(exc)), "error", syntax=True))
        return diags
    return run


def check_toml(root: Path, files: list):
    def run():
        diags = []
        for f in files:
            try:
                tomllib.loads(read_text(root / f, 5_000_000))
            except tomllib.TOMLDecodeError as exc:
                m = re.search(r"line (\d+), column (\d+)", str(exc))
                diags.append(Diag(f, int(m.group(1)) if m else None, int(m.group(2)) if m else None, "toml",
                                  str(exc), "error", syntax=True))
        return diags
    return run


# ---------------------------------------------------------------- lập kế hoạch

@dataclass
class Ctx:
    root: Path
    changed: dict
    moc: str
    covered: dict
    corpus: str
    offline: bool = False
    by_lang: dict = field(default_factory=dict)
    base: str = "HEAD"


@dataclass
class Plan:
    checks: list = field(default_factory=list)
    missing: list = field(default_factory=list)  # (ngôn ngữ, loại, công cụ, cách cài)
    covered: list = field(default_factory=list)  # (ngôn ngữ, loại, lệnh trong Mốc, ghi chú)
    notes: list = field(default_factory=list)


def find_bin(name: str, *dirs: Path):
    """Công cụ trong project trước (node_modules/.bin, .venv/bin, vendor/bin), rồi PATH."""
    for d in dirs:
        for sub in ("node_modules/.bin", ".venv/bin", "venv/bin", "vendor/bin"):
            cand = Path(d) / sub / name
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
    return shutil.which(name)


def nearest(root: Path, rel: str, names: tuple):
    """Thư mục gần file nhất (đi lên tới gốc repo) có một trong các file `names`."""
    d = (root / rel).parent
    while True:
        if any((d / n).exists() for n in names):
            return d
        if d == root or root not in d.parents:
            return None
        d = d.parent


def group_by(root: Path, files: list, names: tuple, top: str = "") -> dict:
    """{thư mục gốc gói: [file]}; `top` là chuỗi trong file cấu hình đánh dấu gốc workspace (lấy gốc cao nhất)."""
    groups = {}
    for f in files:
        d = nearest(root, f, names)
        if d is None:
            groups.setdefault(None, []).append(f)
            continue
        if top:
            up = d.parent
            while root == up or root in up.parents:
                if any(top in read_text(up / n, 200_000) for n in names if (up / n).exists()):
                    d = up
                if up == root:
                    break
                up = up.parent
        groups.setdefault(d, []).append(f)
    return groups


def requires_python(root: Path):
    """(major, minor) nhỏ nhất project cần theo `requires-python` của pyproject.toml, hay None."""
    m = re.search(r'requires-python\s*=\s*"[^"]*?>=?\s*(\d+)\.(\d+)', read_text(root / "pyproject.toml"))
    return (int(m.group(1)), int(m.group(2))) if m else None


def pyproject_has(root: Path, *tables: str) -> bool:
    text = read_text(root / "pyproject.toml")
    return any(f"[tool.{t}" in text for t in tables)


def mentions(corpus: str, *tools: str) -> bool:
    # cho phép đuôi gạch nối: "ruff-pre-commit", "shellcheck-py" vẫn là project gọi công cụ đó
    return any(re.search(rf"(?<![\w-]){re.escape(t)}(?!\w)", corpus) for t in tools)


def add_missing(plan: Plan, lang: str, kind: str, tool: str):
    plan.missing.append((lang, kind, tool, INSTALL.get(tool, "")))


def is_covered(ctx: Ctx, plan: Plan, lang: str, kind: str) -> bool:
    cmd = ctx.covered.get((lang, kind)) or ctx.covered.get(("*", kind))
    note = ""
    if not cmd and kind == "format" and ctx.covered.get((lang, "lint")):
        # Mốc đã có lint của ngôn ngữ này: project tự chọn chuẩn kiểm tĩnh, không thêm luật định dạng ngoài chuẩn đó.
        cmd, note = ctx.covered[(lang, "lint")], "chuẩn kiểm tĩnh project tự chọn, không thêm kiểm định dạng"
    if cmd:
        if (lang, kind, cmd, note) not in plan.covered:
            plan.covered.append((lang, kind, cmd, note))
        return True
    return False


def package_manager(d: Path) -> str:
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun")):
        if (d / lock).exists():
            return pm
    return "npm"


def plan_python(ctx: Ctx, plan: Plan, files: list):
    root = ctx.root
    ruff = find_bin("ruff", root)
    configured = (root / "ruff.toml").exists() or (root / ".ruff.toml").exists() or pyproject_has(root, "ruff")
    lint_covered = is_covered(ctx, plan, "python", "lint")
    if not lint_covered:
        if ruff:
            # Project có cấu hình ruff, hay gọi ruff ở CI, pre-commit, Makefile: dùng đúng luật project chạy (mặc định
            # của ruff khi không có cấu hình) và mọi phát hiện đều chặn. Không thì bộ luật đầy đủ, phong cách chỉ báo.
            enforced = configured or mentions(ctx.corpus, "ruff")
            # --force-exclude: file truyền thẳng vẫn theo exclude của project (đề bài eval, file sinh ra…).
            # --isolated khi project không có cấu hình: không mượn ruff.toml của thư mục cha (exclude của nó có thể
            # bỏ qua cả project, như fixture test nằm trong .tmp/ của agent-stack).
            argv = [ruff, "check", "--no-cache", "--force-exclude", "--output-format", "json", "--exit-zero"]
            if not configured:
                argv.append("--isolated")
            if not enforced:  # bỏ cặp luật docstring xung đột nhau và luật trùng formatter
                argv += ["--select", "ALL", "--ignore", "D203,D213,COM812,ISC001"]
            source = "cấu hình ruff của project" if configured else ("luật mặc định ruff, project có gọi ruff"
                                                                    if enforced else "công cụ gốc")
            plan.checks.append(Check("python", "lint", "ruff", argv + files, root, parse_ruff, block_ruff, enforced,
                                     source))
        else:
            add_missing(plan, "python", "lint", "ruff")
    if not ruff and not lint_covered:  # thiếu ruff: ít nhất kiểm cú pháp, bằng đúng bản Python project cần
        need = requires_python(root)
        if need and need > sys.version_info[:2]:
            plan.missing.append(("python", "syntax", f"python{need[0]}.{need[1]}",
                                 f"project cần Python ≥ {need[0]}.{need[1]}, máy chạy checks.py là "
                                 f"{sys.version_info[0]}.{sys.version_info[1]}; cài ruff để kiểm cú pháp"))
        else:
            plan.checks.append(Check("python", "syntax", "compile() của Python", cwd=root, block=block_all,
                                     anywhere=True, inproc=check_python_syntax(root, files), source="có sẵn"))
    if ruff and not is_covered(ctx, plan, "python", "format"):
        enforced = mentions(ctx.corpus, "ruff format", "black") or pyproject_has(root, "ruff.format", "black")
        plan.checks.append(Check("python", "format", "ruff format",
                                 [ruff, "format", "--check", "--diff", "--no-cache", "--force-exclude",
                                  *([] if configured else ["--isolated"]), *files], root, parse_udiff,
                                 block_if_enforced, enforced, ok_codes=(0, 1)))
    if not is_covered(ctx, plan, "python", "type"):
        if pyproject_has(root, "mypy") or (root / "mypy.ini").exists() or (root / ".mypy.ini").exists() \
                or "[mypy" in read_text(root / "setup.cfg"):
            mypy = find_bin("mypy", root)
            if mypy:
                plan.checks.append(Check("python", "type", "mypy",
                                         [mypy, "--show-column-numbers", "--no-error-summary", "--no-pretty",
                                          "--cache-dir", os.devnull, *files], root, parse_generic, block_errors, True,
                                         "cấu hình mypy của project", anywhere=True, ok_codes=(0, 1)))
            else:
                add_missing(plan, "python", "type", "mypy")
        elif pyproject_has(root, "pyright", "basedpyright") or (root / "pyrightconfig.json").exists():
            pyright = find_bin("pyright", root)
            if pyright:
                plan.checks.append(Check("python", "type", "pyright", [pyright, "--outputjson", *files], root,
                                         parse_pyright, block_errors, True, "cấu hình pyright của project",
                                         anywhere=True, ok_codes=(0, 1)))
            else:
                add_missing(plan, "python", "type", "pyright")
        else:
            plan.notes.append("Python: project chưa cấu hình kiểm kiểu (mypy hay pyright); router gợi ý khi project lớn.")


def plan_ts(ctx: Ctx, plan: Plan, files: list):
    root = ctx.root
    for pkg_dir, group in group_by(root, files, ("package.json",)).items():
        d = pkg_dir or root
        pkg = read_json(d / "package.json")
        scripts = pkg.get("scripts") or {}
        pm = package_manager(d)
        rel = [safe_arg(os.path.relpath(root / f, d)) for f in group]
        where = os.path.relpath(d, root)
        label = "" if where == "." else f" ({where})"
        # kiểu
        if not is_covered(ctx, plan, "ts", "type"):
            script = next((s for s in ("typecheck", "type-check", "check-types", "tsc") if s in scripts), None)
            tsconfig = nearest(root, group[0], ("tsconfig.json",))
            if script:
                plan.checks.append(Check("ts", "type", f"{pm} run {script}{label}", [pm, "run", "--silent", script], d,
                                         parse_script, block_errors, True, "script của project", anywhere=True,
                                         timeout=600))
            elif tsconfig and any(f.endswith((".ts", ".tsx", ".mts", ".cts", ".vue")) for f in group):
                tsc = find_bin("tsc", d, root)
                if tsc:
                    # tsconfig kiểu "solution" (mẫu Vite: "files": [] và references) không tự kiểm file nào:
                    # kiểm từng config được tham chiếu.
                    for cfg in ts_configs(tsconfig / "tsconfig.json"):
                        name = os.path.relpath(cfg, root)
                        plan.checks.append(Check("ts", "type", f"tsc --noEmit -p {name}",
                                                 [tsc, "--noEmit", "--pretty", "false", "-p", str(cfg)], d,
                                                 parse_generic, block_errors, True, "công cụ gốc", anywhere=True,
                                                 timeout=600))
                else:
                    add_missing(plan, "ts", "type", "tsc")
            else:
                ts_files = [f for f in group if f.endswith((".ts", ".tsx", ".mts", ".cts", ".vue"))]
                if ts_files:
                    plan.missing.append(("ts", "type", "tsconfig.json", "project chưa có tsconfig hay script "
                                         "typecheck nên chưa kiểm kiểu; ghi lệnh vào Mốc kiểm tra"))
                # node --check không hiểu JSX: file .js chỉ kiểm khi project không dùng framework JSX
                deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
                jsx = any(k in deps for k in ("react", "preact", "vue", "solid-js", "@babel/preset-react"))
                js = [f for f in group if f.endswith((".mjs", ".cjs")) or (f.endswith(".js") and not jsx)]
                unchecked = [f for f in group if f not in js and f not in ts_files]
                if unchecked:  # .jsx, .svelte, .js dùng JSX: không có công cụ nào kiểm được, không được im lặng
                    plan.missing.append(("ts", "syntax", "tsconfig.json hay linter",
                                         f"{len(unchecked)} file JSX/Svelte chưa kiểm cú pháp vì project chưa có "
                                         "tsconfig, script typecheck hay linter"))
                node = shutil.which("node")
                if js and node:
                    plan.checks.append(Check("ts", "syntax", "node --check", [node, "--check"], root,
                                             parse_node_check, block_all, anywhere=True, per_file=js))
                elif js:
                    add_missing(plan, "ts", "syntax", "node")
        # lint
        if not is_covered(ctx, plan, "ts", "lint"):
            eslint_cfg = any((d / n).exists() or (root / n).exists() for n in (
                "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts", ".eslintrc",
                ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml")) \
                or "eslintConfig" in pkg
            biome_cfg = (d / "biome.json").exists() or (d / "biome.jsonc").exists() or (root / "biome.json").exists()
            fixes = "lint" in scripts and re.search(r"(^|\s)(--fix|--write|-w|--apply)(\s|$)", scripts["lint"])
            if fixes:
                plan.notes.append(f"TS/JS{label}: không chạy `{pm} run lint` vì script tự sửa file "
                                  f"(`{scripts['lint']}`); dùng thẳng linter nếu có cấu hình.")
            if "lint" in scripts and not fixes:
                plan.checks.append(Check("ts", "lint", f"{pm} run lint{label}", [pm, "run", "--silent", "lint"], d,
                                         parse_script, block_errors, True, "script của project", timeout=600))
            elif eslint_cfg:
                eslint = find_bin("eslint", d, root)
                if eslint:
                    plan.checks.append(Check("ts", "lint", f"eslint{label}", [eslint, "--format", "json", *rel], d,
                                             parse_eslint, block_errors, True, "cấu hình eslint của project",
                                             ok_codes=(0, 1)))
                else:
                    add_missing(plan, "ts", "lint", "eslint")
            elif biome_cfg:
                biome = find_bin("biome", d, root)
                if biome:
                    plan.checks.append(Check("ts", "lint", f"biome lint{label}",
                                             [biome, "lint", "--reporter=github", *rel], d, parse_biome,
                                             block_errors, True, "cấu hình biome của project", ok_codes=(0, 1)))
                else:
                    add_missing(plan, "ts", "lint", "biome")
            else:
                plan.notes.append(f"TS/JS{label}: project chưa có linter (eslint hay biome), nên chưa kiểm lint; "
                                  "gợi ý cấu hình eslint.")
        # định dạng
        prettier_cfg = any(p.name.startswith((".prettierrc", "prettier.config")) for p in _ls(d)) or "prettier" in pkg
        if prettier_cfg and not is_covered(ctx, plan, "ts", "format"):
            prettier = find_bin("prettier", d, root)
            if prettier:
                plan.checks.append(Check("ts", "format", f"prettier --check{label}",
                                         [prettier, "--check", "--log-level", "warn", *rel], d,
                                         parse_file_list("[warn]"), block_if_enforced,
                                         mentions(ctx.corpus, "prettier"), ok_codes=(0, 1, 2)))
            else:
                add_missing(plan, "ts", "format", "prettier")


def ts_configs(cfg: Path) -> list:
    """Các tsconfig cần kiểm: chính nó, hay các config trong "references" khi nó là tsconfig kiểu solution."""
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", read_text(cfg), flags=re.S)
    block = re.search(r'"references"\s*:\s*\[(.*?)\]', text, re.S)
    if not block:
        return [cfg]
    out = []
    for ref in re.findall(r'"path"\s*:\s*"([^"]+)"', block.group(1)):
        target = (cfg.parent / ref).resolve()
        target = target / "tsconfig.json" if target.is_dir() else target
        if target.is_file() and target not in out:
            out.append(target)
    solution_only = re.search(r'"files"\s*:\s*\[\s*\]', text)
    if not out:  # references rỗng hay trỏ tới file không có: kiểm chính config này
        return [cfg]
    return out if solution_only else [cfg, *out]


def _ls(d: Path) -> list:
    try:
        return list(d.iterdir())
    except OSError:
        return []


def read_json(path: Path) -> dict:
    try:
        data = json.loads(read_text(path) or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def plan_rust(ctx: Ctx, plan: Plan, files: list):
    root = ctx.root
    cargo = shutil.which("cargo")
    for crate in group_by(root, files, ("Cargo.toml",), top="[workspace]"):
        if crate is None:
            plan.notes.append("Rust: file .rs không thuộc crate nào (không thấy Cargo.toml).")
            continue
        label = "" if crate == root else f" ({os.path.relpath(crate, root)})"
        lint_done = is_covered(ctx, plan, "rust", "lint")
        type_done = is_covered(ctx, plan, "rust", "type")
        if not cargo:
            add_missing(plan, "rust", "lint", "cargo")
            continue
        workspace = ["--workspace"] if "[workspace]" in read_text(crate / "Cargo.toml") else []
        if not lint_done:
            if shutil.which("cargo-clippy"):
                enforced = mentions(ctx.corpus, "clippy")
                extra = [] if enforced else ["--", "-W", "clippy::pedantic"]
                plan.checks.append(Check("rust", "lint", f"cargo clippy{label}",
                                         ["cargo", "clippy", *workspace, "--all-targets", "--message-format=short",
                                          "--quiet", *extra], crate, parse_generic, block_errors, enforced,
                                         anywhere=True, ok_codes=(0, 101), timeout=1200,
                                         missing_if=("no such command: `clippy`", "no such subcommand")))
            else:
                add_missing(plan, "rust", "lint", "cargo-clippy")
                if not type_done:
                    plan.checks.append(Check("rust", "type", f"cargo check{label}",
                                             ["cargo", "check", *workspace, "--all-targets", "--message-format=short",
                                              "--quiet"], crate, parse_generic, block_errors, True, anywhere=True,
                                             ok_codes=(0, 101), timeout=1200))
        if not is_covered(ctx, plan, "rust", "format") and shutil.which("cargo-fmt"):
            plan.checks.append(Check("rust", "format", f"cargo fmt --check{label}", ["cargo", "fmt", "--all", "--check"],
                                     crate, parse_cargo_fmt, block_if_enforced,
                                     mentions(ctx.corpus, "cargo fmt", "rustfmt"), ok_codes=(0, 1)))


def plan_go(ctx: Ctx, plan: Plan, files: list):
    root = ctx.root
    go = shutil.which("go")
    for mod, group in group_by(root, files, ("go.mod",)).items():
        d = mod or root
        if not is_covered(ctx, plan, "go", "lint"):
            if go and mod:
                plan.checks.append(Check("go", "lint", "go vet ./...", [go, "vet", "./..."], d, parse_generic,
                                         block_all, True, anywhere=True, ok_codes=(0, 1), timeout=600))
            elif not go:
                add_missing(plan, "go", "lint", "go")
            else:
                plan.missing.append(("go", "lint", "go.mod", "file .go không thuộc module nào nên chưa chạy go vet"))
            cfg = any((d / n).exists() for n in (".golangci.yml", ".golangci.yaml", ".golangci.toml", ".golangci.json"))
            if cfg:
                gl = shutil.which("golangci-lint")
                if gl:
                    plan.checks.append(Check("go", "lint", "golangci-lint run", [gl, "run", "./..."], d, parse_generic,
                                             block_all, True, "cấu hình golangci-lint của project", ok_codes=(0, 1),
                                             timeout=600))
                else:
                    add_missing(plan, "go", "lint", "golangci-lint")
        gofmt = shutil.which("gofmt")
        if gofmt and not is_covered(ctx, plan, "go", "format"):
            plan.checks.append(Check("go", "format", "gofmt -l", [gofmt, "-l", *[safe_arg(os.path.relpath(root / f, d))
                                                                               for f in group]], d,
                                     parse_file_list(), block_if_enforced, mentions(ctx.corpus, "gofmt", "go fmt")))


def plan_swift(ctx: Ctx, plan: Plan, files: list):
    root = ctx.root
    if not is_covered(ctx, plan, "swift", "lint"):
        sl = shutil.which("swiftlint")
        configured = (root / ".swiftlint.yml").exists() or (root / ".swiftlint.yaml").exists()
        if sl:
            plan.checks.append(Check("swift", "lint", "swiftlint", [sl, "lint", "--quiet", "--reporter", "xcode", *files],
                                     root, parse_generic, block_errors, configured or mentions(ctx.corpus, "swiftlint"),
                                     "cấu hình swiftlint của project" if configured else "công cụ gốc",
                                     ok_codes=(0, 2), timeout=600))
        else:
            add_missing(plan, "swift", "lint", "swiftlint")
    swiftc = shutil.which("swiftc")
    if swiftc:
        plan.checks.append(Check("swift", "syntax", "swiftc -parse", [swiftc, "-parse", *files], root, parse_generic,
                                 block_errors, anywhere=True, ok_codes=(0, 1)))
    else:
        add_missing(plan, "swift", "syntax", "swiftc")
    if not is_covered(ctx, plan, "swift", "type"):
        if (root / "Package.swift").exists() and shutil.which("swift"):
            plan.checks.append(Check("swift", "type", "swift build", ["swift", "build"], root, parse_generic,
                                     block_errors, True, anywhere=True, ok_codes=(0, 1), timeout=1200))
        else:
            plan.notes.append("Swift: chưa kiểm biên dịch vì project không có Package.swift; ghi lệnh build "
                              "(xcodebuild hay script của project) vào Mốc kiểm tra.")


def is_zsh(path: Path) -> bool:
    """Script zsh (đuôi .zsh hay shebang zsh): shellcheck không hỗ trợ, báo SC1071 giả."""
    return str(path).endswith(".zsh") or bool(re.match(r"#!.*\bzsh\b", read_text(path, 200).split("\n", 1)[0]))


def plan_shell(ctx: Ctx, plan: Plan, files: list):
    root = ctx.root
    zsh = [f for f in files if is_zsh(root / f)]
    posix = [f for f in files if f not in zsh]
    if posix and not is_covered(ctx, plan, "shell", "lint"):
        sc = shutil.which("shellcheck")
        if sc:
            enforced = (root / ".shellcheckrc").exists() or mentions(ctx.corpus, "shellcheck")
            plan.checks.append(Check("shell", "lint", "shellcheck", [sc, "-f", "gcc", "-x", *posix], root,
                                     parse_generic, block_errors_warnings, enforced, ok_codes=(0, 1)))
        else:
            add_missing(plan, "shell", "lint", "shellcheck")
            plan.checks.append(Check("shell", "syntax", "bash -n", ["bash", "-n"], root, parse_shell_n, block_all,
                                     anywhere=True, per_file=posix, source="có sẵn"))
    if zsh and shutil.which("zsh"):
        plan.checks.append(Check("shell", "syntax", "zsh -n", ["zsh", "-n"], root, parse_shell_n, block_all,
                                 anywhere=True, per_file=zsh, source="có sẵn"))
    shfmt = shutil.which("shfmt")
    if posix and shfmt and mentions(ctx.corpus, "shfmt") and not is_covered(ctx, plan, "shell", "format"):
        plan.checks.append(Check("shell", "format", "shfmt -d", [shfmt, "-d", *posix], root, parse_udiff,
                                 block_if_enforced, True, ok_codes=(0, 1)))


def plan_c(ctx: Ctx, plan: Plan, files: list):
    root = ctx.root
    if not is_covered(ctx, plan, "c_cpp", "lint"):
        cc = shutil.which("cppcheck")
        if cc:
            plan.checks.append(Check("c_cpp", "lint", "cppcheck",
                                     [cc, "--enable=warning,style,performance,portability", "--quiet", "--inline-suppr",
                                      "--template={file}:{line}:{column}: {severity}: {message} [{id}]",
                                      "--suppress=missingIncludeSystem", "--suppress=missingInclude",
                                      "--suppress=unmatchedSuppression", *files], root, parse_generic,
                                     block_errors_or_enforced if mentions(ctx.corpus, "cppcheck") else block_errors,
                                     mentions(ctx.corpus, "cppcheck")))
        else:
            add_missing(plan, "c_cpp", "lint", "cppcheck")
        cdb = next((d for d in (root, root / "build") if (d / "compile_commands.json").exists()), None)
        if (root / ".clang-tidy").exists() and cdb:
            ct = shutil.which("clang-tidy")
            if ct:
                plan.checks.append(Check("c_cpp", "lint", "clang-tidy", [ct, "-p", str(cdb), "--quiet", *files], root,
                                         parse_generic, block_errors_warnings, True, "cấu hình clang-tidy của project",
                                         ok_codes=(0, 1), timeout=600))
            else:
                add_missing(plan, "c_cpp", "lint", "clang-tidy")
    if (root / ".clang-format").exists() and not is_covered(ctx, plan, "c_cpp", "format"):
        cf = shutil.which("clang-format")
        if cf:
            plan.checks.append(Check("c_cpp", "format", "clang-format --dry-run", [cf, "--dry-run", *files], root,
                                     parse_generic, block_if_enforced, mentions(ctx.corpus, "clang-format")))
    if not is_covered(ctx, plan, "c_cpp", "type"):
        plan.notes.append("C/C++: biên dịch chỉ kiểm qua lệnh build trong Mốc kiểm tra; project chưa ghi thì nên ghi.")


def plan_jvm(ctx: Ctx, plan: Plan, files: list, lang: str):
    root = ctx.root
    if lang == "kotlin" and not is_covered(ctx, plan, "kotlin", "lint"):
        kt = shutil.which("ktlint")
        if kt:
            plan.checks.append(Check("kotlin", "lint", "ktlint", [kt, "--reporter=plain", *files], root, parse_generic,
                                     block_if_enforced, mentions(ctx.corpus, "ktlint") or ((root / ".editorconfig").exists()
                                     and "ktlint" in read_text(root / ".editorconfig")), ok_codes=(0, 1)))
        else:
            add_missing(plan, "kotlin", "lint", "ktlint")
    if is_covered(ctx, plan, lang, "type"):
        return
    task = "compileKotlin" if lang == "kotlin" else "compileJava"
    if (root / "gradlew").exists():
        plan.checks.append(Check(lang, "type", f"./gradlew {task}", ["./gradlew", "-q", "--offline", task], root,
                                 parse_generic, block_errors, True, "build của project", anywhere=True,
                                 ok_codes=(0, 1), timeout=1200))
    elif (root / "pom.xml").exists():
        mvn = shutil.which("mvn")
        if mvn:
            plan.checks.append(Check(lang, "type", "mvn -o compile", [mvn, "-q", "-o", "compile"], root, parse_generic,
                                     block_errors, True, "build của project", anywhere=True, ok_codes=(0, 1),
                                     timeout=1200))
        else:
            add_missing(plan, lang, "type", "mvn")
    elif lang == "java":
        javac = shutil.which("javac")
        if javac and subprocess_ok([javac, "-version"]):
            out_dir = tempfile.mkdtemp(prefix="checks-javac-")  # file .class bỏ đi; xóa khi script thoát
            atexit.register(shutil.rmtree, out_dir, True)
            plan.checks.append(Check("java", "type", "javac -Xlint:all", [javac, "-Xlint:all", "-d", out_dir, *files],
                                     root, parse_generic, block_errors, True, anywhere=True, ok_codes=(0, 1)))
        else:
            add_missing(plan, "java", "type", "javac")
    else:
        plan.notes.append("Kotlin: chưa kiểm biên dịch vì project không có gradlew; ghi lệnh build vào Mốc kiểm tra.")


def subprocess_ok(argv: list) -> bool:
    """Lệnh chạy được (macOS có /usr/bin/javac giả khi chưa cài JDK: chạy là báo lỗi)."""
    try:
        return subprocess.run(argv, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def plan_misc(ctx: Ctx, plan: Plan, lang: str, files: list):
    """C#, Ruby, PHP, Dart, Lua, Dockerfile, GitHub Actions, YAML, JSON, TOML."""
    root = ctx.root
    if lang == "csharp" and not is_covered(ctx, plan, "csharp", "type"):
        dotnet = shutil.which("dotnet")
        target = nearest_glob(root, files[0], ("*.sln", "*.csproj"))
        if dotnet and target:
            plan.checks.append(Check("csharp", "type", "dotnet build", [dotnet, "build", "--nologo", "-v", "q",
                                                                        "-clp:NoSummary"], target, parse_generic,
                                     block_errors, True, anywhere=True, ok_codes=(0, 1), timeout=1200))
        elif not dotnet:
            add_missing(plan, "csharp", "type", "dotnet")
        else:
            plan.notes.append("C#: không thấy .sln hay .csproj nên chưa kiểm biên dịch.")
    elif lang == "ruby":
        if shutil.which("ruby"):
            plan.checks.append(Check("ruby", "syntax", "ruby -wc", ["ruby", "-wc"], root, parse_ruby_wc, block_errors,
                                     anywhere=True, per_file=files, source="có sẵn"))
        if not is_covered(ctx, plan, "ruby", "lint"):
            rc = find_bin("rubocop", root) or (str(root / "bin" / "rubocop") if (root / "bin" / "rubocop").exists()
                                               else None)
            if rc:
                enforced = (root / ".rubocop.yml").exists() or mentions(ctx.corpus, "rubocop")
                plan.checks.append(Check("ruby", "lint", "rubocop", [rc, "--format", "emacs", "--force-exclusion",
                                                                     *files], root, parse_rubocop, block_rubocop,
                                         enforced, ok_codes=(0, 1), timeout=600))
            else:
                add_missing(plan, "ruby", "lint", "rubocop")
    elif lang == "php":
        php = shutil.which("php")
        if php:
            plan.checks.append(Check("php", "syntax", "php -l", [php, "-l"], root, parse_php_lint, block_all,
                                     anywhere=True, per_file=files))
        else:
            add_missing(plan, "php", "syntax", "php")
        cfg = any((root / n).exists() for n in ("phpstan.neon", "phpstan.neon.dist", "phpstan.dist.neon"))
        if cfg and not is_covered(ctx, plan, "php", "lint"):
            ps = find_bin("phpstan", root)
            if ps:
                plan.checks.append(Check("php", "lint", "phpstan", [ps, "analyse", "--error-format=raw", "--no-progress",
                                                                    *files], root, parse_generic, block_all, True,
                                         "cấu hình phpstan của project", ok_codes=(0, 1), timeout=600))
            else:
                add_missing(plan, "php", "lint", "phpstan")
    elif lang == "dart":
        dart = shutil.which("dart")
        if not dart:
            add_missing(plan, "dart", "lint", "dart")
            return
        if not is_covered(ctx, plan, "dart", "lint"):
            enforced = (root / "analysis_options.yaml").exists()
            plan.checks.append(Check("dart", "lint", "dart analyze", [dart, "analyze", "--format=machine", *files], root,
                                     parse_dart, block_errors_warnings if enforced else block_errors, enforced,
                                     anywhere=True, ok_codes=(0, 1, 2, 3), timeout=600))
        if not is_covered(ctx, plan, "dart", "format"):
            plan.checks.append(Check("dart", "format", "dart format", [dart, "format", "--output=none",
                                                                       "--set-exit-if-changed", *files], root,
                                     parse_file_list("Changed"), block_if_enforced,
                                     mentions(ctx.corpus, "dart format"), ok_codes=(0, 1)))
    elif lang == "lua" and not is_covered(ctx, plan, "lua", "lint"):
        lc = shutil.which("luacheck")
        if lc:
            plan.checks.append(Check("lua", "lint", "luacheck", [lc, "--formatter", "plain", "--codes", "--no-color",
                                                                 *files], root, parse_luacheck, block_luacheck,
                                     (root / ".luacheckrc").exists() or mentions(ctx.corpus, "luacheck"),
                                     ok_codes=(0, 1, 2)))
        else:
            add_missing(plan, "lua", "lint", "luacheck")
            luac = shutil.which("luac")
            if luac:
                plan.checks.append(Check("lua", "syntax", "luac -p", [luac, "-p"], root, parse_shell_n, block_all,
                                         anywhere=True, per_file=files))
    elif lang == "docker" and not is_covered(ctx, plan, "docker", "lint"):
        hl = shutil.which("hadolint")
        if hl:
            enforced = any((root / n).exists() for n in (".hadolint.yaml", ".hadolint.yml")) or mentions(ctx.corpus,
                                                                                                          "hadolint")
            plan.checks.append(Check("docker", "lint", "hadolint", [hl, "--no-color", *files], root, parse_hadolint,
                                     block_errors_or_enforced, enforced, ok_codes=(0, 1)))
        else:
            add_missing(plan, "docker", "lint", "hadolint")
    elif lang == "actions" and not is_covered(ctx, plan, "actions", "lint"):
        al = shutil.which("actionlint")
        if al:
            plan.checks.append(Check("actions", "lint", "actionlint", [al, "-no-color", *files], root, parse_generic,
                                     block_actionlint, mentions(ctx.corpus, "actionlint"), ok_codes=(0, 1)))
        else:
            add_missing(plan, "actions", "lint", "actionlint")
    elif lang == "yaml" and not is_covered(ctx, plan, "yaml", "lint"):
        configured = any((root / n).exists() for n in (".yamllint", ".yamllint.yml", ".yamllint.yaml")) \
            or mentions(ctx.corpus, "yamllint")
        yl = shutil.which("yamllint")
        if yl:
            plan.checks.append(Check("yaml", "lint", "yamllint", [yl, "-f", "parsable",
                                                                 *([] if configured else ["-d", "relaxed"]), *files],
                                     root, parse_generic, block_errors_or_enforced if configured else block_errors,
                                     configured, anywhere=False, ok_codes=(0, 1)))
        elif configured:
            add_missing(plan, "yaml", "lint", "yamllint")
        else:
            plan.notes.append("YAML: chưa kiểm cú pháp (yamllint chưa cài; tùy chọn, `brew install yamllint`).")
    elif lang == "json":
        strict = [f for f in files if not JSONC_NAMES.search(f)]
        if strict:
            plan.checks.append(Check("json", "syntax", "json.loads", cwd=root, block=block_all, anywhere=True,
                                     inproc=check_json(root, strict), source="có sẵn"))
    elif lang == "toml":
        plan.checks.append(Check("toml", "syntax", "tomllib", cwd=root, block=block_all, anywhere=True,
                                 inproc=check_toml(root, files), source="có sẵn"))


def nearest_glob(root: Path, rel: str, patterns: tuple):
    d = (root / rel).parent
    while True:
        if any(any(d.glob(p)) for p in patterns):
            return d
        if d == root or root not in d.parents:
            return None
        d = d.parent


def plan_cross(ctx: Ctx, plan: Plan):
    """Kiểm chung mọi ngôn ngữ: khóa lộ (gitleaks), bảo mật (semgrep), thư viện có lỗ hổng (osv-scanner), luật kiến
    trúc (archctl, khi project có `.arch/system.arch`)."""
    root, files = ctx.root, sorted(ctx.changed)
    if not files:
        return
    plan_arch(ctx, plan)
    if not is_covered(ctx, plan, "*", "secrets"):
        gl = shutil.which("gitleaks")
        if gl:
            plan.checks.append(Check("*", "secrets", "gitleaks", cwd=root, block=block_all,
                                     inproc=gitleaks_runner(gl, root, files)))
        else:
            add_missing(plan, "*", "secrets", "gitleaks")
    code = [safe_arg(f) for f in files if (lang_of(f) or "") in LANGS or lang_of(f) in ("docker", "actions")]
    if code and not is_covered(ctx, plan, "*", "security"):
        sg = shutil.which("semgrep")
        cfg = next((root / n for n in (".semgrep.yml", ".semgrep.yaml", ".semgrep") if (root / n).exists()), None)
        if not sg:
            add_missing(plan, "*", "security", "semgrep")
        elif ctx.offline and not cfg:
            plan.missing.append(("*", "security", "semgrep", "bỏ vì --offline: bộ luật p/default tải từ semgrep.dev"))
        else:
            plan.checks.append(Check("*", "security", "semgrep", [sg, "scan", "--json", "--quiet", "--metrics=off",
                                                                  "--disable-version-check", "--config",
                                                                  str(cfg) if cfg else "p/default", *code], root,
                                     parse_semgrep, block_semgrep, bool(cfg),
                                     "cấu hình semgrep của project" if cfg else "bộ luật p/default", ok_codes=(0, 1),
                                     timeout=600))
    locks = [safe_arg(f) for f in files if os.path.basename(f) in LOCKFILES
             or re.search(r"(^|/)requirements[^/]*\.txt$", f)]
    if locks and not is_covered(ctx, plan, "*", "deps"):
        osv = shutil.which("osv-scanner")
        if not osv:
            add_missing(plan, "*", "deps", "osv-scanner")
        elif ctx.offline:
            plan.missing.append(("*", "deps", "osv-scanner", "bỏ vì --offline: cần hỏi osv.dev"))
        else:
            argv = [osv, "scan", "source", "--format", "json"]
            for f in locks:
                argv += ["-L", f]
            plan.checks.append(Check("*", "deps", "osv-scanner", argv, root, parse_osv, block_none, ok_codes=(0, 1),
                                     timeout=300))


def archgate():
    """Thư viện chung `plugin/lib/archgate.py` (tìm archctl ngoài project, TM-112)."""
    lib = str(Path(__file__).resolve().parents[3] / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import archgate as G  # noqa: E402
    return G


def arch_rules_unchanged(root: Path, base: str = "HEAD") -> bool:
    """`.arch/system.arch` trên đĩa giống hệt bản ở HEAD và ở `base` (so mã băm blob, nên `assume-unchanged` hay sửa
    trong lúc làm rồi commit không lọt): chỉ khi đó mới chạy `archctl verify`, vì verify chạy lệnh shell khai trong
    file đó (TM-114). File chưa được git theo dõi, hay không đọc được, thì coi là đổi."""
    git = ["git", "--no-optional-locks", "-c", "core.fsmonitor=", "-c", "core.hooksPath=/dev/null", "-C", str(root)]
    rel = ".arch/system.arch"
    try:
        disk = subprocess.run([*git, "hash-object", "--", rel], capture_output=True, text=True, timeout=20)
        blobs = [subprocess.run([*git, "rev-parse", "--verify", "--quiet", f"{ref}:{rel}"], capture_output=True,
                                text=True, timeout=20) for ref in dict.fromkeys(("HEAD", base or "HEAD"))]
    except (OSError, subprocess.TimeoutExpired):
        return False
    want = disk.stdout.strip()
    return disk.returncode == 0 and bool(want) and all(b.returncode == 0 and b.stdout.strip() == want for b in blobs)


def verify_commands(root: Path) -> list:
    """Tên và lệnh của các dòng `verify <tên> runs "<lệnh>"` trong `.arch/system.arch`, để báo cáo nêu trước."""
    try:
        text = (root / ".arch" / "system.arch").read_text(encoding="utf-8", errors="replace")[:500_000]
    except OSError:
        return []
    return re.findall(r'^\s*verify\s+(\S+)\s+runs\s+"((?:[^"\\]|\\.)*)"', text, re.M)


def parse_archctl(out: str, err: str = "") -> list:
    """Đầu ra người đọc của `archctl check`: khối `✗ VI PHẠM` (dòng sau là `file:dòng  import …`) thành lỗi; dòng `⚠`
    thành cảnh báo, trừ khi không có `✗` nào (khi đó `--strict` trượt vì chính các cảnh báo đó, nên tính là lỗi)."""
    G = archgate()
    diags, lines = [], [G.clean(x) for x in out.splitlines()]
    for i, line in enumerate(lines):
        if line.startswith("✗"):
            loc = lines[i + 1].strip() if i + 1 < len(lines) and lines[i + 1].startswith(" ") else ""
            m = re.match(r"(\S+?):(\d+)\s+(.*)", loc)
            path, lineno, what = (m.group(1), int(m.group(2)), m.group(3)) if m else (None, None, loc)
            msg = " ".join(line.lstrip("✗ ").split()) + (f" · {what}" if what else "")
            diags.append(Diag(path, lineno, None, "archctl", msg, "error"))
        elif line.startswith("⚠"):
            hint = lines[i + 1].strip() if i + 1 < len(lines) and lines[i + 1].startswith(" ") else ""
            msg = " ".join(line.lstrip("⚠ ").split()) + (f" ({hint})" if hint else "")
            diags.append(Diag(None, None, None, "archctl", msg, "warning"))
    if diags and not any(d.level == "error" for d in diags):
        for d in diags:
            d.level = "error"
    return diags


def arch_runner(binary: str, root: Path, run_verify: bool, timeout: int):
    """Chạy `archctl verify` (khi được phép) rồi `archctl check --strict`; mã lạ (2: file luật hỏng) thì lỗi, không
    bao giờ coi là sạch."""
    def run():
        diags = []
        if run_verify:
            code, out, err, _ = run_cmd([binary, "verify", "--root", str(root)], root, timeout)
            if code is None:
                raise RuntimeError(f"archctl verify hết {timeout} giây")
            if code != 0:
                diags.append(Diag(None, None, None, "archctl verify", f"verify trượt (mã {code}): {tail(out + err)}",
                                  "error"))
        code, out, err, _ = run_cmd([binary, "check", "--strict", "--root", str(root)], root, 300)
        if code is None:
            raise RuntimeError("archctl check hết 300 giây")
        if code not in (0, 1):
            raise RuntimeError(f"archctl check mã {code}: {tail(out + err)}")
        found = parse_archctl(out, err) if code == 1 else []
        if code == 1 and not found:
            found = [Diag(None, None, None, "archctl", f"check --strict trượt (mã 1): {tail(out + err)}", "error")]
        return diags + found
    return run


def plan_arch(ctx: Ctx, plan: Plan):
    """Project có `.arch/system.arch`: `archctl check --strict` (vi phạm mới chặn, ở cả file ngoài diff) và
    `archctl verify` khi file luật không đổi so với HEAD (TM-114). Thiếu archctl thì báo chưa kiểm (mã 2)."""
    root = ctx.root
    if not (root / ".arch" / "system.arch").is_file() or is_covered(ctx, plan, "*", "arch"):
        return
    binary = archgate().find_binary(root)
    if not binary:
        add_missing(plan, "*", "arch", "archctl")
        return
    run_verify = arch_rules_unchanged(root, ctx.base)
    cmds = verify_commands(root)
    if cmds and run_verify:
        plan.notes.append("archctl verify chạy các lệnh khai trong `.arch/system.arch`: "
                          + "; ".join(f"{n} = `{c}`" for n, c in cmds[:8]))
    elif cmds:
        plan.missing.append(("*", "arch", "archctl verify", "bỏ vì `.arch/system.arch` đổi so với HEAD hay base, hay "
                             "chưa được git theo dõi (TM-114): người dùng xem `archctl diff` rồi tự chạy `archctl "
                             "verify`"))
    plan.checks.append(Check("*", "arch", "archctl", cwd=root, block=block_errors, enforced=True, anywhere=True,
                             timeout=1800, inproc=arch_runner(binary, root, run_verify and bool(cmds), 1800)))


def gitleaks_runner(gl: str, root: Path, files: list):
    """Chép các file đổi vào thư mục tạm của hệ điều hành (tự xóa) rồi quét một lần, để không quét cả repo."""
    def run():
        with tempfile.TemporaryDirectory(prefix="checks-gitleaks-") as tmp:
            skipped = []
            (Path(tmp) / "src").mkdir()
            for f in files:
                src = root / f
                try:
                    if src.stat().st_size > 5_000_000:
                        skipped.append(f)
                        continue
                    dst = Path(tmp) / "src" / f
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
                except OSError:
                    continue
            report = Path(tmp) / "report.json"
            argv = [gl, "dir", "--no-banner", "--redact", "--exit-code", "0", "--report-format", "json",
                    "--report-path", str(report)]
            if (root / ".gitleaks.toml").exists():
                argv += ["--config", str(root / ".gitleaks.toml")]
            if (root / ".gitleaksignore").exists():
                argv += ["--gitleaks-ignore-path", str(root / ".gitleaksignore")]
            # cwd = bản chép, nguồn ".": đường dẫn trong báo cáo khớp allowlist của .gitleaks.toml (`^tests/`)
            code, out, err, _ = run_cmd(argv + ["."], Path(tmp) / "src", 300)
            if code != 0:
                raise RuntimeError(f"gitleaks lỗi (mã {code}): {tail(out + err)}")
            diags = parse_gitleaks(read_text(report), "")
            base = os.path.realpath(Path(tmp) / "src")
            for d in diags:
                if d.path and os.path.isabs(d.path):
                    d.path = os.path.relpath(os.path.realpath(d.path), base)
                elif d.path:
                    d.path = os.path.normpath(d.path)  # "./tests/a.py" → "tests/a.py", đã tính từ gốc repo
            for f in skipped:  # không quét mà im lặng là báo đạt giả
                diags.append(Diag(f, None, None, "gitleaks", "file trên 5 MB, chưa quét khóa lộ", "warning"))
            return diags
    return run


def safe_arg(path: str) -> str:
    return "./" + path if path.startswith("-") else path


def build_plan(ctx: Ctx) -> Plan:
    plan = Plan()
    by_lang = {}
    for f in sorted(ctx.changed):
        lang = lang_of(f)
        if lang:  # tên file bắt đầu bằng "-" thì công cụ hiểu là tùy chọn: thêm "./"
            by_lang.setdefault(lang, []).append(safe_arg(f))
    ctx.by_lang = by_lang
    for lang, files in by_lang.items():
        if lang == "python":
            plan_python(ctx, plan, files)
        elif lang == "ts":
            plan_ts(ctx, plan, files)
        elif lang == "rust":
            plan_rust(ctx, plan, files)
        elif lang == "go":
            plan_go(ctx, plan, files)
        elif lang == "swift":
            plan_swift(ctx, plan, files)
        elif lang == "shell":
            plan_shell(ctx, plan, files)
        elif lang == "c_cpp":
            plan_c(ctx, plan, files)
        elif lang in ("java", "kotlin"):
            plan_jvm(ctx, plan, files, lang)
        else:
            plan_misc(ctx, plan, lang, files)
    unsupported = {}
    for f in ctx.changed:
        ext = os.path.splitext(f)[1].lower()
        if not lang_of(f) and ext in UNSUPPORTED:
            unsupported.setdefault(UNSUPPORTED[ext], []).append(f)
    for (name, tool), files in sorted(unsupported.items()):
        plan.missing.append((name, "lint", tool, f"agent-stack chưa có công cụ cho {name} ({len(files)} file đổi); "
                                                 "ghi lệnh kiểm vào Mốc kiểm tra của project"))
    plan_cross(ctx, plan)
    return plan


def make_ctx(root: Path, base: str = "HEAD", offline: bool = False, all_files: bool = False):
    changed = changed_lines(root, base, all_files)
    if changed is None:
        return None
    moc = moc_text(root)
    pkg = read_json(root / "package.json")
    return Ctx(root, changed, moc, coverage(moc_commands(moc)), enforcement_corpus(root, moc, pkg), offline, base=base)


# ---------------------------------------------------------------- chạy

def tail(text: str, n: int = 6) -> str:
    lines = [x for x in text.strip().splitlines() if x.strip()]
    return " | ".join(lines[-n:])[:600]


RUNNING = set()  # nhóm tiến trình đang chạy: checks.py bị giết (hết giờ của Bash, Ctrl-C) thì giết theo


def _kill_running(*_):
    for pgid in list(RUNNING):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            pass


def _on_signal(signum, frame):
    _kill_running()
    sys.exit(128 + signum)


def install_signal_handlers():
    """Chỉ gọi từ main (CLI): hook và test import module này không bị đổi handler."""
    atexit.register(_kill_running)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass


def run_cmd(argv: list, cwd, timeout: float):
    """(mã thoát hay None khi hết giờ, stdout, stderr, giây). Hết giờ thì giết cả nhóm tiến trình (npm, cargo).
    Output ghi vào file tạm thay vì pipe: tiến trình nền do lệnh để lại (daemon, `sleep &`) giữ pipe sẽ làm
    communicate() chờ quá hạn."""
    t0 = time.time()
    env = dict(os.environ, NO_COLOR="1", CLICOLOR="0", FORCE_COLOR="0", CARGO_TERM_COLOR="never", TERM="dumb")
    with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe:
        try:
            proc = subprocess.Popen(argv, cwd=str(cwd), stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, env=env,
                                    start_new_session=True)
        except FileNotFoundError:
            return 127, "", f"không tìm thấy {argv[0]}", 0.0
        except OSError as exc:
            return 126, "", str(exc), 0.0
        RUNNING.add(proc.pid)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            code = None
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        finally:
            RUNNING.discard(proc.pid)
        if code is None:
            return None, "", "", time.time() - t0
        fo.seek(0)
        fe.seek(0)
        out = fo.read(20_000_000).decode("utf-8", "replace")
        err = fe.read(20_000_000).decode("utf-8", "replace")
    return code, ANSI.sub("", out), ANSI.sub("", err), time.time() - t0


def normalize(path, cwd, root: Path):
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd or root) / p
    try:
        rel = os.path.relpath(os.path.realpath(p), os.path.realpath(root))
    except ValueError:
        return str(path)
    return rel.replace(os.sep, "/")


def in_diff(changed: dict, d: Diag) -> bool:
    if d.path not in changed:
        return False
    lines = changed[d.path]
    if lines is None or d.line is None:
        return True
    return any(x in lines for x in range(int(d.line), int(d.line) + max(d.span, 1)))


def triage(check: Check, diags: list, changed: dict, result: Result):
    for d in diags:
        is_block = check.block(d, check.enforced) if check.block else True
        if d.path is None or in_diff(changed, d):
            (result.block if is_block else result.warn).append(d)
        elif (check.anywhere or d.syntax) and d.level == "error" and is_block:
            d.outside = True
            result.block.append(d)
        else:
            result.dropped += 1


def execute(check: Check, ctx: Ctx) -> Result:
    result = Result(check)
    t0 = time.time()
    try:
        if check.inproc:
            diags = check.inproc()
        elif check.per_file:
            diags = []
            for f in check.per_file:
                code, out, err, _ = run_cmd(check.argv + [f], check.cwd, check.timeout)
                if code is None:
                    result.status, result.note = "timeout", f"hết {check.timeout} giây ở {f}"
                    break
                found = check.parse(out, err) if check.parse else []
                if code != 0 and not found:
                    found = [Diag(f, None, None, check.tool, tail(out + err) or f"mã {code}", "error", syntax=True)]
                diags += found
        else:
            code, out, err, _ = run_cmd(check.argv, check.cwd, check.timeout)
            result.exit = code
            if code is None:
                result.status, result.note = "timeout", f"hết {check.timeout} giây"
                diags = []
            elif code in (126, 127) or any(s in out + err for s in check.missing_if):
                result.status, result.note = "missing", tail(out + err, 2)
                diags = []
            else:
                diags = check.parse(out, err) if check.parse else []
                if code != 0 and not diags:
                    # Mã khác 0 mà không đọc được phát hiện nào: không bao giờ coi là sạch. Kiểm kiểu, biên dịch,
                    # cú pháp thì chặn (build hỏng, như build.rs panic hay manifest sai); loại khác là lệnh hỏng (mã 2).
                    msg = f"lệnh trượt (mã {code}), không đọc được vị trí: {tail(out + err)}"
                    if check.kind in ("type", "syntax") or check.anywhere:  # clippy, go vet: biên dịch kèm lint
                        diags = [Diag(None, None, None, check.tool, msg, "error")]
                    else:
                        result.status, result.note = "error", msg
        for d in diags:
            d.path = normalize(d.path, check.cwd, ctx.root)
        triage(check, diags, ctx.changed, result)
    except Exception as exc:  # noqa: BLE001 (một lệnh hỏng không được làm mất kết quả các lệnh khác)
        result.status, result.note = "error", f"{type(exc).__name__}: {exc}"[:400]
    result.seconds = time.time() - t0
    return result


def run_plan(plan: Plan, ctx: Ctx, workers: int = 4) -> list:
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(lambda c: execute(c, ctx), plan.checks))


# ---------------------------------------------------------------- báo cáo

def lang_label(code: str) -> str:
    return LANGS[code][0] if code in LANGS else CONFIG_LABELS.get(code, code)


def fmt_diag(d: Diag) -> str:
    where = d.path or "(không rõ file)"
    if d.line:
        where += f":{d.line}" + (f":{d.col}" if d.col else "")
    code = f" {d.code}" if d.code else ""
    extra = " [ngoài dòng đổi: có thể do thay đổi này gây ra, như đổi chữ ký hàm]" if d.outside else ""
    return f"{where}{code}: {d.msg}{extra}"


def summarize(plan: Plan, results: list) -> dict:
    blocking = sum(len(r.block) for r in results)
    warnings = sum(len(r.warn) for r in results)
    broken = [r for r in results if r.status != "ran"]
    missing = list(plan.missing) + [(r.check.lang, r.check.kind, r.check.tool, r.note) for r in broken
                                    if r.status == "missing"]
    failed = [r for r in broken if r.status != "missing"]
    code = 1 if blocking else (2 if missing or failed else 0)
    return {"exit": code, "blocking": blocking, "warnings": warnings, "missing": missing, "failed": failed}


def render(ctx: Ctx, plan: Plan, results: list, base: str, limit: int = 15) -> str:
    s = summarize(plan, results)
    langs = ", ".join(f"{lang_label(k)} {len(v)}" for k, v in sorted(ctx.by_lang.items()))
    out = [f"checks.py · {ctx.root.name} · so với {base} · {len(ctx.changed)} file đổi" + (f" ({langs})" if langs else "")]
    if plan.covered:
        out.append("Đã có trong Mốc kiểm tra (done-gate bước 4 chạy, không chạy lại):")
        for lang, kind, cmd, note in plan.covered:
            out.append(f"  = {lang_label(lang)} {KIND_LABEL.get(kind, kind)} ← `{cmd}`" + (f" ({note})" if note else ""))
    order = sorted(results, key=lambda r: (not r.block, r.status == "ran", not r.warn))
    for r in order:
        c = r.check
        head = f"{lang_label(c.lang)} {KIND_LABEL.get(c.kind, c.kind)} · {c.tool} ({c.source}" + \
               (", project bắt buộc" if c.enforced else "") + f", {r.seconds:.1f}s)"
        if r.status == "timeout":
            out.append(f"? {head}: chưa kiểm xong, {r.note}")
        elif r.status == "missing":
            out.append(f"? {head}: chưa kiểm vì thiếu công cụ ({r.note})")
        elif r.status == "error":
            out.append(f"? {head}: lệnh hỏng, chưa kiểm được ({r.note})")
        elif r.block:
            out.append(f"✗ {head}: {len(r.block)} lỗi chặn" + (f", {len(r.warn)} cảnh báo" if r.warn else ""))
        elif r.warn:
            out.append(f"⚠ {head}: {len(r.warn)} cảnh báo không chặn")
        else:
            out.append(f"✓ {head}: không có phát hiện ở dòng đổi")
        for d in r.block[:limit]:
            out.append(f"    ✗ {fmt_diag(d)}")
        if len(r.block) > limit:
            out.append(f"    … còn {len(r.block) - limit} lỗi chặn")
        shown = max(0, min(len(r.warn), limit - len(r.block[:limit])))
        for d in r.warn[:shown]:
            out.append(f"    ⚠ {fmt_diag(d)}")
        if len(r.warn) > shown:
            counts = {}
            for d in r.warn[shown:]:
                counts[d.code or "khác"] = counts.get(d.code or "khác", 0) + 1
            top = sorted(counts.items(), key=lambda kv: -kv[1])[:8]
            out.append(f"    … còn {len(r.warn) - shown} cảnh báo (" + ", ".join(f"{c} {n}" for c, n in top)
                       + (", …" if len(counts) > 8 else "") + ")")
        if r.dropped:
            out.append(f"    (bỏ qua {r.dropped} phát hiện ở dòng không đổi)")
    for lang, kind, tool, how in plan.missing:
        what = f"? Chưa kiểm {lang_label(lang)} {KIND_LABEL.get(kind, kind)}"
        if how and how not in INSTALL.values():  # lý do khác (--offline, chưa có công cụ, thiếu cấu hình)
            out.append(f"{what}: {how}")
        else:
            out.append(f"{what} vì thiếu {tool}" + (f"; cài: {how}" if how else ""))
    for note in plan.notes:
        out.append(f"· {note}")
    parts = [f"{s['blocking']} lỗi chặn", f"{s['warnings']} cảnh báo không chặn"]
    if s["missing"] or s["failed"]:
        names = sorted({m[2] for m in s["missing"]} | {r.check.tool for r in s["failed"]})
        parts.append("CHƯA KIỂM ĐỦ: " + ", ".join(names))
    verdict = {1: "có lỗi chặn, sửa rồi chạy lại", 2: "không có lỗi chặn ở phần đã kiểm, nhưng chưa kiểm đủ",
               0: "không có lỗi chặn"}[s["exit"]]
    out.append(f"Kết quả: {verdict} · " + " · ".join(parts))
    return "\n".join(out)


def as_json(ctx: Ctx, plan: Plan, results: list) -> dict:
    s = summarize(plan, results)
    def d2(d):
        return {"path": d.path, "line": d.line, "col": d.col, "code": d.code, "msg": d.msg, "level": d.level,
                "outside": d.outside}
    return {"exit": s["exit"], "blocking": s["blocking"], "warnings": s["warnings"],
            "covered": [{"lang": a, "kind": b, "cmd": c, "note": n} for a, b, c, n in plan.covered],
            "missing": [{"lang": a, "kind": b, "tool": c, "install": d} for a, b, c, d in s["missing"]],
            "notes": plan.notes,
            "checks": [{"lang": r.check.lang, "kind": r.check.kind, "tool": r.check.tool, "source": r.check.source,
                        "enforced": r.check.enforced, "status": r.status, "note": r.note,
                        "seconds": round(r.seconds, 2), "block": [d2(d) for d in r.block],
                        "warn": [d2(d) for d in r.warn], "dropped": r.dropped} for r in results]}


def render_plan(ctx: Ctx, plan: Plan) -> str:
    out = [f"Kế hoạch kiểm cho {ctx.root.name}: {len(ctx.changed)} file đổi"]
    for lang, kind, cmd, note in plan.covered:
        out.append(f"  = {lang_label(lang)} {KIND_LABEL.get(kind, kind)}: đã có trong Mốc kiểm tra ← `{cmd}`"
                   + (f" ({note})" if note else ""))
    for c in plan.checks:
        out.append(f"  → {lang_label(c.lang)} {KIND_LABEL.get(c.kind, c.kind)}: {c.tool} ({c.source}"
                   + (", project bắt buộc" if c.enforced else "") + ")")
    for lang, kind, tool, how in plan.missing:
        out.append(f"  ? {lang_label(lang)} {KIND_LABEL.get(kind, kind)}: thiếu {tool}" + (f" ({how})" if how else ""))
    for note in plan.notes:
        out.append(f"  · {note}")
    return "\n".join(out)


# ---------------------------------------------------------------- hình tháp của project (cho session_start, router)

# Code mẫu, fixture, bench và test không cho biết project viết bằng ngôn ngữ gì (archctl có mẫu của 10 ngôn ngữ).
SAMPLE_DIRS = re.compile(r"(^|/)(tests?|spec|__tests__|fixtures?|testdata|examples?|samples?|bench(marks?)?|evals?|"
                         r"templates?|docs?)/", re.IGNORECASE)


def project_gaps(root: Path, files: list) -> dict:
    """Tầng còn thiếu của hình tháp kiểm (linter, test, Mốc kiểm tra, file luật) và ngôn ngữ chưa có công cụ.
    `files`: danh sách file của project (đường dẫn tương đối). Chỉ đọc, không chạy lệnh nào ngoài shutil.which."""
    counts, unsupported = {}, {}
    for f in files:
        if any(f.startswith(d) or f"/{d}" in f for d in SKIP_DIRS) or SAMPLE_DIRS.search(f):
            continue
        lang = lang_of(f)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
        else:
            ext = os.path.splitext(f)[1].lower()
            if ext in UNSUPPORTED:
                name, tool = UNSUPPORTED[ext]
                unsupported.setdefault(name, [0, tool])[0] += 1
    langs = [k for k, n in counts.items() if k in LANGS and n >= 3]
    tools = []  # (ngôn ngữ, công cụ, cách cài)
    need = {"python": ["ruff"], "shell": ["shellcheck"], "swift": ["swiftlint"], "rust": ["cargo-clippy"],
            "go": ["go"], "c_cpp": ["cppcheck"], "kotlin": ["ktlint"], "csharp": ["dotnet"], "ruby": ["rubocop"],
            "php": ["php"], "dart": ["dart"], "lua": ["luacheck"], "java": ["javac"]}
    for lang in langs:
        for tool in need.get(lang, []):
            if not find_bin(tool, root):
                tools.append((lang, tool, INSTALL.get(tool, "")))
    if counts.get("docker") and not shutil.which("hadolint"):
        tools.append(("docker", "hadolint", INSTALL["hadolint"]))
    if counts.get("actions") and not shutil.which("actionlint"):
        tools.append(("actions", "actionlint", INSTALL["actionlint"]))
    layers = []
    if "ts" in langs:
        pkg = read_json(root / "package.json")
        has_lint = "lint" in (pkg.get("scripts") or {}) or "eslintConfig" in pkg or any(
            p.name.startswith(("eslint.config", ".eslintrc", "biome.json")) for p in _ls(root))
        if not has_lint:
            layers.append("linter cho TS/JS (project chưa cấu hình eslint hay biome)")
    code_files = sum(n for k, n in counts.items() if k in LANGS)
    test_re = re.compile(r"(^|/)(tests?|spec|__tests__)/|(^|/)test_[^/]+$|_test\.[a-z]+$|\.(test|spec)\.[a-z]+$|Tests?/")
    if code_files >= 3 and not any(test_re.search(f) for f in files):
        layers.append("test (chưa thấy file test nào)")
    if code_files >= 3 and not moc_text(root).strip():
        layers.append("Mốc kiểm tra (chưa có lệnh kiểm trong PLAN.md §0, CLAUDE.md hay AGENTS.md)")
    if not ((root / "CLAUDE.md").exists() or (root / "AGENTS.md").exists()):
        layers.append("file luật (CLAUDE.md hay AGENTS.md)")
    unsup = [(name, n, tool) for name, (n, tool) in sorted(unsupported.items()) if n >= 3]
    return {"langs": langs, "tools": tools, "layers": layers, "unsupported": unsup}


def gaps_text(gaps: dict):
    """(câu cho agent, dòng ngắn cho người dùng) hay None khi project không thiếu tầng nào."""
    bits, short = [], []
    if gaps["tools"]:
        bits.append("thiếu công cụ kiểm: " + "; ".join(f"{t} cho {lang_label(l)}" + (f" (`{h}`)" if h else "")
                                                   for l, t, h in gaps["tools"]))
        short.append("thiếu " + ", ".join(t for _, t, _ in gaps["tools"][:3]))
    if gaps["unsupported"]:
        bits.append("ngôn ngữ agent-stack chưa có công cụ kiểm: " + "; ".join(
            f"{name} ({n} file; nên tìm hiểu {tool})" for name, n, tool in gaps["unsupported"]))
        short.append("chưa phủ " + ", ".join(name for name, _, _ in gaps["unsupported"][:2]))
    if gaps["layers"]:
        bits.append("thiếu tầng: " + "; ".join(gaps["layers"]))
        short.append("thiếu " + ", ".join(x.split(" (")[0] for x in gaps["layers"][:3]))
    if not bits:
        return None
    context = ("[agent-stack] Hình tháp kiểm của project (mã nguồn → kiểm tĩnh → test → luật bằng lời → người duyệt) "
               "còn thiếu: " + " | ".join(bits) + ". Gợi ý với người dùng cài công cụ hay dựng tầng còn thiếu khi việc "
               "đụng tới code; đừng tự cài toàn cục (chỉ qua install.sh khi người dùng duyệt). done-gate chạy "
               "`checks.py` sẽ báo phần chưa kiểm được.")
    return context, "🔺 " + " · ".join(short)


# ---------------------------------------------------------------- kiểm nhanh cho hook sau khi sửa file

def quick_lint(path: Path, lines, budget: float = 1.8) -> list:
    """Kiểm nhanh một file vừa sửa (hook post_edit). `lines`: tập dòng vừa đổi, hay None nếu cả file.
    Trả danh sách dòng chữ (rỗng nếu sạch). Không bao giờ ném lỗi ra ngoài; hết giờ thì im lặng."""
    deadline = time.time() + budget
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return []
        root = Path(git(path.parent, "rev-parse", "--show-toplevel", timeout=1) or path.parent).resolve() \
            if shutil.which("git") else path.parent
        root = Path(str(root).strip())
        rel = os.path.relpath(path.resolve(), root)
        lang = lang_of(rel)
        if lang is None and path.suffix == "":
            first = read_text(path, 200).split("\n", 1)[0]
            lang = "shell" if re.match(r"#!.*\b(ba|k|z)?sh\b", first) else None
        diags, tool = [], ""
        if lang == "python":
            # Hook chạy không qua bước duyệt lệnh: chỉ lấy công cụ trên PATH, không bao giờ chạy file trong repo
            # (`.venv/bin`, `vendor/bin`, `node_modules/.bin`) — repo lạ có thể đặt ruff giả ở đó (TM-96).
            ruff = shutil.which("ruff")
            if ruff:
                configured = (root / "ruff.toml").exists() or (root / ".ruff.toml").exists() or pyproject_has(root, "ruff")
                argv = [ruff, "check", "--no-cache", "--force-exclude", "--output-format", "json", "--exit-zero"]
                if not configured:  # không mượn cấu hình của thư mục cha (xem plan_python)
                    argv += ["--isolated", "--select", ",".join(RUFF_REAL)]
                code, out, err, _ = run_cmd(argv + [str(path)], root, max(0.1, deadline - time.time()))
                diags, tool = parse_ruff(out, err) if code == 0 else [], "ruff"
            elif not (requires_python(root) or (0, 0)) > sys.version_info[:2]:
                diags, tool = check_python_syntax(root, [rel])(), "compile() (chưa có ruff)"
        elif lang == "shell" and not is_zsh(path):
            sc = shutil.which("shellcheck")
            if sc:
                code, out, err, _ = run_cmd([sc, "-f", "gcc", "-x", str(path)], path.parent,
                                            max(0.1, deadline - time.time()))
                enforced = (root / ".shellcheckrc").exists()
                diags = [d for d in parse_generic(out, err) if enforced or d.level in ("error", "warning")] \
                    if code is not None else []
                tool = "shellcheck"
            else:
                code, out, err, _ = run_cmd(["bash", "-n", str(path)], path.parent, max(0.1, deadline - time.time()))
                diags, tool = (parse_shell_n(out, err) if code else []), "bash -n (chưa có shellcheck)"
        elif lang == "shell":
            code, out, err, _ = run_cmd(["zsh", "-n", str(path)], path.parent, max(0.1, deadline - time.time()))
            diags, tool = (parse_shell_n(out, err) if code else []), "zsh -n"
        elif lang == "json" and not JSONC_NAMES.search(rel):
            diags, tool = check_json(root, [rel])(), "json"
        elif lang == "toml":
            diags, tool = check_toml(root, [rel])(), "tomllib"
        elif lang == "docker" and shutil.which("hadolint"):
            code, out, err, _ = run_cmd(["hadolint", "--no-color", str(path)], root, max(0.1, deadline - time.time()))
            diags, tool = [d for d in parse_hadolint(out, err) if d.level == "error"], "hadolint"
        elif lang == "actions" and shutil.which("actionlint"):
            code, out, err, _ = run_cmd(["actionlint", "-no-color", str(path)], root, max(0.1, deadline - time.time()))
            diags, tool = [d for d in parse_generic(out, err) if d.code != "shellcheck"], "actionlint"
        elif lang == "php" and shutil.which("php"):
            code, out, err, _ = run_cmd(["php", "-l", str(path)], root, max(0.1, deadline - time.time()))
            diags, tool = parse_php_lint(out, err), "php -l"
        elif lang == "ruby" and shutil.which("ruby"):
            code, out, err, _ = run_cmd(["ruby", "-wc", str(path)], root, max(0.1, deadline - time.time()))
            diags, tool = [d for d in parse_ruby_wc(out, err) if d.level == "error"], "ruby -wc"
        elif lang == "lua" and shutil.which("luacheck"):
            code, out, err, _ = run_cmd(["luacheck", "--formatter", "plain", "--codes", "--no-color", str(path)], root,
                                        max(0.1, deadline - time.time()))
            diags, tool = [d for d in parse_luacheck(out, err) if block_luacheck(d, False)], "luacheck"
        if time.time() > deadline + 0.2:
            return []
        shown = []
        for d in diags:
            d.path = normalize(d.path, root, root) if d.path else rel
            syntax = d.syntax or d.code.startswith("E9")
            if lines is None or d.line is None or int(d.line) in lines or syntax:
                shown.append(f"{rel}:{d.line or '?'}" + (f":{d.col}" if d.col else "") +
                             (f" {d.code}" if d.code else "") + f": {d.msg} ({tool})")
        return shown[:10]
    except Exception:  # noqa: BLE001 (hook không bao giờ được làm kẹt phiên)
        return []


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm tĩnh project trên dòng vừa đổi (done-gate bước 4).")
    ap.add_argument("--root", default=".", help="thư mục trong repo cần kiểm (mặc định: thư mục đang đứng)")
    ap.add_argument("--base", default="HEAD", help="so với ref này (mặc định HEAD: phần chưa commit)")
    ap.add_argument("--list", action="store_true", help="chỉ in kế hoạch kiểm, không chạy")
    ap.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    ap.add_argument("--offline", action="store_true", help="bỏ kiểm cần mạng (semgrep p/default, osv-scanner)")
    ap.add_argument("--all", action="store_true", help="coi mọi file git theo dõi là vừa đổi (kiểm cả project)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    install_signal_handlers()
    top = git(Path(args.root).resolve(), "rev-parse", "--show-toplevel")
    if not top:
        print("checks.py: không phải git repo, không biết dòng nào vừa đổi.", file=sys.stderr)
        return 3
    root = Path(top.strip()).resolve()
    ctx = make_ctx(root, args.base, args.offline, args.all)
    if ctx is None:
        print(f"checks.py: không đọc được git diff so với {args.base}.", file=sys.stderr)
        return 3
    plan = build_plan(ctx)
    if args.list:
        print(render_plan(ctx, plan))
        return 0
    if not ctx.changed:
        print(f"checks.py · {root.name} · so với {args.base} · không có file đổi; không có gì để kiểm.")
        return 0
    results = run_plan(plan, ctx, args.workers)
    if args.json:
        print(json.dumps(as_json(ctx, plan, results), ensure_ascii=False, indent=1))
    else:
        print(render(ctx, plan, results, args.base))
    return summarize(plan, results)["exit"]


if __name__ == "__main__":
    sys.exit(main())
