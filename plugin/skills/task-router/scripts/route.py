#!/usr/bin/env python3
"""Gợi ý skill, subagent, model và effort cho một việc, bằng luật từ khóa (0 token, dưới 50 ms); lớp từ khóa không chắc
thì có thể hỏi thêm lớp model (GĐ5, plugin/lib/routemodel.py, mục model_layer của rules.json: hiện chỉ khi chấm từng
bước của kế hoạch phiên vừa duyệt, `--plan-steps`).

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
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))
import agentstack as A  # noqa: E402

RULES_PATH = HERE.parents[1] / "rules.json"
FAMILIES = ("fable", "opus", "sonnet", "haiku")
# Tin nhắn chỉ bảo làm tiếp (đã bỏ dấu): định tuyến theo việc tiếp theo trong §0.
# "commit và làm tiếp đi", "làm tiếp việc đi", "Continue from where you left off." (app gửi khi làm tiếp sau khi ngắt)
# thấy trong nhật ký router 14–15/11/2026.
CONTINUE_RE = re.compile(r"^(ok[a-z]*[ ,.!]*)?(commit( va| roi)? )?(tiep tuc|lam tiep( viec)?|tiep di|tiep theo|lam di|"
                         r"buoc tiep theo|lam buoc tiep theo|continue( from where you left off)?|go on|next|proceed|"
                         r"keep going)( di| nhe| nha| thoi| nao)?[ .!?]*$")
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


_STACK_MEMO = None  # dict trong one_pass(), None ngoài đó


@contextmanager
def one_pass():
    """Một lần chạy hook: turn_flags và hook_suggestion đọc `.agent/stack.json` một lần (effective còn ghi bản chụp).
    Ngoài khối này không nhớ gì, để file đổi giữa hai lần gọi (test, lệnh xem thử) luôn được đọc lại."""
    global _STACK_MEMO, _MODEL_MEMO
    _STACK_MEMO, _MODEL_MEMO = {}, {}
    try:
        yield
    finally:
        _STACK_MEMO = _MODEL_MEMO = None


def project_stack(root):
    """Cấu hình `.agent/stack.json` đã gộp với bản chụp đã duyệt (stackcfg.effective), hay None khi project không có."""
    if not root:
        return None
    key = str(root)
    if _STACK_MEMO is not None and key in _STACK_MEMO:
        return _STACK_MEMO[key]
    value = stack_lib().effective(Path(root), protected_phrases())
    if _STACK_MEMO is not None:
        _STACK_MEMO[key] = value
    return value


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
    return decorate(suggest(text, ignore_mask(stack)), text, profile, stack)


def ignore_mask(stack) -> tuple:
    return tuple(stack["cfg"]["ignore"]) if stack else ()


def rule_hit(rule_id: str, layer: str = "model"):
    """Gợi ý dạng suggest() cho một id luật do lớp model chọn (chưa decorate), hay None khi id lạ."""
    rule = next((r for r in rules()["rules"] if r["id"] == rule_id), None)
    if rule is None:
        return None
    return {"rule": rule["id"], "model": rule.get("model"), "model_id": model_name(rule.get("model")),
            "effort": rule.get("effort"), "agent": rule.get("agent"), "skills": list(rule.get("skills", [])),
            "note": rule.get("note", ""), "matched": [], "layer": layer}


def level_rank(hit) -> tuple:
    """(hạng model, hạng effort) để so hai gợi ý; model nặng ký hơn effort. Thiếu thì hạng thấp nhất."""
    S = stack_lib()
    return (S.MODEL_RANK.get((hit or {}).get("model"), -1), S.EFFORT_RANK.get((hit or {}).get("effort"), -1))


def candidates(text: str, mask=()) -> list:
    """[(luật, cụm khớp, điểm)] của mọi luật tự thắng được (không only_refine), điểm giảm dần; che như score()."""
    raw = folded = A.fold(text or "")
    for phrase in mask:
        folded = stack_lib().pattern(phrase).sub(" ", folded)
    protected = set((rules().get("rule_groups") or {}).get("protected") or []) if mask else set()
    out = []
    for rule in rules()["rules"]:
        if rule.get("only_refine"):
            continue
        seen_text = raw if rule["id"] in protected else folded
        hits = [p for p, pattern in rule["_patterns"] if pattern.search(seen_text)]
        if hits:
            out.append((rule, hits, sum(1 + p.count(" ") for p in hits)))
    out.sort(key=lambda c: (-c[2], c[0]["_order"]))
    return out


def uncertain(text: str, mask=(), long_words: int = 25) -> str:
    """Lớp từ khóa không chắc thì trả lý do (chuỗi rỗng nếu chắc), để chỉ khi đó mới hỏi lớp model:
    "khong-khop": không luật nào khớp (sau khi che từ bỏ qua của project);
    "sat-nut": hai luật đứng đầu bằng điểm mà khác mức (không tính cặp luật gốc và luật tinh chỉnh); chênh một điểm
    thì không tính, vì cụm dài hơn đã nói rõ loại việc (bộ 117 câu: 4 câu chênh một điểm đều đúng theo luật đứng đầu);
    "dai-mong": câu từ `long_words` chữ mà chỉ khớp một cụm một chữ."""
    best, hits = score(text, mask)
    if best is None:
        return "khong-khop"
    cands = candidates(text, mask)
    chain = {best["id"], *best["_refines"]}
    others = [c for c in cands if c[0]["id"] not in chain and best["id"] not in c[0]["_refines"]]
    top = next((c for c in cands if c[0]["id"] in chain), None)
    if top and others and top[2] <= others[0][2] and level_rank(others[0][0]) != level_rank(best):
        return "sat-nut"
    if len((text or "").split()) >= long_words and sum(1 + h.count(" ") for h in hits) <= 1:
        return "dai-mong"
    return ""


def combine(kw, model_rule):
    """Gộp gợi ý lớp từ khóa (chưa decorate) với id luật lớp model chọn: theo trọn một luật, lấy luật có mức cao hơn
    (bằng thì giữ lớp từ khóa). Lớp 1 im lặng (kể cả khi chỉ khớp từ project đã đánh dấu bỏ qua) thì dùng lớp model.
    Mức sàn của project áp sau, trong decorate(). Chốt chặn TM-126: model chỉ chọn được id trong danh sách cho phép."""
    if not model_rule or model_rule == "none":
        return kw
    mod = rule_hit(model_rule)
    if mod is None:
        return kw
    if kw is None:
        return mod
    if level_rank(mod) > level_rank(kw):
        mod["kw_rule"] = kw["rule"]
        return mod
    return kw


def decorate(hit, text: str, profile=None, stack=None):
    """Phần sau khi chọn luật của suggest_for: cấu hình rẻ hơn khi project có test, skill theo loại project, mức sàn
    của project (apply_stack, cả khi chưa có luật nào: luật project-keyword)."""
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


# ---- lớp model (GĐ5): chỉ khi lớp từ khóa không chắc; model chỉ đọc câu, nhãn hồ sơ, cụm ignore có khớp ----

_MODEL_MEMO = None  # dict trong one_pass(): câu → (gợi ý cuối, gợi ý lớp từ khóa, meta lớp model)


def model_lib():
    import routemodel  # noqa: E402 (cùng thư mục lib; chỉ nạp khi cần)
    return routemodel


def profile_labels(profile) -> list:
    """Nhãn hồ sơ (cố định, theo rules.json) cho prompt của lớp model; không đọc gì của project."""
    if not profile:
        return []
    cfg = rules()
    out = [(cfg.get("profiles") or {}).get(k, {}).get("label", k) for k in profile.get("kinds") or []]
    out += [(cfg.get("markers") or {}).get(m, {}).get("label", m) for m in profile.get("markers") or []]
    return [str(x) for x in out if isinstance(x, str)][:8]


def model_job(texts, profile, stack, cfg):
    """(khóa từng câu, việc cho worker). Từ stack.json chỉ gửi cụm `ignore` đã duyệt có khớp trong câu (TM-126)."""
    RM = model_lib()
    S = stack_lib()
    rs = rules()
    labels = profile_labels(profile)
    many = len(texts) > 1
    ignore_hits = sorted({p for t in texts for p in ignore_mask(stack) if S.contains(A.fold(t), p)})
    digest = RM.prompt_digest(rs, cfg)
    keys = [RM.cache_key(cfg, digest, t, [p for p in ignore_hits if S.contains(A.fold(t), p)], labels) for t in texts]
    job_key = keys[0] if not many else hashlib.sha1("".join(keys).encode()).hexdigest()[:24]
    job = {"key": job_key, "keys": keys, "count": len(texts), "allowed": [rid for rid, _ in RM.choices(rs, cfg)],
           "cfg": cfg, "system": RM.system_prompt(rs, cfg, many=many),
           "user": RM.user_prompt(texts[0] if not many else texts, labels, ignore_hits)}
    return keys, job


def ask_model(texts, profile=None, stack=None, data=None, start=None, spawn=True, wait=None, root=None,
              moment: str = "tin") -> list:
    """Kết quả lớp model cho từng câu: [{status, rule?, ms?, key?}]. status: ok, cache (đã có), nen (đã khởi worker,
    không chờ), qua-han, busy, khong-binary, hay lý do tắt (test, tat-bang-env, tat-trong-luat, khong-tuong-tac).
    `wait`: số giây chờ tính từ `start` (mặc định wait_s của luật); 0 thì không chờ. Không bao giờ văng lỗi."""
    texts = list(texts)
    try:
        RM = model_lib()
        cfg = RM.config(rules())
        reason = RM.disabled_reason(cfg, data if data is not None else {}, moment)
        if reason:
            return [{"status": reason} for _ in texts]
        keys, job = model_job(texts, profile, stack, cfg)
        allowed, max_age = job["allowed"], cfg["cache_days"] * 86400
        cached = [RM.read_cache(k, allowed, max_age) for k in keys]
        if all(cached):
            return [dict(c, status="cache" if c.get("status") == "ok" else c.get("status"), key=k)
                    for c, k in zip(cached, keys, strict=True)]
        if not spawn:
            return [dict(c, key=k) if c else {"status": "chua-co", "key": k} for c, k in zip(cached, keys, strict=True)]
        binary = RM.find_binary(project_root=root, cwd=(data or {}).get("cwd"))
        if not binary:
            return [{"status": "khong-binary"} for _ in texts]
        job["binary"] = binary
        started = RM.spawn(job, cfg)
        wait_s = cfg["wait_s"] if wait is None else wait
        if started in ("busy", "error") or wait_s <= 0:
            status = "nen" if started in ("spawned", "running") else started
            return [dict(c, key=k) if c else {"status": status, "key": k} for c, k in zip(cached, keys, strict=True)]
        deadline = (start or time.time()) + wait_s
        out = []
        for c, k in zip(cached, keys, strict=True):
            rec = c or RM.wait(k, deadline, allowed, max_age)
            out.append(dict(rec, key=k) if rec else {"status": "qua-han", "key": k})
        return out
    except Exception as exc:  # noqa: BLE001 (lớp phụ: lỗi thì dùng lớp từ khóa)
        A.log_event("hook-error", {"hook": "router-model", "error": repr(exc)[:300]})
        return [{"status": "loi"} for _ in texts]


def pick_final(kw, rule_id, text: str, profile=None, stack=None):
    """(gợi ý cuối, gợi ý chỉ lớp từ khóa), cả hai đã decorate. So mức SAU decorate (cấu hình rẻ khi có test, mức sàn
    của project): luật model chọn chỉ thắng khi mức cuối của nó cao hơn mức cuối của lớp từ khóa, nên lớp model không
    bao giờ hạ gợi ý (review GĐ5: so trước decorate thì `with_tests` kéo luật model xuống dưới lớp từ khóa)."""
    kw_hit = decorate(copy.deepcopy(kw) if kw else None, text, profile, stack)
    mod = rule_hit(rule_id) if rule_id and rule_id != "none" else None
    if mod is None:
        return kw_hit, kw_hit
    mod_hit = decorate(mod, text, profile, stack)
    if kw_hit is None or level_rank(mod_hit) > level_rank(kw_hit):
        if kw_hit:
            mod_hit["kw_rule"] = kw_hit["rule"]
        return mod_hit, kw_hit
    return kw_hit, kw_hit


def model_rule(meta) -> str | None:
    """Id luật dùng được từ kết quả lớp model, hay None."""
    if not meta or meta.get("status") not in ("ok", "cache"):
        return None
    return meta.get("rule") or None


def two_layer(text: str, profile=None, stack=None, data=None, start=None, spawn=True, wait=None, root=None,
              moment: str = "tin"):
    """(gợi ý cuối, gợi ý chỉ lớp từ khóa, meta lớp model hay None). Lớp từ khóa chắc thì không hỏi model. Cả hai gợi
    ý đã decorate (mức sàn của project áp sau cùng). Trong one_pass() nhớ theo câu, để cờ lượt và gợi ý chỉ hỏi một lần."""
    memo = _MODEL_MEMO if spawn else None  # bản chỉ đọc cache (spawn=False) không được che lần hỏi thật
    if memo is not None and text in memo:
        return memo[text]
    mask = ignore_mask(stack)
    kw = suggest(text, mask)
    why = uncertain(text, mask, model_lib().config(rules())["long_words"])
    meta = None
    if why:
        meta = dict(ask_model([text], profile, stack, data, start, spawn, wait, root, moment)[0], why=why)
    hit, kw_hit = pick_final(kw, model_rule(meta), text, profile, stack)
    out = (hit, kw_hit, meta)
    if memo is not None:
        memo[text] = out
    return out


def prefetch_path(session_id: str) -> Path:
    return A.state_dir() / "router-model" / "sessions" / (hashlib.sha1(session_id.encode()).hexdigest()[:16] + ".json")


def prefetch(root, data: dict) -> str:
    """Hook SessionStart: lớp từ khóa không chắc về việc tiếp theo trong §0 thì khởi worker nền (không chờ), và ghi gợi
    ý lúc mở phiên để tin đầu tiên biết kết quả nền có khác không. Trả trạng thái lớp model (để test và nhật ký)."""
    sid = data.get("session_id") or ""
    try:
        task = next_task(root) if root else ""
        if not task or not sid:
            return ""
        hit, _, meta = two_layer(task, A.project_profile(root), project_stack(root), data, spawn=True, wait=0,
                                 root=root, moment="s0")
    except Exception as exc:  # noqa: BLE001 (việc phụ của hook mở phiên)
        A.log_event("hook-error", {"hook": "router-prefetch", "error": repr(exc)[:300]})
        return "loi"
    meta = meta or {}
    status = meta.get("status") or "chac"
    if status == "nen" and meta.get("key"):
        path = prefetch_path(sid)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            A.prune(path.parent, 2)
            A.write_json_atomic(path, {"session": sid, "key": meta["key"], "rule": (hit or {}).get("rule"),
                                       "ts": time.time()})
        except OSError:
            pass
    return status


def prefetch_note(data: dict) -> str:
    """Tin đầu sau khi mở phiên: kết quả nền của lớp model cho việc tiếp theo trong §0 đã có và khác gợi ý lúc mở phiên
    thì trả một câu cho model (một lần); chưa có thì giữ để tin sau xem (tối đa 30 phút). Không bao giờ văng lỗi."""
    try:
        sid = data.get("session_id") or ""
        if not sid:
            return ""
        path = prefetch_path(sid)
        rec = A.read_json(path, None)
        if not isinstance(rec, dict) or rec.get("session") != sid:
            return ""
        root = A.project_root(data["cwd"]) if data.get("cwd") else None
        task = next_task(root) if root else ""
        hit, _, meta = two_layer(task, A.project_profile(root), project_stack(root), spawn=False, wait=0,
                                 root=root, moment="s0") if task else (None, None, None)
        if not meta or meta.get("key") != rec.get("key") or time.time() - float(rec.get("ts") or 0) > 1800:
            path.unlink(missing_ok=True)  # §0 đã đổi hay quá lâu: bỏ
            return ""
        if meta.get("status") not in ("ok", "cache", "none", "unparsed", "timeout", "error"):
            return ""  # worker chưa xong: để tin sau
        path.unlink(missing_ok=True)
        if not hit or hit.get("rule") == rec.get("rule"):
            return ""
        was = rec.get("rule") or "không gợi ý"
        return (f"[router] Lớp model vừa chấm việc tiếp theo trong §0 («{A.clip(task, 80)}»): {hit['rule']} → "
                f"{describe(hit)} (lúc mở phiên: {was}). Đây chỉ là gợi ý; model của phiên có quyền cuối.")
    except Exception as exc:  # noqa: BLE001
        A.log_event("hook-error", {"hook": "router-prefetch-note", "error": repr(exc)[:300]})
        return ""


# ---- chấm từng bước của kế hoạch phiên vừa duyệt (hook plan_steps.py gọi qua `--plan-steps`) ----

# Mức khai: "opus·high", "Opus 5.5 · high", "claude-sonnet-5-5 low" (review GĐ5: 11/78 chỗ trong kế hoạch thật có số
# phiên bản và từng bị bỏ sót).
LEVEL_RE = re.compile(r"\b(?:claude-)?(haiku|sonnet|opus|fable)(?:[ -]?\d+(?:[.-]\d+)*)?\s*[·•.,\-/ ]?\s*"
                      r"(low|medium|high|xhigh|max)\b", re.I)
STEP_ITEM_RE = re.compile(r"^\s*(\d+)[.)]\s+(\S.*)$")


def plan_step_rows(plan: str) -> list:
    """[(số bước, chữ của việc, mức khai (model, effort) hay None)] của mục `## Các bước` (bảng hay danh sách đánh số)."""
    lines, level, fenced = [], 0, False
    for line in (plan or "").splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            continue
        m = None if fenced else A.HEADING_RE.match(line)
        if m:
            if level and len(m.group(1)) <= level:
                break  # hết mục: đề mục cùng cấp hay cao hơn (đề mục con như "### Giai đoạn 1" vẫn thuộc mục)
            if not level and "cac buoc" in A.fold(m.group(2)):
                level = len(m.group(1))
            continue
        if level and not fenced:
            lines.append(line)
    rows, header = [], None
    for line in lines:
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if header is None:
                header = [A.fold(c) for c in cells]
                continue
            col_text = next((i for i, h in enumerate(header) if "viec" in h), 1 if len(cells) > 1 else 0)
            col_lvl = next((i for i, h in enumerate(header) if "model" in h or "effort" in h), None)
            text = cells[col_text] if col_text < len(cells) else ""
            lv_cell = cells[col_lvl] if col_lvl is not None and col_lvl < len(cells) else line
            m = LEVEL_RE.search(lv_cell)
            rows.append((cells[0] if cells and cells[0] != text else str(len(rows) + 1), text.replace("**", ""),
                         (m.group(1).lower(), m.group(2).lower()) if m else None))
        else:
            m = STEP_ITEM_RE.match(line)
            if m:
                lv = LEVEL_RE.search(m.group(2))
                rows.append((m.group(1), m.group(2).replace("**", ""),
                             (lv.group(1).lower(), lv.group(2).lower()) if lv else None))
    return [r for r in rows if len(r[1].split()) >= 3][:30]


def score_plan(plan: str, cwd, data: dict | None = None, start: float | None = None) -> str:
    """Câu cho model của phiên về các bước khai mức dưới sàn của project hay bước bảo mật khai dưới gợi ý; chuỗi rỗng
    khi không có gì cần nói. Lớp model gộp một lần cho mọi bước không chắc, chờ tới `plan_wait_s`."""
    rows = plan_step_rows(plan)
    if not rows:
        return ""
    root = A.project_root(cwd) if cwd else None
    stack = project_stack(root) if root else None
    profile = A.project_profile(root) if root else None
    mask = ignore_mask(stack)
    cfg = model_lib().config(rules())
    kws = [suggest(text, mask) for _, text, _ in rows]
    unsure = [i for i, (_, text, _) in enumerate(rows) if uncertain(text, mask, cfg["long_words"])]
    data = dict(data or {}, cwd=str(cwd)) if cwd else (data or {})
    metas = dict(zip(unsure, ask_model([rows[i][1] for i in unsure], profile, stack, data, start,
                                       wait=cfg["plan_wait_s"], root=root, moment="buoc"), strict=True)) if unsure else {}
    if unsure:
        statuses = {}
        for m in metas.values():
            statuses[m.get("status")] = statuses.get(m.get("status"), 0) + 1
        A.log_event("plan-steps-model", {"steps": len(rows), "unsure": len(unsure), "status": statuses})
    S = stack_lib()
    protected = set((rules().get("rule_groups") or {}).get("protected") or [])
    notes = []
    for i, (num, text, declared) in enumerate(rows):
        hit, kw_hit = pick_final(kws[i], model_rule(metas.get(i)), text, profile, stack)
        if not hit or not declared or declared[0] not in S.MODEL_RANK or declared[1] not in S.EFFORT_RANK:
            continue
        # Bước là việc bảo mật khi MỘT trong hai lớp nhận ra (model nâng sang luật khác nhóm không được che mất)
        secure = [h for h in (hit, kw_hit) if h and h.get("rule") in protected]
        want = max(((h.get("model"), h.get("effort")) for h in (hit, kw_hit) if h),
                   key=lambda lv: (S.MODEL_RANK.get(lv[0], -1), S.EFFORT_RANK.get(lv[1], -1)))
        floor = tuple(hit["floor"]) if hit.get("floor") else None
        if floor and not S.at_least(declared, floor):
            notes.append(f"bước {num} khai {declared[0]} · {declared[1]}, dưới mức sàn {floor[0]} · {floor[1]} của project"
                         + (f" (khớp {', '.join(repr(m) for m in hit['matched'][:2])})" if hit.get("matched") else ""))
        elif secure and want[0] in S.MODEL_RANK and want[1] in S.EFFORT_RANK and not S.at_least(declared, want):
            notes.append(f"bước {num} là việc bảo mật ({secure[-1]['rule']}) mà khai {declared[0]} · {declared[1]}, "
                         f"router gợi ý {model_name(want[0])} · {want[1]}")
    if not notes:
        return ""
    return ("[router] Chấm các bước của kế hoạch vừa duyệt: " + "; ".join(notes[:6]) + ". Model của phiên có quyền "
            "cuối: nếu giữ mức đã khai, nói một dòng lý do với người dùng trước khi làm bước đó; nếu nâng, bước cần "
            "model khác thì giao subagent (không đổi model giữa phiên).")


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


def bundle_missing(skill: str, plugin: str, root):
    """Mục "missing" cho skill của plugin thuộc một bộ ngoài lõi (plugin/lib/bundles.py, H5): lệnh bật bộ thay cho
    lệnh cài; None nếu plugin thuộc lõi hay không thuộc bộ nào."""
    import bundles  # noqa: E402 (cùng thư mục lib với agentstack)
    names = bundles.bundles_of_plugin(plugin)
    if not names:
        return None
    return {"skill": skill, "bundle": names[0],
            "install": bundles.profile_cmd(Path(root) if root else None, "on", names[0])}


def hidden_skill_notes(skills) -> list:
    """Skill agent-stack ngoài lõi không nạp sẵn (`disable-model-invocation`, H5): công cụ Skill không gọi được, nên
    nêu đường dẫn SKILL.md để đọc thẳng."""
    import bundles  # noqa: E402 (cùng thư mục lib với agentstack)
    notes = []
    for name in skills:
        bundle = bundles.bundle_of_skill(name)
        if bundle and bundle != bundles.CORE:
            notes.append(f"{name} không nạp sẵn (bộ {bundle}): đọc thẳng `{bundles.skill_md(name)}` rồi làm theo")
    return notes


def localize(hit: dict, root) -> dict:
    """Bỏ khỏi gợi ý các skill của plugin chưa bật cho project (hay cho người dùng, khi không có project), thay bằng
    skill dự phòng (mục skill_fallbacks của rules.json), và ghi lệnh cài vào hit["missing"]. Sửa tại chỗ và trả lại hit."""
    import bundles  # noqa: E402 (cùng thư mục lib với agentstack)
    # Claude Code đọc settings.local.json ở cả cwd lẫn gốc git (đo 20/11): bật ở một trong hai là bật. profile.py ghi
    # ở gốc git (bundles.settings_root), file kế hoạch có thể nằm ở thư mục con.
    roots = list(dict.fromkeys((bundles.settings_root(root), Path(root)) if root else (None,)))
    root = roots[0]
    keep, missing = [], []
    for name in hit.get("skills") or []:
        plugin, item = skill_plugin(name)
        if plugin is None or enabled_in(roots, plugin):
            keep.append(name)
            continue
        missing.append(bundle_missing(name, plugin, root) or {"skill": name, "install": install_hint(plugin, item)})
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


def enabled_in(roots: list, plugin: str) -> bool:
    """Như plugin_enabled nhưng xét nhiều gốc theo thứ tự đè: user, rồi từng gốc (gốc git trước, cwd sau), mỗi gốc
    project rồi local; giá trị bool ghi rõ sau cùng thắng (review fable·high 20/11: `false` ở gốc git phải đè `true`
    của user dù cwd là thư mục con)."""
    state = False
    paths = [claude_config_dir() / "settings.json"]
    for root in roots:
        if root:
            paths += [Path(root) / ".claude" / "settings.json", Path(root) / ".claude" / "settings.local.json"]
    for path in paths:
        data = A.read_json(path, {})
        table = data.get("enabledPlugins") if isinstance(data, dict) else None
        value = table.get(plugin) if isinstance(table, dict) else None
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


def answer_line(hit) -> str:
    """Dòng trả lời của skill task-router, đúng định dạng mục "Kết quả trả về" của SKILL.md; không luật nào khớp thì
    trỏ về bảng mặc định (để model chọn theo bảng thay vì đoán)."""
    if not hit:
        return "Không khớp luật nào: chọn theo \"Bảng mặc định cho dòng ➡️\" trong SKILL.md."
    rule = next((r for r in rules()["rules"] if r["id"] == hit.get("rule")), {})
    why = " ".join((rule.get("desc") or hit.get("rule") or "").split(":")[0].split()[:15])  # mệnh đề đầu, không cụt
    line = (f"➡️ Model: {model_name(hit.get('model'))} · Effort: {hit.get('effort') or 'giữ nguyên'} · "
            f"Subagent: {hit.get('agent') or 'không'} · Skill: {', '.join(hit.get('skills') or []) or 'không'} · "
            f"Lý do: {why}")
    if hit.get("fallback"):
        line += f"\nTest trượt thì lên {hit['fallback']}."
    if hit.get("note"):
        line += f"\nGhi chú: {hit['note']}"
    for miss in hit.get("missing") or []:  # skill chưa bật đã được thay bằng skill dự phòng (localize)
        line += f"\nChưa bật {miss.get('skill')}: {miss.get('install') or ''}".rstrip(": ")
    return line


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
    """Câu gợi ý plan mode cho dòng 🧭 (user) và bối cảnh (context)."""
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
    # Lớp model chỉ đọc kết quả đã có (lần mở phiên trước cùng việc); khởi worker là việc của prefetch() trong hook.
    hit = two_layer(task, profile, stack, spawn=False, wait=0, root=root, moment="s0")[0] if task else None
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
    Không phụ thuộc việc gợi ý có bị ẩn vì đã nhắc trong giờ qua hay không. Chỉ so chữ của người dùng (routable_text).
    Có `.agent/stack.json` thì che từ khóa bỏ qua và nâng theo project: câu chỉ khớp từ khóa riêng hay từ của vùng lõi
    (luật project-keyword, mức sàn từ sonnet · medium) cũng cần tiêu chí."""
    prompt = (prompt or "").strip()
    if not prompt or prompt[0] in "/!#" or A.is_automated_prompt(prompt):
        return {}
    prompt = A.routable_text(prompt)
    if not prompt:
        return {}
    root = A.project_root(cwd) if cwd else None
    if is_progress_question(prompt):
        return {"progress": True}
    continuing = bool(root and CONTINUE_RE.match(A.fold(prompt)))
    text = (next_task(root) or prompt) if continuing else prompt
    memo = _MODEL_MEMO.get(text) if _MODEL_MEMO is not None else None
    if memo is not None:  # hook_suggestion đã chấm câu này (cả lớp model): dùng lại, không hỏi model lần hai
        hits = [h for h in memo[:2] if h]  # cờ của cả gợi ý cuối lẫn lớp từ khóa: lớp model không làm mất cờ
    else:
        hits = [suggest_for(text, None, project_stack(root)) if root else suggest(text)]
    flags = {}
    for hit in (h for h in hits if h):
        if hit["rule"] == "feature-boundary":
            flags["threat_model"] = True
        if hit["rule"] in CRITERIA_RULES or hit["rule"] == "project-keyword":
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
    200 ký tự. Các trường rule, model, effort, matched là của lớp từ khóa (learn dùng, nghĩa không đổi); `final` là gợi ý
    sau khi gộp lớp model khi khác lớp từ khóa, `model` là kết quả lớp model (GĐ5). Không bao giờ văng lỗi."""
    try:
        hit = seen.get("hit") or {}
        root = seen.get("root")
        final = seen.get("final") or {}
        meta = seen.get("model")
        extra = {}
        if final and final.get("rule") != hit.get("rule"):
            extra["final"] = {"rule": final.get("rule"), "model": final.get("model"), "effort": final.get("effort")}
        if meta:
            extra["model_layer"] = {k: meta.get(k) for k in ("status", "rule", "ms", "why", "key") if meta.get(k)}
        A.log_event("route", {**extra,
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
    prompt = A.routable_text(prompt)  # chỉ chữ của người dùng: bỏ khối nhắc, thẻ <ide_*>, phần dán, khối code
    if not prompt:
        return None
    root = A.project_root(data["cwd"]) if data.get("cwd") else None
    text, note = prompt, ""
    if root and CONTINUE_RE.match(A.fold(prompt)):
        task = next_task(root)
        if task:
            text, note = task, f", theo việc tiếp theo trong §0: «{A.clip(task, 80)}»"
    seen.update(root=root, text=text)
    if not note and len(prompt.split()) < rules().get("min_words", 4):
        return None
    # Hai lớp: lớp từ khóa không chắc thì hỏi lớp model, chờ tới mốc lúc hook bắt đầu + wait_s (prompt_submit đặt
    # _hook_t0); quá hạn hay tắt thì dùng lớp từ khóa.
    # Tin "làm tiếp" (định tuyến theo §0) chờ tới continue_wait_s: kết quả nền lúc mở phiên thường đã có, hay worker
    # đang chạy cho đúng việc đó. Tin khác chờ tới wait_s (0: chỉ chạy nền, kết quả vào nhật ký).
    wait = model_lib().config(rules())["continue_wait_s"] if note else None
    hit, kw_hit, meta = two_layer(text, A.project_profile(root) if root else None, project_stack(root) if root else None,
                                  data, data.get("_hook_t0"), wait=wait, root=root, moment="s0" if note else "tin")
    seen.update(hit=kw_hit, final=hit, model=meta)
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
                       f"mạnh hơn mới làm đúng thì vẫn nên đổi (chất lượng trước chi phí). Dòng ➡️ không thêm phần Model (`Model: giữ {cur}` là mặc định, không cần ghi).")
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
        parts_ctx += hidden_skill_notes(hit["skills"])
    if hit.get("missing"):
        parts_ctx.append("chưa bật cho project này: " + "; ".join(f"{m['skill']} (`{m['install']}`)" for m in hit["missing"])
                         + ("; lệnh profile.py on <bộ> chỉ bật plugin đã cài (cấu hình local), tự chạy được khi việc "
                            "cần, plugin nạp đủ sau khi người dùng gõ /reload-plugins"
                            if all(m.get("bundle") for m in hit["missing"]) else
                            "; chỉ đề xuất cài với người dùng, đừng tự cài"))
    if hit.get("note"):
        parts_ctx.append(hit["note"])
    if not parts_user:
        return None  # model, effort đã khớp và không có skill/agent để gợi ý
    # Gợi ý đã nâng theo project mang mức trong khóa: lần nâng lên mức khác không bị lần nhắc trước của cùng luật che.
    raised = f"-{hit['model']}-{hit['effort']}" if hit.get("raised") else ""
    if not A.once(f"route-{sid}-{hit['rule']}{raised}", 3600):
        return None  # cùng một gợi ý không nhắc lại trong một giờ
    reason = ", ".join(f"'{m}'" for m in hit["matched"][:3])
    src = f"khớp {reason}"
    if hit.get("layer") == "model":  # gợi ý do lớp model chọn (GĐ5)
        src = ("lớp model chọn, lớp từ khóa không chắc" if not reason else
               f"lớp model chọn mức cao hơn lớp từ khóa ({hit.get('kw_rule')}), khớp {reason}")
    model_note = (f"model {model_effort(hit)}" + (f", test trượt thì {hit['fallback']}" if hit.get("fallback") else "")
                  if hit["model"] else "")
    context = (f"[router] Gợi ý cho việc này ({hit['rule']}, {src}{note}): " + "; ".join(parts_ctx + ([model_note] if model_note else []))
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
    ap.add_argument("--plan-steps", action="store_true",
                    help="đọc kế hoạch phiên từ stdin, in JSON {context} chấm từng bước (hook plan_steps.py gọi)")
    ap.add_argument("--cwd", help="thư mục làm việc của phiên (với --plan-steps)")
    ap.add_argument("--line", action="store_true", help="in dòng ➡️ trả lời thay cho JSON (skill task-router dùng)")
    args = ap.parse_args(argv)
    if args.plan_steps:
        start = time.time()
        context = score_plan(sys.stdin.read()[:20000], args.cwd, {}, start)
        print(json.dumps({"context": context}, ensure_ascii=False))
        return 0
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
    hit = localize(hit, root) if hit else hit
    print(answer_line(hit) if args.line else json.dumps(hit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
