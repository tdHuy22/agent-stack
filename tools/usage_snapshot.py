#!/usr/bin/env python3
"""Ảnh chụp mức dùng token của Claude Code, đọc từ transcript cục bộ (chỉ đọc).

Chỉ lấy metadata `usage` của các lượt assistant trong ~/.claude/projects/**/*.jsonl,
không đọc nội dung hội thoại. Định dạng transcript là nội bộ của Claude Code và có
thể đổi giữa các phiên bản, nên số liệu ở đây là ước tính để so sánh trước/sau,
không phải hóa đơn. Gói thuê bao tính theo hạn mức, không theo đô la; cột USD chỉ
dùng làm thước đo tương đối (giá niêm yết API).

Ví dụ:
  python3 tools/usage_snapshot.py               # 7 ngày gần nhất, Markdown
  python3 tools/usage_snapshot.py --days 30 --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Giá niêm yết API, USD trên 1 triệu token: (input, output, cache_read).
# Nguồn: bảng model trong skill claude-api (cập nhật 2026-09-25).
# cache_read = None nghĩa là dùng mặc định 0,1 x giá input.
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, None),
    "claude-mythos-5-1": (10.0, 50.0, None),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, None),
    "claude-opus-4-8": (5.0, 25.0, None),
    "claude-opus-4-7": (5.0, 25.0, None),
    "claude-opus-4-6": (5.0, 25.0, None),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, None),
    "claude-sonnet-4-6": (3.0, 15.0, None),
    "claude-haiku-4-5": (1.0, 5.0, None),
}
CACHE_WRITE_5M = 1.25  # hệ số so với giá input
CACHE_WRITE_1H = 2.0


def price_for(model: str):
    """Khớp tiền tố dài nhất, để 'claude-haiku-4-5-20251001' vẫn ra giá Haiku 4.5."""
    best = None
    for key in PRICES:
        if model.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return PRICES.get(best) if best else None


def parse_ts(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def entry_cost(model: str, usage: dict):
    price = price_for(model)
    if price is None:
        return None
    p_in, p_out, p_read = price
    if p_read is None:
        p_read = p_in * 0.1
    cache = usage.get("cache_creation") or {}
    w1h = cache.get("ephemeral_1h_input_tokens")
    w5m = cache.get("ephemeral_5m_input_tokens")
    total_write = usage.get("cache_creation_input_tokens", 0) or 0
    if w1h is None and w5m is None:
        w1h, w5m = 0, total_write
    write_cost = (w1h or 0) * p_in * CACHE_WRITE_1H + (w5m or 0) * p_in * CACHE_WRITE_5M
    return (
        (usage.get("input_tokens", 0) or 0) * p_in
        + (usage.get("output_tokens", 0) or 0) * p_out
        + (usage.get("cache_read_input_tokens", 0) or 0) * p_read
        + write_cost
    ) / 1_000_000


def collect(projects_dir: Path, since: datetime, until: datetime):
    """Trả về danh sách bản ghi usage đã khử trùng lặp trong khoảng thời gian."""
    records = {}
    cutoff = since.timestamp()
    for path in projects_dir.rglob("*.jsonl"):
        try:
            if path.stat().st_mtime < cutoff:
                continue  # file không được ghi trong cửa sổ thời gian thì bỏ qua
            handle = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        is_sub_file = "subagents" in path.parts
        with handle:
            for line in handle:
                if '"usage"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                message = entry.get("message") or {}
                usage = message.get("usage")
                model = message.get("model") or ""
                if not usage or not model or model == "<synthetic>":
                    continue
                ts = parse_ts(entry.get("timestamp", ""))
                if ts is None or not (since <= ts <= until):
                    continue
                key = (message.get("id"), entry.get("requestId")) if message.get("id") else entry.get("uuid")
                records[key] = {
                    "model": model,
                    "usage": usage,
                    "ts": ts,
                    "session": entry.get("sessionId", ""),
                    "project": Path(entry.get("cwd") or path.parent.name).name,
                    "subagent": bool(entry.get("isSidechain")) or is_sub_file,
                }
    return list(records.values())


def summarize(records):
    by_model = defaultdict(lambda: defaultdict(float))
    by_project = defaultdict(float)
    sessions, days = set(), set()
    sub_cost = total_cost = 0.0
    read_tokens = input_side = 0
    unknown_models = set()
    for r in records:
        u, m = r["usage"], r["model"]
        cost = entry_cost(m, u)
        if cost is None:
            unknown_models.add(m)
            cost = 0.0
        row = by_model[m]
        row["calls"] += 1
        row["input"] += u.get("input_tokens", 0) or 0
        row["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
        row["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        row["output"] += u.get("output_tokens", 0) or 0
        row["cost"] += cost
        by_project[r["project"]] += cost
        total_cost += cost
        if r["subagent"]:
            sub_cost += cost
        sessions.add(r["session"])
        days.add(r["ts"].date())
        read_tokens += u.get("cache_read_input_tokens", 0) or 0
        input_side += (u.get("input_tokens", 0) or 0) + (u.get("cache_creation_input_tokens", 0) or 0) + (u.get("cache_read_input_tokens", 0) or 0)
    return {
        "by_model": {k: dict(v) for k, v in by_model.items()},
        "by_project": dict(by_project),
        "sessions": len(sessions),
        "active_days": len(days),
        "total_cost": total_cost,
        "subagent_cost_share": (sub_cost / total_cost) if total_cost else 0.0,
        "cache_read_share": (read_tokens / input_side) if input_side else 0.0,
        "unknown_models": sorted(unknown_models),
        "records": len(records),
    }


def fmt_tokens(n: float) -> str:
    n = float(n)
    for unit, size in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return str(int(n))


def to_markdown(summary, since: datetime, until: datetime) -> str:
    lines = [
        f"### Mức dùng từ {since.date()} đến {until.date()}",
        "",
        "Ước tính theo giá niêm yết API, tính từ transcript cục bộ trên máy này. "
        "Không phải hóa đơn gói thuê bao, và không gồm phần dùng trên claude.ai hay máy khác.",
        "",
        "| Model | Lượt gọi | Input | Cache write | Cache read | Output | USD ước tính | Tỉ trọng |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    total = summary["total_cost"] or 1.0
    for model, row in sorted(summary["by_model"].items(), key=lambda kv: -kv[1]["cost"]):
        lines.append(
            f"| `{model}` | {int(row['calls'])} | {fmt_tokens(row['input'])} | {fmt_tokens(row['cache_write'])} "
            f"| {fmt_tokens(row['cache_read'])} | {fmt_tokens(row['output'])} | {row['cost']:.2f} | {row['cost'] / total:.0%} |"
        )
    lines += [
        "",
        f"- Tổng ước tính: **{summary['total_cost']:.2f} USD** trên {summary['records']} lượt gọi model.",
        f"- Phiên: {summary['sessions']}, ngày có hoạt động: {summary['active_days']}.",
        f"- Phần của subagent và workflow: **{summary['subagent_cost_share']:.0%}** chi phí ước tính.",
        f"- Tỉ lệ token đầu vào đọc từ cache: **{summary['cache_read_share']:.0%}**.",
    ]
    top = sorted(summary["by_project"].items(), key=lambda kv: -kv[1])[:5]
    if top:
        lines.append("- Project tốn nhiều nhất: " + ", ".join(f"{name} ({cost / total:.0%})" for name, cost in top) + ".")
    if summary["unknown_models"]:
        lines.append("- Model chưa có trong bảng giá (tính 0): " + ", ".join(f"`{m}`" for m in summary["unknown_models"]) + ".")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=7, help="số ngày tính lùi (mặc định 7)")
    ap.add_argument("--projects-dir", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--now", help="mốc thời gian ISO, dùng cho test")
    ap.add_argument("--json", action="store_true", help="xuất JSON thay cho Markdown")
    args = ap.parse_args(argv)

    until = parse_ts(args.now) if args.now else datetime.now(timezone.utc)
    if until is None:
        ap.error("--now không đúng định dạng ISO 8601")
    since = until - timedelta(days=args.days)
    summary = summarize(collect(Path(args.projects_dir), since, until))
    if args.json:
        summary["since"], summary["until"] = since.isoformat(), until.isoformat()
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(to_markdown(summary, since, until))
    return 0


if __name__ == "__main__":
    sys.exit(main())
