#!/usr/bin/env python3
"""Đo quá trình của các lượt eval đã lưu luồng sự kiện (run_eval.py --save-streams), không gọi model.

Đầu ra đúng hay sai đã có grader chấm. Script này đo cách skill đi tới đầu ra: bao nhiêu lệnh bị chặn
quyền, bao nhiêu lệnh shell ghép, bao nhiêu lần kiểm chứng ứng viên, bao nhiêu khẳng định còn "chưa kiểm".

  python3 evals/trace_stats.py evals/results/20261007-161031.jsonl [evals/results/X.jsonl ...]
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

# Lệnh ghép: nối lệnh, ống, biến shell, vòng lặp. Môi trường hạn chế quyền hay chặn loại này.
COMPOUND = re.compile(r";|&&|\|\||\||\$\(|`|^\s*[A-Za-z_][A-Za-z0-9_]*=|^\s*(for|while|if|cd)\b")
# Khẳng định mà chính skill thừa nhận là chưa kiểm được.
UNVERIFIED = re.compile(r"chưa (kiểm|xác minh|đọc|đo|lấy được|tra)|theo hiểu biết|từ hiểu biết|"
                        r"kiến thức (sẵn có|của mình|của tôi)|bị chặn|not verified|unverified|from memory|"
                        r"couldn'?t verify|could not verify", re.IGNORECASE)
EMPTY_SEARCH = "Không có kết quả"


def tool_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, list):
        return "\n".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
    return str(content or "")


def stream_stats(text: str) -> dict:
    """Số liệu quá trình của một lượt, đọc từ luồng stream-json."""
    stats = {"bash": 0, "compound": 0, "denied": 0, "scout_github": 0, "scout_repo": 0, "scout_papers": 0,
             "empty_search": 0, "gh_or_web": 0, "unverified": 0}
    uses = {}
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            stats["denied"] = len(event.get("permission_denials") or [])
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name, inp = block.get("name"), block.get("input") or {}
                uses[block.get("id")] = (name, inp)
                if name == "WebFetch" or name == "WebSearch":
                    stats["gh_or_web"] += 1
                if name != "Bash":
                    continue
                command = str(inp.get("command") or "")
                stats["bash"] += 1
                stats["compound"] += bool(COMPOUND.search(command))
                if re.search(r"(^|\s)gh\s", command):
                    stats["gh_or_web"] += 1
                if "scout.py" in command:  # đếm cả lần gọi gián tiếp qua biến shell, kể cả khi bị chặn
                    sub = re.search(r"\b(github|repo|papers)\b", command[command.index("scout.py"):])
                    if sub:
                        stats["scout_" + sub.group(1)] += 1
            elif block.get("type") == "tool_result":
                name, inp = uses.get(block.get("tool_use_id"), (None, {}))
                body = tool_text(block)
                if name == "Bash" and "scout.py" in str(inp.get("command") or "") and EMPTY_SEARCH in body:
                    stats["empty_search"] += 1
                if name == "Skill":
                    stats["unverified"] += len(UNVERIFIED.findall(body))
    return stats


def load(paths: list) -> list:
    runs = []
    for path in map(Path, paths):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            stream = path.parent / str(row.get("patch", "")).replace(".patch", ".stream.jsonl")
            if not row.get("patch") or not stream.is_file():
                continue
            runs.append(dict(stream_stats(stream.read_text(encoding="utf-8")), config=row["config"],
                             task=row.get("task"), rep=row.get("rep"), passed=bool(row.get("passed")),
                             cost=row.get("cost_usd") or 0.0, seconds=row.get("seconds") or 0.0))
    return runs


COLUMNS = (("passed", "đạt"), ("cost", "USD"), ("seconds", "giây"), ("bash", "lệnh Bash"), ("compound", "lệnh ghép"),
           ("denied", "bị chặn"), ("scout_github", "tìm GitHub"), ("empty_search", "tìm ra rỗng"),
           ("scout_repo", "kiểm repo"), ("gh_or_web", "gọi gh/web thẳng"), ("unverified", "chỗ 'chưa kiểm'"))


def render(runs: list) -> str:
    """Trung bình mỗi lượt theo cấu hình; cột "đạt" là tỉ lệ."""
    if not runs:
        return "Không có lượt nào có luồng sự kiện (chạy run_eval.py với --save-streams)."
    lines = ["| Cấu hình | Lượt | " + " | ".join(label for _, label in COLUMNS) + " |",
             "|---|---:|" + "---:|" * len(COLUMNS)]
    for config in sorted({r["config"] for r in runs}):
        items = [r for r in runs if r["config"] == config]
        cells = []
        for key, _ in COLUMNS:
            mean = statistics.mean(float(r[key]) for r in items)
            cells.append(f"{mean:.0%}" if key == "passed" else f"{mean:.3f}" if key == "cost" else f"{mean:.1f}")
        lines.append(f"| {config} | {len(items)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv=None) -> int:
    paths = (argv if argv is not None else sys.argv[1:])
    if not paths:
        print(__doc__.strip())
        return 2
    print(render(load(paths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
