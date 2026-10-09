#!/usr/bin/env python3
"""Hook Stop: sau mỗi lượt, ghi .agent/LAST-TURN.md (yêu cầu, câu trả lời cuối đã che khóa, việc tiếp theo,
file đổi) để phiên mới làm tiếp được; nếu lượt có đổi file mà §0 chưa đổi thì chặn một lần để Claude cập nhật §0.

Lúc bắt đầu lượt và dấu §0 lúc đó do hook UserPromptSubmit ghi (state/turns/). Lần Stop thứ hai của cùng lượt
(stop_hook_active) không chặn nữa, và giữ câu trả lời của lần đầu thay cho câu báo "đã cập nhật §0".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402


def block_reason(changed, plan_rel) -> str:
    names = ", ".join(changed[:5]) + (" …" if len(changed) > 5 else "")
    return (f"agent-stack (hook Stop): lượt này đã đổi {len(changed)} file ({names}) nhưng mục §0 của `{plan_rel}` "
            "chưa đổi. Cập nhật §0 cho khớp việc vừa làm: Xong (kèm bằng chứng), Đang dở, Việc tiếp theo, Quyết định "
            "còn treo; ngắn gọn, giữ định dạng, không chép lại cả câu trả lời. Không làm thêm việc khác, rồi kết thúc "
            "lượt bằng một câu ngắn. Nếu các file này không do lượt này đổi (ví dụ phiên khác đang làm cùng repo) "
            "hoặc thay đổi quá nhỏ để ghi, trả lời đúng một câu nói vậy và không sửa gì.")


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

    should_block = bool(changed) and not active and turn is not None and digest_now is not None and not plan_updated

    if digest_now is None:
        plan_status = "project không có mục §0"
    elif plan_updated:
        plan_status = "đã cập nhật trong lượt này"
    elif should_block:
        plan_status = "chưa cập nhật; hook đã nhờ Claude cập nhật ngay sau lượt này"
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
                         "blocked": should_block})

    if should_block:
        A.emit_block(block_reason(changed, plan_rel),
                     f"📝 Lượt này đổi {len(changed)} file mà §0 chưa đổi: nhờ Claude cập nhật §0 trước khi xong.")


if __name__ == "__main__":
    A.run_hook(main)
