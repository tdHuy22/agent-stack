#!/usr/bin/env python3
"""Gợi ý skill, subagent, model và effort cho một việc, bằng luật từ khóa (0 token, dưới 50 ms).

Lệnh:
  route.py "mô tả việc" [--project DIR]     in gợi ý dạng JSON; --project thêm skill theo loại project
  route.py --session [DIR]                  in hồ sơ project và gợi ý skill, như hook SessionStart của Claude Code
                                            (dùng trong OpenCode và công cụ không có hook)
  route.py --eval FILE.jsonl [--min 0.85]   đo độ chính xác trên bộ prompt có nhãn

Dùng làm thư viện:
  suggest(text)                  -> dict hoặc None (skill tien-do dùng)
  hook_suggestion(prompt, data)  -> dict {context, user} hoặc None (hook UserPromptSubmit dùng)
  session_hint(root)             -> dict {context, user} hoặc None (hook SessionStart dùng)

Gợi ý tính cả hồ sơ project (loại code, có test, code nhạy cảm bảo mật) và việc tiếp theo trong §0:
tin nhắn kiểu "làm tiếp" được định tuyến theo việc tiếp theo trong §0.

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
# Tin nhắn chỉ bảo làm tiếp (đã bỏ dấu): định tuyến theo việc tiếp theo trong §0.
CONTINUE_RE = re.compile(r"^(ok[a-z]*[ ,.!]*)?(tiep tuc|lam tiep|tiep di|tiep theo|lam di|buoc tiep theo|"
                         r"lam buoc tiep theo|continue|go on|next|proceed|keep going)( di| nhe| nha| thoi| nao)?[ .!?]*$")
# Skill có sẵn trong Claude Code, không cần cài.
BUILTIN_SKILLS = ("verify", "code-review", "security-review")


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


def suggest_for(text: str, profile=None):
    """Như suggest(), thêm skill theo loại project (ví dụ c-review khi review code C)."""
    hit = suggest(text)
    if hit and profile:
        extras = []
        for kind in profile.get("kinds", []):
            extras += rules().get("rule_extras", {}).get(kind, {}).get(hit["rule"], [])
        hit["skills"] = list(dict.fromkeys(hit["skills"] + extras))
    return hit


def available_skills() -> dict:
    """{tên skill: trạng thái}: "có" (của agent-stack hoặc có sẵn trong Claude Code), "đã duyệt" (cài bằng
    install.sh), "chờ duyệt" (đã kiểm duyệt, chờ người dùng duyệt)."""
    status = {name: "có" for name in BUILTIN_SKILLS}
    home = A.home_dir()
    if not home:
        return status
    for skill_md in (home / "plugin" / "skills").glob("*/SKILL.md"):
        status[skill_md.parent.name] = "có"
    lock = (A.read_json(home / "vetted.lock", {}) or {}).get("entries", {})
    for item in (A.read_json(home / "catalog.json", {}) or {}).get("items", []):
        name = item.get("install", {}).get("name") or item.get("install", {}).get("plugin")
        review = ((lock.get(item.get("key")) or {}).get("human_review") or {}).get("status")
        if name and name not in status:
            status[name] = "đã duyệt" if review == "approved" else "chờ duyệt"
    return status


def profile_summary(profile: dict) -> tuple:
    """(nhãn hồ sơ, skill dùng được, skill chờ duyệt, subagent) theo mục profiles và markers của rules.json."""
    cfg = rules()
    labels, skills, agents = [], [], []
    for kind in profile.get("kinds", []):
        entry = cfg.get("profiles", {}).get(kind, {})
        labels.append(entry.get("label", kind))
        skills += entry.get("skills", [])
    for marker in profile.get("markers", []):
        entry = cfg.get("markers", {}).get(marker, {})
        labels.append(entry.get("label", marker))
        skills += entry.get("skills", [])
        if entry.get("agent"):
            agents.append(entry["agent"])
    status = available_skills()
    skills = list(dict.fromkeys(skills))
    ready = [s for s in skills if status.get(s) in ("có", "đã duyệt")]
    pending = [s for s in skills if status.get(s) == "chờ duyệt"]
    return labels, ready, pending, list(dict.fromkeys(agents))


def next_task(root) -> str:
    """Việc tiếp theo đầu tiên trong §0, hoặc việc đang dở; chuỗi rỗng nếu không có."""
    found = A.read_plan(Path(root))
    if not found:
        return ""
    sec = found[2]
    if sec.get("next"):
        return sec["next"][0]
    in_progress = (sec.get("fields") or {}).get("in_progress")
    return in_progress if A.has_value(in_progress) else ""


def describe(hit: dict) -> str:
    bits = []
    if hit.get("model"):
        bits.append(f"{hit['model']} · {hit['effort']}")
    if hit.get("agent"):
        bits.append(f"subagent {hit['agent']}")
    if hit.get("skills"):
        bits.append("skill " + ", ".join(hit["skills"]))
    return " · ".join(bits)


def session_hint(root):
    """Gợi ý lúc mở phiên: skill hợp với project và cách làm việc tiếp theo trong §0. None nếu không có gì."""
    root = Path(root).resolve()
    profile = A.project_profile(root)
    if not profile:
        return None
    labels, ready, pending, agents = profile_summary(profile)
    task = next_task(root)
    hit = suggest_for(task, profile) if task else None
    if not (labels or ready or hit):
        return None
    ctx = [f"[agent-stack] Hồ sơ project `{root.name}`: {', '.join(labels) or 'chưa rõ loại'}."]
    if ready:
        ctx.append("Skill hợp với project: " + ", ".join(ready) + ".")
    if pending:
        ctx.append("Có thể thêm (đã kiểm duyệt, chờ người dùng duyệt): " + ", ".join(pending) + ".")
    if agents:
        ctx.append("Subagent nên dùng: " + ", ".join(agents) + ".")
    if hit:
        ctx.append(f"Việc tiếp theo trong §0 («{A.clip(task, 100)}») → {describe(hit)}.")
    ctx.append("Dùng các gợi ý này để chọn skill cho từng việc, và cho dòng ➡️ ở cuối mỗi câu trả lời.")
    user = "🧭 " + ", ".join(labels[:3] or [root.name])
    if ready:
        user += " · skill: " + ", ".join(ready[:3])
    if hit:
        user += " · việc tiếp theo → " + describe(hit)
    return {"context": " ".join(ctx), "user": A.clip(user, 180)}


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
    if not prompt or prompt[0] in "/!#":
        return None
    root = A.project_root(data["cwd"]) if data.get("cwd") else None
    text, note = prompt, ""
    if root and CONTINUE_RE.match(A.fold(prompt)):
        task = next_task(root)
        if task:
            text, note = task, f", theo việc tiếp theo trong §0: «{A.clip(task, 80)}»"
    if not note and len(prompt.split()) < rules().get("min_words", 4):
        return None
    hit = suggest_for(text, A.project_profile(root) if root else None)
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
    context = (f"[router] Gợi ý cho việc này ({hit['rule']}, khớp {reason}{note}): " + "; ".join(parts_ctx + ([model_note] if model_note else []))
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
    ap.add_argument("--project", help="thư mục project: thêm skill theo loại project")
    ap.add_argument("--session", nargs="?", const=".", metavar="DIR",
                    help="in hồ sơ project và gợi ý skill lúc mở phiên (cho công cụ không có hook)")
    args = ap.parse_args(argv)
    if args.eval:
        return evaluate(args.eval, args.min)
    if args.session is not None:
        root = A.project_root(Path(args.session).expanduser().resolve())
        hint = session_hint(root)
        if not hint:
            print(f"Không có gợi ý cho {root}: thư mục không phải git repo và không có file kế hoạch, "
                  "hoặc chưa nhận ra loại project.")
            return 0
        print(hint["context"])
        return 0
    text = args.text or sys.stdin.read()
    profile = A.project_profile(A.project_root(Path(args.project).expanduser().resolve())) if args.project else None
    print(json.dumps(suggest_for(text, profile), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
