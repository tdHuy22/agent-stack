# Skill đồng bộ qua tài khoản claude.ai

Thư mục này là nguồn của các skill bạn tải lên claude.ai (Settings → Capabilities → Skills). Claude.ai đồng bộ chúng xuống Claude Code với tiền tố `anthropic-skills:`, nên chúng **không** nằm trong plugin `agent-stack`: để vào plugin thì cùng một skill sẽ hiện hai lần.

| Skill | Ghi chú |
|---|---|
| `paper-anatomy` | Giải phẫu bài báo khoa học có neo trang. Bench so bản cũ và bản mới: `paper-anatomy-bench/` |

## Cập nhật lên claude.ai

1. Đóng gói: `python3 claude-ai-skills/package.py paper-anatomy` → `.tmp/dist/paper-anatomy.skill` (zip, bỏ `__pycache__`).
2. Trên claude.ai, mở skill cũ, thay bằng file `.skill` vừa tạo (giữ nguyên tên `paper-anatomy`).
3. Claude Code nhận bản mới ở lần đồng bộ sau (bản chép nằm ở `~/.claude/skills/synced/…`, chỉ đọc).

Bản trên máy lúc nhập (03/10/2026) có `SKILL.md` sha256 `5ca6a16c…27dd4`; commit đầu tiên của thư mục này giữ nguyên bản đó để so.
