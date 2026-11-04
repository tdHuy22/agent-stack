#!/usr/bin/env python3
"""Nhật ký review của done-gate, để trả lời "reviewer khác model người viết có bắt nhiều lỗi hơn không" (câu 4).

  python3 review_log.py add --writer opus --level cao --reviewers opus,sonnet [--task "…"] \\
      [--found "opus:vua:sua:mô tả lỗi"] [--found "both:cao:sua:…"] [--found "sonnet:thap:bac-bo:…"]
  python3 review_log.py summary [--days N] [--json]

Mỗi lần review (kể cả không tìm được lỗi nào) là một dòng JSON trong state/review-log.jsonl. `--found` có dạng
ai:mức:kết-quả:mô tả, với ai là opus, sonnet hay both (cả hai cùng tìm), mức là cao, vua, thap, kết quả là sua (lỗi
thật), bac-bo (dương tính giả, bác bỏ được) hay hoi (đưa người dùng quyết). Chỉ ghi máy này, không gửi đi đâu.
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
WHO = {"opus": "opus", "sonnet": "sonnet", "both": "both", "ca-hai": "both", "cả-hai": "both"}
# Như risk.py: Fable viết xếp như Opus, Haiku viết xếp như Sonnet, để đếm "reviewer khác model người viết".
WRITER_SIDE = {"opus": "opus", "fable": "opus", "sonnet": "sonnet", "haiku": "sonnet"}
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
        raise ValueError(f"ai phải là opus, sonnet hay both, nhận được {who!r}")
    if severity not in SEVERITIES:
        raise ValueError(f"mức phải là {', '.join(SEVERITIES)}, nhận được {severity!r}")
    if verdict not in VERDICTS:
        raise ValueError(f"kết quả phải là {', '.join(VERDICTS)}, nhận được {verdict!r}")
    text = " ".join(parts[3].split())[:MAX_TEXT] if len(parts) > 3 else ""
    return {"by": WHO[who], "severity": severity, "verdict": verdict, "text": text}


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
    reviewers = [family(r) for r in (args.reviewers or "").split(",") if r.strip()]
    if not reviewers:
        print("Không ghi: --reviewers cần ít nhất một model (vd opus,sonnet).", file=sys.stderr)
        return 2
    unknown = sorted({f["by"] for f in findings} - set(reviewers) - {"both"})
    if unknown or (any(f["by"] == "both" for f in findings) and len(set(reviewers)) < 2):
        print("Không ghi: lỗi được gán cho reviewer không có trong --reviewers "
              f"({', '.join(unknown) or 'both cần hai reviewer'}).", file=sys.stderr)
        return 2
    record = {"ts": int(time.time()), "project": project_name(Path(args.cwd or ".")), "task": (args.task or "")[:MAX_TEXT],
              "writer": family(args.writer), "level": args.level, "reviewers": reviewers, "findings": findings}
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


def summarize(records: list) -> dict:
    """Đếm lỗi thật (sua, hoi) và dương tính giả (bac-bo) theo ai tìm, chỉ trên các lần review kép opus và sonnet.
    "khác model" là reviewer khác họ model người viết; người viết là Opus thì Sonnet là reviewer khác model."""
    dual = [r for r in records if {"opus", "sonnet"} <= set(r.get("reviewers") or [])]
    s = {"runs": len(records), "dual_runs": len(dual), "real": {"opus": 0, "sonnet": 0, "both": 0},
         "false": {"opus": 0, "sonnet": 0, "both": 0}, "real_by_level": {k: {"opus": 0, "sonnet": 0, "both": 0}
                                                                          for k in SEVERITIES},
         "other_only": 0, "same_only": 0, "unknown_writer": 0}
    for r in dual:
        writer = WRITER_SIDE.get(r.get("writer"))
        for f in r.get("findings") or []:
            if not isinstance(f, dict) or f.get("by") not in ("opus", "sonnet", "both"):
                continue
            bucket = "false" if f.get("verdict") == "bac-bo" else "real"
            s[bucket][f["by"]] += 1
            if bucket == "real":
                if f.get("severity") in SEVERITIES:
                    s["real_by_level"][f["severity"]][f["by"]] += 1
                if f["by"] != "both":
                    if writer is None:
                        s["unknown_writer"] += 1
                    elif f["by"] == writer:
                        s["same_only"] += 1
                    else:
                        s["other_only"] += 1
    return s


def render(s: dict, days) -> str:
    span = f"{days} ngày gần nhất" if days else "toàn bộ nhật ký"
    if not s["dual_runs"]:
        return (f"Chưa có lần review kép (opus và sonnet) nào trong {span} ({s['runs']} lần review đã ghi). "
                "Cần vài lần review kép mới so được.")
    real, false = s["real"], s["false"]
    total = sum(real.values())
    lines = [f"Review kép: {s['dual_runs']} lần trong {span} (tổng {s['runs']} lần review đã ghi).",
             f"Lỗi thật: {total} (chỉ Opus tìm {real['opus']}, chỉ Sonnet tìm {real['sonnet']}, cả hai {real['both']}).",
             f"Dương tính giả bị bác bỏ: Opus {false['opus']}, Sonnet {false['sonnet']}, cả hai {false['both']}."]
    for level in SEVERITIES:
        row = s["real_by_level"][level]
        if sum(row.values()):
            lines.append(f"- mức {level}: chỉ Opus {row['opus']}, chỉ Sonnet {row['sonnet']}, cả hai {row['both']}")
    if total:
        lines.append(f"Reviewer khác model người viết tìm riêng {s['other_only']} lỗi thật, reviewer cùng model tìm riêng "
                     f"{s['same_only']}" + (f", không rõ người viết {s['unknown_writer']}" if s["unknown_writer"] else "")
                     + f" (trên {total} lỗi thật).")
    if s["dual_runs"] < 5:
        lines.append("Còn ít lần review kép (dưới 5): chưa đủ để kết luận.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Nhật ký review của done-gate: ghi lỗi nào do reviewer nào tìm, rồi tổng hợp.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="ghi một lần review (kể cả khi không tìm được lỗi nào)")
    a.add_argument("--writer", required=True, help="model viết code: opus, sonnet (hay id model)")
    a.add_argument("--level", required=True, choices=SEVERITIES, help="mức rủi ro risk.py chấm")
    a.add_argument("--reviewers", required=True, help="các model đã review, cách nhau dấu phẩy, vd opus,sonnet")
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
