#!/usr/bin/env python3
"""Hook SessionStart: nạp lại trạng thái project từ đĩa khi mở, resume, clear hoặc sau compact.

Project không có file kế hoạch (PLAN.md §0, .agent/HANDOFF.md...) thì hook im lặng.
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
                                  "model": data.get("model")}, "sessions.jsonl")
    if sid:
        sessions = A.state_dir() / "sessions"
        sessions.mkdir(exist_ok=True)
        A.prune(sessions, 14)
        A.prune(A.state_dir() / "once", 8)
        name = hashlib.sha1(sid.encode()).hexdigest()[:16] + ".json"
        A.write_json_atomic(sessions / name, {"session": sid, "model": data.get("model"),
                                              "effort": (data.get("effort") or {}).get("level"),
                                              "cwd": str(root), "ts": time.time()})
    try:  # bản tóm tắt giàu hơn của skill tien-do; không có thì dùng bản của thư viện
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "tien-do" / "scripts"))
        import collect  # noqa: E402
        info = collect.brief(root)
    except ImportError:
        info = A.brief(root)
    if not info:
        return
    context = info["context"]
    if source == "compact":
        context = "Vừa compact xong: trạng thái dưới đây được nạp lại từ đĩa.\n" + context
    elif source == "resume" and info.get("after_interrupt"):
        steps = " | ".join(info["after_interrupt"][:6])
        context += f"\nPhiên vừa được resume. Trước khi làm tiếp, chạy các bước kiểm tra sau khi bị ngắt: {steps}"
    A.emit("SessionStart", context, info["user"])


if __name__ == "__main__":
    A.run_hook(main)
