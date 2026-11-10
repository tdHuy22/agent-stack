#!/usr/bin/env python3
"""Nhật ký review của done-gate, để trả lời "reviewer khác model người viết có bắt nhiều lỗi hơn không" (câu 4).

  python3 review_log.py add --writer opus --level cao --reviewers fable:high,sonnet:high [--task "…"] \\
      [--found "fable:vua:sua:mô tả lỗi"] [--found "both:cao:sua:…"] [--found "sonnet:thap:bac-bo:…"]
  python3 review_log.py summary [--days N] [--json]

Mỗi lần review, một hay nhiều reviewer, kể cả không tìm được lỗi nào, là một dòng JSON trong state/review-log.jsonl.
`--reviewers` là model, có thể kèm effort (opus:xhigh,sonnet:xhigh; dạng cũ opus,sonnet không effort vẫn nhận, nhưng
đã kèm effort thì phải kèm cho mọi reviewer). `--found` có dạng ai:mức:kết-quả:mô tả, với ai là một model trong
--reviewers hay both (cả hai cùng tìm), mức là cao, vua, thap, kết quả là sua (lỗi thật), bac-bo (dương tính giả,
bác bỏ được) hay hoi (đưa người dùng quyết). Chỉ ghi máy này, không gửi đi đâu.
Summary so reviewer khác nhau trên các lần review kép, và (khi có effort) tách theo model·effort và theo ô của bảng
done-gate (mức, họ model người viết, reviewer) để đánh giá từng ô.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

LOG_NAME = "review-log.jsonl"
MODELS = ("opus", "sonnet", "haiku", "fable")
WHO = {"opus": "opus", "sonnet": "sonnet", "fable": "fable", "haiku": "haiku", "both": "both", "ca-hai": "both",
       "cả-hai": "both"}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
SEVERITIES = ("cao", "vua", "thap")
VERDICTS = ("sua", "bac-bo", "hoi")
MAX_TEXT = 300
MAX_LINE_BYTES = 20_000


def log_path() -> Path:
    """state/review-log.jsonl của agent-stack (theo agentstack.state_dir, đổi được bằng AGENT_STACK_STATE)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    import agentstack
    return agentstack.state_dir() / LOG_NAME


def family(model: str) -> str:
    text = (model or "").lower()
    return next((m for m in MODELS if m in text), text)


def parse_found(value: str) -> dict:
    """"ai:mức:kết-quả:mô tả" thành dict; sai dạng thì ValueError kèm lý do."""
    parts = value.split(":", 3)
    if len(parts) < 3:
        raise ValueError(f"--found cần dạng ai:mức:kết-quả[:mô tả], nhận được {value!r}")
    who, severity, verdict = (p.strip().lower() for p in parts[:3])
    if who not in WHO:
        raise ValueError(f"ai phải là {', '.join(MODELS)} hay both, nhận được {who!r}")
    if severity not in SEVERITIES:
        raise ValueError(f"mức phải là {', '.join(SEVERITIES)}, nhận được {severity!r}")
    if verdict not in VERDICTS:
        raise ValueError(f"kết quả phải là {', '.join(VERDICTS)}, nhận được {verdict!r}")
    text = " ".join(parts[3].split())[:MAX_TEXT] if len(parts) > 3 else ""
    return {"by": WHO[who], "severity": severity, "verdict": verdict, "text": text}


def parse_reviewers(value: str):
    """"opus:xhigh,sonnet:xhigh" hay "opus,sonnet" thành (họ model, cấu hình "model:effort" hoặc []). Effort phải kèm
    cho mọi reviewer hay không kèm ai; sai dạng thì ValueError kèm lý do."""
    models, configs, bare = [], [], 0
    for item in (value or "").split(","):
        if not item.strip():
            continue
        name, _, effort = item.partition(":")
        model, effort = family(name.strip()), effort.strip().lower()
        if effort and effort not in EFFORTS:
            raise ValueError(f"effort phải là {', '.join(EFFORTS)}, nhận được {effort!r}")
        models.append(model)
        if effort:
            configs.append(f"{model}:{effort}")
        else:
            bare += 1
    if configs and bare:
        raise ValueError("--reviewers: kèm effort cho mọi reviewer hay không kèm ai (vd opus:xhigh,sonnet:xhigh)")
    return models, configs


def project_name(cwd: Path) -> str:
    """Tên thư mục gốc của project (git), để biết lần review thuộc project nào; không lưu đường dẫn đầy đủ."""
    here = cwd.resolve()
    for folder in (here, *here.parents):
        if (folder / ".git").exists():
            return folder.name
    return here.name


def add(args) -> int:
    try:
        findings = [parse_found(v) for v in args.found or []]
    except ValueError as exc:
        print(f"Không ghi: {exc}", file=sys.stderr)
        return 2
    try:
        reviewers, configs = parse_reviewers(args.reviewers)
    except ValueError as exc:
        print(f"Không ghi: {exc}", file=sys.stderr)
        return 2
    if not reviewers:
        print("Không ghi: --reviewers cần ít nhất một model (vd sonnet:high hay opus:xhigh,sonnet:xhigh).",
              file=sys.stderr)
        return 2
    unknown = sorted({f["by"] for f in findings} - set(reviewers) - {"both"})
    if unknown or (any(f["by"] == "both" for f in findings) and len(set(reviewers)) < 2):
        print("Không ghi: lỗi được gán cho reviewer không có trong --reviewers "
              f"({', '.join(unknown) or 'both cần hai reviewer'}).", file=sys.stderr)
        return 2
    record = {"ts": int(time.time()), "project": project_name(Path(args.cwd or ".")), "task": (args.task or "")[:MAX_TEXT],
              "writer": family(args.writer), "level": args.level, "reviewers": reviewers, "findings": findings}
    if configs:
        record["configs"] = configs
    path = log_path()
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    # Một lần write với O_APPEND: hai phiên ghi cùng lúc không trộn dòng của nhau.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
    print(f"Đã ghi lần review ({len(findings)} lỗi) vào {path}.")
    return 0


def read_records(path: Path, since: float = 0) -> list:
    out = []
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for raw in f:
                if len(raw) > MAX_LINE_BYTES:
                    continue
                try:
                    rec = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(rec, dict) and isinstance(rec.get("ts"), (int, float)) and rec["ts"] >= since:
                    out.append(rec)
    except OSError:
        pass
    return out


def pretty(config: str) -> str:
    return config.replace(":", "·")


def summarize(records: list) -> dict:
    """Đếm lỗi thật (sua, hoi) và dương tính giả (bac-bo) theo ai tìm, trên các lần review kép (từ hai reviewer khác
    model); `by_config` và `by_cell` đếm trên mọi lần review có ghi effort. "khác model" là reviewer khác họ model
    người viết (Fable review code Opus viết là khác model; bản ghi cũ coi Fable như Opus nay tách riêng)."""
    dual = [r for r in records if len(set(r.get("reviewers") or [])) >= 2]
    s = {"runs": len(records), "dual_runs": len(dual), "real": {"opus": 0, "sonnet": 0, "both": 0},
         "false": {"opus": 0, "sonnet": 0, "both": 0}, "real_by_level": {k: {"opus": 0, "sonnet": 0, "both": 0}
                                                                          for k in SEVERITIES},
         "other_only": 0, "same_only": 0, "unknown_writer": 0, "by_config": {}, "by_cell": {}}

    def bump(table: dict, key: str) -> None:
        table[key] = table.get(key, 0) + 1

    def valid(f) -> bool:
        return isinstance(f, dict) and f.get("by") in WHO.values()

    for r in dual:
        writer = family(r.get("writer"))
        for f in r.get("findings") or []:
            if not valid(f):
                continue
            bucket = "false" if f.get("verdict") == "bac-bo" else "real"
            bump(s[bucket], f["by"])
            if bucket == "real":
                if f.get("severity") in SEVERITIES:
                    bump(s["real_by_level"][f["severity"]], f["by"])
                if f["by"] != "both":
                    if writer not in MODELS:
                        s["unknown_writer"] += 1
                    elif f["by"] == writer:
                        s["same_only"] += 1
                    else:
                        s["other_only"] += 1
    for r in records:
        configs = [c for c in r.get("configs") or [] if isinstance(c, str) and ":" in c]
        if not configs:
            continue
        cell = s["by_cell"].setdefault(f"{r.get('level')}/{family(r.get('writer'))} → {'+'.join(configs)}",
                                       {"runs": 0, "real": 0, "false": 0})
        cell["runs"] += 1
        multi = len(set(r.get("reviewers") or [])) >= 2
        for c in configs:
            s["by_config"].setdefault(c, {"runs": 0, "real": 0, "real_only": 0, "false": 0, "high": 0})["runs"] += 1
        for f in r.get("findings") or []:
            if not valid(f):
                continue
            is_real = f.get("verdict") != "bac-bo"
            cell["real" if is_real else "false"] += 1
            for c in configs:
                if f["by"] in ("both", c.split(":")[0]):
                    entry = s["by_config"][c]
                    entry["real" if is_real else "false"] += 1
                    if is_real and f.get("severity") == "cao":
                        entry["high"] += 1
                    if is_real and multi and f["by"] != "both":
                        entry["real_only"] += 1
    return s


def render(s: dict, days) -> str:
    span = f"{days} ngày gần nhất" if days else "toàn bộ nhật ký"
    lines = []
    if not s["dual_runs"]:
        lines.append(f"Chưa có lần review kép (hai reviewer khác model) nào trong {span} ({s['runs']} lần review đã "
                     "ghi). Cần vài lần review kép mới so được.")
    else:
        real, false = s["real"], s["false"]
        total = sum(real.values())
        names = [m for m in MODELS if m in ("opus", "sonnet") or real.get(m) or false.get(m)]

        def only(row: dict, verb: str = "") -> str:
            return ", ".join(f"chỉ {m.title()} {verb}{row.get(m, 0)}" for m in names) + f", cả hai {row['both']}"

        lines += [f"Review kép: {s['dual_runs']} lần trong {span} (tổng {s['runs']} lần review đã ghi).",
                  f"Lỗi thật: {total} ({only(real, 'tìm ')}).",
                  f"Dương tính giả bị bác bỏ: {', '.join(f'{m.title()} {false.get(m, 0)}' for m in names)}, "
                  f"cả hai {false['both']}."]
        for level in SEVERITIES:
            row = s["real_by_level"][level]
            if sum(row.values()):
                lines.append(f"- mức {level}: {only(row)}")
        if total:
            lines.append(f"Reviewer khác model người viết tìm riêng {s['other_only']} lỗi thật, reviewer cùng model "
                         f"tìm riêng {s['same_only']}" + (f", không rõ người viết {s['unknown_writer']}"
                                                          if s["unknown_writer"] else "")
                         + f" (trên {total} lỗi thật).")
        if s["dual_runs"] < 5:
            lines.append("Còn ít lần review kép (dưới 5): chưa đủ để kết luận.")
    if s["by_config"]:
        lines.append("Theo model·effort (mọi lần review có ghi effort):")
        for config, e in sorted(s["by_config"].items()):
            lines.append(f"- {pretty(config)}: {e['runs']} lần, lỗi thật {e['real']} (một mình tìm {e['real_only']}, "
                         f"mức cao {e['high']}), dương tính giả {e['false']}")
        lines.append("Theo ô của bảng (mức/người viết → reviewer):")
        for cell, e in sorted(s["by_cell"].items()):
            lines.append(f"- {pretty(cell)}: {e['runs']} lần, lỗi thật {e['real']}, dương tính giả {e['false']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Nhật ký review của done-gate: ghi lỗi nào do reviewer nào tìm, rồi tổng hợp.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="ghi một lần review (kể cả khi không tìm được lỗi nào)")
    a.add_argument("--writer", required=True, help="model viết code: opus, sonnet, fable, haiku (hay id model)")
    a.add_argument("--level", required=True, choices=SEVERITIES, help="mức rủi ro risk.py chấm")
    a.add_argument("--reviewers", required=True, help="các reviewer đã chạy, cách nhau dấu phẩy, kèm effort: opus:xhigh,sonnet:xhigh "
                                                    "(dạng cũ opus,sonnet không effort vẫn nhận)")
    a.add_argument("--task", help="tên ngắn của việc")
    a.add_argument("--found", action="append", help="một lỗi: ai:mức:kết-quả:mô tả (lặp lại cho mỗi lỗi)")
    a.add_argument("--cwd", help="thư mục project (mặc định thư mục hiện tại)")
    m = sub.add_parser("summary", help="tổng hợp: reviewer nào bắt lỗi nào")
    m.add_argument("--days", type=int, help="chỉ xét bấy nhiêu ngày gần nhất")
    m.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "add":
        return add(args)
    since = time.time() - args.days * 86400 if args.days else 0
    s = summarize(read_records(log_path(), since))
    print(json.dumps(s, ensure_ascii=False, indent=1) if args.json else render(s, args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
