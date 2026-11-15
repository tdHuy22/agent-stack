#!/usr/bin/env python3
"""Hook PostToolUse sau ExitPlanMode (GĐ5, ý 5 của kế hoạch agent-stack theo project): chấm model cho từng bước của
kế hoạch phiên vừa được người dùng duyệt.

Hook chạy `route.py --plan-steps` bằng subprocess (kế hoạch qua stdin), không import router: luật "hook chỉ import
plugin/lib" giữ nguyên, còn dời router vào lib thì làm hỏng các test khóa đang patch `route.rules`, `route.apply_stack`
(ngoại lệ có chủ ý, kế hoạch GĐ5 bạn duyệt 15/11/2026). Router chấm mỗi bước bằng lớp từ khóa và mức sàn của project;
bước nào lớp từ khóa không chắc thì hỏi lớp model một lần cho cả nhóm (chờ tới `plan_wait_s`). Chỉ báo bước khai mức
dưới sàn của project hay bước bảo mật khai dưới gợi ý; không có gì thì im. Model của phiên có quyền cuối.

Tách khỏi plan_exit.py (ghi tiêu chí xong vào §0) để lớp model chậm không làm mất phần ghi tiêu chí. Mọi lỗi thì im
lặng, thoát 0. pi không có plan mode nên không chạy hook này.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402

ROUTE = Path(__file__).resolve().parents[1] / "skills" / "task-router" / "scripts" / "route.py"
LIMIT_S = 9.0  # dưới timeout 10 giây của hook trong hooks.json
MAX_PLAN = 20_000


def plan_text(data) -> str:
    """Như plan_exit.plan_text: `tool_response.plan`, dự phòng `tool_input.plan`."""
    for key in ("tool_response", "tool_input"):
        value = data.get(key)
        if isinstance(value, dict) and isinstance(value.get("plan"), str):
            return value["plan"][:MAX_PLAN]
        if key == "tool_response" and isinstance(value, str):
            return value[:MAX_PLAN]
    return ""


def main():
    data = A.read_hook_input()
    if data.get("tool_name") not in (None, "ExitPlanMode"):
        return
    response = data.get("tool_response")
    if data.get("agent_id") or (isinstance(response, dict) and response.get("isAgent")):
        return  # ExitPlanMode của subagent: người dùng chưa duyệt gì
    plan = plan_text(data)
    cwd = data.get("cwd")
    if not plan.strip() or not isinstance(cwd, str) or not cwd:
        return
    try:
        out = subprocess.run([sys.executable, str(ROUTE), "--plan-steps", "--cwd", cwd], input=plan,
                             capture_output=True, text=True, timeout=LIMIT_S)
        if out.returncode != 0:
            A.log_event("hook-error", {"hook": "plan-steps", "error": f"route.py mã {out.returncode}: "
                                                                    + (out.stderr or "")[-200:]})
            return
        context = json.loads(out.stdout).get("context") if out.stdout.strip() else ""
    except (subprocess.TimeoutExpired, OSError, ValueError, AttributeError) as exc:
        A.log_event("hook-error", {"hook": "plan-steps", "error": repr(exc)[:300]})
        return
    A.log_event("plan-steps", {"session": data.get("session_id"), "noted": bool(context)})
    if isinstance(context, str) and context:
        A.emit("PostToolUse", context)


if __name__ == "__main__":
    A.run_hook(main)
