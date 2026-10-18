#!/usr/bin/env python3
"""Bench skill paper-anatomy: chạy cùng một đề với từng bản skill (cũ, mới) bằng `claude -p`, lưu bài làm để chấm.

MẶC ĐỊNH CHỈ IN KẾ HOẠCH. Thêm --yes mới chạy thật (tính vào hạn mức).

  python3 claude-ai-skills/paper-anatomy-bench/run_bench.py --iteration 1
  python3 claude-ai-skills/paper-anatomy-bench/run_bench.py --iteration 1 --yes --parallel 4

Chạy công bằng:
- Mỗi lượt chạy trong thư mục tạm của hệ điều hành, ngoài agent-stack, chỉ có file PDF và bản skill của nhánh đó
  (thư mục `skill/`). Không nạp skill nào khác (--disable-slash-commands), không MCP, không hook hay plugin của
  người dùng (--setting-sources project). Hai nhánh nhận cùng một prompt; chỉ nội dung `skill/` khác nhau.
- `python3` trong PATH trỏ tới .venv của repo (có PyMuPDF), giống sandbox của claude.ai. Không cho pip.
- Bài làm, transcript và chi phí lưu ở .tmp/paper-anatomy-bench/iteration-N/<việc>/<nhánh>/run-<k>/.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BENCH = REPO / ".tmp" / "paper-anatomy-bench"
# old: bản claude.ai lúc nhập; v3: bản 03/10 (commit 5765e3d), chụp trước khi sửa v4; new: bản đang sửa trong repo
ARMS = {"old": BENCH / "skill-snapshot", "v3": BENCH / "skill-v3",
        "new": REPO / "claude-ai-skills" / "paper-anatomy"}
ALLOWED = ("Read Write Edit Grep Glob Bash(python3 *) Bash(python *) Bash(ls *) Bash(ls) Bash(cat *) "
           "Bash(head *) Bash(tail *) Bash(sed *) Bash(wc *) Bash(mkdir *) Bash(grep *)")
SUFFIX = ("\n\n---\n(Ghi chú của môi trường thử nghiệm, không phải của người dùng) Skill `paper-anatomy` đã được "
          "nạp cho việc này: đọc `skill/SKILL.md` trước rồi làm theo (scripts/ và references/ nằm cạnh nó). "
          "File PDF nằm trong thư mục hiện tại. Người dùng không trả lời được câu hỏi, nên tự quyết các lựa chọn. "
          "Khi xong, ghi NGUYÊN VĂN câu trả lời cuối cùng gửi người dùng vào `outputs/answer.md`.")
GUESS_USD = {"sonnet": 1.2, "opus": 2.4, "haiku": 0.4}


def load_run_eval():
    spec = importlib.util.spec_from_file_location("run_eval", REPO / "evals" / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_evals(selected):
    data = json.loads((HERE / "evals.json").read_text(encoding="utf-8"))
    items = data["evals"]
    if selected and selected != "all":
        want = {s.strip() for s in selected.split(",")}
        items = [e for e in items if str(e["id"]) in want or e["name"] in want]
    return items


def make_bin(root: Path) -> Path:
    """Thư mục bin đặt đầu PATH: python3/python chạy bằng .venv của repo."""
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    py = REPO / ".venv" / "bin" / "python"
    for name in ("python3", "python"):
        target = bin_dir / name
        target.write_text(f'#!/bin/sh\nexec "{py}" "$@"\n', encoding="utf-8")
        target.chmod(0o755)
    return bin_dir


def parse_stream(text: str) -> dict:
    result, tools = {}, []
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            result = ev
        if ev.get("type") == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    tools.append({"name": block.get("name"), "input": block.get("input")})
    return {"result": result, "tools": tools}


def finished(timing_file: Path) -> bool:
    """Lượt đã chạy xong mà không lỗi. timing.json thiếu, hỏng (bị cắt giữa lúc ghi) hay thiếu khóa is_error
    đều coi là chưa xong, để lần chạy sau chạy lại thay vì kẹt."""
    try:
        timing = json.loads(timing_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(timing, dict) and timing.get("is_error") is False


def run_one(ev: dict, arm: str, rep: int, args, work_root: Path, bin_dir: Path, out_root: Path) -> dict:
    run_dir = out_root / ev["name"] / arm / f"run-{rep}"
    if not args.force and finished(run_dir / "timing.json"):
        return {"eval": ev["name"], "arm": arm, "rep": rep, "skipped": True}
    work = work_root / f"{ev['name']}-{arm}-{rep}"
    if work.exists():
        shutil.rmtree(work)
    (work / "outputs").mkdir(parents=True)
    shutil.copy(Path(os.path.expanduser(ev["pdf"])), work / ev["file"])
    shutil.copytree(ARMS[arm], work / "skill", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    prompt = ev["prompt"] + SUFFIX
    cmd = [os.environ.get("AGENT_STACK_CLAUDE_BIN", "claude"), "-p", prompt, "--model", args.model,
           "--effort", args.effort, "--output-format", "stream-json", "--verbose", "--no-session-persistence",
           "--permission-mode", "acceptEdits", "--allowedTools", ALLOWED, "--setting-sources", "project",
           "--disable-slash-commands", "--strict-mcp-config", "--max-budget-usd", str(args.cap_usd)]
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    start, timed_out, stdout = time.time(), False, ""
    try:
        out = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True, timeout=args.timeout, env=env)
        stdout = out.stdout
        stderr = out.stderr[-2000:]
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = "hết giờ"
    seconds = round(time.time() - start, 1)
    parsed = parse_stream(stdout)
    res = parsed["result"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "transcript.jsonl").write_text(stdout, encoding="utf-8")
    outputs = run_dir / "outputs"
    if outputs.exists():
        shutil.rmtree(outputs)
    shutil.copytree(work / "outputs", outputs)
    answer = outputs / "answer.md"
    from_result = False
    if not answer.exists() or not answer.read_text(encoding="utf-8").strip():
        answer.write_text(str(res.get("result") or ""), encoding="utf-8")
        from_result = True
    files = sorted(str(p.relative_to(work)) for p in work.rglob("*")
                   if p.is_file() and "skill" not in p.relative_to(work).parts[:1])
    usage = res.get("usage") or {}
    tokens = sum(int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                                   "cache_read_input_tokens"))
    timing = {"total_tokens": tokens, "duration_ms": int(seconds * 1000), "total_duration_seconds": seconds,
              "cost_usd": res.get("total_cost_usd"), "turns": res.get("num_turns"),
              "is_error": bool(res.get("is_error")) or timed_out or not res, "timed_out": timed_out,
              "subtype": res.get("subtype"), "answer_from_result": from_result, "work_files": files,
              "tool_calls": len(parsed["tools"]), "stderr": stderr if not res else ""}
    (run_dir / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
    (run_dir / "tools.json").write_text(json.dumps(parsed["tools"], ensure_ascii=False, indent=1), encoding="utf-8")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return {"eval": ev["name"], "arm": arm, "rep": rep, **{k: timing[k] for k in ("cost_usd", "turns", "is_error")},
            "seconds": seconds}


def cli_logged_in():
    """True/False theo `claude auth status`; None khi không đọc được, để không chặn nhầm."""
    try:
        out = subprocess.run([os.environ.get("AGENT_STACK_CLAUDE_BIN", "claude"), "auth", "status"],
                             capture_output=True, text=True, timeout=30)
        return bool(json.loads(out.stdout).get("loggedIn"))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bench paper-anatomy (mặc định chỉ in kế hoạch).")
    ap.add_argument("--iteration", type=int, required=True)
    ap.add_argument("--evals", default="all")
    ap.add_argument("--arms", default="old,new")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--cap-usd", type=float, default=4.0, help="trần chi phí mỗi lượt")
    ap.add_argument("--timeout", type=int, default=2700)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--keep", action="store_true", help="giữ thư mục làm việc để soi")
    ap.add_argument("--force", action="store_true", help="chạy lại cả ô đã có kết quả")
    args = ap.parse_args(argv)

    evals = load_evals(args.evals)
    absent = [e["name"] for e in evals if not Path(os.path.expanduser(e["pdf"])).is_file()]
    if absent:
        print("Không thấy file PDF của: " + ", ".join(absent))
        return 2
    arms = [a for a in args.arms.split(",") if a in ARMS]
    missing = [a for a in arms if not (ARMS[a] / "SKILL.md").exists()]
    if missing:
        print(f"Thiếu bản skill cho nhánh: {', '.join(missing)} ({', '.join(str(ARMS[a]) for a in missing)})")
        return 2
    runs = [(e, a, r) for e in evals for a in arms for r in range(args.repeats)]
    work_root = Path(tempfile.gettempdir()) / "agent-stack-paper-bench" / time.strftime("%Y%m%d-%H%M%S")
    leaks = load_run_eval().context_leaks(work_root)
    print(f"Kế hoạch: {len(evals)} việc × {len(arms)} nhánh × {args.repeats} lần = {len(runs)} lượt, "
          f"{args.model} · {args.effort}, song song {args.parallel}.")
    print(f"Ước tính thô: khoảng {len(runs) * GUESS_USD.get(args.model, 1.5):.0f} USD giá niêm yết "
          f"(trần {args.cap_usd} USD mỗi lượt).")
    for e in evals:
        print(f"  {e['id']}. {e['name']} ({e['difficulty']}): {e['tests']}")
    if leaks:
        print("Không chạy được: model sẽ đọc được " + "; ".join(leaks))
        return 2
    if not args.yes:
        print("Chưa chạy. Thêm --yes để chạy thật.")
        return 0
    if cli_logged_in() is False:
        print("Không chạy: CLI `claude` chưa đăng nhập (`claude auth status`). Chạy `claude auth login` rồi chạy lại.")
        return 2
    out_root = BENCH / f"iteration-{args.iteration}"
    out_root.mkdir(parents=True, exist_ok=True)
    bin_dir = make_bin(work_root)
    rows, crashed = [], 0
    with cf.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(run_one, e, a, r, args, work_root, bin_dir, out_root) for e, a, r in runs]
        for fut in cf.as_completed(futures):
            try:
                row = fut.result()
            except Exception as exc:  # một lượt hỏng (thiếu file…) không được làm mất các lượt khác
                print(f"✗ lỗi bộ chạy: {exc!r}", flush=True)
                crashed += 1
                continue
            rows.append(row)
            if row.get("skipped"):
                print(f"= {row['eval']} {row['arm']} #{row['rep']}: đã có, bỏ qua")
            else:
                print(f"{'✗' if row['is_error'] else '✓'} {row['eval']} {row['arm']} #{row['rep']} · "
                      f"{row['cost_usd']} USD · {row['turns']} lượt · {row['seconds']} giây", flush=True)
    if not args.keep:
        shutil.rmtree(work_root, ignore_errors=True)
    spent = sum(r.get("cost_usd") or 0 for r in rows)
    print(f"\nTổng: {spent:.2f} USD. Kết quả: {out_root}")
    failed = len([r for r in rows if not r.get("skipped") and r.get("is_error")]) + crashed
    if failed:
        print(f"{failed} lượt lỗi: xem dòng ✗ ở trên, timing.json và transcript.jsonl của lượt đó. Chạy lại cùng lệnh "
              "thì chỉ chạy lại các lượt lỗi.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
