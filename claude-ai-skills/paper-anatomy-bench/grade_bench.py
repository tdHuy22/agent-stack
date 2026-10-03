#!/usr/bin/env python3
"""Chấm phần đo được bằng máy cho bench paper-anatomy, không gọi model.

  python3 claude-ai-skills/paper-anatomy-bench/grade_bench.py --iteration 1

Với mỗi lượt (việc × nhánh × lần), ghi metrics.json cạnh bài làm:
- neo: số thẻ 【…】, số khớp / cảnh báo / sai khi kiểm bằng verify_anchors.py trên văn bản trích của bài
  (cùng một bản trích cho cả hai nhánh, dựng bằng extract_paper.py mới trong .tmp/paper-anatomy-bench/papers/);
- độ phủ: tỉ lệ trang thân bài mà một đoạn đặc trưng của trang xuất hiện trong kết quả công cụ (tức là model
  đã thật sự thấy trang đó); số ảnh trang đã mở;
- hành vi: có chạy kiểm neo không; số từ của câu trả lời; chi phí, số lượt, thời gian.
In bảng tổng hợp theo nhánh. Phần chấm nội dung (đúng sai, độ sâu) do người chấm làm riêng.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BENCH = REPO / ".tmp" / "paper-anatomy-bench"
sys.path.insert(0, str(REPO / "claude-ai-skills" / "paper-anatomy" / "scripts"))
import verify_anchors  # noqa: E402


READ_PREFIX = re.compile(r"^\s*\d+[\t→]", re.MULTILINE)  # số dòng mà công cụ Read chèn vào đầu mỗi dòng


def squash(s):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", s).casefold())


def body_pages(cache, body_end=None):
    """Trang thân bài: từ đầu tới trước trang bắt đầu tài liệu tham khảo (hoặc body_end của việc, nếu có)."""
    end = body_end or next((s["page"] for s in cache.get("sections", [])
                            if re.search(r"references|bibliography", s["title"], re.I)), cache["page_count"] + 1)
    return [p for p in cache["pages"] if p["index"] < end and p["chars"] >= 200]


def snippets(page, n=3, size=40):
    """Vài đoạn đặc trưng (đã chuẩn hóa) rải đều trên trang."""
    flat = squash(page["text"])
    if len(flat) < size * 2:
        return []
    step = max(1, (len(flat) - size) // (n + 1))
    return [flat[step * (k + 1): step * (k + 1) + size] for k in range(n)]


def tool_results(transcript):
    """Nội dung mọi kết quả công cụ trong transcript stream-json, đã chuẩn hóa."""
    chunks, images = [], 0
    for line in transcript.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") != "user":
            continue
        for block in (ev.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            content = block.get("content")
            if isinstance(content, str):
                chunks.append(READ_PREFIX.sub("", content))
            elif isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        chunks.append(READ_PREFIX.sub("", part.get("text", "")))
                    elif part.get("type") in ("image", "document"):
                        images += 1
    return squash("\n".join(chunks)), images


def grade_run(run_dir, cache, body_end=None):
    answer = (run_dir / "outputs" / "answer.md").read_text(encoding="utf-8")
    timing = json.loads((run_dir / "timing.json").read_text(encoding="utf-8"))
    tools = json.loads((run_dir / "tools.json").read_text(encoding="utf-8"))
    transcript = (run_dir / "transcript.jsonl").read_text(encoding="utf-8")
    check = verify_anchors.run(answer, cache)
    seen, images = tool_results(transcript)
    pages = body_pages(cache, body_end)
    covered = [p["index"] for p in pages if any(s in seen for s in snippets(p))]
    commands = " ".join(str((t.get("input") or {}).get("command", "")) for t in tools)
    metrics = {
        "words": len(answer.split()),
        "anchors": check["anchors"], "anchor_ok": check["OK"], "anchor_warn": check["WARN"],
        "anchor_fail": check["FAIL"], "with_quote": check["with_quote"],
        "anchor_fail_rate": round(check["FAIL"] / check["anchors"], 3) if check["anchors"] else None,
        "unanchored_paragraphs": len(check["unanchored_paragraphs"]),
        "long_quotes": len(check["long_quotes"]),
        "body_pages": len(pages), "body_pages_seen": len(covered),
        "coverage": round(len(covered) / len(pages), 3) if pages else None,
        "images_seen": images, "ran_verify": "verify_anchors" in commands,
        "cost_usd": timing.get("cost_usd"), "turns": timing.get("turns"),
        "seconds": timing.get("total_duration_seconds"), "error": timing.get("is_error"),
        "fails": [r for r in check["rows"] if r["status"] == "FAIL"][:12],
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    return metrics


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--iteration", type=int, required=True)
    args = ap.parse_args(argv)
    root = BENCH / f"iteration-{args.iteration}"
    evals = {e["name"]: e for e in json.loads((HERE / "evals.json").read_text(encoding="utf-8"))["evals"]}
    rows = []
    for run_dir in sorted(root.glob("*/*/run-*")):
        if not (run_dir / "timing.json").exists():
            continue
        eval_name, arm = run_dir.parts[-3], run_dir.parts[-2]
        cache_file = BENCH / "papers" / eval_name / "pages.json"
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        m = grade_run(run_dir, cache, evals.get(eval_name, {}).get("body_end"))
        rows.append((eval_name, arm, m))
    print("| Việc | Nhánh | Từ | Neo | Sai | Cảnh báo | Có trích | Phủ trang | Ảnh | Kiểm neo | USD | Giây |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|")
    for name, arm, m in rows:
        cov = f"{m['body_pages_seen']}/{m['body_pages']}" if m["body_pages"] else "–"
        print(f"| {name} | {arm} | {m['words']} | {m['anchors']} | {m['anchor_fail']} | {m['anchor_warn']} | "
              f"{m['with_quote']} | {cov} | {m['images_seen']} | {'có' if m['ran_verify'] else 'không'} | "
              f"{m['cost_usd']:.2f} | {m['seconds']:.0f} |")
    print()
    for arm in sorted({a for _, a, _ in rows}):
        ms = [m for _, a, m in rows if a == arm]
        anchors = sum(m["anchors"] for m in ms)
        fails = sum(m["anchor_fail"] for m in ms)
        covs = [m["coverage"] for m in ms if m["coverage"] is not None]
        print(f"{arm}: {len(ms)} lượt · neo sai {fails}/{anchors} ({fails / anchors:.1%}) · "
              f"phủ trang TB {statistics.mean(covs):.0%} · USD TB {statistics.mean(m['cost_usd'] or 0 for m in ms):.2f}"
              if anchors and covs else f"{arm}: {len(ms)} lượt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
