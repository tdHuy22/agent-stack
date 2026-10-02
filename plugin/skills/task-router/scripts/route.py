#!/usr/bin/env python3
"""Gợi ý skill, subagent, model và effort cho một việc, bằng luật từ khóa (0 token, dưới 50 ms).

Lệnh:
  route.py "mô tả việc"                     in gợi ý dạng JSON
  route.py --eval FILE.jsonl [--min 0.85]   đo độ chính xác trên bộ prompt có nhãn

Dùng làm thư viện:
  suggest(text)                  -> dict hoặc None (skill tien-do dùng)
  hook_suggestion(prompt, data)  -> dict {context, user} hoặc None (hook UserPromptSubmit dùng)

Router chỉ GỢI Ý. Hook không thể đổi model hay effort; người dùng tự đổi bằng /model, /effort,
và chỉ nên đổi ở ranh giới giữa hai việc, vì đổi giữa chừng làm mất prompt cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))
import agentstack as A  # noqa: E402

RULES_PATH = HERE.parents[1] / "rules.json"
FAMILIES = ("fable", "opus", "sonnet", "haiku")


@lru_cache(maxsize=1)
def rules() -> dict:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    for order, rule in enumerate(data["rules"]):
        rule["_order"] = order
        rule["_patterns"] = [(phrase, re.compile(r"(?<![a-z0-9])" + re.escape(A.fold(phrase)) + r"(?![a-z0-9])"))
                             for phrase in rule["match"]]
    return data


def score(text: str):
    """Trả về (luật tốt nhất, các cụm khớp) hoặc (None, [])."""
    folded = A.fold(text)
    best, best_hits, best_score = None, [], 0
    for rule in rules()["rules"]:
        hits = [phrase for phrase, pattern in rule["_patterns"] if pattern.search(folded)]
        # Cụm nhiều chữ đặc hiệu hơn, nên nặng ký hơn.
        total = sum(1 + phrase.count(" ") for phrase in hits)
        if total > best_score:
            best, best_hits, best_score = rule, hits, total
    return best, best_hits


def suggest(text: str):
    rule, hits = score(text or "")
    if not rule:
        return None
    return {"rule": rule["id"], "model": rule.get("model"), "effort": rule.get("effort"),
            "agent": rule.get("agent"), "skills": rule.get("skills", []), "note": rule.get("note", ""), "matched": hits}


def family(model) -> str:
    text = (model or "").lower() if isinstance(model, str) else json.dumps(model or {}).lower()
    return next((f for f in FAMILIES if f in text), "")


def current_model(session_id: str) -> str:
    """Model hiện tại, lấy từ thông tin phiên do hook SessionStart ghi, hoặc từ statusline."""
    if session_id:
        name = hashlib.sha1(session_id.encode()).hexdigest()[:16] + ".json"
        info = A.read_json(A.state_dir() / "sessions" / name, {}) or {}
        if info.get("model"):
            return family(info["model"])
    limits = A.read_json(A.state_dir() / "limits.json", {}) or {}
    if limits.get("session_id") == session_id:
        return family(limits.get("model"))
    return ""


def hook_suggestion(prompt: str, data: dict):
    prompt = (prompt or "").strip()
    if not prompt or prompt[0] in "/!#" or len(prompt.split()) < rules().get("min_words", 4):
        return None
    hit = suggest(prompt)
    if not hit:
        return None
    sid = data.get("session_id", "")
    now_family = current_model(sid)
    now_effort = (data.get("effort") or {}).get("level")
    parts_user, parts_ctx = [], []
    if hit["model"] and now_family and hit["model"] != now_family:
        parts_user.append(f"/model {hit['model']}")
    if hit["effort"] and now_effort and hit["effort"] != now_effort:
        parts_user.append(f"/effort {hit['effort']}")
    if hit["agent"]:
        parts_user.append(f"agent {hit['agent']}")
        parts_ctx.append(f"giao cho subagent {hit['agent']}")
    if hit["skills"]:
        parts_user.append("skill " + ", ".join(hit["skills"]))
        parts_ctx.append("dùng skill " + ", ".join(hit["skills"]) + " nếu có"
                         + (f" ({hit['note']})" if hit.get("note") else ""))
    if not parts_user:
        return None  # model, effort đã khớp và không có skill/agent để gợi ý
    if not A.once(f"route-{sid}-{hit['rule']}", 3600):
        return None  # cùng một gợi ý không nhắc lại trong một giờ
    reason = ", ".join(f"'{m}'" for m in hit["matched"][:3])
    model_note = (f"model {hit['model']} · effort {hit['effort']}" if hit["model"] else "")
    context = (f"[router] Gợi ý cho việc này ({hit['rule']}, khớp {reason}): " + "; ".join(parts_ctx + ([model_note] if model_note else []))
               + ". Đây chỉ là gợi ý. Nếu nên đổi model hoặc effort, nói với người dùng ở cuối câu trả lời, đừng tự đổi.")
    user = f"🧭 router: {hit['rule']} → " + " · ".join(parts_user)
    return {"context": context, "user": user, "rule": hit["rule"]}


def evaluate(path: Path, minimum: float) -> int:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    wrong = []
    for row in rows:
        hit = suggest(row["prompt"])
        got = hit["rule"] if hit else "none"
        if got != row["expect"]:
            wrong.append((row["prompt"], row["expect"], got))
    accuracy = 1 - len(wrong) / len(rows)
    print(f"Độ chính xác: {accuracy:.0%} ({len(rows) - len(wrong)}/{len(rows)})")
    for prompt, expect, got in wrong:
        print(f"  ✗ cần {expect:<16} ra {got:<16} {prompt[:70]}")
    return 0 if accuracy >= minimum else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gợi ý skill/agent/model/effort cho một việc.")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--eval", type=Path)
    ap.add_argument("--min", type=float, default=0.85)
    args = ap.parse_args(argv)
    if args.eval:
        return evaluate(args.eval, args.min)
    print(json.dumps(suggest(args.text or sys.stdin.read()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
