#!/usr/bin/env python3
"""Hook UserPromptSubmit: cảnh báo khi hạn mức 5 giờ hoặc hạn mức tuần sắp hết.

Số liệu hạn mức lấy từ state/limits.json do statusline ghi (chỉ có khi chạy trong terminal).
Mỗi ngưỡng chỉ nhắc một lần cho mỗi phiên và mỗi chu kỳ reset.

Hook cũng lưu yêu cầu gần nhất của người dùng theo từng phiên (state/last-request/), để hook SubagentStart
đưa cho subagent chạy context riêng. Tin do hệ thống tạo (thông báo nền, báo cáo của subagent quay về phiên chính)
không được ghi đè yêu cầu thật và không được router gợi ý; khóa và token được che.

Tin của người dùng (không tính lệnh và tin do hệ thống tạo) được ghi ngay vào lượt cuối ở trạng thái đang chạy
(.agent/LAST-TURN.md), để Esc, crash hay lượt dài chưa xong vẫn để lại yêu cầu; lệnh không tương tác (`claude -p`,
`pi -p`) thì không, để không ghi đè lượt của phiên tương tác. Phiên còn chạy agent-stack cũ hơn bản
đã cài thì nhắc một lần.

Mọi tin (kể cả tin do hệ thống tạo) mở một lượt mới: hook ghi lúc bắt đầu lượt, dấu §0 và HEAD lúc đó
(state/turns/), để hook Stop biết lượt vừa xong đổi file nào, §0 đã được cập nhật chưa và có cần chốt việc không.
Khi router thấy việc là chức năng đụng ranh giới tin cậy, lượt được đánh dấu threat_model cho hook PreToolUse.

Tin gõ từ điện thoại vào phiên Desktop (Remote Control): hộp next-step của app không hiện trên điện thoại, nên hook
nhắc Claude viết câu hỏi bằng chữ. Nơi gõ lấy từ trường clientPlatform của tin người dùng cuối trong transcript.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402

WARN_5H = float(os.environ.get("AGENT_STACK_WARN_5H", "90"))
WARN_7D = float(os.environ.get("AGENT_STACK_WARN_7D", "80"))
MAX_AGE_SECONDS = 30 * 60
PHONE_PLATFORMS = {"ios", "android"}  # clientPlatform của tin gõ từ app Claude trên điện thoại (ios đã kiểm 08/11/2026)
TRANSCRIPT_BLOCK_BYTES = 256 * 1024
# Đọc ngược tối đa chừng này byte: một lượt nhiều công cụ đẩy tin người dùng cuối ra xa hơn 1 MB (đo 08/11/2026).
try:  # biến chỉ để test; giá trị hỏng không được làm hook văng lúc nạp
    TRANSCRIPT_SCAN_BYTES = int(os.environ.get("AGENT_STACK_TRANSCRIPT_SCAN_BYTES", ""))
except ValueError:
    TRANSCRIPT_SCAN_BYTES = 8 * 1024 * 1024


def reverse_lines(path: Path, limit: int):
    """Các dòng (bytes) của file từ cuối lên, đọc từng khối, dừng sau `limit` byte. Khi dừng vì `limit`, dòng cuối
    cùng trả về có thể bị cắt ngang: nó hỏng JSON và bị bỏ qua ở nơi gọi."""
    with path.open("rb") as fh:
        pos = fh.seek(0, 2)
        stop = max(0, pos - limit)
        carry = b""
        while pos > stop:
            size = min(TRANSCRIPT_BLOCK_BYTES, pos - stop)
            pos -= size
            fh.seek(pos)
            parts = (fh.read(size) + carry).split(b"\n")
            carry = parts[0]  # có thể là nửa dòng: ghép tiếp với khối đứng trước
            yield from reversed(parts[1:])
        yield carry


def message_text(message) -> str:
    """Chữ của tin người dùng: content là chuỗi, hay danh sách khối (tin kèm ảnh, tệp) thì ghép các khối text."""
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return content if isinstance(content, str) else ""


def last_client_platform(transcript, prompt: str):
    """(clientPlatform của tin người dùng cuối trong transcript, tin đó có phải tin đang gửi không).

    Trả (None, False) khi không đọc được hay không thấy trong TRANSCRIPT_SCAN_BYTES cuối."""
    try:
        for raw in reverse_lines(Path(transcript), TRANSCRIPT_SCAN_BYTES):
            if b'"clientPlatform"' not in raw:
                continue
            try:
                rec = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("type") != "user" or not isinstance(rec.get("clientPlatform"), str):
                continue
            return rec["clientPlatform"], message_text(rec.get("message")).strip() == prompt.strip()
    except (OSError, TypeError, ValueError):
        pass
    return None, False


def phone_note(data: dict) -> str:
    """Dòng ngữ cảnh khi người dùng gõ từ điện thoại vào phiên Desktop; chuỗi rỗng ở mọi nơi khác.

    Phiên `rc`, CloudCLI và terminal không có hộp next-step nên Claude vốn đã viết bằng chữ: không cần nhắc."""
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT", "") != "claude-desktop":
        return ""
    platform, current = last_client_platform(data.get("transcript_path"), data.get("prompt") or "")
    A.log_event("client-platform", {"session": data.get("session_id", ""), "platform": platform, "current": current})
    if platform not in PHONE_PLATFORMS:
        return ""
    which = "tin này" if current else "tin người dùng gần nhất trong transcript"
    return (f"[agent-stack] Người dùng đang gõ từ điện thoại ({platform}, theo {which}) vào phiên Desktop qua Remote "
            "Control. Trên điện thoại hộp next-step (wrap_up) không hiện, hộp AskUserQuestion thì hiện. Mọi câu hỏi "
            "cần người dùng trả lời phải viết bằng chữ trong tin nhắn, kèm lựa chọn đánh số, kể cả câu đã đặt trong "
            "hộp wrap_up.")


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


def main():
    data = A.read_hook_input()
    sid = data.get("session_id", "")
    prompt = data.get("prompt", "") or ""
    digest = hashlib.sha1(prompt.encode("utf-8", "replace")).hexdigest()[:12]
    if sid and not A.once(f"prompt-{sid}-{digest}", 5):
        return  # hook bị đăng ký hai lần
    flags = {}
    # Hạn mức (limits.json do statusline Claude Code ghi) và bản plugin đang chạy là của Claude Code; chạy từ pi qua
    # cầu nối thì bỏ, kẻo model của pi bỏ việc chính đi cập nhật §0 vì hạn mức của công cụ khác.
    claude_code = A.host() == "claude-code"
    try:
        context, user = limit_notes(sid) if claude_code else ([], [])
        stale_ctx, stale_user = stale_plugin_note(sid) if sid and claude_code else ("", "")
        if stale_ctx:
            context.append(stale_ctx)
            user.append(stale_user)
        try:  # nơi người dùng gõ: lỗi ở phần phụ này không được làm mất cảnh báo hạn mức hay gợi ý router
            note = phone_note(data) if claude_code else ""
            if note:
                context.append(note)
        except Exception as exc:  # noqa: BLE001
            A.log_event("hook-error", {"hook": "phone-note", "error": repr(exc)[:300]})
        try:  # router (GĐ5): gợi ý skill, model, effort, subagent
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "task-router" / "scripts"))
            import route  # noqa: E402
            flags = route.turn_flags(prompt, data.get("cwd"))
            suggestion = route.hook_suggestion(prompt, data)
            A.record_router(sid, suggestion)  # dải gợi ý của mod giao diện; tự bắt lỗi
            if suggestion:
                context.append(suggestion["context"])
                user.append(suggestion["user"])
        except Exception as exc:  # noqa: BLE001 (router lỗi không được làm mất cảnh báo hạn mức của tin này)
            A.log_event("hook-error", {"hook": "router", "error": repr(exc)[:300]})
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
