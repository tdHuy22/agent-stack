#!/usr/bin/env python3
"""Gợi ý skill, subagent, model và effort cho một việc, bằng luật từ khóa (0 token, dưới 50 ms).

Lệnh:
  route.py "mô tả việc" [--project DIR]     in gợi ý dạng JSON; --project thêm skill theo loại project
  route.py --session [DIR]                  in hồ sơ project, gợi ý skill và lượt cuối (.agent/LAST-TURN.md),
                                            như hook SessionStart của Claude Code; dùng trong
                                            công cụ không có hook
  route.py --eval FILE.jsonl [--min 0.85]   đo độ chính xác trên bộ prompt có nhãn

Dùng làm thư viện:
  suggest(text)                  -> dict hoặc None (skill progress dùng)
  hook_suggestion(prompt, data)  -> dict {context, user} hoặc None (hook UserPromptSubmit dùng)
  session_hint(root, permission_mode) -> dict {context, user} hoặc None (hook SessionStart dùng)

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
# "lưu/ghi/cập nhật tiến độ", "tiến độ đã lưu chưa" là việc ghi lại (session-save), không phải hỏi tiến độ: bỏ cụm này
# trước khi dò. "cập nhật tiến độ giúp tôi" theo nghĩa nhờ báo tiến độ cũng bị bỏ: chấp nhận, vì nghĩa ghi phổ biến hơn.
SAVE_PROGRESS_RE = re.compile(r"\b(luu|ghi|cap nhat|update|save)( lai| het| lai het| het lai)? (tien do|progress)\b"
                              r"|\b(tien do|progress)( da)?( duoc)? (luu|ghi|cap nhat)\b")
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


def score(text: str, mask=()):
    """Trả về (luật tốt nhất, các cụm khớp) hoặc (None, []).

    Luật có "refines": <id hoặc danh sách id> là bản nặng hơn của luật gốc (ví dụ review bảo mật phần mã hóa so với
    review bảo mật). Khi luật gốc thắng mà luật tinh chỉnh cũng khớp ít nhất một cụm, luật tinh chỉnh được chọn.
    Luật có "only_refine": true không tự thắng được, chỉ áp qua luật gốc. `mask`: cụm (đã bỏ dấu) project đánh dấu bỏ
    qua trong `.agent/stack.json`, che bằng khoảng trắng trước khi so. Luật nhóm protected (bảo mật) luôn chấm trên
    chữ chưa che, để cụm bỏ qua chồng một phần lên cụm bảo mật ("code review" trong "secure code review") không che
    được luật bảo mật."""
    raw = folded = A.fold(text)
    for phrase in mask:
        folded = stack_lib().pattern(phrase).sub(" ", folded)
    protected = set((rules().get("rule_groups") or {}).get("protected") or []) if mask else set()
    best, best_hits, best_score = None, [], 0
    found = {}
    for rule in rules()["rules"]:
        seen_text = raw if rule["id"] in protected else folded
        hits = [phrase for phrase, pattern in rule["_patterns"] if pattern.search(seen_text)]
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


def suggest(text: str, mask=()):
    rule, hits = score(text or "", mask)
    if not rule:
        return None
    return {"rule": rule["id"], "model": rule.get("model"), "model_id": model_name(rule.get("model")),
            "effort": rule.get("effort"),
            "agent": rule.get("agent"), "skills": rule.get("skills", []), "note": rule.get("note", ""), "matched": hits}


def stack_lib():
    import stackcfg  # noqa: E402 (cùng thư mục lib với agentstack; chỉ nạp khi cần)
    return stackcfg


def protected_phrases() -> tuple:
    """Cụm (đã bỏ dấu) của các luật nhóm protected: `ignore` của project không được che chúng."""
    ids = set((rules().get("rule_groups") or {}).get("protected") or [])
    return tuple(A.fold(p) for r in rules()["rules"] if r["id"] in ids for p in r["match"])


def project_stack(root):
    """Cấu hình `.agent/stack.json` đã gộp với bản chụp đã duyệt (stackcfg.effective), hay None khi project không có."""
    if not root:
        return None
    return stack_lib().effective(Path(root), protected_phrases())


def apply_stack(hit, text: str, stack):
    """Nâng gợi ý lên mức sàn của project: từ khóa riêng và từ của vùng lõi khớp trong câu, mức sàn của nhóm luật.
    Không bao giờ hạ. Câu không khớp luật nào mà khớp từ khóa hay vùng thì ra luật `project-keyword`. Chỉ đưa vào
    gợi ý cụm đã khớp trong câu người dùng gõ, không đưa chữ khác của file (TM-117)."""
    S = stack_lib()
    cfg = stack["cfg"]
    folded = A.fold(text or "")
    sources, words = [], []
    for key, kw in cfg["keywords"].items():
        if S.contains(folded, key):
            sources.append((kw["model"], kw["effort"]))
            words.append(key)
    for area in cfg["areas"].values():
        for word in area["words"]:
            if S.contains(folded, word):
                sources.append((area["model"], area["effort"]))
                words.append(word)
    if hit:
        groups = rules().get("rule_groups") or {}
        for group, floor in cfg["floors"].items():
            if hit["rule"] in (groups.get(group) or []):
                sources.append((floor["model"], floor["effort"]))
    if not sources:
        return hit
    floor = sources[0]
    for level in sources[1:]:
        floor = S.lvl_max(floor, level)
    if hit is None:
        return {"rule": "project-keyword", "model": floor[0], "model_id": model_name(floor[0]), "effort": floor[1],
                "agent": None, "skills": [], "note": "", "matched": list(dict.fromkeys(words)), "raised": True,
                "floor": list(floor)}
    hit["matched"] = hit["matched"] + [w for w in dict.fromkeys(words) if w not in hit["matched"]]
    hit["floor"] = list(floor)
    raise_hit(hit)
    return hit


def raise_hit(hit) -> None:
    """Nâng model, effort của `hit` lên `hit["floor"]` (tại chỗ). Dòng "test trượt thì …" bỏ khi mức dự phòng không còn
    cao hơn mức sau khi nâng."""
    S = stack_lib()
    floor = hit.get("floor")
    if not floor:
        return
    model, effort = S.raise_to(hit.get("model"), hit.get("effort"), tuple(floor))
    if (model, effort) == (hit.get("model"), hit.get("effort")):
        return
    hit.update(model=model, model_id=model_name(model), effort=effort, raised=True)
    base = next((r for r in rules()["rules"] if r["id"] == hit["rule"]), None)
    if not hit.get("fallback") or base is None:
        return
    # Mức dự phòng ("test trượt thì …") cũng không dưới sàn; không còn cao hơn mức đã nâng thì bỏ.
    b_model, b_effort = S.raise_to(base.get("model"), base.get("effort"), tuple(floor))
    if b_model in S.MODEL_RANK and b_effort in S.EFFORT_RANK and S.at_least((model, effort), (b_model, b_effort)):
        hit.pop("fallback")
    else:
        hit["fallback"] = f"{model_name(b_model)} · {b_effort}"


def suggest_for(text: str, profile=None, stack=None):
    """Như suggest(), thêm skill theo loại project (mục rule_extras của rules.json, ví dụ webapp-testing khi viết test web).
    `stack`: cấu hình project (project_stack) để che từ khóa bỏ qua và nâng lên mức sàn; None thì như cũ."""
    hit = suggest(text, tuple(stack["cfg"]["ignore"]) if stack else ())
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
    if stack:
        hit = apply_stack(hit, text, stack)
    return hit


def available_skills() -> dict:
    """{tên skill: trạng thái}: "có" (của agent-stack hoặc có sẵn trong Claude Code), "đã duyệt" (cài bằng
    install.sh), "khi cần" (đã duyệt nhưng scope on-demand: không cài mặc định), "chờ duyệt" (đã kiểm duyệt,
    chờ người dùng duyệt)."""
    status = dict.fromkeys(BUILTIN_SKILLS, "có")
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


def pyramid_gaps(root: Path):
    """(câu cho agent, dòng ngắn) khi project thiếu công cụ kiểm cho ngôn ngữ của nó, có ngôn ngữ agent-stack chưa
    phủ, hay thiếu tầng của hình tháp kiểm (linter, test, Mốc kiểm tra, file luật); None nếu đủ hay có lỗi.
    Phần nhận ngôn ngữ và công cụ nằm ở checks.py của done-gate. Chỉ gợi ý, không cài gì."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "done-gate" / "scripts"))
        import checks  # noqa: E402
        return checks.gaps_text(checks.project_gaps(root, A.project_files(root)))
    except Exception:  # noqa: BLE001 (gợi ý phụ: lỗi ở đây không được làm mất gợi ý khác)
        return None


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


PLAN_MODE_PHRASE = "plan mode (Shift+Tab hay /plan)"


def plan_mode_skipped(task: str, hit) -> bool:
    """Việc tiếp theo trong §0 có rõ là nhỏ không, để khỏi gợi ý plan mode. Mặc định là gợi ý (ý 6 của kế hoạch
    agent-stack theo project, bạn chốt 14/11/2026: luật từ khóa hẹp và sót, nên không đoán "đủ lớn" bằng từ khóa).
    Bỏ khi luật khớp thuộc loại việc nhỏ (rules.json, mục plan_mode) hay việc quá ngắn; lớp model của GĐ5 sẽ tinh lại."""
    cfg = rules().get("plan_mode") or {}
    if not (task or "").strip():
        return True
    if hit and hit.get("rule") in (cfg.get("skip_rules") or []) and not hit.get("raised"):
        return True  # project nâng mức (.agent/stack.json) thì không coi là việc nhỏ
    return len(task.split()) < int(cfg.get("min_words", 6)) or is_progress_question(task)


def plan_mode_hint(permission_mode=None) -> dict:
    """Câu gợi ý plan mode cho dòng 🧭 (user) và bối cảnh (context). pi không có plan mode nên nhận câu khác."""
    if A.host() == "pi":
        return {"user": "kế hoạch phiên trước khi làm",
                "context": ("Việc tiếp theo trong §0 là việc cỡ vừa trở lên: pi không có plan mode, nên bước đầu viết kế hoạch "
                            "phiên theo khuôn của skill session-keeper (mục `ke-hoach`: việc, tiêu chí xong, các bước kèm model "
                            "và effort, lệnh kiểm chứng, ngoài phạm vi, điểm dừng) và chờ bạn trả lời trước khi sửa file.")}
    return {"user": PLAN_MODE_PHRASE,
            "context": (f"Việc tiếp theo trong §0 là việc cỡ vừa trở lên: gợi ý người dùng vào {PLAN_MODE_PHRASE} rồi lập kế "
                        "hoạch phiên theo khuôn của skill session-keeper (mục `ke-hoach`: việc, tiêu chí xong, các bước kèm "
                        "model và effort, lệnh kiểm chứng, ngoài phạm vi, điểm dừng) trước khi sửa file; chỉ gợi ý, đừng tự "
                        "vào plan mode.")}


def session_hint(root, permission_mode=None):
    """Gợi ý lúc mở phiên: skill hợp với project và cách làm việc tiếp theo trong §0, kèm gợi ý vào plan mode khi việc
    đó không rõ là nhỏ (không gợi ý khi phiên đã ở plan mode). None nếu không có gì."""
    root = Path(root).resolve()
    profile = A.project_profile(root)
    if not profile:
        return None
    labels, ready, pending, agents = profile_summary(profile, root)
    task = next_task(root)
    stack = project_stack(root)
    hit = suggest_for(task, profile, stack) if task else None
    if hit:
        localize(hit, root)
    gaps = pyramid_gaps(root)
    plan = plan_mode_hint() if task and permission_mode != "plan" and not plan_mode_skipped(task, hit) else None
    notes = stack_notes(root, profile, stack) if stack else None
    if not (labels or ready or hit or gaps or plan or notes):
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
    if gaps:
        ctx.append(gaps[0])
    if hit:
        ctx.append(f"Việc tiếp theo trong §0 («{A.clip(task, 100)}») → {describe(hit)}.")
    if plan:
        ctx.append(plan["context"])
    if notes:
        ctx += notes[0]
    ctx.append("Dùng các gợi ý này để chọn skill cho từng việc, và cho dòng ➡️ ở cuối mỗi câu trả lời.")
    user = "🧭 " + ", ".join(labels[:3] or [root.name])
    if plan:  # đặt trước danh sách skill: dòng bị cắt ở 180 ký tự, gợi ý này không được mất
        user += " · " + plan["user"]
    if notes and notes[1]:
        user += " · " + " · ".join(notes[1])
    if ready:
        user += " · skill: " + ", ".join(ready[:3])
    if lsps:
        user += " · nên bật " + ", ".join(s["plugin"] for s in lsps)
    if gaps:
        user += " · " + gaps[1]
    if hit:
        user += " · việc tiếp theo → " + describe(hit)
    return {"context": " ".join(ctx), "user": A.clip(user, 180)}


SETUP_CMD = "python3 ~/Documents/Claude/agent-stack/plugin/skills/project-setup/scripts/stack.py"


def stack_notes(root: Path, profile: dict, stack: dict):
    """([câu cho agent], [mẩu cho dòng 🧭]) về `.agent/stack.json`: mục sai dạng, mục nới chưa duyệt, hồ sơ đã đổi so với
    lúc chạy project-setup, đề xuất từ nhật ký router. Chỉ số đếm và nhãn cố định, không chép chữ của file (TM-117)."""
    S = stack_lib()
    ctx, user = [], []
    if stack.get("lost"):
        ctx.append("[agent-stack] Bản chụp cấu hình đã duyệt của project này (state/stack-approved/) đã mất: router đang "
                   "dùng `.agent/stack.json` hiện tại như lần đầu gặp (trừ từ khóa bỏ qua). Báo người dùng; mục nới "
                   "đã duyệt trước đây cần duyệt lại.")
        user.append("⚠ mất bản chụp stack.json")
    if stack.get("first"):
        cfg = stack["cfg"]
        n = sum(len(cfg[k]) for k in ("keywords", "areas", "floors", "tools")) + bool(cfg.get("min_risk"))
        ctx.append(f"[agent-stack] Lần đầu thấy `.agent/stack.json` của project này trên máy: {n} mục siết (từ khóa, vùng "
                   "lõi, mức sàn, công cụ, mức rủi ro tối thiểu) có tác dụng ngay. Báo người dùng một dòng và đề nghị xem "
                   f"bằng `{SETUP_CMD} check`, vì file đến từ repo.")
        user.append(f"stack.json mới: {n} mục siết")
    if stack["problems"]:
        ctx.append(f"[agent-stack] `.agent/stack.json` có {len(stack['problems'])} mục sai dạng, router bỏ qua: xem bằng "
                   f"`{SETUP_CMD} check`.")
    if stack["pending"]:
        n = len(stack["pending"])
        ctx.append(f"[agent-stack] `.agent/stack.json` có {n} mục nới (hạ mức, bỏ mục, thêm từ khóa bỏ qua) chưa được "
                   "người dùng duyệt trên máy này, nên router chưa dùng. Xem bằng `" + SETUP_CMD + " check`; người dùng "
                   "duyệt bằng một tin \"duyệt <mã mục>\" thì chạy `stack.py approve <mã mục>` (skill project-setup).")
        user.append(f"⏸ {n} mục nới chờ duyệt (stack.json)")
    drift = S.fingerprint_drift(stack["cfg"].get("fingerprint"), S.fingerprint(profile, root))
    if drift:
        ctx.append("[agent-stack] Hồ sơ project đã đổi so với lúc chạy project-setup (" + ", ".join(drift) + "): đề xuất "
                   "người dùng chạy lại phần đó của skill project-setup.")
        user.append("hồ sơ đổi: " + ", ".join(drift))
    learned = S.learn_count(root)
    if learned:
        ctx.append(f"[agent-stack] Nhật ký router có {learned} đề xuất sửa `.agent/stack.json` (cùng kiểu lệch từ 3 lần): "
                   f"xem bằng `{SETUP_CMD} learn`, đưa người dùng duyệt từng mục.")
        user.append(f"{learned} đề xuất cho stack.json")
    return (ctx, user) if ctx else None


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
    """Đổi effort giữa phiên giữ prompt cache với model này (Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1 trở lên)."""
    return any((model or "").startswith(m) for m in (rules().get("switch") or {}).get("effort_keeps_cache") or [])


def switch_advice(target: str, usage: dict, now: float | None = None) -> dict:
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


# Việc đủ lớn để ghi tiêu chí xong vào §0 trước khi code (cải tiến 3 của trang đánh giá pipeline, 04/11/2026).
CRITERIA_RULES = {"feature", "feature-boundary", "refactor", "architecture", "architecture-critical", "debug-simple",
                  "debug-hard", "debug-production", "debug-stuck", "long-agent"}


def turn_flags(prompt: str, cwd) -> dict:
    """Cờ của lượt cho các hook khác: threat_model khi việc là chức năng đụng ranh giới tin cậy (luật
    feature-boundary), để hook PreToolUse nhắc chạy threat-model trước khi code; criteria khi việc là tính năng, sửa
    lỗi, refactor hay kiến trúc (CRITERIA_RULES), để hook PreToolUse nhắc ghi tiêu chí xong vào §0 trước khi code;
    progress khi người dùng hỏi tiến độ hay việc tiếp theo (is_progress_question), để hook Stop nhắc hiện cây kế hoạch.
    Không phụ thuộc việc gợi ý có bị ẩn vì đã nhắc trong giờ qua hay không."""
    prompt = (prompt or "").strip()
    if not prompt or prompt[0] in "/!#" or A.is_automated_prompt(prompt):
        return {}
    root = A.project_root(cwd) if cwd else None
    if is_progress_question(prompt):
        return {"progress": True}
    continuing = bool(root and CONTINUE_RE.match(A.fold(prompt)))
    hit = suggest((next_task(root) or prompt) if continuing else prompt)
    flags = {}
    if hit and hit["rule"] == "feature-boundary":
        flags["threat_model"] = True
    if hit and hit["rule"] in CRITERIA_RULES:
        flags["criteria"] = True
    return flags


def is_progress_question(prompt: str) -> bool:
    """Người dùng hỏi tiến độ hay việc tiếp theo ("làm tiếp" thì không: đó là lệnh làm việc trong §0)."""
    text = A.fold(prompt or "")
    return (len(text.split()) <= PROGRESS_MAX_WORDS and not CONTINUE_RE.match(text)
            and bool(PROGRESS_RE.search(SAVE_PROGRESS_RE.sub(" ", text))))


ROUTE_LOG = "route-log.jsonl"


def log_route(seen: dict, data: dict) -> None:
    """Một dòng nhật ký router mỗi tin (cả khi gợi ý bị ẩn vì đã nhắc), để `stack.py learn` so gợi ý với mức thật đã cần
    (effort người dùng đổi ở tin sau, test trượt, review tìm ra lỗi). Chỉ ghi trên máy (state/); câu đã bỏ dấu, cắt
    200 ký tự. Không bao giờ văng lỗi."""
    try:
        hit = seen.get("hit") or {}
        root = seen.get("root")
        A.log_event("route", {
            "session": data.get("session_id", ""), "root": str(root) if root else "",
            "key": stack_lib().repo_key(root) if root else "", "effort_now": (data.get("effort") or {}).get("level"),
            "rule": hit.get("rule"), "model": hit.get("model"), "effort": hit.get("effort"),
            "matched": hit.get("matched") or [], "raised": bool(hit.get("raised")), "fallback": bool(hit.get("fallback")),
            "text": A.fold(A.redact_secrets(seen.get("text") or ""))[:200]}, ROUTE_LOG)
    except Exception:  # noqa: BLE001
        pass


def hook_suggestion(prompt: str, data: dict):
    seen = {}
    try:
        return _hook_suggestion(prompt, data, seen)
    finally:
        if seen:
            log_route(seen, data)


def _hook_suggestion(prompt: str, data: dict, seen: dict):
    prompt = (prompt or "").strip()
    if not prompt or prompt[0] in "/!#" or A.is_automated_prompt(prompt):
        return None  # lệnh, hay tin do hệ thống tạo (báo cáo subagent, thông báo nền): không phải việc cần định tuyến
    root = A.project_root(data["cwd"]) if data.get("cwd") else None
    text, note = prompt, ""
    if root and CONTINUE_RE.match(A.fold(prompt)):
        task = next_task(root)
        if task:
            text, note = task, f", theo việc tiếp theo trong §0: «{A.clip(task, 80)}»"
    seen.update(root=root, text=text)
    if not note and len(prompt.split()) < rules().get("min_words", 4):
        return None
    hit = suggest_for(text, A.project_profile(root) if root else None, project_stack(root) if root else None)
    seen["hit"] = hit
    if not hit:
        return None
    localize(hit, root)
    sid = data.get("session_id", "")
    # Số chính thức do mod giao diện ghi (Claude Code có mod); không có hay đã cũ (phiên -p) thì đọc transcript.
    usage = A.mod_session_usage(sid) or (A.session_usage(data["transcript_path"]) if data.get("transcript_path") else {})
    now_model = (usage.get("model") or current_model(sid) or "").lower()
    now_effort = (data.get("effort") or {}).get("level")
    parts_user, parts_ctx = [], []
    switch_note = ""
    # Việc do chính agent làm (reviewer, researcher...) thì model nằm ở agent, không cần đổi model của phiên chính.
    own = hit["agent"] in ((rules().get("switch") or {}).get("agents_doing_the_work") or [])
    want_switch = needs_model_switch(hit["model"], now_model) and not own
    advice = switch_advice(hit["model"], usage) if want_switch else None
    # Luật có cấu hình dự phòng cho phiên đang ấm (long-agent: Fable nên mở phiên mới, không đổi giữa phiên Opus):
    # đổi model không rẻ thì gợi ý cấu hình dự phòng thay cho việc giao cả việc dài cho subagent.
    warm = next((r.get("warm_fallback") for r in rules()["rules"] if r["id"] == hit["rule"]), None)
    if warm and advice and not advice["cheap"]:
        hit.update(model=warm["model"], model_id=model_name(warm["model"]), effort=warm["effort"],
                   note=warm.get("note") or hit["note"])
        raise_hit(hit)  # cấu hình dự phòng cũng không được dưới mức sàn của project
        want_switch = needs_model_switch(hit["model"], now_model) and not own
        advice = switch_advice(hit["model"], usage) if want_switch else None
    if advice and advice["cheap"]:
        parts_user.append(f"/model {model_name(hit['model'])} ({advice['why']})")
    elif advice:
        cur = family(now_model) or now_model
        # Kèm effort đang dùng của phiên chính để thấy mình đang ở đâu; effort của luật thuộc về subagent bên dưới.
        keep = f"{cur} · {now_effort}" if now_effort else cur
        parts_user.append(f"giữ {keep} (đổi tốn ≈{usd(advice['cost'])} USD)")
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
    effort_cmd = None
    effort_differs = hit["effort"] and now_effort and hit["effort"] != now_effort and not own
    if effort_differs and not (advice and not advice["cheap"]) and (
            not now_model or effort_keeps_cache(now_model) or (advice and advice["cheap"])):
        parts_user.append(f"/effort {hit['effort']}")
        effort_cmd = hit["effort"]
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
    # Gợi ý đã nâng theo project mang mức trong khóa: lần nâng lên mức khác không bị lần nhắc trước của cùng luật che.
    raised = f"-{hit['model']}-{hit['effort']}" if hit.get("raised") else ""
    if not A.once(f"route-{sid}-{hit['rule']}{raised}", 3600):
        return None  # cùng một gợi ý không nhắc lại trong một giờ
    reason = ", ".join(f"'{m}'" for m in hit["matched"][:3])
    model_note = (f"model {model_effort(hit)}" + (f", test trượt thì {hit['fallback']}" if hit.get("fallback") else "")
                  if hit["model"] else "")
    context = (f"[router] Gợi ý cho việc này ({hit['rule']}, khớp {reason}{note}): " + "; ".join(parts_ctx + ([model_note] if model_note else []))
               + ". Đây chỉ là gợi ý. Nếu nên đổi model hoặc effort, nói với người dùng ở cuối câu trả lời, đừng tự đổi."
               + (f" {switch_note}" if switch_note else ""))
    user = f"🧭 router: {hit['rule']} → " + " · ".join(parts_user)
    # Cho dải của mod: model chỉ khi đổi còn rẻ, effort chỉ khi đã gợi ý /effort ở trên.
    switch = model_name(hit["model"]) if advice and advice["cheap"] else None
    return {"context": context, "user": user, "rule": hit["rule"], "switch": switch, "effort": effort_cmd}


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
    # Lệnh xem thử: đọc stack.json nhưng không ghi bản chụp đã duyệt.
    stack = stack_lib().effective(root, protected_phrases(), write=False) if root else None
    hit = suggest_for(text, A.project_profile(root) if root else None, stack)
    print(json.dumps(localize(hit, root) if hit else hit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
