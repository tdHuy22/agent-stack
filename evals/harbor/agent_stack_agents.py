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

import asyncio
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

# Cài trước các gói còn thiếu trong bộ mà ClaudeCode.install của Harbor đòi (lệnh curl, bash, node, npm, pgrep), có hẹn
# giờ và thử lại. Ca 07/11/2026 trên tuf: khi vài container cùng xin một tệp InRelease đúng lúc apt-cacher-ng hỏi lại máy
# gốc, bộ đệm trả phần đầu không kèm nội dung và apt-get chờ mãi (tái hiện 1 trên 3 container). Harbor không hẹn giờ bước
# này, nên lượt hỏng vì hết giờ dựng agent (360 giây × 3). Ở đây: quá giờ thì dừng apt; lần thứ hai bỏ bộ đệm, đi thẳng;
# tổng tối đa 2 × (90 + 300) giây; vẫn hỏng thì Harbor tự cài như cũ (nó bỏ qua lệnh đã có). Đầu ra của apt ghi vào file
# để tiến trình con mồ côi của apt không giữ đầu ra của `docker exec`. Hẹn giờ bằng vòng kiểm từng giây: không cần
# `timeout` (image tối giản có thể thiếu) và không để lại `sleep` mồ côi.
APT_PREINSTALL = (
    'wd_update=90; wd_install=300; log=/tmp/agent-stack-apt.log; export DEBIAN_FRONTEND=noninteractive; '
    'run_wd() { s=$1; shift; "$@" </dev/null >>"$log" 2>&1 & p=$!; n=0; '
    'while kill -0 "$p" 2>/dev/null; do if [ "$n" -ge "$s" ]; then kill "$p" 2>/dev/null; break; fi; '
    'sleep 1; n=$((n+1)); done; wait "$p"; }; '
    'pk=""; command -v curl >/dev/null 2>&1 || pk="$pk curl"; command -v bash >/dev/null 2>&1 || pk="$pk bash"; '
    'command -v node >/dev/null 2>&1 || pk="$pk nodejs"; command -v npm >/dev/null 2>&1 || pk="$pk npm"; '
    'command -v pgrep >/dev/null 2>&1 || pk="$pk procps"; '
    'if [ -n "$pk" ] && command -v apt-get >/dev/null 2>&1; then '
    'for i in 1 2; do '
    'find /var/lib/apt/lists/partial /var/cache/apt/archives/partial -type f -size 0 -delete 2>/dev/null; '
    'dpkg --configure -a >/dev/null 2>&1; '
    'run_wd "$wd_update" apt-get update && '
    'run_wd "$wd_install" apt-get install -y -o DPkg::Lock::Timeout=60 $pk && break; '
    'echo "agent-stack: apt lần $i hỏng hay quá giờ; bỏ bộ đệm, đi thẳng" >&2; tail -5 "$log" >&2; '
    'rm -f /etc/apt/apt.conf.d/99agent-stack-proxy; '
    'done; fi; true'
)

# Cài lại một lần khi bước cài của Harbor hỏng. Ca 08/11/2026 trên tuf: apt-cacher-ng giữ InRelease của bookworm-updates và
# bookworm-security ghép lẫn hai bản (180 byte đầu của bản mới, phần còn lại và chữ ký của bản cũ, cùng độ dài), nên apt báo
# BADSIG; 13/25 lượt đầu pilot hỏng ở `apt-get update` của Harbor, trước khi gọi model. Lần hai: hoàn tất dpkg dở, gỡ proxy,
# xóa phần tải dở, đi thẳng tới máy gốc (đã thử: apt không dùng lại InRelease hỏng của lần trước). Không xóa danh sách gói:
# lần hai có thể không chạy `apt-get update`, và agent của riêng lượt đó sẽ không cài được gói. Vẫn hỏng thì báo
# AgentInstallError, Harbor chạy lại cả lượt trong môi trường mới (harbor_bench.py INFRA_RETRY). Như nhau ở bốn cấu hình.
INSTALL_RETRY_WAIT = 30         # giây chờ trước lần cài thứ hai
APT_GO_DIRECT = (
    'DEBIAN_FRONTEND=noninteractive dpkg --configure -a </dev/null >/dev/null 2>&1; '
    'rm -f /etc/apt/apt.conf.d/99agent-stack-proxy; '
    'rm -rf /var/lib/apt/lists/partial/* 2>/dev/null; true'
)


class AgentInstallError(RuntimeError):
    """Cài Claude Code hỏng cả hai lần, trước khi gọi model: lỗi hạ tầng, Harbor thử lại cả lượt."""


def _short(exc: BaseException, head: int = 200, tail: int = 400) -> str:
    """Giữ đầu (lệnh) và đuôi (lỗi thật của apt nằm cuối đầu ra)."""
    text = f"{type(exc).__name__}: {exc}"
    return text if len(text) <= head + tail else text[:head] + " … " + text[-tail:]


class _Probed(ClaudeCode):
    """Khung chung: ghi tình trạng container trước lượt chạy."""

    VARIANT = "plain"

    async def install(self, environment) -> None:
        # Ca 06/11/2026 trên tuf: apt trong container qua mạng bridge của Docker chỉ ~49 kB/s và báo "package cache
        # file is corrupted, it has the wrong hash"; tắt HTTP pipelining thì 6,6 MB/s. Harbor cài Claude Code bằng
        # apt-get, nên tắt pipelining trước, như nhau cho cả bốn cấu hình. Image không có apt thì bỏ qua.
        # Ca 07/11/2026: vẫn có kết nối tới deb.debian.org chỉ 181 kB/s (22 phút cho nodejs), nên dùng bộ đệm
        # apt-cacher-ng trên máy chủ (cổng 3142) qua gateway của mạng container, khi tới được trong 3 giây; không tới
        # được thì apt đi thẳng như cũ. File proxy giữ nguyên suốt lượt, như nhau ở bốn cấu hình, nên apt-cacher-ng phải
        # chạy suốt job.
        await self.exec_as_root(environment, command=(
            'if [ -d /etc/apt/apt.conf.d ]; then '
            'printf \'Acquire::http::Pipeline-Depth "0";\\n\' > /etc/apt/apt.conf.d/99agent-stack-no-pipelining; '
            'gw=$(awk \'$2=="00000000" {print $3; exit}\' /proc/net/route 2>/dev/null); '
            'if [ "${#gw}" -eq 8 ] && command -v bash >/dev/null 2>&1; then '
            'ip=$(printf "%d.%d.%d.%d" "0x$(echo "$gw" | cut -c7-8)" "0x$(echo "$gw" | cut -c5-6)" '
            '"0x$(echo "$gw" | cut -c3-4)" "0x$(echo "$gw" | cut -c1-2)"); '
            'bash -c "exec 3<>/dev/tcp/$ip/3142" </dev/null >/dev/null 2>&1 & p=$!; n=0; '
            'while kill -0 "$p" 2>/dev/null && [ "$n" -lt 3 ]; do sleep 1; n=$((n+1)); done; '
            'kill "$p" 2>/dev/null; '
            'if wait "$p"; then '
            'printf \'Acquire::http::Proxy "http://%s:3142";\\n\' "$ip" > /etc/apt/apt.conf.d/99agent-stack-proxy; '
            'fi; fi; fi'))
        await self.exec_as_root(environment, command=APT_PREINSTALL)
        try:
            await super().install(environment)
        except Exception as first:      # CancelledError (hết giờ cài) không bắt: Harbor tự báo AgentSetupTimeoutError
            await asyncio.sleep(INSTALL_RETRY_WAIT)
            try:
                await self.exec_as_root(environment, command=APT_GO_DIRECT)
                await super().install(environment)
            except Exception as second:
                raise AgentInstallError(
                    f"Cài Claude Code hỏng hai lần. Lần 1: {_short(first)} | Lần 2 (đi thẳng): {_short(second)}") from second

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
            'echo "apt_proxy=$(yn /etc/apt/apt.conf.d/99agent-stack-proxy)"; '
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
