#!/usr/bin/env python3
"""Hook UserPromptSubmit: cảnh báo khi hạn mức 5 giờ hoặc hạn mức tuần sắp hết.

Số liệu hạn mức lấy từ state/limits.json do statusline ghi (chỉ có khi chạy trong terminal).
Mỗi ngưỡng chỉ nhắc một lần cho mỗi phiên và mỗi chu kỳ reset.

Hook cũng lưu yêu cầu gần nhất của người dùng theo từng phiên (state/last-request/), để hook SubagentStart
đưa cho subagent chạy context riêng. Tin do hệ thống tạo (thông báo nền, báo cáo của subagent quay về phiên chính)
không được ghi đè yêu cầu thật và không được router gợi ý; khóa và token được che.

Tin của người dùng (không tính lệnh và tin do hệ thống tạo) được ghi ngay vào lượt cuối ở trạng thái đang chạy
(.agent/LAST-TURN.md), để Esc, crash hay lượt dài chưa xong vẫn để lại yêu cầu. Phiên còn chạy agent-stack cũ hơn bản
đã cài thì nhắc một lần.

Mọi tin (kể cả tin do hệ thống tạo) mở một lượt mới: hook ghi lúc bắt đầu lượt, dấu §0 và HEAD lúc đó
(state/turns/), để hook Stop biết lượt vừa xong đổi file nào, §0 đã được cập nhật chưa và có cần chốt việc không.
Khi router thấy việc là chức năng đụng ranh giới tin cậy, lượt được đánh dấu threat_model cho hook PreToolUse.
"""
import hashlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402

WARN_5H = float(os.environ.get("AGENT_STACK_WARN_5H", "90"))
WARN_7D = float(os.environ.get("AGENT_STACK_WARN_7D", "80"))
MAX_AGE_SECONDS = 30 * 60


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
                           "việc tiếp theo, mốc kiểm tra) để có thể làm tiếp bằng OpenCode nếu hết hạn mức. "
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
    try:
        context, user = limit_notes(sid)
        stale_ctx, stale_user = stale_plugin_note(sid) if sid else ("", "")
        if stale_ctx:
            context.append(stale_ctx)
            user.append(stale_user)
        try:  # router (GĐ5): gợi ý skill, model, effort, subagent
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "task-router" / "scripts"))
            import route  # noqa: E402
            flags = route.turn_flags(prompt, data.get("cwd"))
            suggestion = route.hook_suggestion(prompt, data)
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
            A.start_turn(sid, data.get("cwd"), flags)  # tự bắt lỗi, không bao giờ văng
        A.mark_turn_running(sid, data.get("cwd"), prompt)  # sau cùng vì chậm nhất (vài lệnh git); tự bắt lỗi


if __name__ == "__main__":
    A.run_hook(main)
