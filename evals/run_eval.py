#!/usr/bin/env python3
"""Chạy bộ việc eval qua nhiều cấu hình model/effort để chọn cấu hình rẻ nhất mà vẫn giữ chất lượng.

MẶC ĐỊNH CHỈ IN KẾ HOẠCH VÀ ƯỚC TÍNH CHI PHÍ. Mỗi lượt chạy thật tính vào hạn mức của bạn,
nên phải thêm --yes mới chạy.

  python3 evals/run_eval.py --self-test                  # kiểm grader bằng lời giải mẫu, không gọi model
  python3 evals/run_eval.py --configs A,C,D --repeats 2  # xem kế hoạch + ước tính
  python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes --max-total-usd 15

Quy tắc chọn (KE-HOACH.md mục 7.7): lấy cấu hình RẺ NHẤT có tỉ lệ đạt không thấp hơn
cấu hình tốt nhất quá 1 việc (trên toàn bộ việc), tính trung bình qua các lần lặp.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

EVALS = Path(__file__).resolve().parent
REPO = EVALS.parent
TASKS = EVALS / "tasks"
# Ước tính thô chi phí mỗi việc (USD theo giá niêm yết), chỉ để báo trước khi chạy.
GUESS_USD = {"haiku": 0.04, "sonnet": 0.12, "opus": 0.25, "fable": 0.6}
SUFFIX = ("\n\nLàm việc ngay trong thư mục hiện tại. Không hỏi lại. "
          "Khi xong, trả lời ngắn gọn kết quả cuối cùng.")
ALLOWED_TOOLS = "Read Write Edit Grep Glob Bash(python3 *) Bash(git diff*) Bash(git status*) Bash(ls*) Bash(cat *)"


def load_tasks(selected: str) -> list:
    tasks = sorted(p.parent for p in TASKS.glob("*/task.md"))
    if selected and selected != "all":
        names = {s.strip() for s in selected.split(",")}
        tasks = [t for t in tasks if t.name in names]
    return tasks


def load_check(task: Path):
    spec = importlib.util.spec_from_file_location(f"check_{task.name.replace('-', '_')}", task / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check


def prepare(task: Path, dest: Path, with_solution: bool = False) -> str:
    """Chép setup (và lời giải nếu cần) vào dest, khởi tạo git. Trả về câu trả lời mẫu (nếu có)."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(task / "setup", dest)
    answer = ""
    if with_solution and (task / "solution").exists():
        for src in (task / "solution").rglob("*"):
            if src.is_file():
                if src.name == "answer.md":
                    answer = src.read_text(encoding="utf-8")
                    continue
                target = dest / src.relative_to(task / "solution")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, target)
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(dest.parent))
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=eval", "-c", "user.email=eval@local",
                                                  "commit", "-q", "-m", "setup"]):
        subprocess.run(["git", *args], cwd=str(dest), capture_output=True, env=env)
    return answer


def self_test(tasks: list) -> int:
    """Grader phải chấm TRƯỢT bản chưa sửa và chấm ĐẠT bản lời giải mẫu."""
    root = REPO / ".tmp" / "eval-selftest"
    bad = 0
    for task in tasks:
        check = load_check(task)
        blank = root / task.name / "blank"
        prepare(task, blank)
        ok_blank, why_blank = check(blank, "")
        solved = root / task.name / "solved"
        answer = prepare(task, solved, with_solution=True)
        ok_solved, why_solved = check(solved, answer)
        good = (not ok_blank) and ok_solved
        bad += 0 if good else 1
        print(f"{'✓' if good else '✗'} {task.name:<20} chưa sửa={'đạt' if ok_blank else 'trượt'} · "
              f"lời giải={'đạt' if ok_solved else 'trượt'}" + ("" if good else f"  ({why_blank} | {why_solved})"))
    shutil.rmtree(root, ignore_errors=True)
    return 1 if bad else 0


def run_one(cfg: dict, task: Path, workdir: Path, cap_usd: float) -> dict:
    prompt = (task / "task.md").read_text(encoding="utf-8") + SUFFIX
    cmd = [os.environ.get("AGENT_STACK_CLAUDE_BIN", "claude"), "-p", prompt, "--model", cfg["model"],
           "--effort", cfg["effort"], "--output-format", "json", "--no-session-persistence",
           "--permission-mode", "acceptEdits", "--allowedTools", ALLOWED_TOOLS,
           "--max-budget-usd", str(cap_usd), "--setting-sources", "project"]
    if cfg.get("plugin"):
        cmd += ["--plugin-dir", str(REPO / "plugin")]
    start = time.time()
    try:
        out = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True, timeout=900)
        data = json.loads(out.stdout) if out.stdout.strip().startswith("{") else {}
    except (subprocess.TimeoutExpired, ValueError) as exc:
        data, out = {"is_error": True, "result": f"lỗi chạy: {exc}"}, None
    result = data.get("result") or ""
    passed, why = load_check(task)(workdir, result) if not data.get("is_error") else (False, result[:200])
    return {"config": cfg["name"], "task": task.name, "passed": bool(passed), "why": why,
            "cost_usd": data.get("total_cost_usd"), "turns": data.get("num_turns"),
            "seconds": round(time.time() - start, 1), "error": bool(data.get("is_error")),
            "auth_error": "authenticat" in result.lower() or "oauth" in result.lower()}


def summarize(rows: list, n_tasks: int) -> str:
    by_cfg = {}
    for r in rows:
        by_cfg.setdefault(r["config"], []).append(r)
    stats = []
    for name, items in by_cfg.items():
        costs = [r["cost_usd"] for r in items if r["cost_usd"] is not None]
        pass_rate = sum(r["passed"] for r in items) / len(items)
        p90 = sorted(costs)[int(0.9 * (len(costs) - 1))] if costs else None
        stats.append((name, pass_rate, statistics.mean(costs) if costs else None, p90,
                      statistics.mean(r["seconds"] for r in items)))
    best = max(s[1] for s in stats) if stats else 0
    margin = 1.0 / n_tasks if n_tasks else 0
    eligible = [s for s in stats if s[1] >= best - margin - 1e-9 and s[2] is not None]
    choice = min(eligible, key=lambda s: s[2])[0] if eligible else None
    lines = ["| Cấu hình | Tỉ lệ đạt | USD/việc (TB) | USD p90 | Giây/việc | |", "|---|---:|---:|---:|---:|---|"]
    for name, rate, mean_cost, p90, secs in sorted(stats):
        mark = "← chọn" if name == choice else ""
        lines.append(f"| {name} | {rate:.0%} | {mean_cost:.3f} | {p90:.3f} | {secs:.0f} | {mark} |"
                     if mean_cost is not None else f"| {name} | {rate:.0%} | – | – | {secs:.0f} | {mark} |")
    lines.append("")
    lines.append(f"Quy tắc: rẻ nhất trong các cấu hình đạt ≥ {best:.0%} − 1 việc. Lượt chạy đơn lẻ có nhiễu; "
                 "nếu hai cấu hình sát nhau, chạy thêm lượt lặp trước khi chốt.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chạy eval (mặc định chỉ in kế hoạch).")
    ap.add_argument("--configs", default="A,C,D")
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--yes", action="store_true", help="chạy thật (tốn hạn mức)")
    ap.add_argument("--self-test", action="store_true", help="kiểm grader, không gọi model")
    ap.add_argument("--max-total-usd", type=float, default=15.0, help="dừng khi tổng ước tính vượt mức này")
    ap.add_argument("--cap-usd", type=float, default=1.0, help="trần chi phí mỗi lượt")
    args = ap.parse_args(argv)

    tasks = load_tasks(args.tasks)
    if args.self_test:
        return self_test(tasks)
    all_cfgs = json.loads((EVALS / "configs.json").read_text(encoding="utf-8"))["configs"]
    cfgs = [dict(all_cfgs[n], name=n) for n in args.configs.split(",") if n in all_cfgs]
    runs = [(c, t, r) for c in cfgs for t in tasks for r in range(args.repeats)]
    estimate = sum(GUESS_USD.get(c["model"], 0.2) for c, _, _ in runs)
    print(f"Kế hoạch: {len(cfgs)} cấu hình × {len(tasks)} việc × {args.repeats} lần = {len(runs)} lượt.")
    print(f"Ước tính thô: khoảng {estimate:.1f} USD theo giá niêm yết (gói thuê bao: tính vào hạn mức 5 giờ/tuần).")
    for c in cfgs:
        print(f"  {c['name']}: {c['model']} · {c['effort']}" + (" · có plugin agent-stack" if c.get("plugin") else "")
              + f" — {c.get('note', '')}")
    if not args.yes:
        print("Chưa chạy. Thêm --yes để chạy thật (nên chia ra nhiều ngày để không đốt hạn mức tuần).")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = EVALS / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{stamp}.jsonl"
    rows, spent = [], 0.0
    for cfg, task, rep in runs:
        if spent > args.max_total_usd:
            print(f"Dừng: đã vượt trần {args.max_total_usd} USD.")
            break
        workdir = REPO / ".tmp" / "eval" / stamp / cfg["name"] / f"{task.name}-{rep}"
        workdir.parent.mkdir(parents=True, exist_ok=True)
        prepare(task, workdir)
        row = run_one(cfg, task, workdir, args.cap_usd)
        rows.append(row)
        spent += row["cost_usd"] or 0
        with out_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{'✓' if row['passed'] else '✗'} {cfg['name']} {task.name} #{rep} · {row['cost_usd']} USD · {row['why'][:80]}")
        if row["auth_error"]:
            print("Dừng: Claude Code chưa đăng nhập. Chạy `claude /login` rồi thử lại.")
            break
    print()
    print(summarize(rows, len(tasks)))
    print(f"\nKết quả chi tiết: {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
