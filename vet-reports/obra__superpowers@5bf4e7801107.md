# Kiểm duyệt: obra/superpowers

- Ngày: 2026-10-01 · Công cụ: vet.py/1 + skill-scanner 2.1.0
- Nguồn: github:obra/superpowers · Commit: `5bf4e78011075bcfc0dc295f0724994cd123ee71`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 293768 | 2026-09-27 | False | MIT | User |

File giấy phép: LICENSE: MIT

## Thống kê file

binary: 1, code: 88, md: 119, other: 23 · tổng 1927 KB

## Lý do

- ⚠️ [permission-bypass] Tắt cơ chế xin quyền của agent. (tests/claude-code/test-subagent-driven-development-integration.sh:167)
- ⚠️ [permission-bypass] Tắt cơ chế xin quyền của agent. (trong tài liệu, có thể chỉ là ví dụ) (×2, ví dụ docs/superpowers/plans/2026-03-23-codex-app-compatibility.md:566)
- ⚠️ [skill-scanner COMMAND_INJECTION_JS_CHILD_PROCESS] Node.js child_process module usage for shell command execution (mẫu lỗ hổng, có thể báo nhầm) (×2, ví dụ skills/brainstorming/scripts/server.cjs:537)
- ⚠️ Có 1 hook tự chạy khi dùng.
- ⚠️ Marketplace kéo plugin từ nguồn khác; phải kiểm từng nguồn.
- ⚠️ Có 88 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** 
  - `SessionStart` [startup|clear|compact] command: `"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" session-start` (hooks/hooks.json)
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** 
  - superpowers: `{"source": "url", "url": "./"}`

## Skill và agent

- `skills/using-git-worktrees`: name=`using-git-worktrees`, mô tả 196 ký tự
- `skills/test-driven-development`: name=`test-driven-development`, mô tả 79 ký tự
- `skills/systematic-debugging`: name=`systematic-debugging`, mô tả 91 ký tự
- `skills/using-superpowers`: name=`using-superpowers`, mô tả 154 ký tự
- `skills/dispatching-parallel-agents`: name=`dispatching-parallel-agents`, mô tả 106 ký tự
- `skills/executing-plans`: name=`executing-plans`, mô tả 170 ký tự
- `skills/finishing-a-development-branch`: name=`finishing-a-development-branch`, mô tả 101 ký tự
- `skills/brainstorming`: name=`brainstorming`, mô tả 198 ký tự
- `skills/diagnosing-superpowers`: name=`diagnosing-superpowers`, mô tả 375 ký tự
- `skills/writing-plans`: name=`writing-plans`, mô tả 84 ký tự
- `skills/requesting-code-review`: name=`requesting-code-review`, mô tả 107 ký tự
- `skills/receiving-code-review`: name=`receiving-code-review`, mô tả 234 ký tự
- `skills/writing-skills`: name=`writing-skills`, mô tả 97 ký tự
- `skills/verification-before-completion`: name=`verification-before-completion`, mô tả 225 ký tự
- `skills/subagent-driven-development`: name=`subagent-driven-development`, mô tả 85 ký tự

## Dấu hiệu (luật riêng)

| Mức | Luật | Vị trí | Loại file | Trích |
|---|---|---|---|---|
| high | permission-bypass | tests/claude-code/test-subagent-driven-development-integration.sh:167 | code | `cd "$TEST_PROJECT" && timeout 1800 claude -p "$PROMPT" --plugin-dir "$PLUGIN_DIR" --allowed-tools=all --permission-mode bypassPermissions 2>&1 \| tee "$OUTPUT_FI` |
| high | permission-bypass | docs/superpowers/plans/2026-03-23-codex-app-compatibility.md:566 | md | `Note: these tests require Claude Code with '--dangerously-skip-permissions'. If not available, document that regression tests should be run manually.` |
| high | permission-bypass | docs/superpowers/plans/2026-07-15-sdd-fix-loop-redesign.md:1553 | md | `'--dangerously-skip-permissions', need 'ANTHROPIC_API_KEY' and` |
| medium | permission-bypass | tests/explicit-skill-requests/run-test.sh:73 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-haiku-test.sh:57 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-haiku-test.sh:69 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-haiku-test.sh:81 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-haiku-test.sh:93 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-haiku-test.sh:106 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-multiturn-test.sh:51 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-multiturn-test.sh:65 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-multiturn-test.sh:79 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-extended-multiturn-test.sh:28 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-extended-multiturn-test.sh:39 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-extended-multiturn-test.sh:50 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-extended-multiturn-test.sh:61 | code | `--dangerously-skip-permissions \` |
| medium | permission-bypass | tests/explicit-skill-requests/run-extended-multiturn-test.sh:73 | code | `--dangerously-skip-permissions \` |

## skill-scanner

Đếm theo mức: critical=2, low=16, info=15
- critical · COMMAND_INJECTION_JS_CHILD_PROCESS · Node.js child_process module usage for shell command execution (skills/brainstorming/scripts/server.cjs:537)
- critical · COMMAND_INJECTION_JS_CHILD_PROCESS · Node.js child_process module usage for shell command execution (skills/writing-skills/render-graphs.js:18)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:93)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:138)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:202)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:203)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:217)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:409)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:433)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:515)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:620)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:673)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:676)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/brainstorming/scripts/server.cjs:688)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/writing-skills/render-graphs.js:121)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/writing-skills/render-graphs.js:142)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/writing-skills/render-graphs.js:147)
- low · DATA_EXFIL_JS_FS_ACCESS · Node.js filesystem access candidate for sensitive-flow correlation (skills/writing-skills/render-graphs.js:158)

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `.agents/plugins/marketplace.json`
- [ ] `.claude-plugin/marketplace.json`
- [ ] `.claude-plugin/plugin.json`
- [ ] `.codex-plugin/plugin.json`
- [ ] `.cursor-plugin/plugin.json`
- [ ] `.devin-plugin/plugin.json`
- [ ] `.hermes-plugin/__init__.py`
- [ ] `.kimi-plugin/plugin.json`
- [ ] `.muse-plugin/marketplace.json`
- [ ] `.muse-plugin/plugin.json`
- [ ] `.opencode/plugins/superpowers.js`
- [ ] `.pi/extensions/superpowers.ts`
- [ ] `docs/superpowers/plans/2026-03-23-codex-app-compatibility.md`
- [ ] `docs/superpowers/plans/2026-07-15-sdd-fix-loop-redesign.md`
- [ ] `hooks/hooks.json`
- [ ] `hooks/run-hook.cmd`
- [ ] `hooks/session-start`
- [ ] `index.js`
- [ ] `package.json`
- [ ] `scripts/bump-version.sh`
- [ ] `scripts/lint-shell.sh`
- [ ] `scripts/package-codex-plugin.sh`
- [ ] `scripts/sync-to-codex-plugin.sh`
- [ ] `skills/brainstorming/SKILL.md`
- [ ] `skills/brainstorming/scripts/helper.js`
- [ ] `skills/brainstorming/scripts/server.cjs`
- [ ] `skills/brainstorming/scripts/start-server.sh`
- [ ] `skills/brainstorming/scripts/stop-server.sh`
- [ ] `skills/diagnosing-superpowers/SKILL.md`
- [ ] `skills/dispatching-parallel-agents/SKILL.md`
- [ ] `skills/executing-plans/SKILL.md`
- [ ] `skills/executing-plans/scripts/task-done`
- [ ] `skills/executing-plans/scripts/task-start`
- [ ] `skills/finishing-a-development-branch/SKILL.md`
- [ ] `skills/receiving-code-review/SKILL.md`
- [ ] `skills/requesting-code-review/SKILL.md`
- [ ] `skills/subagent-driven-development/SKILL.md`
- [ ] `skills/subagent-driven-development/scripts/review-package`
- [ ] `skills/subagent-driven-development/scripts/sdd-workspace`
- [ ] `skills/subagent-driven-development/scripts/task-brief`
- [ ] `skills/systematic-debugging/SKILL.md`
- [ ] `skills/systematic-debugging/condition-based-waiting-example.ts`
- [ ] `skills/systematic-debugging/find-polluter.sh`
- [ ] `skills/test-driven-development/SKILL.md`
- [ ] `skills/using-git-worktrees/SKILL.md`
- [ ] `skills/using-superpowers/SKILL.md`
- [ ] `skills/verification-before-completion/SKILL.md`
- [ ] `skills/writing-plans/SKILL.md`
- [ ] `skills/writing-skills/SKILL.md`
- [ ] `skills/writing-skills/render-graphs.js`
- [ ] `tests/antigravity/run-tests.sh`
- [ ] `tests/antigravity/test-antigravity-tools.sh`
- [ ] `tests/brainstorm-server/auth.test.js`
- [ ] `tests/brainstorm-server/branding.test.js`
- [ ] `tests/brainstorm-server/browser-launcher.test.js`
- [ ] `tests/brainstorm-server/helper.test.js`
- [ ] `tests/brainstorm-server/lifecycle.test.js`
- [ ] `tests/brainstorm-server/package.json`
- [ ] `tests/brainstorm-server/server.test.js`
- [ ] `tests/brainstorm-server/start-server.test.sh`
- [ ] `tests/brainstorm-server/stop-server.test.sh`
- [ ] `tests/brainstorm-server/windows-lifecycle.test.sh`
- [ ] `tests/brainstorm-server/ws-protocol.test.js`
- [ ] `tests/claude-code/analyze-token-usage.py`
- [ ] `tests/claude-code/run-skill-tests.sh`
- [ ] `tests/claude-code/test-executing-plans-scripts.sh`
- [ ] `tests/claude-code/test-helpers.sh`
- [ ] `tests/claude-code/test-sdd-workspace.sh`
- [ ] `tests/claude-code/test-subagent-driven-development-integration.sh`
- [ ] `tests/claude-code/test-subagent-driven-development.sh`
- [ ] `tests/claude-code/test-worktree-native-preference.sh`
- [ ] `tests/claude-code/test-worktree-path-policy.sh`
- [ ] `tests/codex-plugin-sync/test-sync-to-codex-plugin.sh`
- [ ] `tests/codex/test-marketplace-manifest.sh`
- [ ] `tests/codex/test-package-codex-plugin.sh`
- [ ] `tests/devin/test-devin-plugin.sh`
- [ ] `tests/diagnosing-superpowers/test-skill-structure.sh`
- [ ] `tests/explicit-skill-requests/run-all.sh`
- [ ] `tests/explicit-skill-requests/run-extended-multiturn-test.sh`
- [ ] `tests/explicit-skill-requests/run-haiku-test.sh`
- [ ] `tests/explicit-skill-requests/run-multiturn-test.sh`
- [ ] `tests/explicit-skill-requests/run-test.sh`
- [ ] `tests/hermes/__init__.py`
- [ ] `tests/hermes/conftest.py`
- [ ] `tests/hermes/test_bootstrap.py`
- [ ] `tests/hermes/test_plugin.py`
- [ ] `tests/hooks/test-session-start.sh`
- [ ] `tests/kimi/run-tests.sh`
- [ ] `tests/kimi/test-plugin-manifest.sh`
- [ ] `tests/opencode/run-tests.sh`
- [ ] `tests/opencode/setup.sh`
- [ ] `tests/opencode/test-bootstrap-caching.mjs`
- [ ] `tests/opencode/test-bootstrap-caching.sh`
- [ ] `tests/opencode/test-plugin-loading.sh`
- [ ] `tests/opencode/test-priority.sh`
- [ ] `tests/opencode/test-session-bootstrap.mjs`
- [ ] `tests/opencode/test-session-bootstrap.sh`
- [ ] `tests/opencode/test-skill-registration.mjs`
- [ ] `tests/opencode/test-skill-registration.sh`
- [ ] `tests/opencode/test-tools.sh`
- [ ] `tests/pi/test-pi-extension.mjs`
- [ ] `tests/shell-lint/test-lint-shell.sh`
- [ ] `tests/systematic-debugging/test-find-polluter.sh`
- [ ] `tests/version-bump/test-bump-version.sh`
- [ ] `tests/writing-skills/test-render-graphs.sh`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).

## Nhận xét đọc tay của claude (2026-10-01, khuyến nghị: thử-1-project)

Hook SessionStart chèn toàn bộ skill using-superpowers vào context mỗi lần mở phiên, clear hoặc compact. Việc này tốn token ở mọi phiên và áp quy trình bắt buộc. 88 file mã, phần lớn là script test; hook không gọi mạng. Thử trong một project trước khi bật toàn cục. Trùng vai với bộ skill của Matt Pocock.
