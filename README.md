# agent-stack

Bộ công cụ cá nhân cho Claude Code và OpenCode. Thiết kế ở `KE-HOACH.md`, tiến độ ở `PLAN.md` (mục §0), số liệu nền ở `BASELINE.md`.

## Có gì

| Thành phần | Vị trí | Việc |
|---|---|---|
| `vet-skill` | `plugin/skills/vet-skill` | Kiểm duyệt skill, plugin, MCP của bên thứ ba: ghim commit, dò dấu hiệu độc hại, chạy skill-scanner, ghi `vetted.lock` |
| `session-keeper` | `plugin/skills/session-keeper` | Giữ trạng thái trên đĩa (mục §0 của PLAN.md, HANDOFF.md) để làm tiếp sau khi hết hạn mức, crash hoặc đổi sang OpenCode; `receipt.py` ghi kết quả kiểm tra gắn với nội dung code |
| `tien-do` | `plugin/skills/tien-do` | Tiến độ, việc dang dở, việc nên làm tiếp (5 bậc ưu tiên); `--all` cho mọi project |
| `task-router` | `plugin/skills/task-router` | Gợi ý model, effort, subagent, skill cho một việc, tính cả hồ sơ project (loại code, test, CI, code nhạy cảm) và việc tiếp theo trong §0; `route.py --session` cho công cụ không có hook như OpenCode |
| `giong-van` | `plugin/skills/giong-van` | Chỉnh văn theo giọng người viết, bỏ dấu hiệu văn AI (`tells.py`) |
| `reuse-best` | `plugin/skills/reuse-best` | Trước khi build: tìm thứ có sẵn tốt nhất trên GitHub và trong nghiên cứu SOTA (`scout.py`), rồi quyết định dùng lại hay tự làm |
| Hook | `plugin/hooks` | SessionStart nạp §0; UserPromptSubmit cảnh báo hạn mức và gợi ý router; PreCompact; Stop; SessionEnd |
| Agent | `plugin/agents` | reviewer, researcher, test-runner, explore-lite, oc-worker (tên có tiền tố `agent-stack:`) |
| Agent OpenCode | `opencode/agents/worker.md` | Worker chạy model local, chỉ được chạy lệnh kiểm tra |
| Statusline | `statusline/statusline.py` | model · effort · ctx · 5h · 7d |
| Luật chung | `global/` | Cho Claude Code và OpenCode; chỉ được link khi cài |
| Eval | `evals/` | 12 việc để chọn cấu hình rẻ nhất mà vẫn giữ chất lượng |
| Công cụ | `tools/` | `usage_snapshot.py`, `install.py`, `maintain.py` |

## Dùng thử mà không thay đổi gì trên máy

```bash
claude --plugin-dir ~/Documents/Claude/agent-stack/plugin
```

## Kích hoạt toàn cục

```bash
./install.sh            # xem trước, không sửa gì
./install.sh --apply    # thực hiện: sao lưu trước, chỉ cài mục đã approve; mã thoát 1 = có lỗi, 2 = cài chưa đủ
./install.sh --rollback --apply
```

## Sau khi sửa code plugin

Claude Code chép plugin vào `~/.claude/plugins/cache/` lúc cài, nên sửa trong repo chưa có hiệu lực ngay. Tăng `version` trong `plugin/.claude-plugin/plugin.json`, rồi:

```bash
./install.sh --apply --only plugin   # chạy cả claude plugin update; mở phiên mới để nạp lại
```

Mọi thứ đã cài được ghi trong `INSTALLED.md` (kèm lệnh gỡ từng mục). Gỡ toàn bộ: `./install.sh --rollback --apply`.

## Kiểm tra

```bash
python3 -m unittest discover -s tests -t .
claude plugin validate plugin
python3 evals/run_eval.py --self-test
python3 tools/maintain.py          # mỗi tháng
```
