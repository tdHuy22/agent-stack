# Đã cài gì

*Cập nhật 21:07 03/10/2026 từ commit `94bbe0a` của agent-stack. File này do `tools/install.py` tạo; đừng sửa tay. Mỗi lần cài là một mục bên dưới, cũ nhất trước.*

## Lần cài 15:19 02/10/2026

- Nhật ký máy đọc: `state/install-logs/20261002-151930.json`
- Sao lưu: `~/Documents/Claude/agent-stack/backups/install-20261002-151930`, gồm bản chụp `pristine/` của cấu hình trước khi cài
- Bước đã chạy: rules, plugin, statusline, autocontinue, catalog, opencode
- Kết quả: 28 thay đổi, 0 mục bị bỏ qua, 0 lỗi

| # | Loại | Ở đâu | Chi tiết | Gỡ riêng mục này |
|---:|---|---|---|---|
| 1 | symlink | ~/.claude/CLAUDE.md | → `~/Documents/Claude/agent-stack/global/CLAUDE.global.md` | `rm ~/.claude/CLAUDE.md` |
| 2 | symlink | ~/.config/opencode/AGENTS.md | → `~/Documents/Claude/agent-stack/global/AGENTS.global.md` | `rm ~/.config/opencode/AGENTS.md` |
| 3 | lệnh claude | `claude plugin marketplace add /Users/macos/Documents/Claude/agent-stack` |  | `claude plugin marketplace remove agent-stack-local` |
| 4 | lệnh claude | `claude plugin install agent-stack@agent-stack-local --scope user` |  | `claude plugin uninstall agent-stack@agent-stack-local --scope user` |
| 5 | sửa file | ~/.claude/settings.json | khóa `statusLine` | chép lại từ `~/Documents/Claude/agent-stack/backups/install-20261002-151930/.claude__settings.json` |
| 6 | sửa file | ~/.claude/settings.json | khóa `autoContinueAtUsageLimit` | chép lại từ `~/Documents/Claude/agent-stack/backups/install-20261002-151930/.claude__settings.json.2` |
| 7 | lệnh claude | `claude plugin install pyright-lsp@claude-plugins-official --scope user` |  | `claude plugin uninstall pyright-lsp@claude-plugins-official --scope user` |
| 8 | lệnh claude | `claude plugin install clangd-lsp@claude-plugins-official --scope user` |  | `claude plugin uninstall clangd-lsp@claude-plugins-official --scope user` |
| 9 | lệnh claude | `claude plugin install claude-code-setup@claude-plugins-official --scope user` |  | `claude plugin uninstall claude-code-setup@claude-plugins-official --scope user` |
| 10 | lệnh claude | `claude plugin install claude-md-management@claude-plugins-official --scope user` |  | `claude plugin uninstall claude-md-management@claude-plugins-official --scope user` |
| 11 | lệnh claude | `claude plugin install session-report@claude-plugins-official --scope user` |  | `claude plugin uninstall session-report@claude-plugins-official --scope user` |
| 12 | thư mục mới | ~/Documents/Claude/agent-stack/vendor | skill bên thứ ba, ghim commit (xem `VENDORED.json`) | `rm -rf ~/Documents/Claude/agent-stack/vendor` |
| 13 | lệnh claude | `claude plugin marketplace add /Users/macos/Documents/Claude/agent-stack/vendor` |  | `claude plugin marketplace remove agent-stack-vendor-local` |
| 14 | lệnh claude | `claude plugin install agent-stack-vendor@agent-stack-vendor-local --scope user` |  | `claude plugin uninstall agent-stack-vendor@agent-stack-vendor-local --scope user` |
| 15 | thư mục mới | ~/.config/opencode/skills |  | `rmdir ~/.config/opencode/skills` (khi đã trống) |
| 16 | symlink | ~/.config/opencode/skills/giong-van | → `~/Documents/Claude/agent-stack/plugin/skills/giong-van` | `rm ~/.config/opencode/skills/giong-van` |
| 17 | symlink | ~/.config/opencode/skills/reuse-best | → `~/Documents/Claude/agent-stack/plugin/skills/reuse-best` | `rm ~/.config/opencode/skills/reuse-best` |
| 18 | symlink | ~/.config/opencode/skills/session-keeper | → `~/Documents/Claude/agent-stack/plugin/skills/session-keeper` | `rm ~/.config/opencode/skills/session-keeper` |
| 19 | symlink | ~/.config/opencode/skills/task-router | → `~/Documents/Claude/agent-stack/plugin/skills/task-router` | `rm ~/.config/opencode/skills/task-router` |
| 20 | symlink | ~/.config/opencode/skills/tien-do | → `~/Documents/Claude/agent-stack/plugin/skills/tien-do` | `rm ~/.config/opencode/skills/tien-do` |
| 21 | symlink | ~/.config/opencode/skills/vet-skill | → `~/Documents/Claude/agent-stack/plugin/skills/vet-skill` | `rm ~/.config/opencode/skills/vet-skill` |
| 22 | symlink | ~/.config/opencode/skills/diagnosing-bugs | → `~/Documents/Claude/agent-stack/vendor/skills/diagnosing-bugs` | `rm ~/.config/opencode/skills/diagnosing-bugs` |
| 23 | symlink | ~/.config/opencode/skills/grill-me | → `~/Documents/Claude/agent-stack/vendor/skills/grill-me` | `rm ~/.config/opencode/skills/grill-me` |
| 24 | symlink | ~/.config/opencode/skills/handoff | → `~/Documents/Claude/agent-stack/vendor/skills/handoff` | `rm ~/.config/opencode/skills/handoff` |
| 25 | symlink | ~/.config/opencode/skills/humanizer | → `~/Documents/Claude/agent-stack/vendor/skills/humanizer` | `rm ~/.config/opencode/skills/humanizer` |
| 26 | symlink | ~/.config/opencode/skills/tdd | → `~/Documents/Claude/agent-stack/vendor/skills/tdd` | `rm ~/.config/opencode/skills/tdd` |
| 27 | thư mục mới | ~/.config/opencode/agents |  | `rmdir ~/.config/opencode/agents` (khi đã trống) |
| 28 | symlink | ~/.config/opencode/agents/worker.md | → `~/Documents/Claude/agent-stack/opencode/agents/worker.md` | `rm ~/.config/opencode/agents/worker.md` |

## Lần cài 15:25 02/10/2026

- Nhật ký máy đọc: `state/install-logs/20261002-152532.json`
- Sao lưu: `~/Documents/Claude/agent-stack/backups/install-20261002-152532`, gồm bản chụp `pristine/` của cấu hình trước khi cài
- Bước đã chạy: plugin
- Kết quả: 2 thay đổi, 0 mục bị bỏ qua, 0 lỗi

| # | Loại | Ở đâu | Chi tiết | Gỡ riêng mục này |
|---:|---|---|---|---|
| 1 | sửa file | ~/Documents/Claude/agent-stack/plugin/.agent-stack-home | khóa `đường dẫn repo` | `rm ~/Documents/Claude/agent-stack/plugin/.agent-stack-home` (trước khi cài chưa có file này) |
| 2 | lệnh claude | `claude plugin update agent-stack@agent-stack-local --scope user` |  | — |

## Lần cài 15:30 02/10/2026

- Nhật ký máy đọc: `state/install-logs/20261002-153032.json`
- Sao lưu: `~/Documents/Claude/agent-stack/backups/install-20261002-153032`, gồm bản chụp `pristine/` của cấu hình trước khi cài
- Bước đã chạy: plugin
- Kết quả: 1 thay đổi, 0 mục bị bỏ qua, 0 lỗi

| # | Loại | Ở đâu | Chi tiết | Gỡ riêng mục này |
|---:|---|---|---|---|
| 1 | lệnh claude | `claude plugin update agent-stack@agent-stack-local --scope user` |  | — |

## Lần cài 22:15 02/10/2026

- Nhật ký máy đọc: `state/install-logs/20261002-221518.json`
- Sao lưu: `~/Documents/Claude/agent-stack/backups/install-20261002-221518`, gồm bản chụp `pristine/` của cấu hình trước khi cài
- Bước đã chạy: catalog
- Kết quả: 1 thay đổi, 0 mục bị bỏ qua, 0 lỗi

| # | Loại | Ở đâu | Chi tiết | Gỡ riêng mục này |
|---:|---|---|---|---|
| 1 | lệnh claude | `claude plugin install context7@claude-plugins-official --scope user` |  | `claude plugin uninstall context7@claude-plugins-official --scope user` |

## Lần cài 09:25 03/10/2026

- Nhật ký máy đọc: `state/install-logs/20261003-092531.json`
- Sao lưu: `~/Documents/Claude/agent-stack/backups/install-20261003-092531`, gồm bản chụp `pristine/` của cấu hình trước khi cài
- Bước đã chạy: plugin
- Kết quả: 1 thay đổi, 0 mục bị bỏ qua, 0 lỗi

| # | Loại | Ở đâu | Chi tiết | Gỡ riêng mục này |
|---:|---|---|---|---|
| 1 | lệnh claude | `claude plugin update agent-stack@agent-stack-local --scope user` |  | — |

## Lần cài 10:11 03/10/2026

- Nhật ký máy đọc: `state/install-logs/20261003-101141.json`
- Sao lưu: `~/Documents/Claude/agent-stack/backups/install-20261003-101141`, gồm bản chụp `pristine/` của cấu hình trước khi cài
- Bước đã chạy: plugin
- Kết quả: 1 thay đổi, 0 mục bị bỏ qua, 0 lỗi

| # | Loại | Ở đâu | Chi tiết | Gỡ riêng mục này |
|---:|---|---|---|---|
| 1 | lệnh claude | `claude plugin update agent-stack@agent-stack-local --scope user` |  | — |

## Lần cài 21:07 03/10/2026

- Nhật ký máy đọc: `state/install-logs/20261003-210751.json`
- Sao lưu: `~/Documents/Claude/agent-stack/backups/install-20261003-210751`, gồm bản chụp `pristine/` của cấu hình trước khi cài
- Bước đã chạy: plugin
- Kết quả: 1 thay đổi, 0 mục bị bỏ qua, 0 lỗi

| # | Loại | Ở đâu | Chi tiết | Gỡ riêng mục này |
|---:|---|---|---|---|
| 1 | lệnh claude | `claude plugin update agent-stack@agent-stack-local --scope user` |  | — |

## Gỡ toàn bộ

```bash
./install.sh --rollback          # xem trước, không sửa gì
./install.sh --rollback --apply  # gỡ thật mọi lần cài ở trên, mới nhất trước
```

Lệnh gỡ chạy ngược từng bảng ở trên:
- gỡ plugin và marketplace bằng `claude plugin`;
- gỡ các symlink;
- khôi phục file từ bản sao lưu;
- xóa thư mục do lần cài tạo ra, kể cả `vendor/`;
- dọn `enabledPlugins` và `extraKnownMarketplaces` trong `~/.claude/settings.json`;
- dọn cache và dữ liệu của đúng các plugin đã cài trong `~/.claude/plugins/`;
- so với bản chụp trước lần cài đầu tiên và báo những gì còn khác.

Muốn gỡ riêng một lần cài: `./install.sh --rollback state/install-logs/<tên>.json --apply`.

## Không thuộc lần cài (lần gỡ không đụng tới)

- Quyết định duyệt trong `vetted.lock` và báo cáo trong `vet-reports/`: đây là hồ sơ kiểm duyệt.
- `state/`, `.vet-cache/` và các thư mục `backups/install-*`: xóa tay khi không cần nữa.
- Công cụ bạn tự cài bằng brew (gitleaks, osv-scanner, pyright…): gỡ bằng `brew uninstall <tên>`.
- Cấu hình bạn tự sửa sau khi cài.
