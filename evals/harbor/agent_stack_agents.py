"""Agent Claude Code cho Harbor: bản trơn và bản có agent-stack, để so ghép cặp trên cùng bộ việc (xem README.md).

Bản có agent-stack dựng lại đúng cách dùng trên máy Mac:
- luật chung `global/CLAUDE.global.md` làm CLAUDE.md cấp người dùng; file này nhập `global/SHARED.global.md` qua
  `@~/Documents/Claude/agent-stack/...`, nên bản chép đặt ở `$HOME/Documents/Claude/agent-stack` trong container để mọi
  đường dẫn trong luật (script của skill, bảng chọn model) trỏ đúng;
- plugin agent-stack (hook, skill, subagent) nạp bằng `--plugin-dir`.
Hai bản dùng cùng model, effort và phiên bản Claude Code (đặt trong cấu hình job), chỉ khác hai điểm trên.

File này chạy trong venv của Harbor trên TUF (import harbor), nên là ngoại lệ của luật "Python chỉ dùng thư viện
chuẩn"; bộ test của repo không import nó.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path

from harbor.agents.installed.claude_code import ClaudeCode

# Bản chép agent-stack (git archive của một commit), do `tuf.sh sync` đặt cạnh file này.
PAYLOAD = Path(os.environ.get("AGENT_STACK_PAYLOAD") or Path(__file__).resolve().parent / "payload")
REMOTE_STAGE = "/tmp/agent-stack-payload"
HOME_REL = "Documents/Claude/agent-stack"


class ClaudeCodePlain(ClaudeCode):
    """Claude Code không có agent-stack: giống agent `claude-code` của Harbor, chỉ khác tên để tách kết quả."""

    @staticmethod
    def name() -> str:
        return "claude-code-plain"


class ClaudeCodeAgentStack(ClaudeCode):
    """Claude Code có luật chung và plugin agent-stack."""

    @staticmethod
    def name() -> str:
        return "claude-code-agent-stack"

    async def install(self, environment) -> None:
        await super().install(environment)
        if not (PAYLOAD / ".agent-stack-root").exists():
            raise RuntimeError(f"Thiếu bản chép agent-stack ở {PAYLOAD}: chạy `evals/harbor/tuf.sh sync` từ máy Mac")
        await environment.upload_dir(PAYLOAD, REMOTE_STAGE)
        await self.exec_as_root(environment, command=f"chmod -R a+rX {REMOTE_STAGE}")
        await self.exec_as_agent(environment, command=(
            f'set -e; dest="$HOME/{HOME_REL}"; rm -rf "$dest"; mkdir -p "$(dirname "$dest")"; '
            f'cp -R {REMOTE_STAGE} "$dest"; '
            # hook của agent-stack gọi python3; thiếu thì ghi lại để lúc so kết quả biết lượt đó chạy thiếu hook
            'command -v python3 >/dev/null 2>&1 || echo "agent-stack: container không có python3, hook sẽ không chạy" >&2'))

    def build_cli_flags(self) -> str:
        return " ".join(x for x in (super().build_cli_flags(), f'--plugin-dir "$HOME/{HOME_REL}/plugin"') if x)

    async def run(self, instruction, environment, context) -> None:
        # Harbor đặt CLAUDE_CONFIG_DIR riêng cho mỗi lượt (thư mục log), nên CLAUDE.md cấp người dùng phải nằm ở đó;
        # chép thêm vào ~/.claude cho chắc. Lệnh dựng thư mục của ClaudeCode.run chỉ mkdir -p, không xoá file này.
        config_dir = shlex.quote((self.environment_logs_dir / "sessions").as_posix())
        rules = f'"$HOME/{HOME_REL}/global/CLAUDE.global.md"'
        await self.exec_as_agent(environment, command=(
            f'mkdir -p {config_dir} "$HOME/.claude" && cp {rules} {config_dir}/CLAUDE.md && cp {rules} "$HOME/.claude/CLAUDE.md"'))
        await super().run(instruction, environment, context)
