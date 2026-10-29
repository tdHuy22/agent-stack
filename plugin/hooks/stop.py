#!/usr/bin/env python3
"""Hook Stop: sau mỗi lượt, ghi lượt cuối (yêu cầu, câu trả lời cuối đã che khóa, việc tiếp theo, file đổi) vào
.agent/LAST-TURN.md của thư mục làm việc, kể cả thư mục không phải project (thư mục chung thì vào state/last-turn/),
để phiên mới làm tiếp được. Ghi trước các bước chậm. Chặn một lần để Claude làm nốt trước khi xong:
- lượt đổi code có mức rủi ro từ vừa trở lên (risk.py của chot-viec) mà chưa chạy chot-viec: chạy chot-viec (nó lo
  luôn threat model khi đụng ranh giới tin cậy, review theo mức rủi ro và §0);
- còn lại, lượt có đổi file mà §0 chưa đổi: cập nhật §0;
- §0 vừa được cập nhật trong lượt mà dài quá ngưỡng, và `state.py trim` rút được nó: chạy trim (chạy xong thì §0 gọn
  nên lần sau không nhắc lại);
- lượt trả lời câu hỏi tiến độ trong project có kế hoạch mà người dùng chưa thấy cây: hiện cây để người dùng chọn việc tiếp theo (gộp
  vào lời nhắc ở trên nếu có). Chạy plan_tree.py để tự đọc không tính: phải có lời gọi show_widget với HTML của cây,
  hay cây chữ trong câu trả lời cuối khi phiên không có công cụ widget.

Lúc bắt đầu lượt và dấu §0 lúc đó do hook UserPromptSubmit ghi (state/turns/). Lần Stop thứ hai của cùng lượt
(stop_hook_active) không chặn nữa, và giữ câu trả lời của lần đầu thay cho câu báo "đã cập nhật §0".
"""
import os
import re
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "lib"))
import agentstack as A  # noqa: E402


def trim_hint(advice) -> str:
    """Nhắc chạy trim khi §0 dài và trim rút được nó (A.trim_advice); trim không giúp được thì không nhắc ở đây, kẻo lượt
    nào cũng nhắc mà §0 không đổi (tien-do và SessionStart đã báo người dùng)."""
    if not advice or not advice[1]:
        return ""
    return f" Sửa xong thì làm theo: {advice[0]}."


def trim_alone(advice) -> str:
    return (f"agent-stack (hook Stop): §0 vừa được cập nhật trong lượt này. {advice[0]}. Chỉ làm việc đó (không sửa tay "
            "§0), rồi kết thúc lượt bằng một câu ngắn.")


def current_trim_advice(root: Path):
    """A.trim_advice trên đúng file `state.py trim` sẽ sửa (không phải HANDOFF.md); lỗi thì None."""
    try:
        target = A.trim_target(root)
        return A.trim_advice(target[1]) if target else None
    except Exception:  # noqa: BLE001
        return None


def block_reason(changed, plan_rel, advice=None) -> str:
    names = ", ".join(changed[:5]) + (" …" if len(changed) > 5 else "")
    return (f"agent-stack (hook Stop): lượt này đã đổi {len(changed)} file ({names}) nhưng mục §0 của `{plan_rel}` "
            "chưa đổi. Cập nhật §0 cho khớp việc vừa làm: Xong (kèm bằng chứng), Đang dở, Việc tiếp theo, Quyết định "
            "còn treo; ngắn gọn (mỗi mục Xong vài dòng, chi tiết để ở commit), giữ định dạng, không chép lại cả câu "
            f"trả lời.{trim_hint(advice)} Không làm thêm việc khác, rồi kết thúc "
            "lượt bằng một câu ngắn. Nếu các file này không do lượt này đổi (ví dụ phiên khác đang làm cùng repo) "
            "hoặc thay đổi quá nhỏ để ghi, trả lời đúng một câu nói vậy và không sửa gì.")


TREE_WIDGET_MARK = "data-plan-tree"  # plan_tree.py --widget gắn vào thẻ gốc của cây
TREE_TEXT_RE = re.compile(r"[├└]─ ")  # nét cây của plan_tree.py --text
WIDGET_TOOL = "show_widget"  # đuôi tên công cụ vẽ widget (mcp__visualize__show_widget và bản deferred)
TREE_HOW = ("chạy `python3 ~/Documents/Claude/agent-stack/plugin/skills/tien-do/scripts/plan_tree.py --widget` rồi "
            "đưa nguyên kết quả vào công cụ vẽ widget nếu có (không có thì chạy với `--text` và in trong khối code), "
            "rồi kết thúc lượt bằng dòng ➡️")
# Chỉ nhắc cây khi người dùng hỏi tiến độ (29/10/2026). Không ép sau mỗi việc xong hay ở lượt đầu phiên: mỗi lần là
# một lượt thêm, ≈5 KB HTML model viết ra và hướng dẫn widget ≈12K token nếu chưa nạp, mà dòng ➡️ đã nêu việc tiếp
# theo; phiên do phiên khác giao việc còn tốn thêm một lượt chỉ để nói nhắc không hợp.
TREE_WHY = {"progress": "trả lời câu hỏi về tiến độ hay việc tiếp theo"}
TREE_SHORT = {"progress": "trả lời câu hỏi tiến độ"}


def join_why(reasons, table) -> str:
    return ", ".join(table[r] for r in reasons)


def tree_alone(reasons) -> str:
    return (f"agent-stack (hook Stop): lượt này {join_why(reasons, TREE_WHY)} mà người dùng chưa thấy cây kế hoạch "
            f"(tự chạy script, hay in cây chữ khi phiên có công cụ widget, không tính). Hiện cây: {TREE_HOW}. "
            "Không làm thêm việc khác. Nhắc này sai thì trả lời đúng một câu nói vậy.")


def tree_after(reasons) -> str:
    return (f" Lượt này cũng {join_why(reasons, TREE_WHY)}: làm xong phần trên thì, thay cho câu kết ngắn, hiện cây "
            f"kế hoạch: {TREE_HOW}.")


def tree_due(root: Path, turn, data: dict) -> list:
    """Lý do lượt này phải hiện cây kế hoạch (["progress"]) mà người dùng chưa thấy cây; rỗng nếu không cần. Chỉ xét
    project có file kế hoạch."""
    start = (turn or {}).get("plan_done")
    if not isinstance(start, dict) or not isinstance(start.get("count"), int):
        return []
    now = A.plan_done_count(root)
    if not now:
        return []
    reasons = ["progress"] if turn.get("progress") is True else []
    # /cay in cây dạng chữ (cloud, nơi pane không hiện) trong lượt: người dùng đã thấy cây.
    seen = A.tree_shown_at(data.get("session_id"))
    if seen is not None and seen >= turn["ts"]:
        return []
    if not reasons or tree_shown(turn, data):
        return []
    return reasons


def tree_shown(turn: dict, data: dict) -> bool:
    """Người dùng đã thấy cây trong lượt: lời gọi show_widget với HTML của cây, hay cây chữ trong câu trả lời cuối
    khi phiên không có công cụ widget (luật chung: có widget thì vẽ widget). Phiên có mod giao diện (ui.tsx đặt
    AGENT_STACK_UI=1, chỉ ở phiên có nơi vẽ) thì cây đã nằm sẵn ở pane Kế hoạch."""
    if os.environ.get("AGENT_STACK_UI") == "1":
        return True
    transcript = data.get("transcript_path")
    if A.tool_used_since(transcript, turn["ts"], TREE_WIDGET_MARK, tool_suffix=WIDGET_TOOL):
        return True
    message = data.get("last_assistant_message")
    return (isinstance(message, str) and bool(TREE_TEXT_RE.search(message))
            and not A.transcript_offers_tool(transcript, WIDGET_TOOL))


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
    result = risk.assess(*risk.fresh_changes([c for c in changes if c["path"] in mine], seen))
    return None if result["empty"] or result["level"] == "thap" else result


def foreign_filters(root: Path) -> bool:
    """Repo tự khai báo clean filter (cấu hình local, kể cả file include): git diff sẽ chạy lệnh đó, và không có cờ
    tắt. Filter toàn cục của người dùng (như git-lfs) là đáng tin."""
    out = A.git_out(root, "config", "--show-scope", "--get-regexp", r"^filter\..*\.(clean|process)$") or ""
    return any(line.split("\t", 1)[0] in ("local", "worktree", "command") for line in out.splitlines())


def gate_reason(result: dict, plan_rel: str, base: str = None) -> str:
    """`base`: HEAD lúc bắt đầu lượt, khi lượt đã commit (diff so với HEAD hiện tại không còn phần đã commit)."""
    level = {"vua": "vừa", "cao": "cao"}[result["level"]]
    why = "; ".join(result["reasons"][:3])
    cmd = "risk.py --new" + (f" --base {base[:12]}" if base else "")
    committed = (f" Lượt đã commit nên chot-viec chạy risk.py với `--base {base[:12]}` (HEAD lúc bắt đầu lượt); không "
                 "có `--base` thì diff rỗng và phần đã commit không được chấm." if base else "")
    return (f"agent-stack (hook Stop): lượt này đổi hay commit code có dòng chưa qua chốt việc, mức rủi ro {level} "
            f"({why}), mà chưa chạy chot-viec. Dòng thêm sau lần chạy chot-viec trước (ví dụ sửa theo review) cũng "
            f"tính; xem chúng bằng `{cmd}`.{committed} Chạy skill chot-viec ngay cho phần đó: nó tự chạy mo-hinh-de-doa "
            f"nếu đụng ranh giới tin cậy, review theo mức rủi ro, và cập nhật §0 của `{plan_rel}`. Rồi kết thúc lượt "
            "bằng báo cáo ngắn của chot-viec. Chỉ khi các dòng này do phiên khác hay người khác viết (không phải "
            "phiên này, kể cả ở lượt trước), trả lời đúng một câu nói vậy và không làm gì thêm.")


def plan_state(digest_now, plan_updated, should_block, gate, changed) -> str:
    if digest_now is None:
        return "project không có mục §0"
    if plan_updated:
        return "đã cập nhật trong lượt này"
    if should_block:
        return ("chưa cập nhật; hook đã nhờ Claude cập nhật ngay sau lượt này"
                + (" (cùng lúc chạy chot-viec)" if gate is not None else ""))
    if changed:
        return "chưa cập nhật dù lượt có đổi file"
    return "không đổi (lượt không đổi file)"


def main():
    data = A.read_hook_input()
    sid = data.get("session_id", "")
    if not sid or not data.get("cwd"):
        return  # đầu vào thiếu hay hỏng: không đoán thư mục, vì hook sẽ ghi file vào đó
    active = bool(data.get("stop_hook_active"))
    root = A.project_root(data.get("cwd"))
    turn = A.load_turn(sid)
    if turn and turn.get("root") != str(root):
        turn = None  # lượt bắt đầu ở thư mục khác: không so được
    changed = A.changed_since(root, turn["ts"]) if turn else []
    digest_now = A.section0_digest(root)
    plan_updated = bool(turn) and digest_now is not None and digest_now != turn.get("plan_digest")
    found = A.read_plan(root)
    plan_rel = str(found[0].relative_to(root)) if found and str(found[0]).startswith(str(root)) else "PLAN.md"
    plan_block = bool(changed) and not active and turn is not None and digest_now is not None and not plan_updated

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
    request = A.request_text(sid)
    git = A.git_summary(root)
    dirty = len(git.get("dirty") or []) if git.get("is_repo") else None

    def write(status):
        try:
            A.record_turn(root, sid, state="done", request=request, answer=answer, next_step=next_step,
                          changed=changed, dirty_count=dirty, branch=git.get("branch"), plan_status=status)
        except Exception as exc:  # noqa: BLE001 (ghi lỗi thì các cổng §0, chot-viec vẫn phải chạy)
            A.log_event("hook-error", {"hook": "record_turn", "error": repr(exc)[:300]})

    # Ghi trước các bước chậm (chấm rủi ro bằng git diff, đọc transcript), để hook có bị ngắt vì quá giờ thì lượt
    # vẫn được lưu.
    status = plan_state(digest_now, plan_updated, plan_block, None, changed)
    write(status)

    gate = None
    if changed and not active and turn is not None and A.is_project(root):
        try:
            gate = chot_viec_gate(root, turn, changed)
        except Exception as exc:  # noqa: BLE001 (chấm rủi ro lỗi thì không chặn, chỉ ghi log)
            A.log_event("hook-error", {"hook": "chot_viec_gate", "error": repr(exc)[:300]})
    tree_block = []
    if not active and turn is not None:
        try:
            tree_block = tree_due(root, turn, data)
        except Exception as exc:  # noqa: BLE001
            A.log_event("hook-error", {"hook": "tree_due", "error": repr(exc)[:300]})
    should_block = plan_block or gate is not None
    final = plan_state(digest_now, plan_updated, should_block, gate, changed)
    if final != status:
        write(final)
    A.log_event("stop", {"session": sid, "cwd": str(root), "changed": len(changed), "plan_updated": plan_updated,
                         "blocked": should_block or bool(tree_block), "chot_viec": gate["level"] if gate else None,
                         "tree": tree_block or False})

    tree_extra = tree_after(tree_block) if tree_block else ""

    if gate is not None:
        head_now = (A.git_out(root, "rev-parse", "--verify", "-q", "HEAD") or "").strip()
        base = turn.get("head") if turn.get("head") and turn.get("head") != head_now else None
        A.emit_block(gate_reason(gate, plan_rel, base) + tree_extra,
                     f"🔒 Lượt này đổi code mức rủi ro {'cao' if gate['level'] == 'cao' else 'vừa'} mà chưa chốt việc: "
                     "Claude chạy chot-viec trước khi xong.")
    elif should_block:
        advice = current_trim_advice(root)
        A.emit_block(block_reason(changed, plan_rel, advice) + tree_extra,
                     f"📝 Lượt này đổi {len(changed)} file mà §0 chưa đổi: nhờ Claude cập nhật §0 trước khi xong.")
    elif tree_block:
        A.emit_block(tree_alone(tree_block),
                     f"🌳 Lượt này {join_why(tree_block, TREE_SHORT)}: nhờ Claude hiện cây để bạn chọn việc tiếp theo.")
    elif plan_updated and not active:
        # §0 vừa được cập nhật (lúc nó phình thêm) mà vượt ngưỡng: nhờ trim ngay. Chỉ khi trim rút được §0, nên
        # chạy trim xong thì lần sau không nhắc lại; §0 dài vì phần trim không dời được thì SessionStart báo.
        advice = current_trim_advice(root)
        if advice and advice[1]:
            A.emit_block(trim_alone(advice), "✂️ §0 vừa cập nhật mà dài quá: nhờ Claude dời việc đã xong sang nhật ký.")


if __name__ == "__main__":
    A.run_hook(main)
