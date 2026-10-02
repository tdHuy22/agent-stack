#!/usr/bin/env python3
"""Chạy bộ việc eval qua nhiều cấu hình model/effort để chọn cấu hình rẻ nhất mà vẫn giữ chất lượng.

MẶC ĐỊNH CHỈ IN KẾ HOẠCH VÀ ƯỚC TÍNH CHI PHÍ. Mỗi lượt chạy thật tính vào hạn mức của bạn,
nên phải thêm --yes mới chạy.

  python3 evals/run_eval.py --self-test                     # kiểm grader và cơ chế chốt bài, không gọi model
  python3 evals/run_eval.py --configs A,C,D --repeats 2     # xem kế hoạch + ước tính
  python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes --max-total-usd 15
  python3 evals/run_eval.py --report evals/results/*.jsonl  # gộp kết quả của nhiều ngày
  python3 evals/run_eval.py --regrade evals/results/X.jsonl # chấm lại bài đã chốt bằng grader hiện tại

Quy tắc chọn (KE-HOACH.md mục 7.7): lấy cấu hình RẺ NHẤT có tỉ lệ đạt không thấp hơn cấu hình
tốt nhất quá 1 việc, tính trung bình qua các lần lặp. Chỉ chốt khi ma trận đủ (xem matrix_problems).

Chạy công bằng:
- Model làm việc trong thư mục tạm của hệ điều hành, ngoài agent-stack, nên không đọc được
  CLAUDE.md của repo, grader hay lời giải. Thư mục làm việc nằm trong repo thì từ chối chạy.
- Bài làm được chốt ngay khi lượt chạy kết thúc: patch và câu trả lời nằm trong evals/results/.
- Đổi grader thì chấm lại mọi bài đã chốt (--regrade) trước khi so sánh.
- Lượt hỏng vẫn được ghi, chia nhóm: "vận hành" (hết giờ, lỗi, chạm trần chi phí) tính là trượt;
  "môi trường" (chưa đăng nhập, hết hạn mức) không tính cho model nào và làm ma trận thiếu.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

EVALS = Path(__file__).resolve().parent
REPO = EVALS.parent
TASKS = EVALS / "tasks"
RESULTS = EVALS / "results"
# Ước tính thô chi phí mỗi việc (USD theo giá niêm yết), chỉ để báo trước khi chạy.
GUESS_USD = {"haiku": 0.04, "sonnet": 0.12, "opus": 0.25, "fable": 0.6}
SUFFIX = ("\n\nLàm việc ngay trong thư mục hiện tại. Không hỏi lại. "
          "Khi xong, trả lời ngắn gọn kết quả cuối cùng.")
ALLOWED_TOOLS = "Read Write Edit Grep Glob Bash(python3 *) Bash(git diff*) Bash(git status*) Bash(ls*) Bash(cat *)"
TIMEOUT_S = 900
# File chỉ dẫn mà Claude Code và OpenCode tự đọc khi đi ngược lên từ thư mục làm việc.
CONTEXT_FILES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md")
FREEZE_EXCLUDE = ":(exclude,glob)**/__pycache__/**"
# Dấu hiệu lỗi do môi trường (không phải do model) trong thông báo lỗi của CLI.
ENV_MARKERS = ("authenticat", "oauth", "/login", "not logged in", "usage limit", "rate limit", "rate_limit",
               "overloaded", "credit balance")
GIT_ISOLATION = ["-c", "user.name=eval", "-c", "user.email=eval@local", "-c", "commit.gpgsign=false",
                 "-c", "core.hooksPath=/dev/null", "-c", "init.defaultBranch=main"]


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


def digests(task: Path) -> tuple:
    """(đề bài + setup mà model thấy, grader). Lời giải không tính vì model không thấy."""
    def digest(paths):
        h = hashlib.sha256()
        for path in sorted(paths):
            h.update(str(path.relative_to(task)).encode() + b"\0" + path.read_bytes() + b"\0")
        return h.hexdigest()[:16]
    visible = [task / "task.md"] + [p for p in (task / "setup").rglob("*")
                                    if p.is_file() and "__pycache__" not in p.parts]
    return digest(visible), digest([task / "check.py"])


# ---------------------------------------------------------------- thư mục làm việc

def git(workdir: Path, *args: str, data: bytes = None):
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(workdir.parent))
    return subprocess.run(["git", *GIT_ISOLATION, *args], cwd=str(workdir), input=data, capture_output=True, env=env)


def prepare(task: Path, dest: Path, with_solution: bool = False) -> str:
    """Chép setup vào dest và commit làm mốc. with_solution: chép thêm lời giải (không commit).
    Trả về câu trả lời mẫu (nếu có)."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(task / "setup", dest)
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "setup"]):
        git(dest, *args)
    return overlay_solution(task, dest) if with_solution else ""


def overlay_solution(task: Path, dest: Path) -> str:
    answer = ""
    solution = task / "solution"
    for src in sorted(solution.rglob("*")) if solution.exists() else []:
        if not src.is_file():
            continue
        if src.name == "answer.md":
            answer = src.read_text(encoding="utf-8")
            continue
        target = dest / src.relative_to(solution)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, target)
    return answer


def freeze(workdir: Path) -> bytes:
    """Chốt bài làm: diff nhị phân so với commit setup, gồm cả file mới, bỏ __pycache__."""
    git(workdir, "add", "-A", "--", ".", FREEZE_EXCLUDE)
    return git(workdir, "diff", "--cached", "--binary", "HEAD").stdout


def apply_patch(workdir: Path, patch: bytes) -> tuple:
    if not patch.strip():
        return True, ""
    out = git(workdir, "apply", "--binary", "--whitespace=nowarn", "-", data=patch)
    return out.returncode == 0, out.stderr.decode("utf-8", "replace")[-300:]


def default_work_root() -> Path:
    return Path(tempfile.gettempdir()) / "agent-stack-eval"


def context_leaks(work_root: Path) -> list:
    """Những thứ model sẽ thấy mà không nên thấy: file chỉ dẫn ở thư mục cha, hoặc chính agent-stack."""
    root = work_root.expanduser().resolve()
    found = []
    if root == REPO or REPO in root.parents:
        found.append(f"{root} nằm trong agent-stack: model đọc được grader, lời giải và CLAUDE.md của repo")
    for parent in (root, *root.parents):
        found += [str(parent / name) for name in CONTEXT_FILES if (parent / name).is_file()]
    return found


# ---------------------------------------------------------------- chạy và chấm

def classify(data: dict, timed_out: bool) -> tuple:
    """('', '') khi lượt chạy kết thúc bình thường; nếu không, (nhóm lỗi, lý do)."""
    if timed_out:
        return "van-hanh", "hết giờ"
    subtype = str(data.get("subtype") or "")
    if not (data.get("is_error") or subtype.startswith("error")):
        return "", ""
    text = str(data.get("result") or "").lower()
    if any(marker in text for marker in ENV_MARKERS):
        return "moi-truong", "chưa đăng nhập, hết hạn mức hoặc dịch vụ quá tải"
    if "budget" in subtype:
        return "van-hanh", "chạm trần chi phí mỗi lượt"
    return "van-hanh", subtype or "lỗi khi chạy"


def run_one(cfg: dict, task: Path, workdir: Path, cap_usd: float, timeout: int = TIMEOUT_S) -> tuple:
    """Chạy một lượt, chốt bài làm rồi mới chấm. Trả về (dòng kết quả, patch đã chốt)."""
    prompt = (task / "task.md").read_text(encoding="utf-8") + SUFFIX
    cmd = [os.environ.get("AGENT_STACK_CLAUDE_BIN", "claude"), "-p", prompt, "--model", cfg["model"],
           "--effort", cfg["effort"], "--output-format", "json", "--no-session-persistence",
           "--permission-mode", "acceptEdits", "--allowedTools", ALLOWED_TOOLS,
           "--max-budget-usd", str(cap_usd), "--setting-sources", "project"]
    if cfg.get("plugin"):
        cmd += ["--plugin-dir", str(REPO / "plugin")]
    start, timed_out = time.time(), False
    try:
        out = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True, timeout=timeout)
        data = (json.loads(out.stdout) if out.stdout.strip().startswith("{")
                else {"is_error": True, "result": (out.stderr or out.stdout)[-300:]})
    except subprocess.TimeoutExpired:
        data, timed_out = {"is_error": True, "result": ""}, True
    except (OSError, ValueError) as exc:
        data = {"is_error": True, "result": f"lỗi chạy: {exc}"}
    seconds = round(time.time() - start, 1)
    answer = str(data.get("result") or "")
    patch = freeze(workdir)
    cluster, reason = classify(data, timed_out)
    if cluster:
        passed, why = False, reason + (f": {answer[:160]}" if answer else "")
    else:
        passed, why = load_check(task)(workdir, answer)
        cluster = "dat" if passed else "chat-luong"
    input_digest, grader_digest = digests(task)
    row = {"config": cfg["name"], "model": cfg["model"], "effort": cfg["effort"], "plugin": bool(cfg.get("plugin")),
           "task": task.name, "passed": bool(passed), "why": str(why)[:400], "cluster": cluster,
           "cost_usd": data.get("total_cost_usd"), "turns": data.get("num_turns"), "seconds": seconds,
           "models_used": sorted((data.get("modelUsage") or {}).keys()),
           "denied": len(data.get("permission_denials") or []), "answer": answer,
           "input_digest": input_digest, "grader_digest": grader_digest}
    return row, patch


def self_test(tasks: list) -> int:
    """Grader phải chấm TRƯỢT bản chưa sửa, chấm ĐẠT lời giải mẫu, và vẫn ĐẠT khi lời giải đi qua
    patch đã chốt (để --regrade đáng tin). Setup không được chứa grader hay lời giải."""
    root = REPO / ".tmp" / "eval-selftest"
    bad = 0
    for task in tasks:
        check = load_check(task)
        leak = sorted(p.name for p in (task / "setup").rglob("*") if p.name in ("check.py", "answer.md"))
        blank = root / task.name / "blank"
        prepare(task, blank)
        ok_blank, why_blank = check(blank, "")
        solved = root / task.name / "solved"
        answer = prepare(task, solved, with_solution=True)
        patch = freeze(solved)
        ok_solved, why_solved = check(solved, answer)
        replay = root / task.name / "replay"
        prepare(task, replay)
        applied, err = apply_patch(replay, patch)
        ok_replay = applied and check(replay, answer)[0]
        good = (not ok_blank) and ok_solved and ok_replay and not leak
        bad += 0 if good else 1
        detail = "" if good else f"  ({why_blank} | {why_solved} | {err or 'patch'}{' | lộ: ' + ', '.join(leak) if leak else ''})"
        print(f"{'✓' if good else '✗'} {task.name:<20} chưa sửa={'đạt' if ok_blank else 'trượt'} · "
              f"lời giải={'đạt' if ok_solved else 'trượt'} · qua patch={'đạt' if ok_replay else 'trượt'}{detail}")
    shutil.rmtree(root, ignore_errors=True)
    return 1 if bad else 0


# ---------------------------------------------------------------- tổng hợp

def load_rows(paths) -> list:
    rows = []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def matrix_problems(rows: list) -> list:
    """Lý do kết quả CHƯA đủ để chốt cấu hình. Danh sách rỗng nghĩa là đủ."""
    problems = []
    env = sum(r.get("cluster") == "moi-truong" for r in rows)
    if env:
        problems.append(f"{env} lượt hỏng vì môi trường (chưa đăng nhập, hết hạn mức…): chạy lại các ô đó")
    scored = [r for r in rows if r.get("cluster") != "moi-truong"]
    seen = {}
    for r in scored:
        seen.setdefault((r.get("task"), "input"), set()).add(r.get("input_digest"))
        if r.get("cluster") in ("dat", "chat-luong"):
            seen.setdefault((r.get("task"), "grader"), set()).add(r.get("grader_digest"))
    changed_input = sorted(str(t) for (t, kind), d in seen.items() if kind == "input" and len(d) > 1)
    changed_grader = sorted(str(t) for (t, kind), d in seen.items() if kind == "grader" and len(d) > 1)
    if changed_input:
        problems.append("đề bài hoặc setup đã đổi giữa các lượt (" + ", ".join(changed_input[:3]) + "): phải chạy lại")
    if changed_grader:
        problems.append("grader đã đổi giữa các lượt (" + ", ".join(changed_grader[:3]) + "): chạy --regrade")
    configs = sorted({r["config"] for r in scored})
    tasks = sorted({str(r.get("task") or "") for r in scored})
    counts = Counter((r["config"], str(r.get("task") or "")) for r in scored)
    missing = [f"{c}/{t}" for c in configs for t in tasks if not counts[(c, t)]]
    if missing:
        problems.append(f"thiếu {len(missing)} ô cấu hình/việc, ví dụ {', '.join(missing[:3])}")
    sizes = sorted({counts[(c, t)] for c in configs for t in tasks if counts[(c, t)]})
    if len(sizes) > 1:
        problems.append("số lượt lặp không đều giữa các ô (" + ", ".join(map(str, sizes)) + ")")
    if len(configs) < 2:
        problems.append("cần ít nhất 2 cấu hình để so sánh")
    return problems


def summarize(rows: list, n_tasks: int = 0) -> str:
    scored = [r for r in rows if r.get("cluster") != "moi-truong"]
    n_tasks = n_tasks or len({r.get("task") for r in scored}) or 1
    by_cfg = {}
    for r in scored:
        by_cfg.setdefault(r["config"], []).append(r)
    stats = []
    for name, items in by_cfg.items():
        costs = [r["cost_usd"] for r in items if r.get("cost_usd") is not None]
        stats.append({"name": name, "runs": len(items), "rate": sum(bool(r["passed"]) for r in items) / len(items),
                      "ops": sum(r.get("cluster") == "van-hanh" for r in items),
                      "cost": statistics.mean(costs) if costs else None,
                      "p90": sorted(costs)[int(0.9 * (len(costs) - 1))] if costs else None,
                      "secs": statistics.mean(r.get("seconds") or 0 for r in items)})
    problems = matrix_problems(rows)
    best = max((s["rate"] for s in stats), default=0)
    choice = None
    if not problems:
        eligible = [s for s in stats if s["rate"] >= best - 1.0 / n_tasks - 1e-9 and s["cost"] is not None]
        choice = min(eligible, key=lambda s: s["cost"])["name"] if eligible else None
    lines = ["| Cấu hình | Lượt | Tỉ lệ đạt | Lỗi vận hành | USD/việc (TB) | USD p90 | Giây/việc | |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for s in sorted(stats, key=lambda s: s["name"]):
        money = f"{s['cost']:.3f} | {s['p90']:.3f}" if s["cost"] is not None else "– | –"
        lines.append(f"| {s['name']} | {s['runs']} | {s['rate']:.0%} | {s['ops']} | {money} | {s['secs']:.0f} | "
                     f"{'← chọn' if s['name'] == choice else ''} |")
    lines.append("")
    if problems:
        lines.append("**Chưa đủ để chốt cấu hình:**")
        lines += [f"- {p}" for p in problems]
    else:
        lines.append(f"Quy tắc: rẻ nhất trong các cấu hình đạt ≥ {best:.0%} − 1 việc. Lượt chạy đơn lẻ có nhiễu; "
                     "nếu hai cấu hình sát nhau, chạy thêm lượt lặp trước khi chốt.")
    return "\n".join(lines)


def regrade(path: Path) -> int:
    """Chấm lại các bài đã chốt bằng grader hiện tại. Lượt hỏng vì vận hành hay môi trường giữ nguyên."""
    rows = load_rows([path])
    current = {t.name: t for t in load_tasks("all")}
    root = REPO / ".tmp" / "eval-regrade"
    out_rows, changed = [], []
    for i, r in enumerate(rows):
        new, task = dict(r), current.get(r.get("task"))
        patch_file = path.parent / r["patch"] if r.get("patch") else None
        if r.get("cluster") not in ("dat", "chat-luong") or task is None:
            out_rows.append(new)
            continue
        if patch_file is None or not patch_file.exists():
            new["regrade"] = "thiếu patch, giữ kết quả cũ"
            out_rows.append(new)
            continue
        if r.get("input_digest") != digests(task)[0]:
            new["regrade"] = "đề bài hoặc setup đã đổi, không chấm lại được"
            out_rows.append(new)
            continue
        work = root / str(i)
        prepare(task, work)
        applied, err = apply_patch(work, patch_file.read_bytes())
        if not applied:
            new["regrade"] = f"không áp được patch: {err[:120]}"
            out_rows.append(new)
            continue
        passed, why = load_check(task)(work, r.get("answer", ""))
        new.update(passed=bool(passed), why=str(why)[:400], cluster="dat" if passed else "chat-luong",
                   grader_digest=digests(task)[1], regraded=time.strftime("%Y-%m-%d %H:%M"))
        if bool(passed) != bool(r.get("passed")):
            changed.append(f"{r['config']} {r['task']} #{r.get('rep', '?')}: "
                           f"{'đạt' if r.get('passed') else 'trượt'} → {'đạt' if passed else 'trượt'}")
        out_rows.append(new)
    shutil.rmtree(root, ignore_errors=True)
    out = path.with_name(path.stem + ".regraded.jsonl")
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out_rows), encoding="utf-8")
    print(f"Chấm lại {len(rows)} lượt bằng grader hiện tại → {out}")
    print("\n".join(["Đổi kết quả:"] + [f"- {c}" for c in changed]) if changed else "Không lượt nào đổi kết quả.")
    print()
    print(summarize(out_rows))
    return 0


def provenance(cfgs: list, tasks: list, args, work_root: Path) -> dict:
    """Ghi lại điều kiện chạy để các lần chạy so được với nhau."""
    def sh(*cmd):
        try:
            out = subprocess.run(list(cmd), capture_output=True, text=True, timeout=20)
            return out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""
    plugin = json.loads((REPO / "plugin" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return {"repo_commit": sh("git", "--no-optional-locks", "-C", str(REPO), "rev-parse", "HEAD"),
            "repo_dirty": bool(sh("git", "--no-optional-locks", "-C", str(REPO), "status", "--porcelain")),
            "claude_version": sh(os.environ.get("AGENT_STACK_CLAUDE_BIN", "claude"), "--version"),
            "plugin_version": plugin.get("version"),
            "user_claude_md": (Path.home() / ".claude" / "CLAUDE.md").exists(),
            "configs": cfgs, "tasks": {t.name: digests(t) for t in tasks}, "repeats": args.repeats,
            "cap_usd": args.cap_usd, "timeout_s": TIMEOUT_S, "allowed_tools": ALLOWED_TOOLS,
            "work_root": str(work_root)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chạy eval (mặc định chỉ in kế hoạch).")
    ap.add_argument("--configs", default="A,C,D")
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--yes", action="store_true", help="chạy thật (tốn hạn mức)")
    ap.add_argument("--self-test", action="store_true", help="kiểm grader, không gọi model")
    ap.add_argument("--report", nargs="+", metavar="JSONL", help="tổng hợp các file kết quả đã có, không gọi model")
    ap.add_argument("--regrade", metavar="JSONL", help="chấm lại bài đã chốt bằng grader hiện tại, không gọi model")
    ap.add_argument("--work-root", help="nơi model làm việc (mặc định: thư mục tạm của hệ điều hành, ngoài agent-stack)")
    ap.add_argument("--keep-workdirs", action="store_true", help="giữ thư mục làm việc sau khi chấm, để soi lỗi")
    ap.add_argument("--max-total-usd", type=float, default=15.0, help="dừng khi tổng chi phí vượt mức này")
    ap.add_argument("--cap-usd", type=float, default=1.0, help="trần chi phí mỗi lượt")
    args = ap.parse_args(argv)

    if args.report:
        print(summarize(load_rows(args.report)))
        return 0
    if args.regrade:
        return regrade(Path(args.regrade))
    tasks = load_tasks(args.tasks)
    if args.self_test:
        return self_test(tasks)
    all_cfgs = json.loads((EVALS / "configs.json").read_text(encoding="utf-8"))["configs"]
    cfgs = [dict(all_cfgs[n], name=n) for n in args.configs.split(",") if n in all_cfgs]
    runs = [(c, t, r) for c in cfgs for t in tasks for r in range(args.repeats)]
    estimate = sum(GUESS_USD.get(c["model"], 0.2) for c, _, _ in runs)
    work_root = Path(args.work_root).expanduser() if args.work_root else default_work_root()
    print(f"Kế hoạch: {len(cfgs)} cấu hình × {len(tasks)} việc × {args.repeats} lần = {len(runs)} lượt.")
    print(f"Ước tính thô: khoảng {estimate:.1f} USD theo giá niêm yết (gói thuê bao: tính vào hạn mức 5 giờ/tuần).")
    for c in cfgs:
        print(f"  {c['name']}: {c['model']} · {c['effort']}" + (" · có plugin agent-stack" if c.get("plugin") else "")
              + f" — {c.get('note', '')}")
    print(f"Model làm việc trong: {work_root}")
    leaks = context_leaks(work_root)
    if leaks:
        print("Không chạy được ở đây, vì model sẽ đọc được:")
        print("\n".join(f"  - {x}" for x in leaks))
        print("Chọn --work-root khác.")
        return 2
    if not args.yes:
        print("Chưa chạy. Thêm --yes để chạy thật (nên chia ra nhiều ngày; gộp lại bằng --report).")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    RESULTS.mkdir(exist_ok=True)
    out_file = RESULTS / f"{stamp}.jsonl"
    (RESULTS / f"{stamp}.meta.json").write_text(
        json.dumps(provenance(cfgs, tasks, args, work_root), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows, spent = [], 0.0
    for cfg, task, rep in runs:
        if spent > args.max_total_usd:
            print(f"Dừng: đã vượt trần {args.max_total_usd} USD.")
            break
        workdir = work_root / stamp / cfg["name"] / f"{task.name}-{rep}"
        workdir.parent.mkdir(parents=True, exist_ok=True)
        prepare(task, workdir)
        row, patch = run_one(cfg, task, workdir, args.cap_usd)
        rel = Path(stamp) / cfg["name"] / f"{task.name}-{rep}.patch"
        (RESULTS / rel).parent.mkdir(parents=True, exist_ok=True)
        (RESULTS / rel).write_bytes(patch)
        row.update(rep=rep, stamp=stamp, patch=rel.as_posix())
        rows.append(row)
        spent += row["cost_usd"] or 0
        with out_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{'✓' if row['passed'] else '✗'} {cfg['name']} {task.name} #{rep} · {row['cost_usd']} USD · "
              f"{row['why'][:80]}")
        if not args.keep_workdirs:
            shutil.rmtree(workdir, ignore_errors=True)
        if row["cluster"] == "moi-truong":
            print("Dừng: lỗi môi trường (chưa đăng nhập, hết hạn mức hoặc dịch vụ quá tải). "
                  "Chạy `claude /login` hoặc đợi hạn mức, rồi chạy lại các ô còn thiếu.")
            break
    if not args.keep_workdirs:
        shutil.rmtree(work_root / stamp, ignore_errors=True)
    print()
    print(summarize(rows, len(tasks)))
    print(f"\nKết quả chi tiết: {out_file} (điều kiện chạy: {stamp}.meta.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
