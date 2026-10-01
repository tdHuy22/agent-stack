@~/Documents/Claude/agent-stack/global/AGENTS.global.md

# Riêng Claude Code

## Gợi ý bước tiếp theo

Khi câu trả lời kết thúc một việc và còn việc tiếp theo, thêm đúng một dòng cuối:

`➡️ Tiếp: <việc> · Model: <sonnet|opus|haiku|fable> · Effort: <low…max> · Subagent: <tên|không>`

Bỏ qua dòng này với câu hỏi nhanh. Chọn theo bảng dưới. Chỉ khuyên đổi model hay effort ở ranh giới giữa hai việc, vì đổi giữa chừng làm mất prompt cache.

| Việc tiếp theo | Model · Effort | Subagent |
|---|---|---|
| Hỏi nhanh, xem tiến độ | sonnet · low | không |
| Tìm và đọc nhiều file | giữ nguyên | Explore (hoặc explore-lite để rẻ hơn) |
| Nghiên cứu web, tài liệu | sonnet · medium | researcher |
| Viết tính năng thông thường | sonnet · medium | không |
| Debug khó, nhiều bước | opus · high | không |
| Lập kế hoạch, thiết kế kiến trúc | opus · high (hoặc opusplan) | Plan |
| Review code hoặc bảo mật trước commit | opus · high | reviewer |
| Chạy test, tóm tắt lỗi | giữ nguyên | test-runner |
| Việc cơ học hàng loạt | haiku · low | oc-worker |
| Viết văn bản | sonnet · medium | không (skill giong-van) |

## Subagent

- Subagent của agent-stack có tiền tố `agent-stack:`, ví dụ `agent-stack:reviewer`, `agent-stack:test-runner`.
- Giao cho subagent các việc đọc nhiều hoặc sinh output dài (log test, kết quả tìm kiếm), để context chính gọn.
- Subagent vẫn tính vào hạn mức. Không chia nhỏ việc nếu một model làm liền mạch thì tốt hơn.
