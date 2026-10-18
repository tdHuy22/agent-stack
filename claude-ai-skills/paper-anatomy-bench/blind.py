#!/usr/bin/env python3
"""Chấm mù bench paper-anatomy: dựng đề cho người chấm và tổng hợp kết quả, không gọi model.

  python3 claude-ai-skills/paper-anatomy-bench/blind.py prepare --iteration 4 --round 4 --arms v3,new
  (giao mỗi file blind-4/<việc>/prompt.md cho một người chấm opus, chạy song song được)
  python3 claude-ai-skills/paper-anatomy-bench/blind.py summary --round 4
  Lặp nhiều lượt (run_bench.py --repeats 2): mỗi lượt một vòng chấm riêng, rồi gộp khi tổng hợp:
  blind.py prepare --iteration 7 --rep 0 --round 7 ; blind.py prepare --iteration 7 --rep 1 --round 8
  blind.py summary --round 7 8

prepare: với mỗi việc có bài làm của cả hai nhánh, chép hai câu trả lời thành A.md, B.md theo thứ tự ngẫu nhiên
vào .tmp/paper-anatomy-bench/blind-<vòng>/<việc>/, ghi bảng giải mã vào .tmp/paper-anatomy-bench-mappings/
<việc>-<vòng>.json (ngoài cây thư mục người chấm được đọc), và dựng prompt.md từ grader-prompt.md. Ý chính gợi ý
lấy từ lần chấm gần nhất của việc đó, nếu có. Không ghi đè vòng đã có kết quả chấm.
summary: giải mã grading.json của vòng, in điểm theo nhánh, tỉ lệ ý chính đủ, tỉ lệ kiểm chứng ngẫu nhiên đúng,
và nhánh được chọn.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BENCH = REPO / ".tmp" / "paper-anatomy-bench"
MAPPINGS = REPO / ".tmp" / "paper-anatomy-bench-mappings"
SCORES = ("trung_thuc", "do_sau", "dung_cau_hoi", "kiem_chung", "de_doc", "nam_y_1_phut")


def load_evals():
    return json.loads((HERE / "evals.json").read_text(encoding="utf-8"))["evals"]


def seed_facts(name: str, before_round: int) -> str:
    """Ý chính của lần chấm gần nhất trước vòng này, làm gợi ý (người chấm vẫn phải kiểm lại với bài)."""
    for r in range(before_round - 1, 0, -1):
        f = BENCH / f"blind-{r}" / name / "grading.json"
        if f.is_file():
            facts = json.loads(f.read_text(encoding="utf-8")).get("key_facts") or []
            return "\n".join(f"  {k}. {x.get('fact', '')} ({x.get('where', '')})" for k, x in enumerate(facts, 1))
    return "(không có; tự dựng)"


def run_dir(iteration: int, name: str, arm: str, rep: int = 0) -> Path:
    return BENCH / f"iteration-{iteration}" / name / arm / f"run-{rep}"


def usable(run: Path) -> bool:
    """Lượt chạy xong không lỗi và có câu trả lời. Lượt lỗi (CLI chưa đăng nhập, vượt ngân sách…) có thể để lại
    answer.md là thông báo lỗi; không được đưa thứ đó cho người chấm."""
    try:
        timing = json.loads((run / "timing.json").read_text(encoding="utf-8"))
        answer = (run / "outputs" / "answer.md").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    return isinstance(timing, dict) and timing.get("is_error") is False and bool(answer.strip())


def prepare(args) -> int:
    arms = args.arms.split(",")
    if len(arms) != 2:
        print("Cần đúng hai nhánh, ví dụ --arms v3,new")
        return 2
    template = (HERE / "grader-prompt.md").read_text(encoding="utf-8")
    rng = random.Random(args.seed)
    MAPPINGS.mkdir(parents=True, exist_ok=True)
    ready = []
    for ev in load_evals():
        name = ev["name"]
        runs = {a: run_dir(args.iteration, name, a, args.rep) for a in arms}
        if not all(usable(r) for r in runs.values()):
            print(f"- {name}: thiếu bài làm hợp lệ của một nhánh (chưa chạy hay lượt lỗi), bỏ qua")
            continue
        out = BENCH / f"blind-{args.round}" / name
        if (out / "grading.json").exists():
            print(f"- {name}: vòng {args.round} đã có kết quả chấm, không dựng lại")
            continue
        out.mkdir(parents=True, exist_ok=True)
        order = arms[:]
        rng.shuffle(order)
        mapping = {"A": order[0], "B": order[1]}
        for label, arm in mapping.items():
            shutil.copy(runs[arm] / "outputs" / "answer.md", out / f"{label}.md")
        (MAPPINGS / f"{name}-{args.round}.json").write_text(json.dumps(mapping), encoding="utf-8")
        paper_dir = BENCH / "papers" / name
        prompt = template.format(
            prompt=ev["prompt"], paper_txt=paper_dir / "paper.txt",
            paper_note=ev.get("grader_note", "").replace("{papers}", str(BENCH / "papers")),
            answer_a=out / "A.md", answer_b=out / "B.md", seed_facts="\n" + seed_facts(name, args.round),
            out_file=out / "grading.json")
        (out / "prompt.md").write_text(prompt, encoding="utf-8")
        ready.append(out / "prompt.md")
        print(f"+ {name}: {out / 'prompt.md'}")
    print(f"\n{len(ready)} đề sẵn sàng. Bảng giải mã ở {MAPPINGS} (đừng đưa cho người chấm).")
    return 0


def ratio(items, good):
    items = list(items)
    return sum(1 for x in items if x in good) / len(items) if items else None


def summary(args) -> int:
    rounds = args.round
    per_arm, rows = {}, []
    gradings = [(r, g) for r in rounds for g in sorted((BENCH / f"blind-{r}").glob("*/grading.json"))]
    for rnd, grading in gradings:
        name = grading.parent.name if len(rounds) == 1 else f"{grading.parent.name} (vòng {rnd})"
        mapping = json.loads((MAPPINGS / f"{grading.parent.name}-{rnd}.json").read_text(encoding="utf-8"))
        g = json.loads(grading.read_text(encoding="utf-8"))
        winner = mapping.get(g.get("preference"), "hoà")
        rows.append((name, winner, g.get("margin"), g.get("reason", "")))
        for label, arm in mapping.items():
            a = (g.get("answers") or {}).get(label) or {}
            d = per_arm.setdefault(arm, {"scores": {k: [] for k in SCORES}, "facts": [], "checks": []})
            for k in SCORES:
                if isinstance((a.get("scores") or {}).get(k), (int, float)):
                    d["scores"][k].append(a["scores"][k])
            d["facts"] += [f.get("status") for f in a.get("facts") or []]
            d["checks"] += [c.get("verdict") for c in a.get("spot_checks") or []]
    if not rows:
        print("Chưa có grading.json trong " + ", ".join(str(BENCH / f"blind-{r}") for r in rounds))
        return 1
    print("| Việc | Chọn | Chênh | Lý do |\n|---|---|---|---|")
    for name, winner, margin, reason in rows:
        reason = re.sub(r"\s+", " ", reason)
        print(f"| {name} | {winner} | {margin} | {reason} |")
    print("\n| Nhánh | " + " | ".join(SCORES) + " | Ý chính đủ | Kiểm chứng đúng |")
    print("|---|" + "---:|" * (len(SCORES) + 2))
    for arm, d in sorted(per_arm.items()):
        means = [f"{statistics.mean(d['scores'][k]):.1f}" if d["scores"][k] else "–" for k in SCORES]
        pct = [f"{x:.0%}" if x is not None else "–"
               for x in (ratio(d["facts"], {"đủ"}), ratio(d["checks"], {"đúng"}))]
        print(f"| {arm} | " + " | ".join(means + pct) + " |")
    wins = {}
    for _, winner, _, _ in rows:
        wins[winner] = wins.get(winner, 0) + 1
    print("\nThắng: " + ", ".join(f"{k} {v}/{len(rows)}" for k, v in sorted(wins.items())))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chấm mù bench paper-anatomy (không gọi model).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--iteration", type=int, required=True)
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--rep", type=int, default=0, help="lượt lặp (run-<rep>) của run_bench --repeats")
    p.add_argument("--arms", default="v3,new")
    p.add_argument("--seed", type=int, default=None)
    s = sub.add_parser("summary")
    s.add_argument("--round", type=int, nargs="+", required=True, help="một hay nhiều vòng, gộp khi tổng hợp")
    args = ap.parse_args(argv)
    return prepare(args) if args.cmd == "prepare" else summary(args)


if __name__ == "__main__":
    sys.exit(main())
