"""Đếm mức dùng hạn mức của các phiên Claude Code 14 ngày qua (mọi project), chỉ đếm token, lần gọi, hook, subagent; không in nội dung. Chạy: python3 tools/usage_report.py. Mốc 10/11/2026: 88,6 triệu đơn vị, một phiên dài 47%, subagent review 14%."""
import json, glob, os, time, collections, statistics
root = os.path.expanduser("~/.claude/projects")
cut = time.time() - 14 * 86400
W = {"in": 1, "cw": 1.25, "cr": 0.1, "out": 5}   # trọng số so với token vào thường, cùng model
def units(u):
    return (u.get("input_tokens", 0) * W["in"] + u.get("cache_creation_input_tokens", 0) * W["cw"]
            + u.get("cache_read_input_tokens", 0) * W["cr"] + u.get("output_tokens", 0) * W["out"])
main_u = collections.Counter(); sub_u = collections.Counter(); sub_by_type = collections.Counter(); sub_n = collections.Counter()
hook_ctx = collections.Counter(); hook_ctx_n = collections.Counter(); blocks = collections.Counter()
skills = collections.Counter(); first_ctx = []; sessions = 0; calls = collections.Counter(); prompts = 0
cr_share = collections.Counter()
for f in glob.glob(f"{root}/*/*.jsonl"):
    if os.path.getmtime(f) < cut: continue
    sessions += 1; first = None; seen_ids = set()
    for line in open(f, errors="replace"):
        try: e = json.loads(line)
        except Exception: continue
        t = e.get("type")
        if t == "user" and isinstance((e.get("message") or {}).get("content"), str): prompts += 1
        if t == "attachment":
            a = e.get("attachment") or {}
            if a.get("type") == "hook_additional_context":
                hook_ctx[a.get("hookEvent") or a.get("hookName")] += len(str(a.get("content") or "")); hook_ctx_n[a.get("hookEvent")] += 1
            if a.get("type") == "hook_blocking_error": blocks[a.get("hookName")] += 1
        if t == "assistant":
            m = e.get("message") or {}
            mid = m.get("id")
            u = m.get("usage") or {}; model = m.get("model", "?")
            if mid not in seen_ids and u:
                seen_ids.add(mid); main_u[model] += units(u); calls[model] += 1
                cr_share["cr"] += u.get("cache_read_input_tokens", 0) * W["cr"]; cr_share["all"] += units(u)
            if u and first is None: first = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Skill":
                    skills[(b.get("input") or {}).get("skill", "?")] += 1
    if first: first_ctx.append(first)
for meta in glob.glob(f"{root}/*/*/subagents/*.meta.json"):
    j = meta.replace(".meta.json", ".jsonl")
    if not os.path.exists(j) or os.path.getmtime(j) < cut: continue
    try: typ = json.load(open(meta)).get("agentType", "?")
    except Exception: typ = "?"
    seen = set(); tot = 0
    for line in open(j, errors="replace"):
        try: e = json.loads(line)
        except Exception: continue
        if e.get("type") == "assistant":
            m = e.get("message") or {}
            if m.get("id") in seen or not m.get("usage"): continue
            seen.add(m.get("id")); x = units(m["usage"]); tot += x; sub_u[m.get("model", "?")] += x
    sub_by_type[typ] += tot; sub_n[typ] += 1
print(f"{sessions} phiên chính, {prompts} tin nhắn người dùng")
print("context lượt đầu (token): trung vị", f"{statistics.median(first_ctx):,.0f}", "min", f"{min(first_ctx):,}", "max", f"{max(first_ctx):,}")
tm, ts = sum(main_u.values()), sum(sub_u.values())
print(f"đơn vị chi phí: phiên chính {tm/1e6:.1f}M, subagent {ts/1e6:.1f}M ({100*ts/(tm+ts):.0f}%)")
print("phiên chính theo model:", {k: f"{v/1e6:.1f}M/{calls[k]} lần gọi" for k, v in main_u.most_common()})
print("subagent theo model:", {k: f"{v/1e6:.1f}M" for k, v in sub_u.most_common()})
print("đọc cache chiếm", f"{100*cr_share['cr']/cr_share['all']:.0f}% đơn vị phiên chính")
print("subagent theo loại (đơn vị, số lần):"); [print(f"   {k:32s} {v/1e6:6.2f}M  {sub_n[k]}") for k, v in sub_by_type.most_common(15)]
print("hook chèn context (ký tự, số lần):", {k: (v, hook_ctx_n[k]) for k, v in hook_ctx.most_common()})
print("hook chặn:", dict(blocks))
print("skill gọi:", dict(skills.most_common(20)))
