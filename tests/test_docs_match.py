"""Tài liệu khớp code (cải tiến 5): lệnh, cờ và đường dẫn nhắc trong tài liệu phải có thật.

Đọc README.md, HUONG-DAN.html, CLAUDE.md, global/*.md, plugin/skills/*/SKILL.md, plugin/agents/*.md. Trong từng
đoạn code (`…` và khối ``` của Markdown, <code>, <pre> của HTML):
- chỗ gọi `<script>.py [lệnh con] --cờ` với script có trong repo: lệnh con và cờ phải có trong `--help` thật của
  script (của lệnh con, nếu có). Script không dùng argparse thì cờ phải có trong mã nguồn cùng thư mục.
- đường dẫn bắt đầu bằng thư mục của repo (plugin/, tools/, tests/, global/, evals/, .agent/): phải có trong repo.
Tránh báo nhầm: bỏ token có ký hiệu mẫu (<…>, …, *, {}, $), bỏ đường dẫn git bỏ qua (state/, .tmp/, file chỉ có
trên máy), không đoán lệnh con của script không có danh sách lệnh con.
"""
from __future__ import annotations

import functools
import html
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._util import REPO

DOC_GLOBS = ("README.md", "HUONG-DAN.html", "CLAUDE.md", "global/*.md", "plugin/skills/*/SKILL.md",
             "plugin/agents/*.md")
REPO_DIRS = ("plugin", "tools", "tests", "global", "evals", ".agent")
REPO_PREFIX = "~/Documents/Claude/agent-stack/"
PLACEHOLDER_RE = re.compile(r"[<>…*{}$?\[\]]|\.\.\.")
MD_SPAN_RE = re.compile(r"```[^\n]*\n(.*?)```|(`+)(.+?)\2", re.S)
HTML_SPAN_RE = re.compile(r"<(code|pre)\b[^>]*>(.*?)</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|\n()]")
SCRIPT_RE = re.compile(r"(?:^|(?<=[\s\"'=<]))([\w./${}~-]*?)([A-Za-z_][\w-]*\.py)(?=$|[\s\"'>:,.])")
FLAG_RE = re.compile(r"^(--[A-Za-z][\w-]*|-[A-Za-z])(?:=.*)?$")
WORD_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
PATH_RE = re.compile(r"(?<![\w./~${}-])(?:" + re.escape(REPO_PREFIX) + r")?((?:" +
                     "|".join(re.escape(d) for d in REPO_DIRS) + r")/[^\s`'\"()\[\],;|]*)")
HELP_FLAG_RE = re.compile(r"(?<![\w-])(--?[A-Za-z][\w-]*)")
# File agent-stack tạo trong mọi project (bàn giao, kế hoạch, trang, giọng văn): tài liệu nhắc chúng như quy ước của
# project đang làm, không phải file của repo này.
AGENT_CONVENTIONS = (".agent/HANDOFF.md", ".agent/PLAN.md", ".agent/.gitignore", ".agent/trang/", ".agent/giong-van/")


def code_spans(text: str, is_html: bool) -> list:
    """Nội dung các đoạn code của một tài liệu (HTML đã bỏ thẻ con và giải mã thực thể)."""
    if is_html:
        return [html.unescape(TAG_RE.sub("", m.group(2))) for m in HTML_SPAN_RE.finditer(text)]
    return [m.group(1) if m.group(1) is not None else m.group(3) for m in MD_SPAN_RE.finditer(text)]


@functools.lru_cache(maxsize=None)
def tracked() -> frozenset:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True)
    return frozenset(out.stdout.splitlines()) if out.returncode == 0 else frozenset()


@functools.lru_cache(maxsize=None)
def scripts() -> dict:
    """Tên file → các đường dẫn script Python của repo (bỏ test và bài eval, là dữ liệu chứ không phải lệnh)."""
    out = {}
    for rel in sorted(tracked()):
        if rel.endswith(".py") and not rel.startswith(("tests/", "evals/tasks/")):
            out.setdefault(Path(rel).name, []).append(REPO / rel)
    return out


@functools.lru_cache(maxsize=None)
def help_text(script: Path, sub: str = ""):
    """Đầu ra `--help` thật của script (hay của lệnh con), hoặc None khi script không dùng argparse hay không in được.
    Chạy với state riêng trong thư mục tạm, stdin rỗng, để không đụng trạng thái thật."""
    if "argparse" not in script.read_text(encoding="utf-8", errors="replace"):
        return None
    with tempfile.TemporaryDirectory() as state:
        env = dict(os.environ, AGENT_STACK_STATE=state, AGENT_STACK_NO_BACKGROUND="1")
        try:
            out = subprocess.run([sys.executable, str(script), *([sub] if sub else []), "--help"], cwd=str(REPO),
                                 capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL, env=env)
        except subprocess.TimeoutExpired:
            return None
    return out.stdout if out.returncode == 0 and "usage:" in out.stdout else None


def subcommands(help_out: str) -> set:
    """Lệnh con trong dòng usage: khối {a,b,c} không đứng sau một cờ (cờ có giá trị chọn trước như --level {x,y})."""
    usage = help_out.split("\n\n", 1)[0].split()
    for prev, token in zip([""] + usage, usage):
        # `[-h]` là cờ đã đóng ngoặc; `--level` hay `[--level` thì {…} đứng sau là giá trị của nó.
        takes_value = prev.lstrip("[").startswith("-") and not prev.endswith("]")
        if token.startswith("{") and not takes_value:
            return set(token.strip("{}[].").split(","))
    return set()


def hidden_flag(script: Path, flag: str) -> bool:
    """Cờ có thật nhưng ẩn khỏi --help (help=argparse.SUPPRESS, như `vet.py drift --save-state` cho lượt kiểm nền)."""
    pattern = r"add_argument\([^)]*[\"']" + re.escape(flag) + r"[\"'][^)]*SUPPRESS"
    return re.search(pattern, script.read_text(encoding="utf-8", errors="replace")) is not None


def source_flags(script: Path) -> str:
    """Mã nguồn các file .py cùng thư mục với script (script tự phân tích đối số, có thể nhờ module bên cạnh)."""
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(script.parent.glob("*.py")))


def check_call(script: Path, args: list) -> list:
    """Lỗi của một lần gọi script: lệnh con không có, cờ không có. Bỏ token mẫu; dừng ở `--` (phần sau là lệnh khác)."""
    main = help_text(script)
    if main is None:
        source = source_flags(script)
        return [f"cờ {a.split('=')[0]} không có trong mã nguồn" for a in args if FLAG_RE.match(a)
                and a.split("=")[0] not in ("-h", "--help") and f"\"{a.split('=')[0]}\"" not in source
                and f"'{a.split('=')[0]}'" not in source]
    subs = subcommands(main)
    problems, helps = [], [main]
    if subs and args and WORD_RE.match(args[0]):
        if args[0] not in subs:
            return [f"lệnh con `{args[0]}` không có (có: {', '.join(sorted(subs))})"]
        helps.append(help_text(script, args[0]) or "")
    elif subs:  # không rõ lệnh con: cờ phải có ở ít nhất một lệnh con
        helps += [help_text(script, s) or "" for s in sorted(subs)]
    known = set().union(*(HELP_FLAG_RE.findall(h) for h in helps))
    for arg in args:
        m = FLAG_RE.match(arg)
        if m and m.group(1) not in known | {"-h", "--help"} and not hidden_flag(script, m.group(1)):
            problems.append(f"cờ {m.group(1)} không có trong --help" + (f" của `{args[0]}`" if len(helps) == 2 else ""))
    return problems


def call_args(rest: str) -> list:
    """Đối số theo sau tên script trong một đoạn lệnh: dừng ở `--`, chuyển hướng hay chú thích; bỏ token mẫu."""
    out = []
    for token in rest.split():
        token = token.strip("\"'")
        if token == "--" or token.startswith(("#", ">", "2>", "<<")):
            break
        if token and not PLACEHOLDER_RE.search(token):
            out.append(token.rstrip(",.:"))
        elif not out and token:  # lệnh con là token mẫu (<lệnh>): không biết lệnh con, vẫn xét cờ
            out.append("")
    return out


def problems_in_span(span: str) -> list:
    out = []
    for segment in SEGMENT_SPLIT_RE.split(span):
        for m in SCRIPT_RE.finditer(segment):
            candidates = scripts().get(m.group(2))
            if not candidates or segment[m.end():m.end() + 1] in (":", ",", "."):
                continue  # script ngoài repo, hay tên file đứng trong câu (risk.py: …) chứ không phải lệnh
            args = call_args(segment[m.end():])
            results = [check_call(path, args) for path in candidates]
            if all(results):  # trùng tên: chỉ báo khi không script nào nhận
                out += [f"`{segment.strip()[:120]}`: {m.group(2)}: {p}" for p in results[0]]
    for m in PATH_RE.finditer(span):
        rel = re.sub(r"(:\d+(-\d+)?|#[\w-]*)$", "", m.group(1)).rstrip(".:,")
        if not rel or PLACEHOLDER_RE.search(rel) or rel.rstrip("/") in REPO_DIRS:
            continue
        if not rel.endswith("/") and "." not in rel.rsplit("/", 1)[-1]:
            continue  # không có đuôi file hay dấu / cuối: có thể là tên khác (phương thức MCP tools/list), không đoán
        if rel.startswith(".agent/") and any(rel == c or (c.endswith("/") and rel.startswith(c))
                                             for c in AGENT_CONVENTIONS):
            continue
        if not path_known(rel):
            out.append(f"`{m.group(0)[:120]}`: đường dẫn {rel} không có trong repo")
    return out


def path_known(rel: str) -> bool:
    """Đường dẫn là file hay thư mục git theo dõi, hay bị git bỏ qua (chỉ có trên máy: state/, .tmp/, LAST-TURN)."""
    rel = rel.rstrip("/")
    files = tracked()
    if rel in files or any(f.startswith(rel + "/") for f in files):
        return True
    ignored = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", "--no-index", rel], capture_output=True)
    return ignored.returncode == 0


def doc_files() -> list:
    return sorted({p for pattern in DOC_GLOBS for p in REPO.glob(pattern) if p.is_file()})


def problems_in_doc(path: Path) -> list:
    text = path.read_text(encoding="utf-8", errors="replace")
    out = []
    for span in code_spans(text, path.suffix.lower() in (".html", ".htm")):
        out += problems_in_span(span)
    return list(dict.fromkeys(out))


class DocsMatchCode(unittest.TestCase):
    def test_docs_mention_only_real_commands_flags_and_paths(self):
        docs = doc_files()
        self.assertGreater(len(docs), 10, "không tìm thấy tài liệu để soi")
        self.assertTrue(tracked(), "test cần chạy trong bản git clone của repo (dùng git ls-files)")
        problems = [f"{p.relative_to(REPO)}: {msg}" for p in docs for msg in problems_in_doc(p)]
        self.assertEqual(problems, [], "Tài liệu lệch code:\n" + "\n".join(problems))


class Extractor(unittest.TestCase):
    """Chốt chặn chống báo nhầm và chống bỏ sót của bộ soi (lệch giả phải bị bắt, chỗ mẫu phải được bỏ qua)."""

    def problems(self, text, is_html=False):
        return [msg for span in code_spans(text, is_html) for msg in problems_in_span(span)]

    def test_fake_flag_subcommand_and_path_are_caught(self):
        self.assertTrue(self.problems("Chạy `python3 receipt.py run --khong-co -- python3 -m unittest`."))
        self.assertTrue(self.problems("Chạy `receipt.py khong-co`."))
        self.assertTrue(self.problems("Chạy `python3 risk.py --khong-co`."))
        self.assertTrue(self.problems("Xem `plugin/khong-co.py`."))
        self.assertTrue(self.problems("<pre>python3 plugin/skills/done-gate/scripts/review_log.py add --khong-co"
                                      "</pre>", is_html=True))

    def test_real_commands_and_placeholders_pass(self):
        ok = ["`python3 receipt.py run -- python3 -m unittest discover -s tests -t .`",
              "`receipt.py fails-before --base <commit> --link .venv -- <lệnh test>`",
              "`python3 <risk.py> --new`", "`risk.py --base <ref> --writer opus`",
              "`review_log.py add --writer opus --level cao --reviewers opus,sonnet --found \"<ai>:<mức>:…\"`",
              "`receipt.py <lệnh> --base x`", "`plugin/skills/done-gate/scripts/risk.py:120`",
              "`plugin/skills/<tên>/SKILL.md`", "`~/Documents/Claude/agent-stack/plugin/hooks/stop.py`",
              "`~/other/plugin/x.py --khong-co`", "`state/review-log.jsonl`", "`.tmp/done-gate.diff`",
              "`git diff --no-index /dev/null <file>`", "`foo.py --bat-ky`"]
        for text in ok:
            with self.subTest(text=text):
                self.assertEqual(self.problems(text), [])

    def test_html_entities_and_nested_tags(self):
        self.assertEqual(self.problems("<code>receipt.py run -- &lt;lệnh&gt;</code>", is_html=True), [])
        self.assertTrue(self.problems("<code>receipt.py <b>run</b> --khong-co</code>", is_html=True))

    def test_subcommand_choices_skip_flag_values(self):
        help_out = "usage: x.py add [-h] --level {cao,vua,thap} [--found FOUND]\n\noptions:\n"
        self.assertEqual(subcommands(help_out), set())
        self.assertEqual(subcommands("usage: x.py [-h] {add,summary} ...\n\n"), {"add", "summary"})


if __name__ == "__main__":
    unittest.main()
