@~/Documents/Claude/agent-stack/global/AGENTS.global.md

# Riêng Claude Code

## Bảng chọn cho dòng ➡️

Luật của dòng ➡️ nằm ở phần chung phía trên: thêm sau mọi câu trả lời, kèm Skill, và ưu tiên gợi ý `[agent-stack]` và `[router]` trong context. Trong Claude Code, Model là `sonnet`, `opus`, `haiku` hoặc `fable`; Effort từ `low` tới `max`. Khi không có gợi ý nào, chọn theo bảng:

| Việc tiếp theo | Model · Effort | Subagent | Skill |
|---|---|---|---|
| Hỏi nhanh, xem tiến độ | sonnet · low | không | tien-do |
| Tìm và đọc nhiều file | giữ nguyên | Explore (hoặc explore-lite để rẻ hơn) | không |
| Nghiên cứu web, tài liệu | sonnet · medium | researcher | không |
| Trước khi build: tìm công cụ, thư viện, bài nghiên cứu SOTA có sẵn | sonnet · medium | không | reuse-best |
| Viết tính năng thông thường | sonnet · medium | không | reuse-best nếu việc không tầm thường |
| Debug khó, nhiều bước | opus · high | không | diagnosing-bugs nếu đã cài |
| Lập kế hoạch, thiết kế kiến trúc | opus · high (hoặc opusplan) | Plan | reuse-best |
| Review code hoặc bảo mật trước commit | opus · high | reviewer | differential-review nếu đã cài |
| Chạy test, tóm tắt lỗi | giữ nguyên | test-runner | không (kết quả ghi bằng `receipt.py`) |
| Việc cơ học hàng loạt | haiku · low | oc-worker | không |
| Viết văn bản | sonnet · medium | không | giong-van |
| Lưu tiến độ, bàn giao | sonnet · low | không | session-keeper |
| Cài skill, plugin, MCP của bên thứ ba | opus · high | không | vet-skill |

## Subagent

- Subagent của agent-stack có tiền tố `agent-stack:`, ví dụ `agent-stack:reviewer`, `agent-stack:test-runner`.
- Giao cho subagent các việc đọc nhiều hoặc sinh output dài (log test, kết quả tìm kiếm), để context chính gọn.
- Subagent vẫn tính vào hạn mức. Không chia nhỏ việc nếu một model làm liền mạch thì tốt hơn.
