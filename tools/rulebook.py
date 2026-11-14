#!/usr/bin/env python3
"""Sổ luật (`rulebook.json`): mỗi luật trong luật chung và `CLAUDE.md` của repo khai một loại kiểm và thứ đảm nhận.

Loại kiểm: may-chan (máy chặn), may-bao (máy báo), bo-viec (đo bằng bộ việc), model-review (model khác review),
nguoi-duyet (người dùng duyệt). Thứ đảm nhận là các tham chiếu:
  test:<file>::<Lớp>[.<hàm>]   test có thật (đọc bằng ast, không chạy)
  hook:plugin/hooks/<file>.py   hook có đăng ký trong plugin/hooks/hooks.json
  eval:<đường dẫn>             bài đo (file hay thư mục) có thật
  skill:<…/SKILL.md>, agent:<…/*.md>, file:<đường dẫn>   file có thật

Kiểm câu chữ (`tests/test_global_rules.py`) chỉ chống mất chữ, không tính là kiểm: luật máy chặn hay máy báo phải có
test hay hook khác. Mọi gạch đầu dòng luật của ba file phải thuộc ít nhất một mục (mục luật chung lấy chuỗi neo từ
RULES của test chống mất chữ, mục khác khai `anchor`).

Lệnh: `python3 tools/rulebook.py` in số luật theo loại kiểm và các lỗi (mã 1 khi có lỗi).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOK = "rulebook.json"
RULE_FILES = ("global/SHARED.global.md", "global/CLAUDE.global.md", "CLAUDE.md")
TYPES = {"may-chan": "máy chặn", "may-bao": "máy báo", "bo-viec": "đo bằng bộ việc",
         "model-review": "model khác review", "nguoi-duyet": "người dùng duyệt"}
REF_KINDS = ("test", "hook", "eval", "skill", "agent", "file")
TEXT_ONLY_TESTS = ("tests/test_global_rules.py",)  # test chống mất chữ: không tính là kiểm
# Loại kiểm → loại tham chiếu bắt buộc có ít nhất một.
NEEDS = {"may-chan": ("test", "hook"), "may-bao": ("test", "hook"), "bo-viec": ("eval",),
         "model-review": ("agent", "skill"), "nguoi-duyet": REF_KINDS}
BULLET_RE = re.compile(r"^\s*(?:-|\d+\.)\s+(.*\S)")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def bullets(text: str) -> list:
    """Các gạch đầu dòng (kể cả mục đánh số) của một file luật, đã gộp khoảng trắng."""
    return [norm(m.group(1)) for m in map(BULLET_RE.match, text.splitlines()) if m]


def legacy_anchors(rules=None) -> dict:
    """{mã: [(file, chuỗi), …]} từ RULES của test chống mất chữ, chỉ phần nằm trong ba file luật. Không có `rules`
    thì nạp file test theo đường dẫn (tools/ không import gói tests)."""
    if rules is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_global_rules", REPO / "tests" / "test_global_rules.py")
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(REPO))
        spec.loader.exec_module(mod)
        rules = mod.RULES
    return {rid: [(rel, n) for rel, needles in places if rel in RULE_FILES for n in needles if not n.startswith("re:")]
            for rid, _, places in rules}


def test_exists(repo: Path, ref: str) -> str | None:
    """Lỗi của tham chiếu test `file::Lớp[.hàm]`, hay None khi có thật."""
    rel, _, name = ref.partition("::")
    path = repo / rel
    if not rel.startswith("tests/") or not path.is_file():
        return f"không có file test {rel}"
    if not name:
        return f"thiếu ::Lớp sau {rel}"
    cls_name, _, method = name.partition(".")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name), None)
    if cls is None:
        return f"không có lớp {cls_name} trong {rel}"
    if method and not any(isinstance(n, ast.FunctionDef) and n.name == method for n in cls.body):
        return f"không có hàm {method} trong {rel}::{cls_name}"
    return None


def hooks_registered(repo: Path) -> set:
    """Tên file hook có trong hooks.json."""
    text = (repo / "plugin" / "hooks" / "hooks.json").read_text(encoding="utf-8")
    return set(re.findall(r"/hooks/([\w.-]+\.py)", text))


def ref_problem(repo: Path, ref: str, hooks: set) -> str | None:
    kind, sep, target = ref.partition(":")
    if not sep or kind not in REF_KINDS or not target:
        return f"tham chiếu sai dạng {ref!r} (cần {', '.join(k + ':' for k in REF_KINDS)})"
    if ".." in Path(target.split("::")[0]).parts or target.startswith("/"):
        return f"tham chiếu ra ngoài repo {ref!r}"
    if kind == "test":
        return test_exists(repo, target)
    if kind == "hook":
        if not (repo / target).is_file() or not target.startswith("plugin/hooks/"):
            return f"không có hook {target}"
        if Path(target).name not in hooks:
            return f"hook {target} chưa đăng ký trong hooks.json"
        return None
    if not (repo / target).exists():
        return f"không có {kind} {target}"
    return None


def problems(book: dict, repo: Path = REPO, anchors: dict | None = None) -> list:
    """Danh sách lỗi của sổ luật (rỗng là đạt)."""
    anchors = legacy_anchors() if anchors is None else anchors
    out, hooks = [], hooks_registered(repo)
    rules = book.get("rules") if isinstance(book, dict) else None
    if not isinstance(rules, list) or not rules:
        return ["sổ luật không có danh sách rules"]
    seen, covered = set(), {rel: [] for rel in RULE_FILES}
    for i, rule in enumerate(rules):
        rid = rule.get("id") if isinstance(rule, dict) else None
        where = f"mục {rid or i}"
        if not isinstance(rid, str) or not rid:
            out.append(f"{where}: thiếu id")
            continue
        if rid in seen:
            out.append(f"{where}: id trùng")
        seen.add(rid)
        check = rule.get("check")
        if check not in TYPES:
            out.append(f"{where}: loại kiểm {check!r} không thuộc {', '.join(TYPES)}")
        refs = rule.get("by")
        if not isinstance(refs, list) or not refs or not all(isinstance(r, str) for r in refs):
            out.append(f"{where}: thiếu thứ đảm nhận (by)")
            refs = []
        for ref in refs:
            msg = ref_problem(repo, ref, hooks)
            if msg:
                out.append(f"{where}: {msg}")
        real = [r for r in refs if not any(r.startswith(f"test:{t}") for t in TEXT_ONLY_TESTS)]
        if check in NEEDS and not any(r.partition(":")[0] in NEEDS[check] for r in real):
            only_text = len(real) < len(refs)
            out.append(f"{where}: loại {TYPES[check]} cần ít nhất một tham chiếu {'/'.join(NEEDS[check])}"
                       + (" (test chống mất chữ không tính là kiểm)" if only_text else ""))
        places = anchors.get(rid, [])
        if rule.get("anchor"):
            rel = rule.get("file")
            if rel not in RULE_FILES:
                out.append(f"{where}: file {rel!r} không phải file luật")
            else:
                places = places + [(rel, rule["anchor"])]
        if not places:
            out.append(f"{where}: không có chuỗi neo (thêm file + anchor, hay mã có trong RULES)")
        for rel, needle in places:
            covered[rel].append(norm(needle))
    for rid in anchors:
        if anchors[rid] and rid not in seen:
            out.append(f"luật {rid} (có trong luật chung) chưa có mục trong sổ luật")
    for rel in RULE_FILES:
        for line in bullets((repo / rel).read_text(encoding="utf-8")):
            if not any(n and n in line for n in covered[rel]):
                out.append(f"{rel}: gạch đầu dòng chưa có luật nào trong sổ: {line[:90]}")
    return out


def load(repo: Path = REPO) -> dict:
    return json.loads((repo / BOOK).read_text(encoding="utf-8"))


def main() -> int:
    book = load()
    found = problems(book)
    counts = {}
    for rule in book.get("rules", []):
        counts[rule.get("check")] = counts.get(rule.get("check"), 0) + 1
    print(f"Sổ luật: {sum(counts.values())} luật · " + ", ".join(f"{TYPES.get(k, k)} {v}" for k, v in counts.items()))
    for msg in found:
        print(f"- {msg}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
