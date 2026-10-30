#!/usr/bin/env python3
"""Hook SessionStart: nạp lại trạng thái project từ đĩa khi mở, resume, clear hoặc sau compact,
kèm gợi ý skill hợp với project và cách làm việc tiếp theo trong §0 (router), và lượt cuối do hook Stop ghi ở
.agent/LAST-TURN.md (trừ khi resume lại đúng phiên đã ghi lượt đó).

Thư mục không phải git repo và không có file kế hoạch (PLAN.md §0, .agent/HANDOFF.md...) thì hook im lặng.
"""
import hashlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402


def main():
    data = A.read_hook_input()
    sid = data.get("session_id", "")
    source = data.get("source", "startup")
    cwd = data.get("cwd") or os.getcwd()
    if sid and not A.once(f"start-{sid}-{source}", 15):
        return  # hook bị đăng ký hai lần: chỉ chạy một
    root = A.project_root(cwd)
    A.log_event("session-start", {"session": sid, "cwd": str(root), "source": source,
                                  "model": data.get("model"),
                                  # bản plugin nào đang chạy: thư mục repo (nạp tại chỗ) hay bản chép trong cache
                                  "plugin_root": os.environ.get("CLAUDE_PLUGIN_ROOT")}, "sessions.jsonl")
    if sid:
        sessions = A.state_dir() / "sessions"
        sessions.mkdir(exist_ok=True)
        A.prune(sessions, 14)
        A.prune(A.state_dir() / "once", 8)
        name = hashlib.sha1(sid.encode()).hexdigest()[:16] + ".json"
        A.write_json_atomic(sessions / name, {"session": sid, "model": data.get("model"),
                                              "effort": (data.get("effort") or {}).get("level"),
                                              "cwd": str(root), "ts": time.time()})
    try:  # cloud: kéo bản agent-stack mới ở nền, tối đa một lần mỗi 10 phút (không chờ)
        import cloud_update  # noqa: E402
        cloud_update.maybe_start(A.home_dir())
    except Exception:  # việc phụ: lỗi ở đây không được làm mất phần còn lại của hook
        pass
    try:  # bản tóm tắt giàu hơn của skill tien-do; không có thì dùng bản của thư viện
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "tien-do" / "scripts"))
        import collect  # noqa: E402
        info = collect.brief(root)
    except ImportError:
        info = A.brief(root)
    hint = None
    try:  # router: skill hợp với project và cách làm việc tiếp theo
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "task-router" / "scripts"))
        import route  # noqa: E402
        hint = route.session_hint(root)
    except ImportError:
        pass
    drift_note, drift_user = plugin_drift() if source == "startup" else ("", "")
    last = A.last_turn_context(root, sid, source)
    if not info and not hint and not drift_note and not last:
        return
    if not info and not hint and not last:
        A.emit("SessionStart", drift_note, drift_user)
        return
    context, user = (info["context"], info["user"]) if info else ("", "")
    if info and source == "compact":
        context = "Vừa compact xong: trạng thái dưới đây được nạp lại từ đĩa.\n" + context
    elif info and source == "resume" and info.get("after_interrupt"):
        steps = " | ".join(info["after_interrupt"][:6])
        context += f"\nPhiên vừa được resume. Trước khi làm tiếp, chạy các bước kiểm tra sau khi bị ngắt: {steps}"
    if hint:
        context = (context + "\n" + hint["context"]).strip()
        user = f"{user} · {hint['user']}" if user else hint["user"]
    if last:
        context = (context + "\n" + last["context"]).strip()
        user = f"{user}\n{last['user']}" if user else last["user"]
    if drift_note:
        context = drift_note + "\n" + context
        user = f"{drift_user} · {user}"
    A.emit("SessionStart", context, user)


def plugin_drift():
    """(context, dòng cho người dùng) khi plugin đã cài lệch bản đã kiểm duyệt, ví dụ vì marketplace
    tự cập nhật. Cả hai rỗng nếu ổn, không tìm được thư mục agent-stack, hoặc có lỗi khi kiểm."""
    try:
        home = A.home_dir()
        if not home:
            return "", ""
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "vet-skill" / "scripts"))
        import drift  # noqa: E402
        plugins = Path(os.environ.get("AGENT_STACK_PLUGINS_DIR") or "~/.claude/plugins").expanduser()
        rows = [r for r in drift.check(home, plugins) if r["status"] not in drift.OK_STATUSES]
    except Exception:  # kiểm phụ: lỗi ở đây không được làm mất phần còn lại của hook
        return "", ""
    try:  # MCP từ xa: đọc kết quả lần kiểm nền trước, và khởi lần mới nếu đã quá một ngày (không chờ)
        import mcp_remote  # noqa: E402
        saved = A.state_dir() / "mcp-drift.json"
        claude_json = mcp_remote.claude_json_path()
        rows += mcp_remote.saved_problems(saved, home, claude_json)
        mcp_remote.maybe_start_background(home, claude_json, saved)
    except Exception:
        pass
    if not rows:
        return "", ""
    try:
        names = ", ".join(r["plugin"] for r in rows[:5])
        detail = drift.render(rows, quiet=True).strip()
    except Exception:  # dòng lạ không được làm mất §0 và phần còn lại của hook
        return "", ""
    context = (f"[agent-stack] Plugin hay MCP lệch hoặc chưa qua bản đã kiểm duyệt: {names}. Báo cho người dùng "
               f"trước khi dùng chúng; kiểm lại bằng `vet.py drift` (MCP từ xa: `vet.py drift --remote`)."
               f"\n{A.clip(detail, 1200)}")
    return context, f"⚠️ Lệch bản đã kiểm duyệt: {names}"


if __name__ == "__main__":
    A.run_hook(main)
