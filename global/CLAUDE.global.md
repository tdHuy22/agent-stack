@~/Documents/Claude/agent-stack/global/SHARED.global.md

# Riêng Claude Code

## Bảng chọn cho dòng ➡️

Khi không có gợi ý `[agent-stack]` hay `[router]`, chọn theo mục "Bảng mặc định cho dòng ➡️" trong `~/Documents/Claude/agent-stack/plugin/skills/task-router/SKILL.md` (đọc thẳng file; căn cứ: `routing-table.md`). Chưa đạt thì lên bậc theo skill đó; chỉ cần nghĩ sâu một lượt thì thêm `ultrathink` vào prompt.

Model trong bảng là model hợp với việc, không phải lệnh đổi ngay. Cách đổi effort, đổi model và giao Agent với `model`, `effort` của dòng bảng: `task-router`, mục 5. Skill có `model:` trong frontmatter phải có `context: fork`.

## Trang HTML và Artifact

- Trang cho người đọc: nội dung theo `reader-page`, trình bày theo `artifact-design`. Kế hoạch có từ hai phương án đáng so sánh hay ba quyết định cần chốt: ngoài tóm tắt trong chat, đăng Artifact riêng tư và đọc bình luận bằng `ArtifactComments` rồi mới làm.

## Subagent

- Subagent của agent-stack có tiền tố `agent-stack:` (như `agent-stack:reviewer`). Giao subagent việc đọc nhiều hay sinh output dài, cho context chính gọn; đừng chia nhỏ việc mà một model làm liền mạch tốt hơn.
- Việc chạy lâu: chạy `watch_change.py` bằng Monitor (Bash chạy nền chỉ báo khi script thoát).
