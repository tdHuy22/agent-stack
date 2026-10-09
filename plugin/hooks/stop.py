#!/usr/bin/env python3
"""Hook Stop: sau mỗi lượt, ghi .agent/LAST-TURN.md (yêu cầu, câu trả lời cuối đã che khóa, việc tiếp theo,
file đổi) để phiên mới làm tiếp được. Chặn một lần để Claude làm nốt trước khi xong:
- lượt đổi code có mức rủi ro từ vừa trở lên (risk.py của chot-viec) mà chưa chạy chot-viec: chạy chot-viec (nó lo
  luôn threat model khi đụng ranh giới tin cậy, review theo mức rủi ro và §0);
- còn lại, lượt có đổi file mà §0 chưa đổi: cập nhật §0.

Lúc bắt đầu lượt và dấu §0 lúc đó do hook UserPromptSubmit ghi (state/turns/). Lần Stop thứ hai của cùng lượt
(stop_hook_active) không chặn nữa, và giữ câu trả lời của lần đầu thay cho câu báo "đã cập nhật §0".
"""
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "lib"))
import agentstack as A  # noqa: E402


def block_reason(changed, plan_rel) -> str:
    names = ", ".join(changed[:5]) + (" …" if len(changed) > 5 else "")
    return (f"agent-stack (hook Stop): lượt này đã đổi {len(changed)} file ({names}) nhưng mục §0 của `{plan_rel}` "
            "chưa đổi. Cập nhật §0 cho khớp việc vừa làm: Xong (kèm bằng chứng), Đang dở, Việc tiếp theo, Quyết định "
            "còn treo; ngắn gọn, giữ định dạng, không chép lại cả câu trả lời. Không làm thêm việc khác, rồi kết thúc "
            "lượt bằng một câu ngắn. Nếu các file này không do lượt này đổi (ví dụ phiên khác đang làm cùng repo) "
            "hoặc thay đổi quá nhỏ để ghi, trả lời đúng một câu nói vậy và không sửa gì.")


def chot_viec_gate(root: Path, turn: dict, changed: list):
    """Kết quả chấm rủi ro (dict của risk.assess) cho phần lượt này đổi, nếu cần chạy chot-viec; không thì None.
    Không cần khi lượt không đổi file, khi chot-viec (risk.py) đã chạy trong lượt, hoặc khi mức rủi ro thấp."""
    if not changed or A.chot_viec_ran_since(root, turn["ts"]):
        return None
    sys.path.insert(0, str(PLUGIN / "skills" / "chot-viec" / "scripts"))
    import risk  # noqa: E402
    if foreign_filters(root):
        return None  # git diff sẽ chạy clean filter do repo khai báo: không tự chạy lệnh của repo lạ
    try:
        changes = risk.collect(root, turn.get("head") or None)
    except (risk.NotARepo, risk.GitError):
        return None
    # Chỉ chấm file lượt này đổi; git in đường dẫn tính từ gốc repo nên so cả hai dạng. File đã qua chốt việc ở
    # lượt trước (dấu của risk.py) chỉ chấm dòng mới, không tính lại luật theo đường dẫn: sửa nhiều lượt rồi mới
    # commit thì không bị ép chốt lại toàn bộ diff cũ.
    top = (A.git_out(root, "rev-parse", "--show-prefix") or "").strip()
    mine = set(changed) | {top + c for c in changed}
    seen = (A.chot_viec_mark(root).get("files") or {})
    picked, reviewed = [], set()
    for c in changes:
        if c["path"] not in mine:
            continue
        known = seen.get(c["path"])
        if isinstance(known, list):
            known = set(known)
            fresh = [line for line in (c.get("text") or "").splitlines()
                     if line.strip() and risk.line_hashes(line)[0] not in known]
            if not fresh:
                continue
            c = dict(c, text="\n".join(fresh), added=len(fresh), deleted=0)
            reviewed.add(c["path"])
        picked.append(c)
    result = risk.assess(picked, frozenset(reviewed))
    return None if result["empty"] or result["level"] == "thap" else result


def foreign_filters(root: Path) -> bool:
    """Repo tự khai báo clean filter (cấu hình local, kể cả file include): git diff sẽ chạy lệnh đó, và không có cờ
    tắt. Filter toàn cục của người dùng (như git-lfs) là đáng tin."""
    out = A.git_out(root, "config", "--show-scope", "--get-regexp", r"^filter\..*\.(clean|process)$") or ""
    return any(line.split("\t", 1)[0] in ("local", "worktree", "command") for line in out.splitlines())


def gate_reason(result: dict, plan_rel: str) -> str:
    level = {"vua": "vừa", "cao": "cao"}[result["level"]]
    why = "; ".join(result["reasons"][:3])
    return (f"agent-stack (hook Stop): lượt này đổi code có mức rủi ro {level} ({why}) mà chưa chạy chot-viec. "
            "Chạy skill chot-viec ngay cho phần việc của lượt này: nó tự chạy mo-hinh-de-doa nếu đụng ranh giới tin "
            f"cậy, review theo mức rủi ro, và cập nhật §0 của `{plan_rel}`. Rồi kết thúc lượt bằng báo cáo ngắn của "
            "chot-viec. Nếu các file này không do lượt này đổi (ví dụ phiên khác đang làm cùng repo), trả lời đúng "
            "một câu nói vậy và không làm gì thêm.")


def main():
    data = A.read_hook_input()
    sid = data.get("session_id", "")
    if not sid or not data.get("cwd"):
        return  # đầu vào thiếu hay hỏng: không đoán thư mục, vì hook sẽ ghi file vào đó
    active = bool(data.get("stop_hook_active"))
    root = A.project_root(data.get("cwd"))
    if not A.is_project(root):
        return
    turn = A.load_turn(sid)
    if turn and turn.get("root") != str(root):
        turn = None  # lượt bắt đầu ở thư mục khác: không so được
    changed = A.changed_since(root, turn["ts"]) if turn else []
    digest_now = A.section0_digest(root)
    plan_updated = bool(turn) and digest_now is not None and digest_now != turn.get("plan_digest")
    found = A.read_plan(root)
    plan_rel = str(found[0].relative_to(root)) if found and str(found[0]).startswith(str(root)) else "PLAN.md"

    gate = None
    if changed and not active and turn is not None:
        try:
            gate = chot_viec_gate(root, turn, changed)
        except Exception as exc:  # noqa: BLE001 (chấm rủi ro lỗi thì không chặn, chỉ ghi log)
            A.log_event("hook-error", {"hook": "chot_viec_gate", "error": repr(exc)[:300]})
    plan_block = bool(changed) and not active and turn is not None and digest_now is not None and not plan_updated
    should_block = plan_block or gate is not None

    if digest_now is None:
        plan_status = "project không có mục §0"
    elif plan_updated:
        plan_status = "đã cập nhật trong lượt này"
    elif should_block:
        plan_status = "chưa cập nhật; hook đã nhờ Claude cập nhật ngay sau lượt này"
        if gate is not None:
            plan_status += " (cùng lúc chạy chot-viec)"
    elif changed:
        plan_status = "chưa cập nhật dù lượt có đổi file"
    else:
        plan_status = "không đổi (lượt không đổi file)"

    # Lần Stop thứ hai của cùng lượt: giữ câu trả lời thật của lần đầu.
    message = data.get("last_assistant_message")
    if active and turn and isinstance(turn.get("answer"), str):
        answer, next_step = turn["answer"], turn.get("next")
    else:
        answer = A.strip_next(message) if isinstance(message, str) else ""
        next_step = A.extract_next(message)
        if turn:
            turn.update(answer=A.redact_secrets(answer)[:A.LAST_TURN_ANSWER_CHARS + 200], next=next_step)
            A.save_turn(sid, turn)
    request = A.load_last_request(sid) or {}
    prompt = request.get("prompt", "")
    if request.get("earlier") and len(prompt) < A.LAST_REQUEST_FULL:
        prompt = f"{prompt} (trước đó: {request['earlier']['prompt']})"
    git = A.git_summary(root)
    A.write_last_turn(root, sid, prompt, answer, next_step, changed, len(git.get("dirty") or []),
                      git.get("branch"), plan_status)
    A.log_event("stop", {"session": sid, "cwd": str(root), "changed": len(changed), "plan_updated": plan_updated,
                         "blocked": should_block, "chot_viec": gate["level"] if gate else None})

    if gate is not None:
        A.emit_block(gate_reason(gate, plan_rel),
                     f"🔒 Lượt này đổi code mức rủi ro {'cao' if gate['level'] == 'cao' else 'vừa'} mà chưa chốt việc: "
                     "Claude chạy chot-viec trước khi xong.")
    elif should_block:
        A.emit_block(block_reason(changed, plan_rel),
                     f"📝 Lượt này đổi {len(changed)} file mà §0 chưa đổi: nhờ Claude cập nhật §0 trước khi xong.")


if __name__ == "__main__":
    A.run_hook(main)
