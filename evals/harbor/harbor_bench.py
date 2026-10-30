#!/usr/bin/env python3
"""Bench Claude Code có và không có agent-stack trên Harbor (xem README.md cùng thư mục).

Lệnh:
  harbor_bench.py make-configs --tasks FILE --name TÊN [--attempts N] [--out DIR]
      sinh cấu hình job (JSON, Harbor đọc qua --config): TÊN.json chạy hai bản Claude Code, TÊN-oracle.json chạy lời
      giải mẫu trên cùng bộ việc để biết grader nào chấm đạt được
  harbor_bench.py export JOB_DIR... --out DIR
      chép result.json, log Claude Code, reward.txt sang thư mục mới và che token Anthropic (chạy trên TUF trước khi
      kéo kết quả về Mac)
  harbor_bench.py compare JOB_DIR... [--oracle JOB_DIR] [--json]
      so ghép cặp theo việc: tỉ lệ đạt, kiểm định McNemar chính xác, token, chi phí, thời gian, và bản có agent-stack
      có thật sự nạp plugin không

Chỉ dùng thư viện chuẩn; chạy được trên Mac (kết quả đã kéo về) hay trên TUF.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from pathlib import Path

PLAIN = "claude-code-plain"
STACK = "claude-code-agent-stack"
ORACLE = "oracle"
MODULE = "agent_stack_agents"
DEFAULTS = {
    "model": "anthropic/claude-sonnet-5-5",
    "effort": "medium",
    "version": "2.1.308",       # Claude Code bản brew stable lúc dựng bench; hai bản dùng cùng phiên bản
    "dataset": "datasets/openthoughts-tblite",
    "concurrent": 3,            # TUF có 15 GB RAM, mỗi việc được cấp tới 4 GB
}


# ---------------------------------------------------------------- make-configs

def read_tasks(path: Path) -> list:
    """Tên việc, mỗi dòng một tên; bỏ dòng trống và dòng bắt đầu bằng #."""
    names = [ln.split("#", 1)[0].strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    names = [n for n in names if n]
    if not names:
        raise SystemExit(f"{path} không có tên việc nào")
    if len(set(names)) != len(names):
        raise SystemExit(f"{path} có tên việc trùng")
    return names


def agent_config(cls: str, opts: dict, extra_env: dict) -> dict:
    return {
        "import_path": f"{MODULE}:{cls}",
        "model_name": opts["model"],
        "kwargs": {"version": opts["version"], "reasoning_effort": opts["effort"]},
        # dùng gói thuê bao: token nằm trong .env trên TUF (CLAUDE_CODE_OAUTH_TOKEN), không bao giờ trong cấu hình
        "env": {"CLAUDE_FORCE_OAUTH": "1", **extra_env},
    }


def make_configs(tasks: list, name: str, attempts: int, opts: dict) -> dict:
    """{tên file: cấu hình}. Hai bản nằm chung một job để Harbor xen kẽ lượt chạy, tránh lệch theo giờ trong ngày."""
    dataset = [{"path": opts["dataset"], "task_names": tasks}]
    common = {"jobs_dir": "jobs", "n_concurrent_trials": opts["concurrent"], "datasets": dataset}
    bench = dict(common, job_name=name, n_attempts=attempts, agents=[
        agent_config("ClaudeCodePlain", opts, {}),
        # tắt lượt kiểm MCP chạy nền lúc mở phiên: chỉ gọi mạng, không đổi gì model thấy
        agent_config("ClaudeCodeAgentStack", opts, {"AGENT_STACK_NO_BACKGROUND": "1"}),
    ])
    oracle = dict(common, job_name=f"{name}-oracle", n_attempts=1, agents=[{"name": ORACLE}])
    return {f"{name}.json": bench, f"{name}-oracle.json": oracle}


def cmd_make_configs(args) -> int:
    opts = {k: getattr(args, k) for k in DEFAULTS}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for fname, cfg in make_configs(read_tasks(Path(args.tasks)), args.name, args.attempts, opts).items():
        (out / fname).write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(out / fname)
    return 0


# ---------------------------------------------------------------- compare

def _seconds(span) -> float | None:
    from datetime import datetime
    try:
        a = datetime.fromisoformat(span["started_at"].replace("Z", "+00:00"))
        b = datetime.fromisoformat(span["finished_at"].replace("Z", "+00:00"))
        return (b - a).total_seconds()
    except (TypeError, KeyError, ValueError, AttributeError):
        return None


def plugin_loaded(trial_dir: Path):
    """True/False theo sự kiện init của Claude Code (stream-json) có nhắc agent-stack không; None khi không có log."""
    logs = sorted(trial_dir.glob("agent/**/claude-code.txt"))
    if not logs:
        return None
    for line in logs[0].read_text(encoding="utf-8", errors="replace").splitlines():
        if '"subtype":"init"' in line.replace(" ", ""):
            return "agent-stack" in line
    return None


def load_trials(job_dirs) -> list:
    trials = []
    for job in job_dirs:
        for res in sorted(Path(job).glob("*/result.json")):
            try:
                d = json.loads(res.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(d, dict) or "task_name" not in d:
                continue
            rewards = (d.get("verifier_result") or {}).get("rewards") or {}
            ar = d.get("agent_result") or {}
            exc = d.get("exception_info") or None
            trials.append({
                "task": d["task_name"],
                "agent": (d.get("agent_info") or {}).get("name") or "?",
                "reward": rewards.get("reward"),
                "exception": (exc.get("exception_type") or "lỗi") if isinstance(exc, dict) else (str(exc) if exc else None),
                "input": ar.get("n_input_tokens"), "cache": ar.get("n_cache_tokens"),
                "output": ar.get("n_output_tokens"), "cost": ar.get("cost_usd"),
                "seconds": _seconds(d.get("agent_execution")),
                "loaded": plugin_loaded(res.parent),
                "trial": res.parent.name,
            })
    return trials


# Lỗi do hạ tầng, không do agent: Harbor vẫn chạy grader sau các lỗi này nên lượt có điểm 0 mà không nói gì về
# chất lượng. Lượt dính lỗi này bị loại cả cặp. Hết giờ, hết context, lỗi thoát chung thì giữ là kết quả thật (luật
# dài hơn có thể chính là nguyên nhân).
INFRA_ERRORS = {"ApiUsageLimitError", "ApiRateLimitError", "ApiOverloadedError", "AgentAuthenticationError",
                "NetworkConnectionError", "ModelNotFoundError"}


def graded(t) -> bool:
    """Lượt dùng được để so: grader đã chấm và không hỏng vì hạ tầng."""
    return t["reward"] is not None and t["exception"] not in INFRA_ERRORS


def passed(t) -> bool:
    return isinstance(t["reward"], (int, float)) and t["reward"] >= 1.0 - 1e-9


def exact_binomial_p(b: int, c: int) -> float:
    """Kiểm định McNemar chính xác (hai phía) trên b, c cặp lệch nhau."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def _summary(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    return {"n": len(vals), "median": statistics.median(vals), "total": sum(vals)}


def compare(trials: list, oracle: list = None, a: str = PLAIN, b: str = STACK) -> dict:
    """So ghép cặp theo việc. Lượt không có điểm (môi trường hỏng) bị loại cả cặp; hết giờ mà grader vẫn chấm thì
    tính như kết quả thật. Nhiều lượt mỗi việc thì so tỉ lệ đạt theo việc (thắng/thua), một lượt thì đúng McNemar."""
    by = {}
    for t in trials:
        by.setdefault((t["agent"], t["task"]), []).append(t)
    tasks = sorted({t["task"] for t in trials if t["agent"] in (a, b)})
    bad_grader = sorted({t["task"] for t in (oracle or []) if not passed(t)})
    oracle_tasks = {t["task"] for t in (oracle or [])}
    rows, excluded = [], []
    for task in tasks:
        if task in bad_grader:
            excluded.append((task, "lời giải mẫu không đạt"))
            continue
        if oracle is not None and task not in oracle_tasks:
            excluded.append((task, "chưa chạy lời giải mẫu"))
            continue
        ta, tb = by.get((a, task), []), by.get((b, task), [])
        graded_a = [t for t in ta if graded(t)]
        graded_b = [t for t in tb if graded(t)]
        if not graded_a or not graded_b:
            excluded.append((task, "thiếu điểm ở một bản: " + ", ".join(
                sorted({t["exception"] or "chưa chạy" for t in ta + tb if not graded(t)}) or ["chưa chạy"])))
            continue
        rows.append({"task": task,
                     "a": sum(passed(t) for t in graded_a) / len(graded_a),
                     "b": sum(passed(t) for t in graded_b) / len(graded_b)})
    worse = [r["task"] for r in rows if r["b"] < r["a"]]   # bản có agent-stack kém hơn
    better = [r["task"] for r in rows if r["b"] > r["a"]]
    paired = {r["task"] for r in rows}

    def arm(name):
        ts = [t for t in trials if t["agent"] == name and t["task"] in paired and graded(t)]
        return {
            "trials": len(ts),
            "pass_rate": (sum(passed(t) for t in ts) / len(ts)) if ts else None,
            "exceptions": sorted({t["exception"] for t in ts if t["exception"]}),
            "infra_dropped": sum(1 for t in trials if t["agent"] == name and t["exception"] in INFRA_ERRORS),
            "n_exceptions": sum(1 for t in ts if t["exception"]),
            "input": _summary(t["input"] for t in ts), "cache": _summary(t["cache"] for t in ts),
            "output": _summary(t["output"] for t in ts), "cost": _summary(t["cost"] for t in ts),
            "seconds": _summary(t["seconds"] for t in ts),
            "loaded": [t["loaded"] for t in ts],
        }
    return {"pairs": len(rows), "rows": rows, "excluded": excluded, "worse": worse, "better": better,
            "p_value": exact_binomial_p(len(worse), len(better)), "a": arm(a), "b": arm(b),
            "names": (a, b)}


def _fmt(s, key="median", digits=0):
    if not s:
        return "—"
    v = s[key]
    return f"{v:,.{digits}f}"


def report(res: dict) -> str:
    a, b = res["names"]
    lines = [f"Cặp việc so được: {res['pairs']}" + (f" (loại {len(res['excluded'])})" if res["excluded"] else "")]
    for task, why in res["excluded"]:
        lines.append(f"  - loại {task}: {why}")
    lines.append("")
    lines.append(f"{'':28s}{a:>26s}{b:>26s}")
    pa, pb = res["a"], res["b"]
    rate = lambda x: "—" if x["pass_rate"] is None else f"{100 * x['pass_rate']:.1f}% ({x['trials']} lượt)"
    lines.append(f"{'Tỉ lệ đạt':28s}{rate(pa):>26s}{rate(pb):>26s}")
    for label, key, digits in (("Token vào (trung vị)", "input", 0), ("Token cache (trung vị)", "cache", 0),
                               ("Token ra (trung vị)", "output", 0), ("Chi phí USD (trung vị)", "cost", 3),
                               ("Thời gian agent, giây (trung vị)", "seconds", 0)):
        lines.append(f"{label:28s}{_fmt(pa[key], digits=digits):>26s}{_fmt(pb[key], digits=digits):>26s}")
    lines.append(f"{'Chi phí USD (tổng)':28s}{_fmt(pa['cost'], 'total', 2):>26s}{_fmt(pb['cost'], 'total', 2):>26s}")
    lines.append(f"{'Lượt lỗi (hết giờ, lỗi agent)':28s}{pa['n_exceptions']:>26d}{pb['n_exceptions']:>26d}")
    lines.append(f"{'Lượt bỏ vì hạ tầng (hạn mức…)':28s}{pa['infra_dropped']:>26d}{pb['infra_dropped']:>26d}")
    lines.append("")
    lines.append(f"Bản có agent-stack kém hơn ở {len(res['worse'])} việc, tốt hơn ở {len(res['better'])} việc; "
                 f"McNemar chính xác p = {res['p_value']:.3f}.")
    for label, names in (("kém hơn", res["worse"]), ("tốt hơn", res["better"])):
        if names:
            lines.append(f"  {label}: {', '.join(names)}")
    loaded_b = res["b"]["loaded"]
    on = sum(1 for x in loaded_b if x is True)
    lines.append(f"Bản có agent-stack nạp plugin ở {on}/{len(loaded_b)} lượt"
                 + (f"; {sum(1 for x in loaded_b if x is None)} lượt không có log" if None in loaded_b else ""))
    leaked = sum(1 for x in res["a"]["loaded"] if x is True)
    if leaked:
        lines.append(f"⚠️ Bản trơn thấy agent-stack ở {leaked} lượt: hai bản không tách nhau, kết quả không dùng được.")
    if res["pairs"] < 100:
        lines.append(f"Lưu ý: {res['pairs']} cặp chỉ đủ thấy chênh lệch lớn; muốn thấy chênh 10 điểm cần khoảng "
                     "160–235 cặp.")
    return "\n".join(lines)


# Token của Anthropic có thể lọt vào log nếu model chạy `env` trong container; che trước khi file rời TUF.
TOKEN_RE = re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}")
EXPORT_NAMES = ("result.json", "claude-code.txt", "reward.txt")


def export(job_dirs, out: Path) -> tuple:
    """Chép result.json, log Claude Code và reward.txt của các job sang `out` (giữ đường dẫn job/lượt/...), che token.
    Trả (số file, số file đã che)."""
    n = masked = 0
    for job in job_dirs:
        job = Path(job)
        if not job.is_dir():
            continue
        for src in sorted(job.rglob("*")):
            if not src.is_file() or src.name not in EXPORT_NAMES:
                continue
            dst = out / job.name / src.relative_to(job)
            dst.parent.mkdir(parents=True, exist_ok=True)
            text = src.read_text(encoding="utf-8", errors="replace")
            clean = TOKEN_RE.sub("[đã che]", text)
            masked += clean != text
            dst.write_text(clean, encoding="utf-8")
            n += 1
    return n, masked


def cmd_export(args) -> int:
    out = Path(args.out)
    try:
        out.mkdir(parents=True)
    except FileExistsError:
        print(f"{out} đã có; chọn thư mục mới", file=sys.stderr)
        return 1
    n, masked = export(args.jobs, out)
    if not n:  # job chưa có lượt nào xong: báo lỗi để fetch dừng trước khi xoá bản cũ trên Mac
        print("Chưa có kết quả nào để chép (job chưa có lượt nào xong?)", file=sys.stderr)
        return 1
    print(f"Đã chép {n} file vào {out}" + (f"; che token trong {masked} file" if masked else ""))
    return 0


def cmd_compare(args) -> int:
    trials = load_trials(args.jobs)
    if not trials:
        print("Không thấy lượt chạy nào (*/result.json) trong các thư mục đã cho.", file=sys.stderr)
        return 1
    oracle = [t for t in load_trials([args.oracle]) if t["agent"] == ORACLE] if args.oracle else None
    res = compare(trials, oracle)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(report(res))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make-configs", help="sinh cấu hình job cho Harbor")
    mk.add_argument("--tasks", required=True, help="file tên việc, mỗi dòng một tên")
    mk.add_argument("--name", required=True, help="tên job, cũng là tên file cấu hình")
    mk.add_argument("--attempts", type=int, default=1, help="số lượt mỗi việc cho mỗi bản (mặc định 1)")
    mk.add_argument("--out", default=".", help="thư mục ghi cấu hình")
    for key, val in DEFAULTS.items():
        mk.add_argument(f"--{key}", type=type(val), default=val, help=f"mặc định {val}")
    cp = sub.add_parser("compare", help="so ghép cặp kết quả hai bản")
    cp.add_argument("jobs", nargs="+", help="thư mục job của Harbor (chứa */result.json)")
    cp.add_argument("--oracle", help="thư mục job chạy lời giải mẫu; việc mà lời giải mẫu không đạt bị loại")
    cp.add_argument("--json", action="store_true")
    ex = sub.add_parser("export", help="chép kết quả ra thư mục mới, che token (chạy trên TUF trước khi kéo về)")
    ex.add_argument("jobs", nargs="+")
    ex.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "make-configs":
        if args.attempts < 1:
            ap.error("--attempts phải từ 1")
        return cmd_make_configs(args)
    if args.cmd == "export":
        return cmd_export(args)
    return cmd_compare(args)


if __name__ == "__main__":
    sys.exit(main())
