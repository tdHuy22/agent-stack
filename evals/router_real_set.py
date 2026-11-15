#!/usr/bin/env python3
"""Gom bộ câu thật để đo lớp model của router (GĐ5), chỉ trên máy: kết quả ở `state/router-eval/set.jsonl` (ngoài git).

Ba tập:
  tin     tin người dùng gõ trong transcript Claude Code (~/.claude/projects/*/*.jsonl) và `state/last-request/`,
          bỏ tin tự động, lệnh, thư mục tạm của eval hay test; qua đúng cổng của router (chữ của người dùng, đủ số chữ)
  s0      việc tiếp theo và việc đang dở trong §0 của các project ở ~/Documents/Claude
  buoc    cột việc của bảng `## Các bước` trong kế hoạch phiên đã duyệt (~/.claude/plans/*.md)
Thêm `eval-none`: các câu nhãn `none` của evals/router-prompts.jsonl, để gắn nhãn lại như câu thật.

Mỗi câu đã che secret, có mã ổn định (sha1), tập con dev (40%) hay test (60%) theo mã băm. Không gọi model nào.

  python3 evals/router_real_set.py            gom và in số đếm
  python3 evals/router_real_set.py --show 5   in thử vài câu mỗi tập
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugin" / "lib"))
import agentstack as A  # noqa: E402

OUT = A.state_dir() / "router-eval" / "set.jsonl"
PROJECTS = Path.home() / "Documents" / "Claude"
TRANSCRIPTS = Path.home() / ".claude" / "projects"
PLANS = Path.home() / ".claude" / "plans"
# Vết transcript mà hook UserPromptSubmit không nhận: kết quả lệnh `!`, chỉ dẫn app chèn vào, dấu ngắt lượt.
TRANSCRIPT_ONLY = ("<bash-input>", "<bash-stdout>", "<bash-stderr>", "<browser_instruction>", "<local-command-",
                   "<command-name>", "[Request interrupted")
SCRATCH_RE = re.compile(r"^-private-|^-var-|-scratchpad|claude-worktrees")  # thư mục tạm của eval, test, worktree
MAX_CHARS = 1500
DEV_SHARE = 0.4


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", A.redact_secrets(text)).strip()[:MAX_CHARS]


def gated(prompt: str, min_words: int) -> str:
    """Chữ router thật sự so (rỗng nếu tin bị bỏ qua): như cổng của hook_suggestion."""
    if not isinstance(prompt, str) or not prompt.strip() or prompt.lstrip()[:1] in "/!#":
        return ""
    if A.is_automated_prompt(prompt) or prompt.lstrip().startswith(TRANSCRIPT_ONLY):
        return ""
    text = A.routable_text(prompt)
    return text if len(text.split()) >= min_words else ""


def user_texts(path: Path):
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("type") != "user" or row.get("isMeta") or row.get("isSidechain"):
            continue
        content = (row.get("message") or {}).get("content")
        if isinstance(content, list):
            parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            content = "\n".join(parts) if parts else None
        if isinstance(content, str):
            yield content


def messages(min_words: int) -> list:
    out = []
    for path in sorted(TRANSCRIPTS.glob("*/*.jsonl")):
        if SCRATCH_RE.search(path.parent.name):
            continue
        source = path.parent.name.replace("-Users-macos-Documents-Claude-", "").replace("-Users-macos-Documents-", "")
        for text in user_texts(path):
            text = gated(text, min_words)
            if text:
                out.append(("tin", source, text))
    for path in sorted((A.state_dir() / "last-request").glob("*.json")):
        row = A.read_json(path, {}) or {}
        cwd = str(row.get("cwd") or "")
        if not cwd.startswith(str(PROJECTS)) or "/.tmp/" in cwd or "/.claude/worktrees/" in cwd:
            continue
        text = gated(row.get("prompt") or "", min_words)
        if text:
            out.append(("tin", Path(cwd).name, text))
    return out


def section0_tasks() -> list:
    out = []
    for root in sorted(p for p in PROJECTS.iterdir() if p.is_dir()):
        found = A.read_plan(root)
        if not found:
            continue
        sec = found[2]
        steps = list(A.next_open(sec) or [])
        doing = (sec.get("fields") or {}).get("in_progress")
        if A.has_value(doing):
            steps.append(doing)
        for step in steps:
            step = re.sub(r"^@\w+\s+", "", str(step).strip())  # nhãn @cho, @ban không phải chữ của việc
            if len(step.split()) >= 3:
                out.append(("s0", root.name, step))
    return out


def plan_steps() -> list:
    out = []
    for path in sorted(PLANS.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^## Các bước\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        if not m:
            continue
        for line in m.group(1).splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3 or set(cells[0]) <= set("-: ") or cells[0] in ("#", "Bước"):
                continue
            step = cells[1] if cells[0].isdigit() or len(cells[0]) <= 3 else cells[0]
            step = re.sub(r"\*\*", "", step)
            if len(step.split()) >= 3:
                out.append(("buoc", path.stem[:24], step))
    return out


def eval_none() -> list:
    rows = [json.loads(x) for x in (REPO / "evals" / "router-prompts.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()]
    return [("eval-none", "router-prompts", r["prompt"]) for r in rows if r["expect"] == "none"]


def build(min_words: int) -> list:
    seen, rows = set(), []
    for kind, source, text in messages(min_words) + section0_tasks() + plan_steps() + eval_none():
        text = norm(text)
        key = A.fold(text)
        if not text or key in seen:
            continue
        seen.add(key)
        rid = hashlib.sha1(f"{kind}\0{key}".encode()).hexdigest()[:10]
        split = "dev" if int(rid, 16) % 1000 < DEV_SHARE * 1000 else "test"
        rows.append({"id": rid, "set": kind, "source": source, "split": split, "text": text})
    rows.sort(key=lambda r: r["id"])  # thứ tự theo mã băm: xáo, nhưng ổn định giữa các lần gom
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--show", type=int, default=0, help="in thử N câu mỗi tập")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(REPO / "plugin" / "skills" / "task-router" / "scripts"))
    import route  # noqa: E402
    rows = build(int(route.rules().get("min_words", 4)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    OUT.chmod(0o600)
    counts = {}
    for r in rows:
        counts.setdefault(r["set"], {"dev": 0, "test": 0})[r["split"]] += 1
    print(f"Đã ghi {len(rows)} câu vào {OUT}")
    for kind, c in counts.items():
        print(f"  {kind:<10} dev {c['dev']:>3}  test {c['test']:>3}")
    if args.show:
        for kind in counts:
            for r in [r for r in rows if r["set"] == kind][:args.show]:
                print(f"[{kind}] {r['text'][:140]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
