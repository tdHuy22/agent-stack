#!/usr/bin/env python3
"""Gợi ý skill, subagent, model và effort cho một việc, bằng luật từ khóa (0 token, dưới 50 ms).

Lệnh:
  route.py "mô tả việc" [--project DIR]     in gợi ý dạng JSON; --project thêm skill theo loại project
  route.py --session [DIR]                  in hồ sơ project, gợi ý skill và lượt cuối (.agent/LAST-TURN.md),
                                            như hook SessionStart của Claude Code; dùng trong OpenCode và
                                            công cụ không có hook
  route.py --eval FILE.jsonl [--min 0.85]   đo độ chính xác trên bộ prompt có nhãn

Dùng làm thư viện:
  suggest(text)                  -> dict hoặc None (skill tien-do dùng)
  hook_suggestion(prompt, data)  -> dict {context, user} hoặc None (hook UserPromptSubmit dùng)
  session_hint(root)             -> dict {context, user} hoặc None (hook SessionStart dùng)

Gợi ý tính cả hồ sơ project (loại code, có test, code nhạy cảm bảo mật) và việc tiếp theo trong §0:
tin nhắn kiểu "làm tiếp" được định tuyến theo việc tiếp theo trong §0. Lúc mở phiên, project lớn (hoặc có
cấu hình kiểm kiểu, biên dịch) mà chưa bật LSP thì được đề xuất bật LSP riêng cho project đó (scope local).

Router chỉ GỢI Ý. Hook không thể đổi model hay effort; người dùng tự đổi bằng /model, /effort. Đổi model giữa phiên
phải ghi lại cả context vào cache của model mới, nên router đọc model, cỡ context và lúc gọi gần nhất (số do mod giao
diện ghi trong state/session-usage/, không có thì phần cuối transcript) và chỉ gợi ý /model khi rẻ (đầu phiên, context
nhỏ, hay cache đã hết hạn); còn lại gợi ý giữ model và giao phần việc cho subagent chạy model đó. Đổi effort giữ cache trên các model 5.x nên được gợi ý thoải mái.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
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
# Câu hỏi tiến độ cho cờ progress của hook Stop (nhắc hiện cây). Hẹp hơn luật progress của router: "đang do" (bị gây
# bởi) hay "việc tiếp theo là…" giữa câu lệnh không tính; câu dài coi là việc, không phải câu hỏi.
PROGRESS_RE = re.compile(r"\b(tien do|lam gi tiep|viec gi tiep|viec tiep theo (la gi|nao)|con (viec |gi )+(chua lam|dang do"
                         r"|nua)|dang o dau|toi dau roi|lam toi dau|what'?s next|what next)\b|^status\b")
PROGRESS_MAX_WORDS = 12
# Skill có sẵn trong Claude Code, không cần cài.
BUILTIN_SKILLS = ("verify", "code-review", "security-review")


@lru_cache(maxsize=1)
def rules() -> dict:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    for order, rule in enumerate(data["rules"]):
        rule["_order"] = order
        refines = rule.get("refines") or []
        rule["_refines"] = [refines] if isinstance(refines, str) else list(refines)
        rule["_patterns"] = [(phrase, re.compile(r"(?<![a-z0-9])" + re.escape(A.fold(phrase)) + r"(?![a-z0-9])"))
                             for phrase in rule["match"]]
    return data


def score(text: str):
    """Trả về (luật tốt nhất, các cụm khớp) hoặc (None, []).

    Luật có "refines": <id hoặc danh sách id> là bản nặng hơn của luật gốc (ví dụ review bảo mật phần mã hóa so với
    review bảo mật). Khi luật gốc thắng mà luật tinh chỉnh cũng khớp ít nhất một cụm, luật tinh chỉnh được chọn.
    Luật có "only_refine": true không tự thắng được, chỉ áp qua luật gốc."""
    folded = A.fold(text)
    best, best_hits, best_score = None, [], 0
    found = {}
    for rule in rules()["rules"]:
        hits = [phrase for phrase, pattern in rule["_patterns"] if pattern.search(folded)]
        # Cụm nhiều chữ đặc hiệu hơn, nên nặng ký hơn.
        total = sum(1 + phrase.count(" ") for phrase in hits)
        if hits:
            found[rule["id"]] = (rule, hits, total)
        if rule.get("only_refine"):
            continue  # chỉ áp khi luật gốc thắng (vd "thanh toán" một mình không phải việc bảo mật)
        if total > best_score:
            best, best_hits, best_score = rule, hits, total
    seen = set()
    while best is not None and best["id"] not in seen:
        seen.add(best["id"])
        finer = [v for v in found.values() if best["id"] in v[0]["_refines"]]
        if not finer:
            break
        rule, hits, _ = max(finer, key=lambda v: v[2])
        best, best_hits = rule, best_hits + [h for h in hits if h not in best_hits]
    return best, best_hits


def suggest(text: str):
    rule, hits = score(text or "")
    if not rule:
        return None
    return {"rule": rule["id"], "model": rule.get("model"), "model_id": model_name(rule.get("model")),
            "effort": rule.get("effort"),
            "agent": rule.get("agent"), "skills": rule.get("skills", []), "note": rule.get("note", ""), "matched": hits}


def suggest_for(text: str, profile=None):
    """Như suggest(), thêm skill theo loại project (mục rule_extras của rules.json, ví dụ webapp-testing khi viết test web)."""
    hit = suggest(text)
    if hit and profile and "tests" in (profile.get("markers") or []):
        # Có test để kiểm thì dùng cấu hình rẻ hơn (mục with_tests của luật); test trượt thì lên bậc cũ.
        cheaper = next((r.get("with_tests") for r in rules()["rules"] if r["id"] == hit["rule"]), None)
        if cheaper:
            note = "; ".join(x for x in (hit["note"], cheaper.get("note", "")) if x)
            fallback = model_effort(hit)
            hit.update(model=cheaper["model"], model_id=model_name(cheaper["model"]), effort=cheaper["effort"], note=note,
                       fallback=fallback)
    if hit and profile:
        extras = []
        for kind in profile.get("kinds", []):
            extras += rules().get("rule_extras", {}).get(kind, {}).get(hit["rule"], [])
        status = available_skills()
        extras = [x for x in extras if status.get(x) != "khi cần"]  # skill chỉ cài khi cần thì không gợi ý
        hit["skills"] = list(dict.fromkeys(hit["skills"] + extras))
    return hit


def available_skills() -> dict:
    """{tên skill: trạng thái}: "có" (của agent-stack hoặc có sẵn trong Claude Code), "đã duyệt" (cài bằng
    install.sh), "khi cần" (đã duyệt nhưng scope on-demand: không cài mặc định), "chờ duyệt" (đã kiểm duyệt,
    chờ người dùng duyệt)."""
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
            if review != "approved":
                status[name] = "chờ duyệt"
            else:
                status[name] = {"on-demand": "khi cần", "project": "theo project"}.get(item.get("scope"), "đã duyệt")
    return status


def skill_plugin(name: str):
    """(id plugin "tên@marketplace", mục catalog) của skill do một plugin bên thứ ba cung cấp, hoặc (None, None)."""
    home = A.home_dir()
    for item in ((A.read_json(home / "catalog.json", {}) or {}).get("items", []) if home else []):
        inst = item.get("install") or {}
        if item.get("kind") in ("claude-plugin", "vendor-plugin") and inst.get("plugin") == name and inst.get("marketplace"):
            return f"{inst['plugin']}@{inst['marketplace']}", item
    return None, None


def install_hint(plugin: str, item: dict) -> str:
    """Lệnh để người dùng tự chạy: mục scope user cài qua install.sh (cho mọi project), mục khác cài riêng project."""
    if item.get("scope") == "user":
        return "./install.sh --apply --only catalog (trong agent-stack, cài cho mọi project)"
    verb = "enable" if plugin_installed(plugin) else "install"
    return f"claude plugin {verb} {plugin} --scope {'local' if verb == 'enable' else 'project'}"


def localize(hit: dict, root) -> dict:
    """Bỏ khỏi gợi ý các skill của plugin chưa bật cho project (hay cho người dùng, khi không có project), thay bằng
    skill dự phòng (mục skill_fallbacks của rules.json), và ghi lệnh cài vào hit["missing"]. Sửa tại chỗ và trả lại hit."""
    keep, missing = [], []
    for name in hit.get("skills") or []:
        plugin, item = skill_plugin(name)
        if plugin is None or plugin_enabled(Path(root) if root else None, plugin):
            keep.append(name)
            continue
        missing.append({"skill": name, "install": install_hint(plugin, item)})
        keep += (rules().get("skill_fallbacks") or {}).get(name, [])
    hit["skills"] = list(dict.fromkeys(keep))
    hit["missing"] = missing
    return hit


def profile_summary(profile: dict, root=None) -> tuple:
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
    enabled = {s for s in skills if status.get(s) == "theo project" and root
               and plugin_enabled(Path(root), skill_plugin(s)[0] or "")}
    ready = [s for s in skills if status.get(s) in ("có", "đã duyệt") or s in enabled]
    pending = [s for s in skills if status.get(s) in ("chờ duyệt", "khi cần", "theo project") and s not in enabled]
    return labels, ready, pending, list(dict.fromkeys(agents))


def claude_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser()


def plugin_enabled(root: Path, plugin: str) -> bool:
    """Plugin đang bật cho project này: local đè project, project đè user (như thứ tự settings của Claude Code)."""
    state = False
    paths = [claude_config_dir() / "settings.json"]
    if root:
        paths += [root / ".claude" / "settings.json", root / ".claude" / "settings.local.json"]
    for path in paths:
        value = ((A.read_json(path, {}) or {}).get("enabledPlugins") or {}).get(plugin)
        if isinstance(value, bool):
            state = value
    return state


def plugin_installed(plugin: str) -> bool:
    plugins_dir = Path(os.environ.get("AGENT_STACK_PLUGINS_DIR") or claude_config_dir() / "plugins").expanduser()
    return plugin in ((A.read_json(plugins_dir / "installed_plugins.json", {}) or {}).get("plugins") or {})


def lsp_signal(root: Path, lsp: dict):
    """File cho thấy project cần LSP (cấu hình kiểm kiểu hay biên dịch), hoặc None."""
    for name in lsp.get("signals", []):
        if (root / name).exists():
            return name
    if lsp.get("pyproject_tools"):
        try:
            text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        for tool in lsp["pyproject_tools"]:
            if f"[tool.{tool}]" in text:
                return f"pyproject.toml [tool.{tool}]"
    return None


def lsp_suggestions(root: Path, profile: dict) -> list:
    """LSP nên bật riêng cho project này: project đủ lớn hoặc có cấu hình, và plugin chưa bật.
    Mỗi mục: {plugin, reason, steps}. Không cài gì, chỉ gợi ý lệnh."""
    out = []
    for kind in profile.get("kinds", []):
        entry = rules().get("profiles", {}).get(kind, {})
        lsp = entry.get("lsp")
        if not lsp:
            continue
        count = (profile.get("counts") or {}).get(kind, 0)
        signal = lsp_signal(root, lsp)
        if count < lsp.get("min_files", 10 ** 9) and not signal:
            continue
        if plugin_enabled(root, lsp["plugin"]):
            continue
        steps = []
        if lsp.get("binary") and not shutil.which(lsp["binary"]):
            steps.append(lsp["binary_install"])
        verb = "enable" if plugin_installed(lsp["plugin"]) else "install"
        steps.append(f"claude plugin {verb} {lsp['plugin']} --scope local")
        reason = f"{count} file {entry.get('label', kind)}" + (f", có {signal}" if signal else "")
        out.append({"plugin": lsp["plugin"].split("@")[0], "reason": reason, "steps": steps})
    return out


def next_task(root) -> str:
    """Việc tiếp theo đầu tiên trong §0, hoặc việc đang dở; chuỗi rỗng nếu không có."""
    found = A.read_plan(Path(root))
    if not found:
        return ""
    sec = found[2]
    steps = A.next_open(sec)
    if steps:
        return steps[0]
    in_progress = (sec.get("fields") or {}).get("in_progress")
    return in_progress if A.has_value(in_progress) else ""


def model_name(model) -> str:
    """Tên để gõ vào /model: alias, trừ họ có alias còn trỏ bản cũ (mục model_ids của rules.json)."""
    return str((rules().get("model_ids") or {}).get(model) or model or "")


def model_effort(hit: dict) -> str:
    """"opus · xhigh"; luật không ghi effort thì chỉ tên model."""
    name = model_name(hit.get("model"))
    return f"{name} · {hit['effort']}" if hit.get("effort") else name


def describe(hit: dict) -> str:
    bits = []
    if hit.get("model"):
        bits.append(model_effort(hit) + (f" (test trượt thì {hit['fallback']})" if hit.get("fallback") else ""))
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
    labels, ready, pending, agents = profile_summary(profile, root)
    task = next_task(root)
    hit = suggest_for(task, profile) if task else None
    if hit:
        localize(hit, root)
    if not (labels or ready or hit):
        return None
    ctx = [f"[agent-stack] Hồ sơ project `{root.name}`: {', '.join(labels) or 'chưa rõ loại'}."]
    if ready:
        ctx.append("Skill hợp với project: " + ", ".join(ready) + ".")
    if pending:
        ctx.append("Có thể thêm (đã kiểm duyệt; chưa cài, chờ người dùng duyệt hoặc cài khi cần): " + ", ".join(pending) + ".")
    if agents:
        ctx.append("Subagent nên dùng: " + ", ".join(agents) + ".")
    lsps = lsp_suggestions(root, profile)
    for s in lsps:
        ctx.append(f"Nên bật LSP {s['plugin']} riêng cho project này ({s['reason']}): nhảy tới định nghĩa, tìm chỗ dùng, "
                   "báo lỗi ngay sau khi sửa. Chưa bật. Đề xuất với người dùng khi việc cần đọc hay sửa nhiều code, "
                   "đừng tự cài: " + " rồi ".join(f"`{x}`" for x in s["steps"]) + ".")
    if hit:
        ctx.append(f"Việc tiếp theo trong §0 («{A.clip(task, 100)}») → {describe(hit)}.")
    ctx.append("Dùng các gợi ý này để chọn skill cho từng việc, và cho dòng ➡️ ở cuối mỗi câu trả lời.")
    user = "🧭 " + ", ".join(labels[:3] or [root.name])
    if ready:
        user += " · skill: " + ", ".join(ready[:3])
    if lsps:
        user += " · nên bật " + ", ".join(s["plugin"] for s in lsps)
    if hit:
        user += " · việc tiếp theo → " + describe(hit)
    return {"context": " ".join(ctx), "user": A.clip(user, 180)}


def family(model) -> str:
    text = (model or "").lower() if isinstance(model, str) else json.dumps(model or {}).lower()
    return next((f for f in FAMILIES if f in text), "")


def current_model(session_id: str) -> str:
    """Model hiện tại (chuỗi gốc, chữ thường), lấy từ thông tin phiên do hook SessionStart ghi, hoặc từ statusline."""
    def raw(model) -> str:
        return (model or "").lower() if isinstance(model, str) else json.dumps(model or {}).lower()
    if session_id:
        name = hashlib.sha1(session_id.encode()).hexdigest()[:16] + ".json"
        info = A.read_json(A.state_dir() / "sessions" / name, {}) or {}
        if info.get("model"):
            return raw(info["model"])
    limits = A.read_json(A.state_dir() / "limits.json", {}) or {}
    if limits.get("session_id") == session_id:
        return raw(limits.get("model"))
    return ""


def needs_model_switch(wanted: str, now: str) -> bool:
    """Có nên gợi ý /model không: khác họ, hoặc cùng họ mà đang ở bản cũ (vd Haiku 4.5 khi luật muốn claude-haiku-5-5)."""
    if not wanted or not now:
        return False
    if family(now) != wanted:
        return True
    target = model_name(wanted)
    return target != wanted and target not in now


def effort_keeps_cache(model: str) -> bool:
    """Đổi effort giữa phiên giữ prompt cache với model này (Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1)."""
    return any((model or "").startswith(m) for m in (rules().get("switch") or {}).get("effort_keeps_cache") or [])


def switch_advice(target: str, usage: dict, now: float = None) -> dict:
    """Đổi sang model họ `target` lúc này có rẻ không, theo usage của phiên (A.session_usage). Rẻ khi chưa có lần gọi
    nào (đầu phiên, sau /clear), context dưới free_tokens, hay đã nghỉ quá TTL (cache hết hạn). `cost` là giá niêm yết
    (USD) để ghi lại cả context vào cache của model mới. Trả {cheap, why, cost, context, idle, ttl}."""
    cfg = rules().get("switch") or {}
    usage = usage or {}
    ctx = int(usage.get("context") or 0)
    ts = usage.get("ts")
    ttl = int(usage.get("ttl") or 3600)
    idle = (now or time.time()) - ts if isinstance(ts, (int, float)) else None
    long_price = (cfg.get("price_in_long") or {}).get(target) if ctx > cfg.get("long_from", 10 ** 12) else None
    price = long_price or (cfg.get("price_in") or {}).get(target) or 0
    cost = ctx * price * float((cfg.get("cache_write") or {}).get(str(ttl), 2.0)) / 1e6
    if not ctx or idle is None:
        cheap, why = True, "đầu phiên"
    elif usage.get("switched"):
        cheap, why = True, "vừa đổi model, cache mới chưa có"
    elif idle > ttl:
        cheap, why = True, "cache đã nguội"
    elif ctx < cfg.get("free_tokens", 40000):
        cheap, why = True, "context nhỏ"
    else:
        cheap, why = False, "cache còn ấm"
    return {"cheap": cheap, "why": why, "cost": cost, "context": ctx, "idle": idle, "ttl": ttl}


def usd(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def turn_flags(prompt: str, cwd) -> dict:
    """Cờ của lượt cho các hook khác: threat_model khi việc là chức năng đụng ranh giới tin cậy (luật
    feature-boundary), để hook PreToolUse nhắc chạy mo-hinh-de-doa trước khi code; progress khi người dùng hỏi tiến
    độ hay việc tiếp theo (is_progress_question), để hook Stop nhắc hiện cây kế hoạch. Không phụ thuộc việc gợi ý có bị ẩn
    vì đã nhắc trong giờ qua hay không."""
    prompt = (prompt or "").strip()
    if not prompt or prompt[0] in "/!#" or A.is_automated_prompt(prompt):
        return {}
    root = A.project_root(cwd) if cwd else None
    if is_progress_question(prompt):
        return {"progress": True}
    continuing = bool(root and CONTINUE_RE.match(A.fold(prompt)))
    hit = suggest((next_task(root) or prompt) if continuing else prompt)
    if hit and hit["rule"] == "feature-boundary":
        return {"threat_model": True}
    return {}


def is_progress_question(prompt: str) -> bool:
    """Người dùng hỏi tiến độ hay việc tiếp theo ("làm tiếp" thì không: đó là lệnh làm việc trong §0)."""
    text = A.fold(prompt or "")
    return (len(text.split()) <= PROGRESS_MAX_WORDS and not CONTINUE_RE.match(text)
            and bool(PROGRESS_RE.search(text)))


def hook_suggestion(prompt: str, data: dict):
    prompt = (prompt or "").strip()
    if not prompt or prompt[0] in "/!#" or A.is_automated_prompt(prompt):
        return None  # lệnh, hay tin do hệ thống tạo (báo cáo subagent, thông báo nền): không phải việc cần định tuyến
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
    localize(hit, root)
    sid = data.get("session_id", "")
    # Số chính thức do mod giao diện ghi (Claude Code có mod); không có hay đã cũ (OpenCode, phiên -p) thì đọc transcript.
    usage = A.mod_session_usage(sid) or (A.session_usage(data["transcript_path"]) if data.get("transcript_path") else {})
    now_model = (usage.get("model") or current_model(sid) or "").lower()
    now_effort = (data.get("effort") or {}).get("level")
    parts_user, parts_ctx = [], []
    switch_note = ""
    # Việc do chính agent làm (reviewer, researcher...) thì model nằm ở agent, không cần đổi model của phiên chính.
    own = hit["agent"] in ((rules().get("switch") or {}).get("agents_doing_the_work") or [])
    want_switch = needs_model_switch(hit["model"], now_model) and not own
    advice = switch_advice(hit["model"], usage) if want_switch else None
    if advice and advice["cheap"]:
        parts_user.append(f"/model {model_name(hit['model'])} ({advice['why']})")
    elif advice:
        cur = family(now_model) or now_model
        parts_user.append(f"giữ {cur} (đổi tốn ≈{usd(advice['cost'])} USD)")
        parts_user.append(f"subagent {model_effort(hit)}")
        idle = f"{advice['idle'] / 60:.0f} phút trước" if advice["idle"] is not None else "chưa rõ lúc nào"
        switch_note = (f"Đừng đổi /model lúc này: context ≈{advice['context'] // 1000}K token, cache còn ấm (lần gọi model "
                       f"gần nhất {idle}, cache giữ {advice['ttl'] // 60} phút); đổi sẽ ghi lại cả context vào cache "
                       f"của model mới, ≈{usd(advice['cost'])} USD giá niêm yết. Phần việc hợp {model_effort(hit)}: giao "
                       f"subagent (Agent với model \"{model_name(hit['model'])}\""
                       + (f", effort \"{hit['effort']}\"" if hit["effort"] else "")
                       + "); việc dài sửa nhiều file thì thêm isolation \"worktree\" rồi gộp bằng merge_back.py của "
                       "task-router. Sang việc mới không cần hội thoại này thì đề nghị /clear rồi mới đổi. Việc cần model "
                       f"mạnh hơn mới làm đúng thì vẫn nên đổi (chất lượng trước chi phí). Dòng ➡️ ghi `Model: giữ {cur}`.")
    # Effort của luật đi kèm model của luật; việc do agent tự làm thì effort cũng nằm ở agent.
    effort_differs = hit["effort"] and now_effort and hit["effort"] != now_effort and not own
    if effort_differs and not (advice and not advice["cheap"]) and (
            not now_model or effort_keeps_cache(now_model) or (advice and advice["cheap"])):
        parts_user.append(f"/effort {hit['effort']}")
    if hit["agent"]:
        parts_user.append(f"agent {hit['agent']}")
        parts_ctx.append(f"giao cho subagent {hit['agent']}")
    if hit["skills"]:
        parts_user.append("skill " + ", ".join(hit["skills"]))
        parts_ctx.append("dùng skill " + ", ".join(hit["skills"]))
        parts_ctx += [n for n in ((rules().get("skill_notes") or {}).get(x) for x in hit["skills"]) if n]
    if hit.get("missing"):
        parts_ctx.append("chưa bật cho project này: " + "; ".join(f"{m['skill']} (`{m['install']}`)" for m in hit["missing"])
                         + "; chỉ đề xuất cài với người dùng, đừng tự cài")
    if hit.get("note"):
        parts_ctx.append(hit["note"])
    if not parts_user:
        return None  # model, effort đã khớp và không có skill/agent để gợi ý
    if not A.once(f"route-{sid}-{hit['rule']}", 3600):
        return None  # cùng một gợi ý không nhắc lại trong một giờ
    reason = ", ".join(f"'{m}'" for m in hit["matched"][:3])
    model_note = (f"model {model_effort(hit)}" + (f", test trượt thì {hit['fallback']}" if hit.get("fallback") else "")
                  if hit["model"] else "")
    context = (f"[router] Gợi ý cho việc này ({hit['rule']}, khớp {reason}{note}): " + "; ".join(parts_ctx + ([model_note] if model_note else []))
               + ". Đây chỉ là gợi ý. Nếu nên đổi model hoặc effort, nói với người dùng ở cuối câu trả lời, đừng tự đổi."
               + (f" {switch_note}" if switch_note else ""))
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
        last = A.last_turn_context(root)
        if not hint and not last:
            print(f"Không có gợi ý cho {root}: thư mục không phải git repo và không có file kế hoạch, "
                  "hoặc chưa nhận ra loại project.")
            return 0
        print("\n".join(x["context"] for x in (hint, last) if x))
        return 0
    text = args.text or sys.stdin.read()
    root = A.project_root(Path(args.project).expanduser().resolve()) if args.project else None
    hit = suggest_for(text, A.project_profile(root) if root else None)
    print(json.dumps(localize(hit, root) if hit else hit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
