#!/usr/bin/env python3
"""Đo lớp model của router (GĐ5): độ trễ `claude -p`, rồi độ chính xác của hai lớp so với lớp từ khóa.

Bộ câu thật ở `state/router-eval/set.jsonl` (evals/router_real_set.py gom), nhãn ở `state/router-eval/labels.jsonl`
(subagent Opus gắn, không thấy đầu ra của router). Kết quả ở `state/router-eval/` (ngoài git: có mã câu và số đo).
Gọi model thật tốn hạn mức nên cần `--yes`; mặc định chỉ in kế hoạch chạy. Mọi lần gọi được đếm vào
`state/router-eval/calls.json`, vượt `--budget` thì dừng.

  router_model_eval.py                                   in kế hoạch: prompt, số câu sẽ hỏi, binary
  router_model_eval.py latency --yes [--n 10 --gap 120 --cold 3]   đo độ trễ, xen kẽ haiku và sonnet
  router_model_eval.py run --yes --model haiku --split dev          hỏi model trên các câu không chắc
  router_model_eval.py report [--split test] [--hard-page]          điểm ròng, điều kiện đạt, trang câu khó

Điểm mỗi câu (bạn chốt 15/11/2026, ngưỡng +10 điểm %): gợi ý đúng mức +1 (luật nằm trong nhãn, hay cùng mức tối thiểu
của nhãn; im lặng khi nhãn chấp nhận `none`), không gợi ý 0, gợi ý sai −1. Hai lớp chỉ dùng kết quả model khi lớp
từ khóa không chắc (route.uncertain) và lần gọi xong trong hạn chờ (`wait_s`).
"""
from __future__ import annotations

import argparse
import html
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugin" / "lib"))
sys.path.insert(0, str(REPO / "plugin" / "skills" / "task-router" / "scripts"))
import agentstack as A  # noqa: E402
import route  # noqa: E402
import routemodel as RM  # noqa: E402

DIR = A.state_dir() / "router-eval"
MODELS = {"haiku": "haiku", "sonnet": "sonnet"}
BUDGET = 480


def load(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def eval117() -> list:
    rows = load(REPO / "evals" / "router-prompts.jsonl")
    return [{"id": f"e117-{i:03d}", "set": "eval117", "source": "router-prompts", "split": "all", "text": r["prompt"],
             "expect": r["expect"]} for i, r in enumerate(rows)]


def cfg_for(model: str) -> dict:
    cfg = RM.config(route.rules())
    cfg.update(model=MODELS[model], effort="low")
    return cfg


def gated(row) -> bool:
    if row["set"] in ("s0", "buoc"):
        return True
    return len(row["text"].split()) >= int(route.rules().get("min_words", 4))


def to_ask(rows) -> list:
    return [r for r in rows if gated(r) and route.uncertain(r["text"], (), RM.config(route.rules())["long_words"])]


# ---- đếm lần gọi ----

def calls_used() -> int:
    return int((A.read_json(DIR / "calls.json", {}) or {}).get("calls") or 0)


def add_calls(n: int) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    A.write_json_atomic(DIR / "calls.json", {"calls": calls_used() + n, "ts": time.time()})


def guard_budget(n: int, budget: int) -> bool:
    used = calls_used()
    if used + n > budget:
        print(f"Dừng: đã gọi {used} lần, thêm {n} sẽ vượt trần {budget} (hỏi người dùng rồi chạy lại với --budget).")
        return False
    return True


# ---- độ trễ ----

def latency(args) -> int:
    binary = RM.find_binary()
    if not binary:
        print("Không thấy binary claude.")
        return 2
    total = len(args.models.split(",")) * args.n
    if not args.yes:
        print(f"Sẽ gọi {total} lần ({args.models}, {args.n} lần mỗi model, xen kẽ), binary {binary}. Thêm --yes để chạy.")
        return 0
    if not guard_budget(total, args.budget):
        return 1
    sessions = A.state_dir() / "sessions.jsonl"
    marker = str(RM.child_cwd().resolve())

    def child_lines() -> int:  # dòng SessionStart từ thư mục làm việc của phiên con (phiên khác mở thì không tính)
        if not sessions.exists():
            return 0
        text = sessions.read_text(encoding="utf-8", errors="replace").splitlines()
        return sum(1 for x in text if marker in x or "agent-stack-router" in x)

    before = child_lines()
    rules = route.rules()
    texts = ["."] + [r["text"] for r in load(DIR / "set.jsonl") if r["set"] == "tin"][: args.n - 1]
    out = DIR / "latency.jsonl"
    cold_at = set(range(args.n - args.cold, args.n)) if args.cold else set()
    for i in range(args.n):
        if i in cold_at and args.gap:
            print(f"  chờ {args.gap} giây (lần lạnh)…", flush=True)
            time.sleep(args.gap)
        for model in args.models.split(","):
            cfg = cfg_for(model)
            res = RM.call(binary, cfg, RM.system_prompt(rules, cfg), RM.user_prompt(texts[i % len(texts)]), 60)
            add_calls(1)
            rec = dict(res, model=model, i=i, cold=i in cold_at, empty=i == 0, ts=time.time(), digest=RM.prompt_digest(
                rules, cfg))
            rec.pop("raw", None)
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            print(f"  {model:<6} #{i} {res['status']:<7} {res.get('ms')} ms (CLI {res.get('cli_ms')}, API "
                  f"{res.get('api_ms')}) vào {res.get('tokens_in')} ra {res.get('tokens_out')}", flush=True)
    print(f"Dòng SessionStart của phiên con trong state/sessions.jsonl: {child_lines() - before} (phải là 0: phiên con "
          "không chạy hook của agent-stack).")
    return 0


# ---- độ chính xác ----

def result_path(model: str) -> Path:
    return DIR / f"results-{model}.jsonl"


def done_ids(model: str, digest: str) -> set:
    return {r["id"] for r in load(result_path(model)) if r.get("digest") == digest}


def run(args) -> int:
    binary = RM.find_binary()
    rules = route.rules()
    cfg = cfg_for(args.model)
    system = RM.system_prompt(rules, cfg)
    system_many = RM.system_prompt(rules, cfg, many=True)
    digest = RM.prompt_digest(rules, cfg)
    allowed = [rid for rid, _ in RM.choices(rules, cfg)]
    labeled = {x["id"] for x in load(DIR / "labels.jsonl")}
    rows = [r for r in load(DIR / "set.jsonl") if args.split in ("all", r["split"]) and r["id"] in labeled]
    if args.with117:
        rows += eval117()
    if args.sets:
        rows = [r for r in rows if r["set"] in args.sets.split(",")]
    done = set() if args.redo else done_ids(args.model, digest)
    asked = [r for r in to_ask(rows) if r["id"] not in done]
    singles = [r for r in asked if r["set"] != "buoc"]
    batches = {}
    for r in asked:
        if r["set"] == "buoc":
            batches.setdefault(r["source"], []).append(r)
    n_calls = len(singles) + len(batches)
    print(f"{args.model}: {len(asked)} câu không chắc chưa có kết quả ({len(singles)} lẻ, {len(batches)} lô bước), "
          f"{n_calls} lần gọi; prompt {len(system)} ký tự, mã {digest}; binary {binary}")
    if not args.yes or not n_calls:
        return 0
    if not binary or not guard_budget(n_calls, args.budget):
        return 1
    out = result_path(args.model)

    def one(job):
        texts = [r["text"] for r in job]
        res = RM.call(binary, cfg, system if len(job) == 1 else system_many,
                      RM.user_prompt(texts[0] if len(job) == 1 else texts), 60)
        ids = RM.parse_ids(res.get("raw", ""), allowed, len(job) if len(job) > 1 else 0) if res["status"] == "ok" \
            else ([None] * len(job) if len(job) > 1 else None)
        lines = []
        for k, r in enumerate(job):
            rid = ids[k] if len(job) > 1 and isinstance(ids, list) else ids
            lines.append({"id": r["id"], "digest": digest, "rule": rid, "status": res["status"], "ms": res.get("ms"),
                          "cli_ms": res.get("cli_ms"), "api_ms": res.get("api_ms"), "tokens_in": res.get("tokens_in"),
                          "tokens_out": res.get("tokens_out"), "cost": res.get("cost"), "batch": len(job),
                          "raw": (res.get("raw") or "")[:80] if rid is None else ""})
        return lines

    jobs = [[r] for r in singles] + list(batches.values())
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for lines in pool.map(one, jobs):
            add_calls(1)
            with out.open("a", encoding="utf-8") as fh:
                for line in lines:
                    fh.write(json.dumps(line) + "\n")
            bad = [x for x in lines if x["rule"] is None]
            print(f"  {lines[0]['ms']} ms {lines[0]['status']} {len(lines)} câu" + (f", {len(bad)} không đọc được" if bad
                                                                                       else ""), flush=True)
    return 0


# ---- chấm ----

def level(rule_id):
    hit = route.rule_hit(rule_id) if rule_id else None
    return (hit["model"], hit["effort"]) if hit else None


def ranks(lv):
    S = route.stack_lib()
    return (S.MODEL_RANK.get(lv[0], -1), S.EFFORT_RANK.get(lv[1], -1)) if lv else None


def judge(rule_id, label) -> dict:
    """Điểm một gợi ý so với nhãn: {score, under, over2}."""
    rules_ok = set(label.get("rules") or [])
    lmin = tuple(label["min"]) if label.get("min") else None
    if not rule_id:
        return {"score": 1 if "none" in rules_ok else 0, "under": False, "over2": False}
    lv = level(rule_id)
    ok = rule_id in rules_ok or (lmin is not None and lv == lmin)
    S = route.stack_lib()
    under = bool(lmin and lv and not S.at_least(lv, lmin))
    over2 = bool(lmin and lv and S.at_least(lv, lmin) and sum(ranks(lv)) - sum(ranks(lmin)) >= 2)
    return {"score": 1 if ok else -1, "under": under, "over2": over2}


def wait_for(row, mode: str) -> float:
    """Hạn chờ (ms) theo cách triển khai: `cho` = mỗi tin chờ wait_s; `nen` = tin nhắn không chờ (kết quả chỉ vào nhật
    ký), việc trong §0 dùng kết quả nền lúc mở phiên (không giới hạn), bước kế hoạch chờ tới plan_wait_s."""
    cfg = RM.config(route.rules())
    if mode == "khong-han":  # bỏ hạn chờ: model đúng sai thế nào, không tính chậm
        return float("inf")
    if row["set"] == "s0":
        return float("inf") if mode == "nen" else cfg["wait_s"] * 1000
    if row["set"] == "buoc":
        return cfg["plan_wait_s"] * 1000
    return 0.0 if mode == "nen" else cfg["wait_s"] * 1000


def layers(row, result, wait_ms):
    """(gợi ý lớp từ khóa, gợi ý hai lớp, model có được dùng không)."""
    if not gated(row):
        return None, None, False
    kw = route.suggest(row["text"])
    if not route.uncertain(row["text"], (), RM.config(route.rules())["long_words"]) or not result:
        return (kw or {}).get("rule"), (kw or {}).get("rule"), False
    used = result.get("status") == "ok" and (result.get("ms") or 10 ** 9) <= wait_ms and result.get("rule")
    rule = result["rule"] if used else None
    both = route.combine(kw, None if rule == "none" else rule)
    return (kw or {}).get("rule"), (both or {}).get("rule"), bool(used)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(q * (len(xs) - 1)))] if xs else None


def report(args) -> int:
    rows = {r["id"]: r for r in load(DIR / "set.jsonl")}
    labels = {x["id"]: x for x in load(DIR / "labels.jsonl")}
    wait_ms = RM.config(route.rules())["wait_s"] * 1000
    print(f"Cách triển khai khi chấm: {args.mode} ({'mỗi tin chờ' if args.mode == 'cho' else 'tin nhắn chạy nền'}); "
          f"tập quyết định: {args.decide}")
    lat = load(DIR / "latency.jsonl")
    if lat:
        print("Độ trễ (đợt 1, gọi tuần tự):")
        for model, digest in sorted({(x["model"], x.get("digest") or "v1") for x in lat}):
            ok = [x for x in lat if x["model"] == model and (x.get("digest") or "v1") == digest and x["status"] == "ok"]
            ms = [x["ms"] for x in ok]
            boot = [x["cli_ms"] - x["api_ms"] for x in ok if x.get("cli_ms") and x.get("api_ms")]
            empty = [x["tokens_in"] for x in ok if x.get("empty")]
            if ms:
                print(f"  {model:<6} prompt {digest:<12} n={len(ms)} p50 {pct(ms, .5)} ms, p90 {pct(ms, .9)} ms, max {max(ms)} ms; phần "
                      f"ngoài API p50 {pct(boot, .5)} ms; token vào câu rỗng {empty[:1]}; lỗi "
                      f"{sum(1 for x in lat if x['model'] == model and x['status'] != 'ok')}; token ra p50 "
                      f"{pct([x.get('tokens_out') or 0 for x in ok], .5)}, max {max(x.get('tokens_out') or 0 for x in ok)}")
    verdict = {}
    for model in MODELS:
        res = {}
        for x in load(result_path(model)):
            res[x["id"]] = x  # bản sau cùng của mỗi câu (prompt mới nhất)
        if not res:
            continue
        print(f"\n== {model} ({len(res)} câu có kết quả) ==")
        ms_all = [x["ms"] for x in res.values() if x.get("status") == "ok" and x.get("batch", 1) == 1]
        if ms_all:
            print(f"  độ trễ lúc đo độ chính xác (2 luồng): p50 {pct(ms_all, .5)} ms, p90 {pct(ms_all, .9)} ms; quá hạn "
                  f"{wait_ms:.0f} ms: {sum(1 for m in ms_all if m > wait_ms)}/{len(ms_all)}")
        totals = {"kw": 0, "two": 0, "n": 0, "under_model": 0, "under_abs": 0, "over2": 0, "fixed": 0, "broken": 0}
        by_set = {}
        for rid, row in rows.items():
            if args.split != "all" and row["split"] != args.split:
                continue
            label = labels.get(rid)
            if not label:
                continue
            kw, two, _ = layers(row, res.get(rid), wait_for(row, args.mode))
            jk, jt = judge(kw, label), judge(two, label)
            s = by_set.setdefault(row["set"], {"kw": 0, "two": 0, "n": 0})
            for d in ((s, totals) if row["set"] in args.decide.split(",") else (s,)):
                d["kw"] += jk["score"]
                d["two"] += jt["score"]
                d["n"] += 1
            if row["set"] not in args.decide.split(","):
                continue  # các đếm dưới chỉ tính trên tập quyết định
            if label.get("risk_high") and jt["under"]:
                totals["under_abs"] += 1
                if two != kw:
                    totals["under_model"] += 1
            totals["over2"] += jt["over2"] and two != kw
            totals["fixed"] += jt["score"] > jk["score"]
            totals["broken"] += jt["score"] < jk["score"]
        n = max(1, totals["n"])
        gain = 100 * (totals["two"] - totals["kw"]) / n
        print(f"  điểm ròng trên {totals['n']} câu ({args.split}): từ khóa {100 * totals['kw'] / n:+.1f}%, hai lớp "
              f"{100 * totals['two'] / n:+.1f}% (hơn {gain:+.1f} điểm); câu sửa được {totals['fixed']}, làm hỏng "
              f"{totals['broken']}")
        for name, s in sorted(by_set.items()):
            m = max(1, s["n"])
            print(f"    {name:<10} n={s['n']:<3} từ khóa {100 * s['kw'] / m:+.0f}%  hai lớp {100 * s['two'] / m:+.0f}%")
        print(f"  rủi ro cao bị gợi ý dưới nhãn: do lớp model {totals['under_model']}, tổng {totals['under_abs']}; "
              f"lớp model gợi ý cao hơn nhãn từ 2 bậc: {totals['over2']}")
        changed = 0
        for row in eval117():
            if row["expect"] == "none":
                continue
            kw, two, _ = layers(row, None, wait_ms)
            changed += kw != two or bool(route.uncertain(row["text"]))
        p90 = pct(ms_all, .9) if ms_all else None
        fast = args.mode == "nen" or (p90 is not None and p90 <= wait_ms)
        ok = gain >= 10 and totals["under_model"] == 0 and changed == 0 and fast
        print(f"  108 câu có khớp của bộ 117 đổi kết quả: {changed}; độ trễ đạt: {fast} "
              f"({'chạy nền: tin nhắn không chờ' if args.mode == 'nen' else f'p90 {p90} ms ≤ {wait_ms:.0f}'})")
        print(f"  ĐẠT: {'có' if ok else 'không'}")
        verdict[model] = ok
    winner = next((m for m in MODELS if verdict.get(m)), None)
    print(f"\nModel rẻ nhất đạt: {winner or 'không có (bỏ lớp model)'}")
    if args.hard_page:
        hard_page(rows, labels, winner or args.page_model, args.mode)
    return 0


def hard_page(rows, labels, model, mode) -> None:
    """Trang câu khó cho người dùng duyệt nhãn (ngoài git): câu nhãn lệch gợi ý hai lớp, câu subagent đánh dấu khó,
    và 20 câu ngẫu nhiên."""
    res = {x["id"]: x for x in load(result_path(model))} if model else {}
    picked, rest = [], []
    for rid, row in rows.items():
        label = labels.get(rid)
        if not label or row["split"] != "test":
            continue
        kw, two, _ = layers(row, res.get(rid), wait_for(row, mode))
        item = (row, label, kw, two, (res.get(rid) or {}).get("rule"))
        # Chỉ câu mà nhãn quyết kết quả so sánh: hai lớp khác lớp từ khóa, và nhãn lệch hay bị đánh dấu khó.
        if kw != two and (judge(two, label)["score"] < 1 or judge(kw, label)["score"] < 1 or label.get("kho")):
            picked.append(item)
        else:
            rest.append(item)
    random.Random(15112026).shuffle(rest)
    items = picked + rest[:20]
    trs = []
    for i, (row, label, kw, two, mr) in enumerate(items, 1):
        lmin = " · ".join(label["min"]) if label.get("min") else "không cần gợi ý"
        trs.append(
            f"<tr><td>{i}</td><td>{html.escape(row['set'])}</td><td class=t>{html.escape(row['text'][:600])}</td>"
            f"<td><b>{html.escape(', '.join(label.get('rules') or []))}</b><br>{html.escape(lmin)}"
            f"{' · rủi ro cao' if label.get('risk_high') else ''}<br><i>{html.escape(label.get('why') or '')}</i></td>"
            f"<td>{html.escape(str(kw or '–'))}</td><td>{html.escape(str(mr or '–'))}</td>"
            f"<td>{html.escape(str(two or '–'))}</td></tr>")
    page = DIR.parent.parent / ".tmp" / "router-eval" / "cau-kho.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Câu khó: nhãn router</title><style>
:root{{--bg:#fff;--fg:#1d1d1f;--mut:#666;--line:#ddd}}@media (prefers-color-scheme:dark){{:root{{--bg:#1b1b1d;--fg:#eee;--mut:#aaa;--line:#444}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:16px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid var(--line);padding:6px;vertical-align:top;text-align:left}}
td.t{{max-width:420px}}th{{position:sticky;top:0;background:var(--bg)}}p{{color:var(--mut)}}
@media (max-width:700px){{td,th{{font-size:13px}}}}</style>
<h1>Câu khó: duyệt nhãn router</h1>
<p>{len(picked)} câu mà hai lớp ({html.escape(str(model))}) gợi ý khác lớp từ khóa, và nhãn lệch một trong hai hay được đánh dấu khó; rồi 20 câu ngẫu nhiên.
Cột "Nhãn" là mức Opus cho là đủ. Nhãn nào sai thì trả lời trong chat: số dòng và nhãn đúng (ví dụ "7: opus·high").</p>
<table><tr><th>#</th><th>Tập</th><th>Câu</th><th>Nhãn (luật · mức tối thiểu)</th><th>Từ khóa</th><th>Model</th><th>Hai lớp</th></tr>
{''.join(trs)}</table>""", encoding="utf-8")
    page.chmod(0o600)
    print(f"Trang câu khó: {page} ({len(items)} dòng)")


def plan(args) -> int:
    rules = route.rules()
    rows = load(DIR / "set.jsonl")
    print(f"binary: {RM.find_binary()}")
    for model in MODELS:
        cfg = cfg_for(model)
        print(f"{model}: prompt {len(RM.system_prompt(rules, cfg))} ký tự, {len(RM.choices(rules, cfg))} luật cho phép")
    asked = to_ask(rows)
    sets = {}
    for r in asked:
        sets.setdefault((r["set"], r["split"]), 0)
        sets[(r["set"], r["split"])] += 1
    print(f"Câu không chắc sẽ hỏi: {len(asked)}/{len(rows)}; {dict(sorted(sets.items()))}; bộ 117: "
          f"{len(to_ask(eval117()))} câu; đã gọi {calls_used()} lần (trần {BUDGET})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("latency")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--gap", type=int, default=0)
    p.add_argument("--cold", type=int, default=0)
    p.add_argument("--models", default="haiku,sonnet")
    p.add_argument("--budget", type=int, default=BUDGET)
    p = sub.add_parser("run")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--model", choices=sorted(MODELS), required=True)
    p.add_argument("--split", choices=("dev", "test", "all"), default="dev")
    p.add_argument("--with117", action="store_true", help="hỏi thêm các câu không chắc của bộ 117")
    p.add_argument("--sets", default="", help="chỉ hỏi các tập này (vd buoc)")
    p.add_argument("--redo", action="store_true", help="hỏi lại cả câu đã có kết quả (sau khi sửa prompt lô)")
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--budget", type=int, default=BUDGET)
    p = sub.add_parser("report")
    p.add_argument("--split", choices=("dev", "test", "all"), default="test")
    p.add_argument("--hard-page", action="store_true")
    p.add_argument("--page-model", default="haiku")
    p.add_argument("--mode", choices=("nen", "cho", "khong-han"), default="nen",
                   help="nen: tin nhắn chạy nền (bạn chọn 15/11/2026 vì p90 Haiku 3,3 giây > 3,2); cho: mỗi tin chờ")
    p.add_argument("--decide", default="s0,buoc",
                   help="tập tính điều kiện đạt: nơi lớp model thật sự đổi gợi ý (mặc định §0 và bước kế hoạch)")
    args = ap.parse_args(argv)
    return {"latency": latency, "run": run, "report": report}.get(args.cmd, plan)(args)


if __name__ == "__main__":
    sys.exit(main())
