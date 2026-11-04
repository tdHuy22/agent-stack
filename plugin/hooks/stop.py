#!/usr/bin/env python3
"""Hook Stop: sau mỗi lượt, ghi lượt cuối (yêu cầu, câu trả lời cuối đã che khóa, việc tiếp theo, file đổi) vào
.agent/LAST-TURN.md của thư mục làm việc, kể cả thư mục không phải project (thư mục chung thì vào state/last-turn/),
để phiên mới làm tiếp được. Ghi trước các bước chậm. Chặn một lần để Claude làm nốt trước khi xong:
- lượt đổi code có mức rủi ro từ vừa trở lên (risk.py của done-gate) mà chưa chạy done-gate: chạy done-gate (nó lo
  luôn threat model khi đụng ranh giới tin cậy, review theo mức rủi ro và §0);
- lượt đã chạy done-gate ở mức vừa trở lên mà thiếu bằng chứng: không có biên nhận đạt nào còn đúng cho code hiện
  tại, có lệnh kiểm tra trượt trên code hiện tại, hay chưa giao reviewer. Xét cả ở lần Stop thứ hai (đường thường
  gặp: hook chặn, Claude chạy done-gate rồi dừng lại), nhưng chỉ nhắc một lần mỗi lượt;
- còn lại, lượt có đổi file mà §0 chưa đổi: cập nhật §0;
- §0 vừa được cập nhật trong lượt mà dài quá ngưỡng, và `state.py trim` rút được nó: chạy trim (chạy xong thì §0 gọn
  nên lần sau không nhắc lại);
- lượt trả lời câu hỏi tiến độ trong project có kế hoạch mà người dùng chưa thấy cây: hiện cây để người dùng chọn việc tiếp theo (gộp
  vào lời nhắc ở trên nếu có). Chạy plan_tree.py để tự đọc không tính: phải có lời gọi show_widget với HTML của cây,
  hay cây chữ trong câu trả lời cuối khi phiên không có công cụ widget.

Lúc bắt đầu lượt và dấu §0 lúc đó do hook UserPromptSubmit ghi (state/turns/). Lần Stop thứ hai của cùng lượt
(stop_hook_active) chỉ còn xét bằng chứng của done-gate, và giữ câu trả lời của lần đầu thay cho câu báo "đã cập
nhật §0".
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "lib"))
import agentstack as A  # noqa: E402


def trim_hint(advice) -> str:
    """Nhắc chạy trim khi §0 dài và trim rút được nó (A.trim_advice); trim không giúp được thì không nhắc ở đây, kẻo lượt
    nào cũng nhắc mà §0 không đổi (progress và SessionStart đã báo người dùng)."""
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
TREE_HOW = ("chạy `python3 ~/Documents/Claude/agent-stack/plugin/skills/progress/scripts/plan_tree.py --widget` rồi "
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
    # /tree in cây dạng chữ (cloud, nơi pane không hiện) trong lượt: người dùng đã thấy cây.
    seen = A.tree_shown_at(data.get("session_id"))
    if seen is not None and seen >= turn["ts"]:
        return []
    if not reasons or tree_shown(turn, data):
        return []
    return reasons


def tree_shown(turn: dict, data: dict) -> bool:
    """Người dùng đã thấy cây trong lượt: lời gọi show_widget với HTML của cây, hay cây chữ trong câu trả lời cuối
    khi phiên không có công cụ widget (luật chung: có widget thì vẽ widget). Phiên có mod giao diện (ui.tsx đặt
    AGENT_STACK_UI=1, chỉ ở phiên có nơi vẽ) hay mod đã ghi dấu pane đang hiện (biến chỉ đặt lúc ghép system prompt,
    nên pane mở bằng /tree giữa các lượt hay sau khi nạp lại mod có thể chưa có biến) thì cây đã nằm sẵn ở pane."""
    if os.environ.get("AGENT_STACK_UI") == "1" or A.pane_open(data.get("session_id")):
        return True
    transcript = data.get("transcript_path")
    if A.tool_used_since(transcript, turn["ts"], TREE_WIDGET_MARK, tool_suffix=WIDGET_TOOL):
        return True
    message = data.get("last_assistant_message")
    return (isinstance(message, str) and bool(TREE_TEXT_RE.search(message))
            and not A.transcript_offers_tool(transcript, WIDGET_TOOL))


def done_gate_gate(root: Path, turn: dict, changed: list):
    """Kết quả chấm rủi ro (dict của risk.assess) cho phần lượt này đổi, nếu cần chạy done-gate; không thì None.
    Không cần khi lượt không đổi file, khi done-gate (risk.py) đã chạy trong lượt, hoặc khi mức rủi ro thấp."""
    if not changed or A.done_gate_ran_since(root, turn["ts"]):
        return None
    sys.path.insert(0, str(PLUGIN / "skills" / "done-gate" / "scripts"))
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
    result = risk.assess(*risk.fresh_since_mark([c for c in changes if c["path"] in mine], A.done_gate_mark(root)))
    return None if result["empty"] or result["level"] == "thap" else result


def receipt_epoch(rec: dict):
    try:
        return datetime.fromisoformat(rec["ts"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return None


def receipt_current(rec: dict, since: float) -> bool:
    """Biên nhận còn đúng cho code hiện tại: dấu vân tay phần không phải tài liệu khớp, nên cập nhật §0, threat model,
    README hay commit sau bước kiểm chứng không làm cũ nó (so nội dung, không so thời điểm sửa file). Biên nhận cũ
    chưa có dấu đó thì xét cả cây. Không tính được dấu vân tay (repo git lồng chưa ignore làm hash-object lỗi) thì
    tính biên nhận chạy trong lượt (từ `since`), để không đòi một điều không làm được. Cờ current của
    A.receipt_status, cùng cờ receipt.py show và progress hiện."""
    if rec.get("current") is not None:
        return rec["current"]
    return (receipt_epoch(rec) or 0) >= since


def evidence_gaps(root: Path, turn: dict, sid: str):
    """(mức, [bằng chứng còn thiếu]) khi lượt đã chạy done-gate và mức cao nhất trong lượt từ vừa trở lên. None khi
    đủ bằng chứng hay không xét: chưa chạy done-gate (cổng ở trên lo), mức thấp, đã nhắc trong lượt, hay repo có
    clean filter riêng (tính dấu vân tay sẽ chạy lệnh của repo lạ, TM-53)."""
    if turn.get("evidence_asked") or not A.done_gate_ran_since(root, turn["ts"]):
        return None
    levels = set(A.done_gate_levels_since(root, turn["ts"])) | {turn.get("gate_level")}
    level = "cao" if "cao" in levels else "vua" if "vua" in levels else None
    if level is None or foreign_filters(root):
        return None
    checks = A.receipt_status(root)
    gaps = []
    failing = [label for label, rec in checks.items()
               if not rec.get("ok") and (receipt_epoch(rec) or 0) >= turn["ts"] and receipt_current(rec, turn["ts"])]
    if failing:
        gaps.append(("test trượt", "lệnh kiểm tra trượt trên code hiện tại: "
                     + ", ".join(f"`{label}` (mã {checks[label].get('exit')})" for label in failing[:3])))
    if not any(rec.get("ok") and receipt_current(rec, turn["ts"]) for rec in checks.values()):
        gaps.append(("chưa có biên nhận đạt", "không có biên nhận đạt nào còn đúng cho code hiện tại: chạy mốc kiểm "
                     "tra của project qua `receipt.py run -- <lệnh>`"))
    # pi không có SubagentStart nên không có dấu reviewer để kiểm (plugin/hosts/pi.json). Payload SubagentStart không
    # có model, nên chỉ kiểm có ít nhất một lần giao reviewer, không kiểm đúng model hay đủ hai reviewer (done-gate bước 5).
    if A.host() != "pi" and not A.subagent_started_since(sid, "reviewer", turn["ts"]):
        gaps.append(("chưa review", "chưa giao `agent-stack:reviewer` (bước 5 của done-gate, bắt buộc từ mức vừa)"))
    return (level, gaps) if gaps else None


def evidence_reason(level: str, gaps: list, plan_rel: str, plan_block: bool) -> str:
    items = "; ".join(f"({i}) {detail}" for i, (_, detail) in enumerate(gaps, 1))
    plan = f" Rồi cập nhật §0 của `{plan_rel}`." if plan_block else ""
    return (f"agent-stack (hook Stop): lượt này đã chạy done-gate (mức rủi ro {'cao' if level == 'cao' else 'vừa'}) "
            f"nhưng còn thiếu bằng chứng: {items}. Làm nốt đúng các bước đó của done-gate (bước 4: mốc kiểm tra qua "
            "receipt.py; bước 5: reviewer), sửa nếu trượt, rồi kết thúc lượt bằng báo cáo ngắn của done-gate." + plan
            + " Bước nào không làm được (thiếu môi trường, project không có test) thì ghi rõ trong báo cáo bước đó "
            "chưa kiểm và vì sao, không báo xong. Hook chỉ nhắc điều này một lần mỗi lượt.")


def foreign_filters(root: Path) -> bool:
    return A.local_clean_filters(root)


def gate_reason(result: dict, plan_rel: str, base: str = None) -> str:
    """`base`: HEAD lúc bắt đầu lượt, khi lượt đã commit (diff so với HEAD hiện tại không còn phần đã commit)."""
    level = {"vua": "vừa", "cao": "cao"}[result["level"]]
    why = "; ".join(result["reasons"][:3])
    cmd = "risk.py --new" + (f" --base {base[:12]}" if base else "")
    committed = (f" Lượt đã commit nên done-gate chạy risk.py với `--base {base[:12]}` (HEAD lúc bắt đầu lượt); không "
                 "có `--base` thì diff rỗng và phần đã commit không được chấm." if base else "")
    return (f"agent-stack (hook Stop): lượt này đổi hay commit code có dòng chưa qua chốt việc, mức rủi ro {level} "
            f"({why}), mà chưa chạy done-gate. Dòng thêm sau lần chạy done-gate trước (ví dụ sửa theo review) cũng "
            f"tính; xem chúng bằng `{cmd}`.{committed} Chạy skill done-gate ngay cho phần đó: nó tự chạy threat-model "
            f"nếu đụng ranh giới tin cậy, review theo mức rủi ro, và cập nhật §0 của `{plan_rel}`. Rồi kết thúc lượt "
            "bằng báo cáo ngắn của done-gate. Chỉ khi các dòng này do phiên khác hay người khác viết (không phải "
            "phiên này, kể cả ở lượt trước), trả lời đúng một câu nói vậy và không làm gì thêm.")


def plan_state(digest_now, plan_updated, should_block, gate, changed) -> str:
    if digest_now is None:
        return "project không có mục §0"
    if plan_updated:
        return "đã cập nhật trong lượt này"
    if should_block:
        return ("chưa cập nhật; hook đã nhờ Claude cập nhật ngay sau lượt này"
                + (" (cùng lúc chạy done-gate)" if gate is not None else ""))
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
    # File phiên khác đang làm cùng project sửa trong lúc lượt này chạy: không nhắc §0 hay done-gate cho chúng.
    foreign = set()
    if changed:
        try:
            foreign = A.foreign_files(root, sid, turn["ts"], changed, data.get("transcript_path"))
        except Exception as exc:  # noqa: BLE001
            A.log_event("hook-error", {"hook": "foreign_files", "error": repr(exc)[:300]})
    changed = [c for c in changed if c not in foreign]
    digest_now = A.section0_digest(root)
    plan_updated = bool(turn) and digest_now is not None and digest_now != turn.get("plan_digest")
    found = A.read_plan(root)
    plan_rel = str(found[0].relative_to(root)) if found and str(found[0]).startswith(str(root)) else "PLAN.md"
    # Lượt chỉ commit phần sửa ở lượt trước (§0 đã ghi lúc đó) thì không nhắc §0; done-gate vẫn chấm phần commit.
    plan_block = (bool(changed) and not active and turn is not None and digest_now is not None and not plan_updated
                  and any(c not in foreign for c in A.changed_since(root, turn["ts"], edited_only=True)))

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
        except Exception as exc:  # noqa: BLE001 (ghi lỗi thì các cổng §0, done-gate vẫn phải chạy)
            A.log_event("hook-error", {"hook": "record_turn", "error": repr(exc)[:300]})

    # Ghi trước các bước chậm (chấm rủi ro bằng git diff, đọc transcript), để hook có bị ngắt vì quá giờ thì lượt
    # vẫn được lưu.
    status = plan_state(digest_now, plan_updated, plan_block, None, changed)
    write(status)

    gate = None
    if changed and not active and turn is not None and A.is_project(root):
        try:
            gate = done_gate_gate(root, turn, changed)
        except Exception as exc:  # noqa: BLE001 (chấm rủi ro lỗi thì không chặn, chỉ ghi log)
            A.log_event("hook-error", {"hook": "done_gate_gate", "error": repr(exc)[:300]})
    # Cả ở lần Stop thứ hai: đường thường gặp là hook chặn ở trên, Claude chạy done-gate rồi dừng lại. Không cần
    # `changed`: lượt chỉ xóa file thì danh sách đó rỗng (changed_since bỏ file đã xóa), mà done-gate vẫn đã chạy.
    evidence = None
    if gate is None and turn is not None and A.is_project(root):
        try:
            evidence = evidence_gaps(root, turn, sid)
        except Exception as exc:  # noqa: BLE001 (lỗi thì không chặn, chỉ ghi log)
            A.log_event("hook-error", {"hook": "evidence_gaps", "error": repr(exc)[:300]})
    tree_block = []
    if not active and turn is not None:
        try:
            tree_block = tree_due(root, turn, data)
        except Exception as exc:  # noqa: BLE001
            A.log_event("hook-error", {"hook": "tree_due", "error": repr(exc)[:300]})
    should_block = plan_block or gate is not None or evidence is not None
    final = plan_state(digest_now, plan_updated, should_block, gate, changed)
    if final != status:
        write(final)
    A.log_event("stop", {"session": sid, "cwd": str(root), "changed": len(changed), "plan_updated": plan_updated,
                         "blocked": should_block or bool(tree_block), "done_gate": gate["level"] if gate else None,
                         "evidence": [short for short, _ in evidence[1]] if evidence else None,
                         "tree": tree_block or False})

    tree_extra = tree_after(tree_block) if tree_block else ""

    if gate is not None:
        turn["gate_level"] = gate["level"]  # để lần Stop sau biết lượt cần bằng chứng tới đâu
        A.save_turn(sid, turn)
        head_now = (A.git_out(root, "rev-parse", "--verify", "-q", "HEAD") or "").strip()
        base = turn.get("head") if turn.get("head") and turn.get("head") != head_now else None
        A.emit_block(gate_reason(gate, plan_rel, base) + tree_extra,
                     f"🔒 Lượt này đổi code mức rủi ro {'cao' if gate['level'] == 'cao' else 'vừa'} mà chưa chốt việc: "
                     "Claude chạy done-gate trước khi xong.")
    elif evidence is not None:
        turn["evidence_asked"] = True
        A.save_turn(sid, turn)
        A.emit_block(evidence_reason(evidence[0], evidence[1], plan_rel, plan_block) + tree_extra,
                     "🧾 Chốt việc còn thiếu bằng chứng (" + ", ".join(short for short, _ in evidence[1])
                     + "): nhờ Claude làm nốt trước khi xong.")
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
