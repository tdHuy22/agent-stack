#!/usr/bin/env python3
"""Hook UserPromptSubmit: cảnh báo khi hạn mức 5 giờ hoặc hạn mức tuần sắp hết.

Số liệu hạn mức lấy từ state/limits.json do statusline ghi (chỉ có khi chạy trong terminal).
Mỗi ngưỡng chỉ nhắc một lần cho mỗi phiên và mỗi chu kỳ reset.

Hook cũng lưu yêu cầu gần nhất của người dùng theo từng phiên (state/last-request/), để hook SubagentStart
đưa cho subagent chạy context riêng. Tin do hệ thống tạo (thông báo nền, báo cáo của subagent quay về phiên chính)
không được ghi đè yêu cầu thật và không được router gợi ý; khóa và token được che.

Tin của người dùng (không tính lệnh và tin do hệ thống tạo) được ghi ngay vào lượt cuối ở trạng thái đang chạy
(.agent/LAST-TURN.md), để Esc, crash hay lượt dài chưa xong vẫn để lại yêu cầu; lệnh không tương tác (`claude -p`)
thì không, để không ghi đè lượt của phiên tương tác. Phiên còn chạy agent-stack cũ hơn bản
đã cài thì nhắc một lần.

Mọi tin (kể cả tin do hệ thống tạo) mở một lượt mới: hook ghi lúc bắt đầu lượt, dấu §0 và HEAD lúc đó
(state/turns/), để hook Stop biết lượt vừa xong đổi file nào, §0 đã được cập nhật chưa và có cần chốt việc không.
Khi router thấy việc là chức năng đụng ranh giới tin cậy, lượt được đánh dấu threat_model cho hook PreToolUse.

Phiên Desktop: hook đánh dấu lượt mới để hook PreToolUse kiểm nơi người dùng gõ (Mac hay điện thoại) và nhắc Claude
viết câu hỏi bằng chữ khi người dùng sang điện thoại (xem plugin/lib/client_place.py).
Phiên có context từ 200K token thì nhắc (tối đa một lần mỗi giờ): mỗi lần gọi model đọc lại cả hội thoại, nên việc mới
không cần hội thoại cũ nên mở phiên mới ở ranh giới việc. Hook không tự nén: nén giữa chừng làm mất chi tiết.
"""
import hashlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402
import client_place  # noqa: E402

WARN_5H = float(os.environ.get("AGENT_STACK_WARN_5H", "90"))
WARN_7D = float(os.environ.get("AGENT_STACK_WARN_7D", "80"))
MAX_AGE_SECONDS = 30 * 60
LONG_CONTEXT_TOKENS = 200_000  # từ cỡ này nhắc mở phiên mới ở ranh giới việc
LONG_SESSION_REMIND_SECONDS = 3600


def limit_notes(sid: str):
    data = A.read_json(A.state_dir() / "limits.json", {}) or {}
    if time.time() - float(data.get("ts", 0)) > MAX_AGE_SECONDS:
        return [], []
    limits = data.get("rate_limits") or {}
    context, user = [], []
    for window, label, threshold in (("seven_day", "tuần", WARN_7D), ("five_hour", "5 giờ", WARN_5H)):
        info = limits.get(window) or {}
        pct = info.get("used_percentage")
        if pct is None or float(pct) < threshold:
            continue
        pct = float(pct)
        band = 95 if pct >= 95 else threshold
        resets = info.get("resets_at")
        if not A.once(f"limit-{sid}-{window}-{band}-{resets}", 8 * 86400):
            continue
        when = time.strftime("%H:%M %d/%m", time.localtime(float(resets))) if resets else "?"
        user.append(f"⚠️ Hạn mức {label} đã dùng {pct:.0f}% (reset lúc {when}).")
        if window == "seven_day":
            context.append(f"Hạn mức tuần đã dùng {pct:.0f}%. Cập nhật ngay mục §0 trong file kế hoạch (đang dở, "
                           "việc tiếp theo, mốc kiểm tra) để phiên sau làm tiếp được nếu hết hạn mức. "
                           "Ưu tiên việc quan trọng; giao việc cơ học cho subagent rẻ hơn.")
        else:
            context.append(f"Hạn mức 5 giờ đã dùng {pct:.0f}%. Ghi checkpoint vào §0 trước khi bắt đầu bước dài tiếp theo.")
    return context, user


def long_session_note(sid: str, data: dict, prompt: str):
    """(context, dòng cho người dùng) khi phiên đã dài: context từ LONG_CONTEXT_TOKENS token, nhắc một lần mỗi giờ.
    Chỉ với tin thật của người dùng (không phải tin tự động, lệnh, phiên -p). Số token lấy như router."""
    if (not sid or not prompt.strip() or A.is_automated_prompt(prompt) or A.is_command_prompt(prompt)
            or A.non_interactive(data)):
        return "", ""
    usage = A.mod_session_usage(sid) or (A.session_usage(data["transcript_path"]) if data.get("transcript_path") else {})
    tokens = int(usage.get("context") or 0)
    if tokens < LONG_CONTEXT_TOKENS or not A.once(f"long-session-{sid}", LONG_SESSION_REMIND_SECONDS):
        return "", ""
    k = tokens // 1000
    return (f"[agent-stack] Phiên đã ≈{k}K token context: mỗi lần gọi model đọc lại cả hội thoại. Nếu tin này là việc "
            "mới không cần hội thoại cũ: cập nhật §0 và đề nghị người dùng (một câu, không dừng chờ) mở phiên mới hay "
            "/compact cho việc này. Đang dở việc thì làm tiếp, đừng nén giữa chừng (mất nguyên văn lỗi, giả thuyết đã "
            "loại).",
            f"📏 phiên ≈{k}K token: việc mới thì nên mở phiên mới")


def remember_request(sid, cwd, prompt):
    """Lưu yêu cầu gần nhất cho hook SubagentStart. Đây chỉ là phần phụ: lỗi nào cũng bỏ qua êm."""
    try:
        if sid and not A.is_automated_prompt(prompt):
            A.save_last_request(sid, cwd, prompt)
    except Exception:  # noqa: BLE001
        pass


def stale_plugin_note(sid: str):
    """(context, dòng cho người dùng) khi phiên này còn chạy agent-stack cũ hơn bản đã cài; nhắc một lần mỗi phiên cho
    mỗi bản đã cài."""
    found = A.plugin_staleness()
    if not found or not A.once(f"stale-plugin-{sid}-{found[1]}", 8 * 86400):
        return "", ""
    running, installed = found
    return (f"[agent-stack] Phiên này chạy plugin agent-stack {running}, nhưng máy đã cài {installed}: hook của bản "
            "mới (tự lưu lượt cuối, nhắc §0, router) chưa chạy trong phiên này. Nhắc người dùng gõ /reload-plugins "
            "hoặc mở lại phiên.",
            f"⚠️ Phiên này chạy agent-stack {running}, máy đã cài {installed}: gõ /reload-plugins hoặc mở lại phiên.")


def bundle_note(prompt: str, data: dict, sid: str) -> str:
    """Dòng gợi ý bật bộ (plugin/lib/bundles.py) khi chữ của người dùng khớp từ khóa của bộ chưa bật; rỗng nếu không.
    Mỗi bộ nhắc tối đa một lần mỗi phiên trong 6 giờ."""
    if not prompt.strip() or A.is_automated_prompt(prompt) or A.is_command_prompt(prompt):
        return ""
    text = A.routable_text(prompt)
    if not text:
        return ""
    import bundles  # noqa: E402 (cùng thư mục lib với agentstack)
    root = bundles.settings_root(data["cwd"]) if data.get("cwd") else None
    order = bundles.asked_note(text, root)  # "bật bộ ml": lời của chính người dùng, luôn báo
    if order:
        return order
    fresh = [n for n in bundles.pending(text, root) if not sid or A.once(f"bundle-{sid}-{n}", 6 * 3600)]
    return bundles.prompt_hint(text, root, only=fresh) if fresh else ""


def main():
    t0 = time.time()  # mốc cho hạn chờ lớp model của router (tính từ lúc hook bắt đầu, không từ lúc gọi model)
    data = A.read_hook_input()
    sid = data.get("session_id", "")
    prompt = data.get("prompt", "") or ""
    digest = hashlib.sha1(prompt.encode("utf-8", "replace")).hexdigest()[:12]
    if sid and not A.once(f"prompt-{sid}-{digest}", 5):
        return  # hook bị đăng ký hai lần
    flags = {}
    try:
        context, user = limit_notes(sid)
        stale_ctx, stale_user = stale_plugin_note(sid) if sid else ("", "")
        if stale_ctx:
            context.append(stale_ctx)
            user.append(stale_user)
        try:  # duyệt spec (GĐ6, S5, TM-128): chỉ lời của chính người dùng, mã khớp đúng một file spec
            if (prompt.strip() and not A.is_automated_prompt(prompt) and not A.is_command_prompt(prompt)
                    and not A.non_interactive(data)):
                import specbook
                said = specbook.approval_text(prompt)
                results = specbook.approve_from_prompt(said, data.get("cwd"))
                if not results and specbook.mentions_approval(prompt):
                    context.append("[agent-stack] Tin có cụm \"duyệt spec <mã>\" nhưng hook chưa ghi bản duyệt: câu là "
                                   "câu hỏi, có phủ định hay loại trừ (trừ, nhưng … Sn), nằm trong phần dán, khối code, "
                                   "khối hệ thống hay brief của phiên khác. Đừng coi là đã duyệt; nhờ người dùng nhắn "
                                   "lại đúng câu `duyệt spec <mã>` nếu họ muốn duyệt.")
                for code, rec in results:
                    if rec:
                        context.append(f"[agent-stack] Đã ghi bản duyệt spec `{rec['path']}` ({len(rec['lines'])} "
                                       f"dòng, mã {code}) theo lời người dùng; bánh cóc của done-gate tính các dòng "
                                       "này là đã duyệt.")
                        texts = rec.get("texts", [])
                        shown = " | ".join(specbook.shown_line(sid, text) for sid, text in texts[:20])
                        if len(texts) > 20:
                            shown += f" | … và {len(texts) - 20} dòng nữa (xem {rec['path']})"
                        user.append(f"📝 Đã ghi bản duyệt spec {rec['path']} ({len(rec['lines'])} dòng): {shown}"
                                    " (sai dòng nào thì báo agent, đừng code tiếp)")
                    else:
                        context.append(f"[agent-stack] Người dùng nhắn duyệt spec {code} nhưng mã không khớp đúng một "
                                       "file trong .agent/spec/ (sai mã, file đã sửa sau khi dựng trang, hay hai file "
                                       "trùng nội dung): chưa ghi bản duyệt. Dựng lại trang (`spec.py page <slug>`) "
                                       "và báo người dùng mã mới.")
                # Câu gần đúng ("duyệt spec MW1 (mã …)", "duyệt <mã>", "duyệt" trần khi có trang chờ): nói câu cần gõ
                # cho cả người dùng lẫn agent. Chỉ báo, không ghi gì (TM-139).
                if not results or any(rec is None for _, rec in results):
                    waiting = specbook.hint_specs(said, data.get("cwd"), bool(results))
                    if waiting:
                        hint = specbook.approval_hint(waiting)
                        context.append("[agent-stack] Người dùng có vẻ muốn duyệt spec nhưng câu không đúng mẫu nên hook "
                                       "chưa ghi bản duyệt. Đừng coi là đã duyệt; nói nguyên văn câu cần gửi, thành "
                                       f"một tin riêng khi agent đã dừng lượt: {hint}")
                        user.append("📝 Chưa ghi bản duyệt spec: hook chỉ ghi khi bạn gửi đúng câu, thành một tin riêng "
                                    f"khi agent đã dừng lượt. Câu cần gửi: {hint}")
        except Exception as exc:  # noqa: BLE001 (lỗi phần phụ không được làm mất cảnh báo hạn mức hay router)
            A.log_event("hook-error", {"hook": "spec-approve", "error": repr(exc)[:300]})
        try:  # nơi người dùng gõ: chỉ đánh dấu, hook PreToolUse đọc khi tin đã vào transcript (xem client_place)
            client_place.mark_pending(data)
        except Exception as exc:  # noqa: BLE001 (lỗi phần phụ không được làm mất cảnh báo hạn mức hay router)
            A.log_event("hook-error", {"hook": "client-place", "error": repr(exc)[:300]})
        try:  # phiên dài: nhắc mở phiên mới (lỗi không được làm mất cảnh báo hạn mức hay router)
            long_ctx, long_user = long_session_note(sid, data, prompt)
            if long_ctx:
                context.append(long_ctx)
                user.append(long_user)
        except Exception as exc:  # noqa: BLE001
            A.log_event("hook-error", {"hook": "long-session", "error": repr(exc)[:300]})
        try:  # router: gợi ý skill, model, effort, subagent; lớp model (GĐ5) khi lớp từ khóa không chắc
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "task-router" / "scripts"))
            import route  # noqa: E402
            with route.one_pass():  # đọc .agent/stack.json và hỏi lớp model một lần cho cả gợi ý và cờ lượt
                try:
                    suggestion = route.hook_suggestion(prompt, dict(data, _hook_t0=t0))
                finally:  # gợi ý lỗi không được làm mất cờ threat model, tiêu chí của lượt
                    flags = route.turn_flags(prompt, data.get("cwd"))  # dùng lại kết quả hai lớp vừa chấm
                note = route.prefetch_note(data)  # kết quả nền của lớp model cho §0, khi khác gợi ý lúc mở phiên
            if note:
                context.append(note)
            A.record_router(sid, suggestion)  # dải gợi ý của mod giao diện; tự bắt lỗi
            if suggestion:
                context.append(suggestion["context"])
                user.append(suggestion["user"])
        except Exception as exc:  # noqa: BLE001 (router lỗi không được làm mất cảnh báo hạn mức của tin này)
            A.log_event("hook-error", {"hook": "router", "error": repr(exc)[:300]})
        try:  # bộ chưa bật mà việc cần (H5): đường dẫn SKILL.md và lệnh bật bộ, mỗi bộ một lần mỗi phiên
            bundle_hint = bundle_note(prompt, data, sid)
            if bundle_hint:
                context.append(bundle_hint)
        except Exception as exc:  # noqa: BLE001
            A.log_event("hook-error", {"hook": "bundles", "error": repr(exc)[:300]})
        A.emit("UserPromptSubmit", "\n".join(context), " ".join(user))
    finally:
        remember_request(sid, data.get("cwd"), prompt)  # ghi sau khi xử lý như cũ, kể cả khi bước trên lỗi
        A.mark_user_message(sid, prompt)  # cổng nhắc audit trước phát hành; tự bắt lỗi
        if sid and data.get("cwd"):
            # transcript: hook Stop của phiên khác cùng project đọc để biết file nào do phiên này sửa.
            transcript = data.get("transcript_path")
            extra = dict(flags or {}, **({"transcript": transcript} if isinstance(transcript, str) else {}))
            if (prompt.strip() and not A.is_automated_prompt(prompt) and not A.is_command_prompt(prompt)
                    and not A.non_interactive(data)):  # `-p`: prompt có thể chứa chữ không tin cậy (issue, PR)
                # đồng ý trước cho lệnh không đảo ngược (pretool_guard): chỉ tin thật của người dùng, đã che khóa
                extra.update(consent_text=A.redact_secrets(A.own_words(prompt)), consent_ts=time.time())
            A.start_turn(sid, data.get("cwd"), extra)  # tự bắt lỗi, không bao giờ văng
        if not A.non_interactive(data):  # `-p` không ghi đè lượt cuối của phiên tương tác (hook Stop ghi nếu đổi file)
            A.mark_turn_running(sid, data.get("cwd"), prompt)  # sau cùng vì chậm nhất (vài lệnh git); tự bắt lỗi


if __name__ == "__main__":
    A.run_hook(main)
