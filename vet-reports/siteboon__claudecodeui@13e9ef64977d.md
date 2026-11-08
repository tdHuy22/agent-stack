# Kiểm duyệt: siteboon/claudecodeui

- Ngày: 2026-11-06 · Công cụ: vet.py/1 + skill-scanner 2.1.0 + SkillSpector 2.12.0
- Nguồn: github:siteboon/claudecodeui · Commit: `13e9ef64977d909eaf881eb83fec250c679f3d5c`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 14470 | 2026-11-04 | False | AGPL-3.0 | Organization |

File giấy phép: LICENSE: AGPL

## Thống kê file

binary: 21, code: 558, md: 29, other: 481 · tổng 10660 KB

## Lý do

- ⚠️ [credential-access] Đọc khóa SSH, token, keychain hoặc dữ liệu đăng nhập trình duyệt. (trong tài liệu, có thể chỉ là ví dụ) (README.md:196)
- ⚠️ [credential-access] Đọc khóa SSH, token, keychain hoặc dữ liệu đăng nhập trình duyệt. (×4, ví dụ server/shared/tests/image-attachments.test.ts:334)
- ⚠️ [permission-bypass] Tắt cơ chế xin quyền của agent. (×142, ví dụ server/modules/websocket/tests/shell-websocket.service.test.ts:125)
- ⚠️ [permission-bypass] Tắt cơ chế xin quyền của agent. (trong tài liệu, có thể chỉ là ví dụ) (×2, ví dụ docs/README.id.md:151)
- ⚠️ package.json có script tự chạy khi cài.
- ⚠️ Có 558 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** 
  - `postinstall`: `node scripts/fix-node-pty.js`
  - `prepare`: `husky`
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- `.agents/skills/backend-module-standards`: name=`backend-module-standards`, mô tả 326 ký tự
- `.agents/skills/frontend-module-standards`: name=`frontend-module-standards`, mô tả 377 ký tự

## Dấu hiệu (luật riêng)

| Mức | Luật | Vị trí | Loại file | Trích |
|---|---|---|---|---|
| high | credential-access | README.md:196 | md | `- **'git@' URLs:** give that user an SSH key the git host accepts and that works without a prompt: either it has no passphrase, or it is loaded into an 'ssh-age` |
| high | credential-access | server/shared/tests/image-attachments.test.ts:334 | code | `assert.equal(isAllowedImageSourcePath(path.join(os.homedir(), '.ssh', 'id_rsa'), cwd), false);` |
| high | credential-access | server/shared/tests/image-attachments.test.ts:342 | code | `const outsidePath = path.join(os.homedir(), '.ssh', 'id_rsa.png');` |
| high | credential-access | server/modules/websocket/tests/chat-attachment-filter.test.ts:31 | code | `{ path: 'C:/Users/victim/.ssh/id_rsa' },` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:125 | code | `test('bypassPermissions launches claude with --dangerously-skip-permissions', () => {` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:145 | code | `bypassPermissions: true,` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:162 | code | `assert.deepEqual(spawnedCommands, ['claude --dangerously-skip-permissions', 'claude']);` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:165 | code | `test('bypassPermissions carries through to resumed claude sessions', () => {` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:185 | code | `bypassPermissions: true,` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:193 | code | `'claude --resume "resumed-session-id" --dangerously-skip-permissions \|\| claude --dangerously-skip-permissions'` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:335 | code | `launch(dependencies, { provider: 'claude', colorScheme: 'dark', bypassPermissions: true }, projectPath);` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:345 | code | `'claude --dangerously-skip-permissions',` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:553 | code | `{ hasSession: true, provider: 'claude', bypassPermissions: true, colorScheme: 'light' },` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:559 | code | `const flags = ' --dangerously-skip-permissions${themeFlag('light')}';` |
| high | permission-bypass | server/modules/websocket/tests/shell-websocket.service.test.ts:728 | code | `const loginCommand = 'claude --dangerously-skip-permissions /login';` |
| high | permission-bypass | server/modules/websocket/services/shell-websocket.service.ts:22 | code | `bypassPermissions?: boolean;` |
| high | permission-bypass | server/modules/websocket/services/shell-websocket.service.ts:256 | code | `const bypassFlag = readBoolean(message.bypassPermissions)` |
| high | permission-bypass | server/modules/websocket/services/shell-websocket.service.ts:257 | code | `? ' --dangerously-skip-permissions'` |
| high | credential-access | server/modules/plugins/plugin-git.service.ts:49 | code | `+ 'and the host in its ~/.ssh/known_hosts, then try again.',` |
| high | permission-bypass | server/modules/providers/tests/codex-runtime.test.ts:12 | code | `for (const permissionMode of [undefined, 'default', 'unknown', 'acceptEdits', 'bypassPermissions']) {` |
| high | permission-bypass | server/modules/providers/tests/codex-runtime.test.ts:53 | code | `assert.equal(capturedOptions?.sandboxMode, permissionMode === 'bypassPermissions' ? 'danger-full-access' : 'workspace-write');` |
| high | permission-bypass | server/modules/providers/tests/codex-runtime.test.ts:54 | code | `assert.equal(capturedOptions?.approvalPolicy, permissionMode === 'acceptEdits' \|\| permissionMode === 'bypassPermissions' ? 'never' : 'on-request');` |
| high | permission-bypass | server/modules/providers/tests/opencode-runtime.test.ts:374 | code | `test('bypassPermissions answers permissions and questions without asking anyone', async () => {` |
| high | permission-bypass | server/modules/providers/tests/opencode-runtime.test.ts:376 | code | `permissionMode: 'bypassPermissions',` |
| high | permission-bypass | server/modules/providers/tests/opencode-runtime.test.ts:698 | code | `assert.equal(resolveAutomaticPermissionReply('bypassPermissions', 'bash'), 'once');` |
| high | permission-bypass | server/modules/providers/list/cursor/cursor-runtime.provider.js:21 | code | `/pass --trust,\s*--yolo,\s*or -f/i` |
| high | permission-bypass | server/modules/providers/list/claude/claude-runtime.provider.ts:333 | code | `sdkOptions.permissionMode = 'bypassPermissions';` |
| high | permission-bypass | server/modules/providers/list/claude/claude-runtime.provider.ts:1151 | code | `if (sdkOptions.permissionMode === 'bypassPermissions') {` |
| high | permission-bypass | server/modules/providers/list/codex/codex-runtime.provider.ts:237 | code | `case 'bypassPermissions':` |
| high | permission-bypass | server/modules/providers/list/opencode/opencode-runtime.provider.ts:219 | code | `if (permissionMode === 'bypassPermissions') {` |
| high | permission-bypass | server/modules/providers/list/opencode/opencode-runtime.provider.ts:1022 | code | `if (permissionMode === 'bypassPermissions' \|\| request.questions.length === 0) {` |
| high | permission-bypass | server/modules/providers/list/opencode/opencode-runtime.provider.ts:1248 | code | `if (permissionMode !== 'bypassPermissions') {` |
| high | permission-bypass | server/modules/providers/services/provider-capabilities.service.ts:57 | code | `permissionModes: ['default', 'auto', 'acceptEdits', 'bypassPermissions', 'plan'],` |
| high | permission-bypass | server/modules/providers/services/provider-capabilities.service.ts:73 | code | `permissionModes: ['default', 'acceptEdits', 'bypassPermissions', 'plan'],` |
| high | permission-bypass | server/modules/providers/services/provider-capabilities.service.ts:87 | code | `permissionModes: ['default', 'acceptEdits', 'bypassPermissions'],` |
| high | permission-bypass | server/modules/providers/services/provider-capabilities.service.ts:110 | code | `permissionModes: ['default', 'acceptEdits', 'bypassPermissions', 'plan'],` |
| high | permission-bypass | server/modules/agent/agent.routes.ts:1050 | code | `permissionMode: 'bypassPermissions' // Bypass all permissions for API calls` |
| high | permission-bypass | server/modules/agent/agent.routes.ts:1072 | code | `permissionMode: 'bypassPermissions'` |
| high | permission-bypass | server/modules/agent/agent.routes.ts:1083 | code | `permissionMode: 'bypassPermissions' // Agent runs are non-interactive, like the other providers above` |
| high | permission-bypass | server/modules/git/git.routes.ts:1190 | code | `permissionMode: 'bypassPermissions',` |
| high | permission-bypass | docs/README.id.md:151 | md | `Gunakan Pengaturan Tools untuk membatasi tools yang dapat digunakan. Permintaan API non-interaktif menggunakan 'bypassPermissions', sehingga tools yang tersedia` |
| high | permission-bypass | docs/architecture/02-realtime-stream.md:389 | md | `answers later matching requests itself. In bypassPermissions (also how '/api/agent'` |
| high | permission-bypass | src/shared/types.ts:293 | code | `export type PermissionMode = 'default' \| 'acceptEdits' \| 'auto' \| 'bypassPermissions' \| 'plan';` |
| high | permission-bypass | src/shared/types.ts:1424 | code | `export type CodexPermissionMode = 'default' \| 'acceptEdits' \| 'bypassPermissions';` |
| high | permission-bypass | src/modules/provider-auth/ProviderLoginModal.tsx:47 | other | `return 'claude --dangerously-skip-permissions /login';` |
| high | permission-bypass | src/modules/provider-auth/ProviderLoginModal.tsx:62 | other | `return 'claude --dangerously-skip-permissions /login';` |
| high | permission-bypass | src/modules/settings/tabs/agents-settings/sections/content/PermissionsContent.tsx:545 | other | `className={'cursor-pointer rounded-lg border p-4 transition-all ${permissionMode === 'bypassPermissions'` |
| high | permission-bypass | src/modules/settings/tabs/agents-settings/sections/content/PermissionsContent.tsx:549 | other | `onClick={() => onPermissionModeChange('bypassPermissions')}` |
| high | permission-bypass | src/modules/settings/tabs/agents-settings/sections/content/PermissionsContent.tsx:555 | other | `checked={permissionMode === 'bypassPermissions'}` |
| high | permission-bypass | src/modules/settings/tabs/agents-settings/sections/content/PermissionsContent.tsx:556 | other | `onChange={() => onPermissionModeChange('bypassPermissions')}` |
| high | permission-bypass | src/modules/settings/tabs/agents-settings/sections/content/PermissionsContent.tsx:561 | other | `{t('permissions.codex.modes.bypassPermissions.title')}` |
| high | permission-bypass | src/modules/settings/tabs/agents-settings/sections/content/PermissionsContent.tsx:565 | other | `{t('permissions.codex.modes.bypassPermissions.description')}` |
| high | permission-bypass | src/modules/settings/tabs/agents-settings/sections/content/PermissionsContent.tsx:578 | other | `<p><strong>{t('permissions.codex.modes.bypassPermissions.title')}:</strong> {t('permissions.codex.technicalInfo.bypassPermissions')}</p>` |
| high | permission-bypass | src/modules/settings/hooks/useSettingsController.ts:69 | code | `if (value === 'acceptEdits' \|\| value === 'bypassPermissions') {` |
| high | permission-bypass | src/modules/chat/tools/BashEditDiff.tsx:111 | other | `* 'bypassPermissions' modes (or when 'bashEditDiffEnabled' turns it on).` |
| high | permission-bypass | src/modules/chat/composer/ComposerPermissionMenu.tsx:56 | other | `bypassPermissions: {` |
| high | permission-bypass | src/modules/chat/tests/composerPermissionMenu.test.tsx:18 | other | `const MODES = ['default', 'auto', 'acceptEdits', 'bypassPermissions', 'plan'] as const;` |
| high | permission-bypass | src/modules/chat/tests/composerPermissionMenu.test.tsx:76 | other | `['bypassPermissions', 'Bypass Permissions'],` |
| high | permission-bypass | src/modules/chat/hooks/useChatProviderState.ts:50 | code | `claude: ['default', 'auto', 'acceptEdits', 'bypassPermissions', 'plan'],` |
| high | permission-bypass | src/modules/chat/hooks/useChatProviderState.ts:51 | code | `cursor: ['default', 'acceptEdits', 'bypassPermissions', 'plan'],` |

## skill-scanner

Đếm theo mức: info=2

## SkillSpector (máy quét thứ hai, chỉ đẩy lên REVIEW)

Điểm rủi ro cao nhất: 0 · mạng: chỉ OSV · đếm theo mức: không có

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `.agents/skills/backend-module-standards/SKILL.md`
- [ ] `.agents/skills/frontend-module-standards/SKILL.md`
- [ ] `README.md`
- [ ] `commitlint.config.js`
- [ ] `docker/shared/install-cloudcli.sh`
- [ ] `docker/shared/start-cloudcli.sh`
- [ ] `docs/README.id.md`
- [ ] `docs/architecture/02-realtime-stream.md`
- [ ] `electron/cloud.js`
- [ ] `electron/desktopNotifications.js`
- [ ] `electron/desktopWindow.js`
- [ ] `electron/launcher/launcher.js`
- [ ] `electron/localServer.js`
- [ ] `electron/main.js`
- [ ] `electron/preload.cjs`
- [ ] `electron/scripts/generate-macos-icon.js`
- [ ] `electron/serverInstaller.js`
- [ ] `electron/tabs.js`
- [ ] `electron/viewHost.js`
- [ ] `package.json`
- [ ] `postcss.config.js`
- [ ] `public/generate-icons.js`
- [ ] `public/sw.js`
- [ ] `redirect-package/bin.js`
- [ ] `redirect-package/index.js`
- [ ] `redirect-package/package.json`
- [ ] `release.sh`
- [ ] `scripts/fix-node-pty.js`
- [ ] `scripts/promote-dist-server.mjs`
- [ ] `scripts/release/build-server-bundle.js`
- [ ] `scripts/release/prepare-desktop-app.js`
- [ ] `server/index.ts`
- [ ] `server/load-env.ts`
- [ ] `server/modules/agent/agent.module.ts`
- [ ] `server/modules/agent/agent.routes.ts`
- [ ] `server/modules/agent/index.ts`
- [ ] `server/modules/agent/tests/agent-run-registration.test.ts`
- [ ] `server/modules/agent/tests/agent.routes.test.ts`
- [ ] `server/modules/assets/assets.routes.ts`
- [ ] `server/modules/assets/index.ts`
- [ ] `server/modules/assets/services/image-assets.service.ts`
- [ ] `server/modules/assets/tests/image-assets.service.test.ts`
- [ ] `server/modules/auth/auth.middleware.ts`
- [ ] `server/modules/auth/auth.module.ts`
- [ ] `server/modules/auth/auth.routes.ts`
- [ ] `server/modules/auth/auth.service.ts`
- [ ] `server/modules/auth/index.ts`
- [ ] `server/modules/auth/tests/auth.service.test.ts`
- [ ] `server/modules/browser-use/browser-use-mcp.routes.ts`
- [ ] `server/modules/browser-use/browser-use-mcp.ts`
- [ ] `server/modules/browser-use/browser-use-runtime.ts`
- [ ] `server/modules/browser-use/browser-use.routes.ts`
- [ ] `server/modules/browser-use/browser-use.service.ts`
- [ ] `server/modules/browser-use/index.ts`
- [ ] `server/modules/browser-use/tests/browser-use.service.test.ts`
- [ ] `server/modules/cli/cli.module.ts`
- [ ] `server/modules/cli/cli.service.ts`
- [ ] `server/modules/cli/cli.ts`
- [ ] `server/modules/cli/index.ts`
- [ ] `server/modules/cli/sandbox.service.ts`
- [ ] `server/modules/cli/tests/cli-environment-bootstrap.test.ts`
- [ ] `server/modules/cli/tests/cli.service.test.ts`
- [ ] `server/modules/cli/tests/sandbox.service.test.ts`
- [ ] `server/modules/commands/commands.module.ts`
- [ ] `server/modules/commands/commands.routes.ts`
- [ ] `server/modules/commands/index.ts`
- [ ] `server/modules/commands/tests/commands.test.ts`
- [ ] `server/modules/commands/tests/customCommandArguments.test.ts`
- [ ] `server/modules/database/connection.ts`
- [ ] `server/modules/database/index.ts`
- [ ] `server/modules/database/init-db.ts`
- [ ] `server/modules/database/migrations.ts`
- [ ] `server/modules/database/repositories/api-keys.ts`
- [ ] `server/modules/database/repositories/app-config.ts`
- [ ] `server/modules/database/repositories/credentials.ts`
- [ ] `server/modules/database/repositories/github-tokens.ts`
- [ ] `server/modules/database/repositories/notification-channel-endpoints.ts`
- [ ] `server/modules/database/repositories/notification-preferences.ts`
- [ ] `server/modules/database/repositories/projects.db.ts`
- [ ] `server/modules/database/repositories/provider-models.ts`
- [ ] `server/modules/database/repositories/push-subscriptions.ts`
- [ ] `server/modules/database/repositories/scan-state.db.ts`
- [ ] `server/modules/database/repositories/scheduled-messages.db.ts`
- [ ] `server/modules/database/repositories/session-drafts.db.ts`
- [ ] `server/modules/database/repositories/sessions.db.ts`
- [ ] `server/modules/database/repositories/user-preferences.db.ts`
- [ ] `server/modules/database/repositories/users.ts`
- [ ] `server/modules/database/repositories/vapid-keys.ts`
- [ ] `server/modules/database/schema.ts`
- [ ] `server/modules/database/tests/projects.db.integration.test.ts`
- [ ] `server/modules/database/tests/provider-models.db.integration.test.ts`
- [ ] `server/modules/database/tests/sessions-provider-mapping.test.ts`
- [ ] `server/modules/database/tests/sessions.db.integration.test.ts`
- [ ] `server/modules/database/tests/user-preferences.db.integration.test.ts`
- [ ] `server/modules/file-tree/file-tree.module.ts`
- [ ] `server/modules/file-tree/file-tree.routes.ts`
- [ ] `server/modules/file-tree/file-tree.service.ts`
- [ ] `server/modules/file-tree/index.ts`
- [ ] `server/modules/file-tree/tests/file-tree.routes.test.ts`
- [ ] `server/modules/file-tree/tests/file-tree.service.test.ts`
- [ ] `server/modules/git/git-branch-diff.service.ts`
- [ ] `server/modules/git/git-branch.service.ts`
- [ ] `server/modules/git/git-parsing.service.ts`
- [ ] `server/modules/git/git.module.ts`
- [ ] `server/modules/git/git.routes.ts`
- [ ] `server/modules/git/index.ts`
- [ ] `server/modules/git/tests/git-branch-diff.service.test.ts`
- [ ] `server/modules/git/tests/git-branch.service.test.ts`
- [ ] `server/modules/git/tests/git-init.routes.test.ts`
- [ ] `server/modules/git/tests/git.test.ts`
- [ ] `server/modules/notifications/index.ts`
- [ ] `server/modules/notifications/notifications.routes.ts`
- [ ] `server/modules/notifications/services/desktop-notification-clients.service.ts`
- [ ] `server/modules/notifications/services/notification-orchestrator.service.js`
- [ ] `server/modules/notifications/tests/notification-orchestrator.integration.test.ts`
- [ ] `server/modules/notifications/vapid-keys.service.ts`
- [ ] `server/modules/notifications/websocket/desktop-notifications-websocket.service.ts`
- [ ] `server/modules/plugins/index.ts`
- [ ] `server/modules/plugins/plugin-git.service.ts`
- [ ] `server/modules/plugins/plugin-process.service.ts`
- [ ] `server/modules/plugins/plugin-registry.service.ts`
- [ ] `server/modules/plugins/plugins.module.ts`
- [ ] `server/modules/plugins/plugins.routes.ts`
- [ ] `server/modules/plugins/plugins.service.ts`
- [ ] `server/modules/plugins/tests/plugin-git-failures.test.ts`
- [ ] `server/modules/plugins/tests/plugins.service.test.ts`
- [ ] `server/modules/projects/index.ts`
- [ ] `server/modules/projects/project-clone.routes.ts`
- [ ] `server/modules/projects/projects.routes.ts`
- [ ] `server/modules/projects/services/project-clone-request.service.ts`
- [ ] `server/modules/projects/services/project-clone.service.ts`
- [ ] `server/modules/projects/services/project-delete.service.ts`
- [ ] `server/modules/projects/services/project-management.service.ts`
- [ ] `server/modules/projects/services/project-star.service.ts`
- [ ] `server/modules/projects/services/projects-has-taskmaster.service.ts`
- [ ] `server/modules/projects/services/projects-with-sessions-fetch.service.ts`
- [ ] `server/modules/projects/tests/project-clone.routes.test.ts`
- [ ] `server/modules/projects/tests/project-clone.service.test.ts`
- [ ] `server/modules/projects/tests/project-management.service.test.ts`
- [ ] `server/modules/projects/tests/project-star.service.test.ts`
- [ ] `server/modules/projects/tests/projects-has-taskmaster.service.test.ts`
- [ ] `server/modules/providers/index.ts`
- [ ] `server/modules/providers/list/claude/claude-auth.provider.ts`
- [ ] `server/modules/providers/list/claude/claude-fork.provider.ts`
- [ ] `server/modules/providers/list/claude/claude-mcp.provider.ts`
- [ ] `server/modules/providers/list/claude/claude-models.provider.ts`
- [ ] `server/modules/providers/list/claude/claude-runtime.provider.ts`
- [ ] `server/modules/providers/list/claude/claude-session-synchronizer.provider.ts`
- [ ] `server/modules/providers/list/claude/claude-sessions.provider.ts`
- [ ] `server/modules/providers/list/claude/claude-skills.provider.ts`
- [ ] `server/modules/providers/list/claude/claude.provider.ts`
- [ ] `server/modules/providers/list/codex/codex-app-server.client.ts`
- [ ] `server/modules/providers/list/codex/codex-auth.provider.ts`
- [ ] `server/modules/providers/list/codex/codex-fork.provider.ts`
- [ ] `server/modules/providers/list/codex/codex-mcp.provider.ts`
- [ ] `server/modules/providers/list/codex/codex-models.provider.ts`
- [ ] `server/modules/providers/list/codex/codex-runtime.provider.ts`
- [ ] `server/modules/providers/list/codex/codex-session-synchronizer.provider.ts`
- [ ] `server/modules/providers/list/codex/codex-sessions.provider.ts`
- [ ] `server/modules/providers/list/codex/codex-skills.provider.ts`
- [ ] `server/modules/providers/list/codex/codex.provider.ts`
- [ ] `server/modules/providers/list/cursor/cursor-auth.provider.ts`
- [ ] `server/modules/providers/list/cursor/cursor-mcp.provider.ts`
- [ ] `server/modules/providers/list/cursor/cursor-models.provider.ts`
- [ ] `server/modules/providers/list/cursor/cursor-runtime.provider.js`
- [ ] `server/modules/providers/list/cursor/cursor-session-synchronizer.provider.ts`
- [ ] `server/modules/providers/list/cursor/cursor-sessions.provider.ts`
- [ ] `server/modules/providers/list/cursor/cursor-skills.provider.ts`
- [ ] `server/modules/providers/list/cursor/cursor.provider.ts`
- [ ] `server/modules/providers/list/opencode/opencode-auth.provider.ts`
- [ ] `server/modules/providers/list/opencode/opencode-mcp.provider.ts`
- [ ] `server/modules/providers/list/opencode/opencode-models.provider.ts`
- [ ] `server/modules/providers/list/opencode/opencode-runtime.provider.ts`
- [ ] `server/modules/providers/list/opencode/opencode-session-synchronizer.provider.ts`
- [ ] `server/modules/providers/list/opencode/opencode-sessions.provider.ts`
- [ ] `server/modules/providers/list/opencode/opencode-skills.provider.ts`
- [ ] `server/modules/providers/list/opencode/opencode.provider.ts`
- [ ] `server/modules/providers/provider.registry.ts`
- [ ] `server/modules/providers/provider.routes.ts`
- [ ] `server/modules/providers/services/claude-cli-liveness.service.ts`
- [ ] `server/modules/providers/services/claude-settings-permissions.service.ts`
- [ ] `server/modules/providers/services/mcp.service.ts`
- [ ] `server/modules/providers/services/provider-auth.service.ts`
- [ ] `server/modules/providers/services/provider-capabilities.service.ts`
- [ ] `server/modules/providers/services/provider-cli.service.ts`
- [ ] `server/modules/providers/services/provider-models.service.ts`
- [ ] `server/modules/providers/services/provider-runtime.service.ts`
- [ ] `server/modules/providers/services/provider-token-usage.service.ts`
- [ ] `server/modules/providers/services/session-conversations-search.service.ts`
- [ ] `server/modules/providers/services/session-history-cache.service.ts`
- [ ] `server/modules/providers/services/session-synchronizer.service.ts`
- [ ] `server/modules/providers/services/sessions-watcher.service.ts`
- [ ] `server/modules/providers/services/sessions.service.ts`
- [ ] `server/modules/providers/services/skills.service.ts`
- [ ] `server/modules/providers/shared/base/abstract.provider.ts`
- [ ] `server/modules/providers/shared/mcp/mcp.provider.ts`
- [ ] `server/modules/providers/shared/skills/skills.provider.ts`
- [ ] `server/modules/providers/tests/claude-api-request-log.test.ts`
- [ ] `server/modules/providers/tests/claude-auth.test.ts`
- [ ] `server/modules/providers/tests/claude-background-work.test.ts`
- [ ] `server/modules/providers/tests/claude-compaction.test.ts`
- [ ] `server/modules/providers/tests/claude-context-window.test.ts`
- [ ] `server/modules/providers/tests/claude-message-model.test.ts`
- [ ] `server/modules/providers/tests/claude-models.test.ts`
- [ ] `server/modules/providers/tests/claude-pasted-content.test.ts`
- [ ] `server/modules/providers/tests/claude-runtime-hold.test.ts`
- [ ] `server/modules/providers/tests/claude-sdk-env.test.ts`
- [ ] `server/modules/providers/tests/claude-sessions.test.ts`
- [ ] `server/modules/providers/tests/claude-settings-permissions.test.ts`
- [ ] `server/modules/providers/tests/claude-subagent-echo.test.ts`
- [ ] `server/modules/providers/tests/claude-token-budget.test.ts`
- [ ] `server/modules/providers/tests/codex-fork-history.test.ts`
- [ ] `server/modules/providers/tests/codex-message-editing.test.ts`
- [ ] `server/modules/providers/tests/codex-models.test.ts`
- [ ] `server/modules/providers/tests/codex-runtime.test.ts`
- [ ] `server/modules/providers/tests/codex-session-fork.test.ts`
- [ ] `server/modules/providers/tests/codex-sessions.test.ts`
- [ ] `server/modules/providers/tests/cursor-auth.test.ts`
- [ ] `server/modules/providers/tests/fixtures/fake-opencode-serve.ts`
- [ ] `server/modules/providers/tests/mcp.test.ts`
- [ ] `server/modules/providers/tests/opencode-models.test.ts`
- [ ] `server/modules/providers/tests/opencode-runtime.test.ts`
- [ ] `server/modules/providers/tests/opencode-sessions.test.ts`
- [ ] `server/modules/providers/tests/opencode-subagents.test.ts`
- [ ] `server/modules/providers/tests/provider-attachment-history.test.ts`
- [ ] `server/modules/providers/tests/provider-capabilities.service.test.ts`
- [ ] `server/modules/providers/tests/provider-cli.service.test.ts`
- [ ] `server/modules/providers/tests/provider-models.service.test.ts`
- [ ] `server/modules/providers/tests/provider-runtime.service.test.ts`
- [ ] `server/modules/providers/tests/provider-token-usage.service.test.ts`
- [ ] `server/modules/providers/tests/provider.routes.test.ts`
- [ ] `server/modules/providers/tests/session-fork.test.ts`
- [ ] `server/modules/providers/tests/session-history-cache.service.test.ts`
- [ ] `server/modules/providers/tests/session-orphan-prune.test.ts`
- [ ] `server/modules/providers/tests/session-synchronizer-coalescing.test.ts`
- [ ] `server/modules/providers/tests/sessions-details.test.ts`
- [ ] `server/modules/providers/tests/sessions-watcher.test.ts`
- [ ] `server/modules/providers/tests/sessions.service.test.ts`
- [ ] `server/modules/providers/tests/skills.test.ts`
- [ ] `server/modules/scheduled-messages/index.ts`
- [ ] `server/modules/scheduled-messages/scheduled-messages.routes.ts`
- [ ] `server/modules/scheduled-messages/services/scheduled-message-dispatcher.service.ts`
- [ ] `server/modules/scheduled-messages/services/scheduled-messages.service.ts`
- [ ] `server/modules/scheduled-messages/tests/scheduled-messages.test.ts`
- [ ] `server/modules/settings/index.ts`
- [ ] `server/modules/settings/settings.module.ts`
- [ ] `server/modules/settings/settings.routes.ts`
- [ ] `server/modules/settings/settings.service.ts`
- [ ] `server/modules/settings/tests/settings.service.test.ts`
- [ ] `server/modules/system/index.ts`
- [ ] `server/modules/system/system.module.ts`
- [ ] `server/modules/system/system.routes.ts`
- [ ] `server/modules/system/system.service.ts`
- [ ] `server/modules/system/tests/system.service.test.ts`
- [ ] `server/modules/taskmaster/index.ts`
- [ ] `server/modules/taskmaster/taskmaster.module.ts`
- [ ] `server/modules/taskmaster/taskmaster.routes.ts`
- [ ] `server/modules/taskmaster/taskmaster.service.ts`
- [ ] `server/modules/taskmaster/tests/taskmaster.routes.test.ts`
- [ ] `server/modules/taskmaster/tests/taskmaster.service.test.ts`
- [ ] `server/modules/user/index.ts`
- [ ] `server/modules/user/tests/user.routes.test.ts`
- [ ] `server/modules/user/tests/user.service.test.ts`
- [ ] `server/modules/user/user.module.ts`
- [ ] `server/modules/user/user.routes.ts`
- [ ] `server/modules/user/user.service.ts`
- [ ] `server/modules/voice/index.ts`
- [ ] `server/modules/voice/tests/voice.service.test.ts`
- [ ] `server/modules/voice/voice.module.ts`
- [ ] `server/modules/voice/voice.routes.ts`
- [ ] `server/modules/voice/voice.service.ts`
- [ ] `server/modules/websocket/index.ts`
- [ ] `server/modules/websocket/services/chat-run-registry.service.ts`
- [ ] `server/modules/websocket/services/chat-session-writer.service.ts`
- [ ] `server/modules/websocket/services/chat-websocket.service.ts`
- [ ] `server/modules/websocket/services/plugin-websocket-proxy.service.ts`
- [ ] `server/modules/websocket/services/session-upsert-broadcast.service.ts`
- [ ] `server/modules/websocket/services/shell-websocket.service.ts`
- [ ] `server/modules/websocket/services/websocket-auth.service.ts`
- [ ] `server/modules/websocket/services/websocket-server.service.ts`
- [ ] `server/modules/websocket/services/websocket-state.service.ts`
- [ ] `server/modules/websocket/services/websocket-writer.service.ts`
- [ ] `server/modules/websocket/tests/chat-abort-opencode.test.ts`
- [ ] `server/modules/websocket/tests/chat-attachment-filter.test.ts`
- [ ] `server/modules/websocket/tests/chat-background-subscribe.test.ts`
- [ ] `server/modules/websocket/tests/chat-edit-send.test.ts`
- [ ] `server/modules/websocket/tests/chat-run-registry.test.ts`
- [ ] `server/modules/websocket/tests/chat-stop-task.test.ts`
- [ ] `server/modules/websocket/tests/session-upsert-broadcast.test.ts`
- [ ] `server/modules/websocket/tests/shell-websocket.service.test.ts`
- [ ] `server/modules/websocket/tests/websocket-heartbeat.service.test.ts`
- [ ] `server/modules/worktrees/index.ts`
- [ ] `server/modules/worktrees/services/worktree-create-and-open.service.ts`
- [ ] `server/modules/worktrees/services/worktree-create.service.ts`
- [ ] `server/modules/worktrees/services/worktree-git.service.ts`
- [ ] `server/modules/worktrees/services/worktree-list.service.ts`
- [ ] `server/modules/worktrees/services/worktree-merge.service.ts`
- [ ] `server/modules/worktrees/services/worktree-open.service.ts`
- [ ] `server/modules/worktrees/services/worktree-remove.service.ts`
- [ ] `server/modules/worktrees/tests/worktree-create-and-open.service.test.ts`
- [ ] `server/modules/worktrees/tests/worktree-create.service.test.ts`
- [ ] `server/modules/worktrees/tests/worktree-git.service.test.ts`
- [ ] `server/modules/worktrees/tests/worktree-list.service.test.ts`
- [ ] `server/modules/worktrees/tests/worktree-merge.service.test.ts`
- [ ] `server/modules/worktrees/tests/worktree-open.service.test.ts`
- [ ] `server/modules/worktrees/tests/worktree-remove.service.test.ts`
- [ ] `server/modules/worktrees/tests/worktrees.routes.test.ts`
- [ ] `server/modules/worktrees/worktrees.module.ts`
- [ ] `server/modules/worktrees/worktrees.routes.ts`
- [ ] `server/shared/claude-cli-path.ts`
- [ ] `server/shared/frontmatter.ts`
- [ ] `server/shared/image-attachments.ts`
- [ ] `server/shared/index.ts`
- [ ] `server/shared/interfaces.ts`
- [ ] `server/shared/message-unification.ts`
- [ ] `server/shared/tests/claude-cli-path.test.ts`
- [ ] `server/shared/tests/image-attachments.test.ts`
- [ ] `server/shared/tests/message-unification.test.ts`
- [ ] `server/shared/tests/read-only-roots.test.ts`
- [ ] `server/shared/tests/read-queued-chat-message.test.ts`
- [ ] `server/shared/tests/slice-tail-page.test.ts`
- [ ] `server/shared/tests/strip-ansi-sequences.test.ts`
- [ ] `server/shared/types.ts`
- [ ] `server/shared/utils.ts`
- [ ] `shared/networkHosts.js`
- [ ] `src/modules/auth/index.ts`
- [ ] `src/modules/browser-use/hooks/useBrowserUseEnabled.ts`
- [ ] `src/modules/browser-use/index.ts`
- [ ] `src/modules/chat/composer/ComposerPermissionMenu.tsx`
- [ ] `src/modules/chat/composer/useScheduledMessages.ts`
- [ ] `src/modules/chat/context/MarkdownWorkspaceContext.ts`
- [ ] `src/modules/chat/context/TranscriptRenderContext.ts`
- [ ] `src/modules/chat/context/TranscriptSessionContext.ts`
- [ ] `src/modules/chat/export/buildTranscriptMarkdown.ts`
- [ ] `src/modules/chat/hooks/useChatComposerState.ts`
- [ ] `src/modules/chat/hooks/useChatMessages.ts`
- [ ] `src/modules/chat/hooks/useChatProviderState.ts`
- [ ] `src/modules/chat/hooks/useChatRealtimeHandlers.ts`
- [ ] `src/modules/chat/hooks/useChatSessionState.ts`
- [ ] `src/modules/chat/hooks/useComposerMenuAnchor.ts`
- [ ] `src/modules/chat/hooks/useInputHistory.ts`
- [ ] `src/modules/chat/hooks/useLazyRowObserver.ts`
- [ ] `src/modules/chat/hooks/usePermissionNameFit.ts`
- [ ] `src/modules/chat/hooks/useSessionStore.ts`
- [ ] `src/modules/chat/hooks/useSlashCommands.ts`
- [ ] `src/modules/chat/hooks/useTts.ts`
- [ ] `src/modules/chat/hooks/useVoiceAvailable.ts`
- [ ] `src/modules/chat/hooks/useVoiceInput.ts`
- [ ] `src/modules/chat/index.ts`
- [ ] `src/modules/chat/tests/chatFormatting.test.ts`
- [ ] `src/modules/chat/tests/chatPermissions.test.ts`
- [ ] `src/modules/chat/tests/chatProviderModels.test.ts`
- [ ] `src/modules/chat/tests/compactionRows.test.ts`
- [ ] `src/modules/chat/tests/composerNewChatSingleSession.test.ts`
- [ ] `src/modules/chat/tests/composerPermissionMenu.test.tsx`
- [ ] `src/modules/chat/tests/composerQueuedFollowUps.test.ts`
- [ ] `src/modules/chat/tests/composerSendOverBackgroundWork.test.ts`
- [ ] `src/modules/chat/tests/composerToolsSettingsResolution.test.ts`
- [ ] `src/modules/chat/tests/diffStats.test.ts`
- [ ] `src/modules/chat/tests/liveSubagentGrouping.test.ts`
- [ ] `src/modules/chat/tests/messageHistoryRefreshCoordinator.test.ts`
- [ ] `src/modules/chat/tests/searchTargetLocator.test.ts`
- [ ] `src/modules/chat/tests/sessionMessagePagination.test.ts`
- [ ] `src/modules/chat/tests/sessionMessageReconciliation.test.ts`
- [ ] `src/modules/chat/tests/slashCommandArguments.test.ts`
- [ ] `src/modules/chat/tests/slashCommandTabCompletion.test.ts`
- [ ] `src/modules/chat/tests/streamingMarkdown.test.ts`
- [ ] `src/modules/chat/tests/syntaxHighlightTheme.test.ts`
- [ ] `src/modules/chat/tests/toolGrouping.test.ts`
- [ ] `src/modules/chat/tests/useChatMessages.test.ts`
- [ ] `src/modules/chat/tests/useInputHistory.test.ts`
- [ ] `src/modules/chat/tools/BashEditDiff.tsx`
- [ ] `src/modules/chat/tools/configs/permissionPanelRegistry.ts`
- [ ] `src/modules/chat/tools/configs/toolConfigs.ts`
- [ ] `src/modules/chat/tools/index.ts`
- [ ] `src/modules/chat/utils/backgroundTasks.ts`
- [ ] `src/modules/chat/utils/chatExport.ts`
- [ ] `src/modules/chat/utils/chatFormatting.ts`
- [ ] `src/modules/chat/utils/chatPermissions.ts`
- [ ] `src/modules/chat/utils/chatStorage.ts`
- [ ] `src/modules/chat/utils/latexDelimiters.ts`
- [ ] `src/modules/chat/utils/messageHistoryRefreshCoordinator.ts`
- [ ] `src/modules/chat/utils/messageKeys.ts`
- [ ] `src/modules/chat/utils/messageTransforms.ts`
- [ ] `src/modules/chat/utils/modelLabel.ts`
- [ ] `src/modules/chat/utils/pageTitleNotification.ts`
- [ ] `src/modules/chat/utils/searchTargetLocator.ts`
- [ ] `src/modules/chat/utils/sessionMessagePagination.ts`
- [ ] `src/modules/chat/utils/sessionMessageReconciliation.ts`
- [ ] `src/modules/chat/utils/streamingMarkdown.ts`
- [ ] `src/modules/chat/utils/syntaxHighlightTheme.ts`
- [ ] `src/modules/chat/utils/toolGrouping.ts`
- [ ] `src/modules/chat/utils/voicePlayer.ts`
- [ ] `src/modules/chat/utils/workflowScriptMeta.ts`
- [ ] `src/modules/code-editor/hooks/useCodeEditorDocument.ts`
- [ ] `src/modules/code-editor/hooks/useCodeEditorSettings.ts`
- [ ] `src/modules/code-editor/hooks/useEditorKeyboardShortcuts.ts`
- [ ] `src/modules/code-editor/hooks/useEditorSidebar.ts`
- [ ] `src/modules/code-editor/index.ts`
- [ ] `src/modules/code-editor/tests/codeEditorSettingsSync.test.ts`
- [ ] `src/modules/code-editor/utils/binaryFile.ts`
- [ ] `src/modules/code-editor/utils/editorExtensions.ts`
- [ ] `src/modules/code-editor/utils/editorStyles.ts`
- [ ] `src/modules/code-editor/utils/editorToolbarPanel.ts`
- [ ] `src/modules/code-editor/utils/previewableFile.ts`
- [ ] `src/modules/command-palette/hooks/useApiSource.ts`
- [ ] `src/modules/command-palette/hooks/useBranchesSource.ts`
- [ ] `src/modules/command-palette/hooks/useCommitsSource.ts`
- [ ] `src/modules/command-palette/hooks/useFilesSource.ts`
- [ ] `src/modules/command-palette/hooks/useGitActions.ts`
- [ ] `src/modules/command-palette/hooks/useSessionMessageSearch.ts`
- [ ] `src/modules/command-palette/hooks/useSessionsSource.ts`
- [ ] `src/modules/command-palette/index.ts`
- [ ] `src/modules/file-tree/hooks/useExpandedDirectories.ts`
- [ ] `src/modules/file-tree/hooks/useFileTreeData.ts`
- [ ] `src/modules/file-tree/hooks/useFileTreeOperations.ts`
- [ ] `src/modules/file-tree/hooks/useFileTreeSearch.ts`
- [ ] `src/modules/file-tree/hooks/useFileTreeUpload.ts`
- [ ] `src/modules/file-tree/hooks/useFileTreeViewMode.ts`
- [ ] `src/modules/file-tree/index.ts`
- [ ] `src/modules/file-tree/tests/revealDirectory.test.ts`
- [ ] `src/modules/file-tree/utils/fileIcons.ts`
- [ ] `src/modules/file-tree/utils/fileTreeUtils.ts`
- [ ] `src/modules/file-tree/utils/revealDirectory.ts`
- [ ] `src/modules/git-panel/hooks/useBranchCompare.ts`
- [ ] `src/modules/git-panel/hooks/useGitPanelController.ts`
- [ ] `src/modules/git-panel/hooks/useRevertLocalCommit.ts`
- [ ] `src/modules/git-panel/hooks/useWorktreesController.ts`
- [ ] `src/modules/git-panel/index.ts`
- [ ] `src/modules/git-panel/tests/commitGraph.test.ts`
- [ ] `src/modules/git-panel/tests/pickDefaultCompareBase.test.ts`
- [ ] `src/modules/git-panel/tests/useBranchCompare.test.ts`
- [ ] `src/modules/git-panel/utils/commitGraph.ts`
- [ ] `src/modules/git-panel/utils/gitPanelUtils.ts`
- [ ] `src/modules/i18n/config.ts`
- [ ] `src/modules/i18n/index.ts`
- [ ] `src/modules/i18n/languages.ts`
- [ ] `src/modules/i18n/locales/cs/chat.json`
- [ ] `src/modules/i18n/locales/cs/settings.json`
- [ ] `src/modules/i18n/locales/de/chat.json`
- [ ] `src/modules/i18n/locales/de/settings.json`
- [ ] `src/modules/i18n/locales/en/chat.json`
- [ ] `src/modules/i18n/locales/en/settings.json`
- [ ] `src/modules/i18n/locales/es/chat.json`
- [ ] `src/modules/i18n/locales/es/settings.json`
- [ ] `src/modules/i18n/locales/fr/chat.json`
- [ ] `src/modules/i18n/locales/fr/settings.json`
- [ ] `src/modules/i18n/locales/he/chat.json`
- [ ] `src/modules/i18n/locales/he/settings.json`
- [ ] `src/modules/i18n/locales/id/chat.json`
- [ ] `src/modules/i18n/locales/id/settings.json`
- [ ] `src/modules/i18n/locales/it/chat.json`
- [ ] `src/modules/i18n/locales/it/settings.json`
- [ ] `src/modules/i18n/locales/ja/chat.json`
- [ ] `src/modules/i18n/locales/ja/settings.json`
- [ ] `src/modules/i18n/locales/ko/chat.json`
- [ ] `src/modules/i18n/locales/ko/settings.json`
- [ ] `src/modules/i18n/locales/pt-BR/chat.json`
- [ ] `src/modules/i18n/locales/pt-BR/settings.json`
- [ ] `src/modules/i18n/locales/ru/chat.json`
- [ ] `src/modules/i18n/locales/ru/settings.json`
- [ ] `src/modules/i18n/locales/tr/chat.json`
- [ ] `src/modules/i18n/locales/tr/settings.json`
- [ ] `src/modules/i18n/locales/zh-CN/chat.json`
- [ ] `src/modules/i18n/locales/zh-CN/settings.json`
- [ ] `src/modules/i18n/locales/zh-TW/chat.json`
- [ ] `src/modules/i18n/locales/zh-TW/settings.json`
- [ ] `src/modules/i18n/tests/translationCoverage.test.ts`
- [ ] `src/modules/mcp/hooks/useMcpServerForm.ts`
- [ ] `src/modules/mcp/hooks/useMcpServers.ts`
- [ ] `src/modules/mcp/index.ts`
- [ ] `src/modules/mcp/utils/mcpFormatting.ts`
- [ ] `src/modules/onboarding/index.ts`
- [ ] `src/modules/plugins/index.ts`
- [ ] `src/modules/prd-editor/hooks/usePrdDocument.ts`
- [ ] `src/modules/prd-editor/hooks/usePrdKeyboardShortcuts.ts`
- [ ] `src/modules/prd-editor/hooks/usePrdRegistry.ts`
- [ ] `src/modules/prd-editor/hooks/usePrdSave.ts`
- [ ] `src/modules/prd-editor/index.ts`
- [ ] `src/modules/prd-editor/utils/fileName.ts`
- [ ] `src/modules/project-creation-wizard/hooks/useGithubTokens.ts`
- [ ] `src/modules/project-creation-wizard/index.ts`
- [ ] `src/modules/project-creation-wizard/tests/workspaceApi.test.ts`
- [ ] `src/modules/project-creation-wizard/utils/pathUtils.ts`
- [ ] `src/modules/project-creation-wizard/utils/workspaceApi.ts`
- [ ] `src/modules/project-workspace/hooks/useFileOpenResolver.ts`
- [ ] `src/modules/project-workspace/hooks/useMobileMenuHandlers.ts`
- [ ] `src/modules/project-workspace/hooks/useProjectsState.ts`
- [ ] `src/modules/project-workspace/hooks/useSessionTitleRename.ts`
- [ ] `src/modules/project-workspace/hooks/useVisualViewportKeyboardOffset.ts`
- [ ] `src/modules/project-workspace/index.ts`
- [ ] `src/modules/project-workspace/tests/projectSelectionMetadata.test.ts`
- [ ] `src/modules/project-workspace/tests/projectsStateRenameSession.test.ts`
- [ ] `src/modules/project-workspace/tests/projectsStateScheduledAnnouncement.test.ts`
- [ ] `src/modules/project-workspace/tests/projectsStateSelectionSync.test.ts`
- [ ] `src/modules/project-workspace/tests/projectsStateSessionAlias.test.ts`
- [ ] `src/modules/project-workspace/utils/projectSelectionMetadata.ts`
- [ ] `src/modules/provider-auth/ProviderLoginModal.tsx`
- [ ] `src/modules/provider-auth/hooks/useProviderAuthStatus.ts`
- [ ] `src/modules/provider-auth/index.ts`
- [ ] `src/modules/provider-auth/tests/useProviderAuthStatusSubscriptionOverride.test.ts`
- [ ] `src/modules/quick-settings-panel/hooks/useQuickSettingsDrag.ts`
- [ ] `src/modules/quick-settings-panel/hooks/useQuickSettingsPanelState.ts`
- [ ] `src/modules/quick-settings-panel/index.ts`
- [ ] `src/modules/quick-settings-panel/tests/quickSettingsPanelState.test.ts`
- [ ] `src/modules/settings/hooks/useClaudeSettingsPermissionRules.ts`
- [ ] `src/modules/settings/hooks/useCredentialsSettings.ts`
- [ ] `src/modules/settings/hooks/useGitSettings.ts`
- [ ] `src/modules/settings/hooks/useProviderCliVersion.ts`
- [ ] `src/modules/settings/hooks/useSettingsController.ts`
- [ ] `src/modules/settings/hooks/useVoiceConfig.ts`
- [ ] `src/modules/settings/hooks/useWebPush.ts`
- [ ] `src/modules/settings/index.ts`
- [ ] `src/modules/settings/tabs/agents-settings/sections/content/PermissionsContent.tsx`
- [ ] `src/modules/settings/tests/codeEditorSettingsPersistence.test.ts`
- [ ] `src/modules/settings/tests/settingsControllerCodeEditor.test.ts`
- [ ] `src/modules/shell/Shell.tsx`
- [ ] `src/modules/shell/hooks/useShellConnection.ts`
- [ ] `src/modules/shell/hooks/useShellRuntime.ts`
- [ ] `src/modules/shell/hooks/useShellTerminal.ts`
- [ ] `src/modules/shell/index.ts`
- [ ] `src/modules/shell/tests/shellErrorFrame.test.ts`
- [ ] `src/modules/shell/tests/shellTerminalTheme.test.ts`
- [ ] `src/modules/shell/utils/mobileTerminalSelection.ts`
- [ ] `src/modules/shell/utils/socket.ts`
- [ ] `src/modules/shell/utils/terminalStyles.ts`
- [ ] `src/modules/sidebar/hooks/useCompactSidebar.ts`
- [ ] `src/modules/sidebar/hooks/useGitHubStars.ts`
- [ ] `src/modules/sidebar/hooks/useProviderSessionIdCopy.ts`
- [ ] `src/modules/sidebar/hooks/useSidebarController.ts`
- [ ] `src/modules/sidebar/hooks/useTabOverflow.ts`
- [ ] `src/modules/sidebar/index.ts`
- [ ] `src/modules/sidebar/tests/loadMoreProjectSessions.test.ts`
- [ ] `src/modules/sidebar/tests/recentConversationTitleSync.test.ts`
- [ ] `src/modules/sidebar/tests/sessionBulkSelection.test.ts`
- [ ] `src/modules/sidebar/tests/tabOverflow.test.ts`
- [ ] `src/modules/sidebar/utils/sidebarProjectFormatting.ts`
- [ ] `src/modules/sidebar/utils/sidebarStoredPreferences.ts`
- [ ] `src/modules/skills/hooks/useProviderSkills.ts`
- [ ] `src/modules/skills/index.ts`
- [ ] `src/modules/standalone-shell/index.ts`
- [ ] `src/modules/task-master/hooks/useProjectPrdFiles.ts`
- [ ] `src/modules/task-master/hooks/useTaskBoardState.ts`
- [ ] `src/modules/task-master/hooks/useTaskMasterProjectSync.ts`
- [ ] `src/modules/task-master/index.ts`
- [ ] `src/modules/task-master/utils/taskKanban.ts`
- [ ] `src/modules/task-master/utils/taskSorting.ts`
- [ ] `src/modules/version-upgrade/index.ts`
- [ ] `src/shared/api.ts`
- [ ] `src/shared/authToken.ts`
- [ ] `src/shared/chatDrafts.ts`
- [ ] `src/shared/codeEditorSettings.ts`
- [ ] `src/shared/constants.ts`
- [ ] `src/shared/hooks/useDeviceSettings.ts`
- [ ] `src/shared/hooks/useProjectSlashCommands.ts`
- [ ] `src/shared/hooks/useProviderCapabilities.ts`
- [ ] `src/shared/hooks/useSelectedProvider.ts`
- [ ] `src/shared/hooks/useSessionProtection.ts`
- [ ] `src/shared/hooks/useSidebarWidth.ts`
- [ ] `src/shared/hooks/useVersionCheck.ts`
- [ ] `src/shared/selectedProvider.ts`
- [ ] `src/shared/syntaxHighlighter.ts`
- [ ] `src/shared/tests/authToken.test.ts`
- [ ] `src/shared/tests/authenticatedFetch.test.ts`
- [ ] `src/shared/tests/chatDrafts.test.ts`
- [ ] `src/shared/tests/pageTitle.test.ts`
- [ ] `src/shared/tests/readApiErrorMessage.test.ts`
- [ ] `src/shared/tests/readApiJson.test.ts`
- [ ] `src/shared/tests/selectedProvider.test.ts`
- [ ] `src/shared/tests/uiPreferences.test.ts`
- [ ] `src/shared/tests/useSidebarWidth.test.ts`
- [ ] `src/shared/tests/userSettings.test.ts`
- [ ] `src/shared/tests/voiceConfig.test.ts`
- [ ] `src/shared/types.ts`
- [ ] `src/shared/ui/index.ts`
- [ ] `src/shared/uiPreferences.ts`
- [ ] `src/shared/userSettings.ts`
- [ ] `src/shared/utils.ts`
- [ ] `src/shared/voiceConfig.ts`
- [ ] `src/vite-env.d.ts`
- [ ] `tailwind.config.js`
- [ ] `vite.config.js`
- [ ] `vitest.config.ts`
- [ ] `vitest.setup.ts`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).
