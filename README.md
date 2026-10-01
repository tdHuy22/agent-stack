# agent-stack

Bộ công cụ cá nhân cho Claude Code và OpenCode, gồm:

- **vet-skill:** kiểm duyệt skill, plugin và MCP của bên thứ ba trước khi cài.
- **session-keeper:** giữ trạng thái công việc trên đĩa, để làm tiếp được sau khi hết hạn mức, crash, hoặc khi đổi sang OpenCode.
- **tien-do:** báo tiến độ, việc dang dở và việc nên làm tiếp.
- **task-router:** gợi ý skill, model, effort và subagent cho từng việc.
- **giong-van:** chỉnh văn theo giọng của chính bạn, bỏ các dấu hiệu văn AI.

| File | Nội dung |
|---|---|
| `KE-HOACH.md` | Kế hoạch và thiết kế |
| `PLAN.md` | Tiến độ triển khai (mục §0: đang ở đâu, việc tiếp theo) |
| `BASELINE.md` | Số liệu nền trước khi thay đổi |
| `CLAUDE.md` | Luật khi làm việc trong repo này |

## Dùng thử mà không thay đổi gì trên máy (từ GĐ2)

Plugin nằm trong `plugin/`. Mở Claude Code ở terminal và nạp plugin cho riêng phiên đó:

```bash
claude --plugin-dir ~/Documents/Claude/agent-stack/plugin
```

## Chạy test

```bash
python3 -m unittest discover -s tests -t .
```

## Kích hoạt toàn cục

Dùng `install.sh` (có từ GĐ3). Mặc định script chỉ in ra những việc sẽ làm. Chỉ khi chạy kèm `--apply` nó mới sửa `~/.claude` và `~/.config/opencode`, và luôn sao lưu trước khi sửa.
