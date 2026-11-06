"""Bốn agent Claude Code cho Harbor, để so trên cùng bộ việc (xem README.md).

1. ClaudeCodePlain: Claude Code trơn. Không CLAUDE.md cấp người dùng, không plugin; trước mỗi lượt xóa mọi thứ đó nếu image
   lỡ có sẵn.
2. ClaudeCodeAgentStack: luật chung `global/CLAUDE.global.md` làm CLAUDE.md cấp người dùng + plugin agent-stack nạp bằng
   `--plugin-dir`. Bản chép đặt ở `$HOME/Documents/Claude/agent-stack` trong container, vì luật nhập
   `@~/Documents/Claude/agent-stack/global/SHARED.global.md` và nhắc script ở đường dẫn đó.
3. ClaudeCodeAgentStackNoHooks: như 2, bản chép plugin bỏ `plugin/hooks/hooks.json` nên không hook nào chạy.
4. ClaudeCodeAgentStackNoAgents: như 2, bản chép plugin bỏ thư mục `plugin/agents/` (subagent riêng của agent-stack;
   subagent có sẵn của Claude Code vẫn dùng được).

Bốn bản dùng cùng model, effort, phiên bản Claude Code (đặt trong cấu hình job). Bản 3 và 4 do `harbor_bench.py
build-payload` dựng lúc `tuf.sh sync` từ cùng một bản chép; không sửa `plugin/` thật.

Mỗi lượt ghi `agent-stack-env.txt` vào thư mục log của agent: phiên bản python3 trong container (hook cần python3 từ 3.9),
commit của bản chép và cấu trúc thật của nó; `harbor_bench.py compare` đọc file này.

File này chạy trong venv của Harbor trên TUF (import harbor), nên là ngoại lệ của luật "Python chỉ dùng thư viện chuẩn";
bộ test của repo không import nó (test chỉ đọc cú pháp).

API Harbor dùng (đã đọc ở tag v0.25.0): ClaudeCode kế thừa BaseInstalledAgent; `install`, `run`, `build_cli_flags`,
`exec_as_agent`, `exec_as_root`, `environment_logs_dir`, `environment.upload_dir`.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path

from harbor.agents.installed.claude_code import ClaudeCode

# Gốc các bản chép (git archive của một commit, đã lọc theo danh sách cho phép), do `tuf.sh sync` đặt cạnh file này:
# <gốc>/full, <gốc>/nohooks, <gốc>/noagents.
PAYLOAD = Path(os.environ.get("AGENT_STACK_PAYLOAD") or Path(__file__).resolve().parent / "payload")
REMOTE_STAGE = "/tmp/agent-stack-payload"
HOME_REL = "Documents/Claude/agent-stack"
ENV_FILE = "agent-stack-env.txt"


class _Probed(ClaudeCode):
    """Khung chung: ghi tình trạng container trước lượt chạy."""

    VARIANT = "plain"

    async def _write_env_file(self, environment) -> None:
        out = shlex.quote((self.environment_logs_dir / ENV_FILE).as_posix())
        root = f'"$HOME/{HOME_REL}"'
        # Harbor đặt CLAUDE_CONFIG_DIR=<logs>/sessions: CLAUDE.md cấp người dùng mà Claude Code thật sự đọc nằm ở đó
        config_md = shlex.quote((self.environment_logs_dir / "sessions" / "CLAUDE.md").as_posix())
        await self.exec_as_agent(environment, command=(
            f'out={out}; py=$(command -v python3 2>/dev/null || true); ver=""; '
            'if [ -n "$py" ]; then ver=$("$py" -c \'import sys; print("%d.%d.%d" % sys.version_info[:3])\' '
            '2>/dev/null || true); fi; '
            'yn() { if [ -e "$1" ]; then echo yes; else echo no; fi; }; '
            '{ '
            f'echo "variant={self.VARIANT}"; echo "python3=$ver"; '
            f'echo "payload_commit=$(cat {root}/.payload-commit 2>/dev/null || true)"; '
            'echo "user_claude_md=$(yn "$HOME/.claude/CLAUDE.md")"; '
            f'echo "config_claude_md=$(yn {config_md})"; '
            f'echo "plugin_dir=$(yn {root}/plugin)"; echo "hooks_json=$(yn {root}/plugin/hooks/hooks.json)"; '
            f'echo "agents_dir=$(yn {root}/plugin/agents)"; '
            '} > "$out"'))


class ClaudeCodePlain(_Probed):
    """Claude Code không có agent-stack: giống agent `claude-code` của Harbor, chỉ khác tên để tách kết quả."""

    VARIANT = "plain"

    @staticmethod
    def name() -> str:
        return "claude-code-plain"

    async def run(self, instruction, environment, context) -> None:
        # Harbor đặt CLAUDE_CONFIG_DIR riêng cho mỗi lượt (thư mục log), nên thường không có gì để xóa; xóa thêm ở
        # ~/.claude phòng image lỡ có sẵn luật hay plugin, để bản trơn chắc chắn trơn.
        await self.exec_as_agent(environment, command=(
            'rm -rf "$HOME/.claude/CLAUDE.md" "$HOME/.claude/skills" "$HOME/.claude/plugins" "$HOME/.claude/agents" '
            f'{shlex.quote((self.environment_logs_dir / "sessions" / "CLAUDE.md").as_posix())}'))
        await self._write_env_file(environment)
        await super().run(instruction, environment, context)


class ClaudeCodeAgentStack(_Probed):
    """Claude Code có luật chung và plugin agent-stack (đủ hook, skill, subagent)."""

    VARIANT = "full"   # thư mục con của PAYLOAD

    @staticmethod
    def name() -> str:
        return "claude-code-agent-stack"

    async def install(self, environment) -> None:
        await super().install(environment)
        src = PAYLOAD / self.VARIANT
        if not (src / ".agent-stack-root").exists():
            raise RuntimeError(f"Thiếu bản chép agent-stack ở {src}: chạy `evals/harbor/tuf.sh sync` từ máy Mac")
        await environment.upload_dir(src, REMOTE_STAGE)
        await self.exec_as_root(environment, command=f"chmod -R a+rX {REMOTE_STAGE}")
        await self.exec_as_agent(environment, command=(
            f'set -e; dest="$HOME/{HOME_REL}"; rm -rf "$dest"; mkdir -p "$(dirname "$dest")"; '
            f'cp -R {REMOTE_STAGE} "$dest"'))

    def build_cli_flags(self) -> str:
        return " ".join(x for x in (super().build_cli_flags(), f'--plugin-dir "$HOME/{HOME_REL}/plugin"') if x)

    async def run(self, instruction, environment, context) -> None:
        # CLAUDE.md cấp người dùng phải nằm ở thư mục cấu hình của lượt này; chép thêm vào ~/.claude cho chắc. Lệnh dựng
        # thư mục của ClaudeCode.run chỉ mkdir -p, không xóa file này.
        config_dir = shlex.quote((self.environment_logs_dir / "sessions").as_posix())
        rules = f'"$HOME/{HOME_REL}/global/CLAUDE.global.md"'
        await self.exec_as_agent(environment, command=(
            f'mkdir -p {config_dir} "$HOME/.claude" && cp {rules} {config_dir}/CLAUDE.md && '
            f'cp {rules} "$HOME/.claude/CLAUDE.md"'))
        await self._write_env_file(environment)
        await super().run(instruction, environment, context)


class ClaudeCodeAgentStackNoHooks(ClaudeCodeAgentStack):
    """Như bản đủ, bản chép bỏ `plugin/hooks/hooks.json`: không hook nào chạy."""

    VARIANT = "nohooks"

    @staticmethod
    def name() -> str:
        return "claude-code-agent-stack-nohooks"


class ClaudeCodeAgentStackNoAgents(ClaudeCodeAgentStack):
    """Như bản đủ, bản chép bỏ `plugin/agents/`: không có subagent riêng của agent-stack."""

    VARIANT = "noagents"

    @staticmethod
    def name() -> str:
        return "claude-code-agent-stack-noagents"
