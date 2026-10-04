@~/Documents/Claude/agent-stack/global/AGENTS.global.md

# Riêng Claude Code

## Bảng chọn cho dòng ➡️

Luật của dòng ➡️ nằm ở phần chung phía trên: thêm sau mọi câu trả lời, kèm Skill, và ưu tiên gợi ý `[agent-stack]` và `[router]` trong context. Trong Claude Code, Model là `sonnet`, `opus`, `haiku` hoặc `fable`; Effort từ `low` tới `max`. Khi không có gợi ý nào, chọn theo bảng:

| Việc tiếp theo | Model · Effort | Subagent | Skill |
|---|---|---|---|
| Hỏi nhanh, tra cú pháp, sửa nhỏ vài dòng, tin nhắn ngắn | sonnet · low | không | không (giong-van cho tin nhắn) |
| Xem tiến độ; lưu tiến độ, bàn giao | sonnet · low | không | tien-do; session-keeper |
| Tìm và đọc nhiều file | giữ nguyên | Explore (hoặc explore-lite để rẻ hơn) | không |
| Việc cơ học hàng loạt, dịch tài liệu | haiku (không có effort) | oc-worker | không |
| Nghiên cứu web, so sánh công cụ | sonnet · medium | researcher | reuse-best |
| Nghiên cứu sâu nhiều nguồn, sai thì đắt | opus · medium | researcher | không |
| Đọc sâu bài báo; phản biện bài báo | sonnet · medium; sonnet · high | không | paper-anatomy |
| Tính năng, refactor, viết test, lỗi có traceback rõ | sonnet · medium | test-runner khi chạy test | reuse-best nếu không tầm thường; tdd |
| Debug nhiều file, race, lỗi lúc được lúc không | opus · medium, chưa ra thì high | không | diagnosing-bugs nếu đã cài |
| Lỗi chỉ có trên production, không tái hiện được | opus · high | không | diagnosing-bugs nếu đã cài |
| Debug đã thử hai lần ở mức cao vẫn bế tắc | opus · xhigh, rồi fable · high | không | diagnosing-bugs nếu đã cài |
| Review diff nhỏ của mình trước commit | sonnet · high | reviewer | không |
| Review PR lớn; review bảo mật code thường | opus · high | reviewer | differential-review nếu đã cài |
| Review bảo mật phần mã hóa, token, thanh toán, sandbox | opus · xhigh | reviewer | differential-review nếu đã cài |
| Audit bảo mật cả repo trước phát hành | opus · max | reviewer | security-review |
| Kế hoạch việc vừa; văn bản dài | sonnet · high | Plan khi lập kế hoạch | reuse-best; giong-van |
| Thiết kế kiến trúc; refactor lớn nhiều module | opus · high (hoặc opusplan) | Plan | reuse-best |
| Quyết định khó đảo ngược (schema dữ liệu thật, giao thức) | opus · xhigh | Plan | reuse-best |
| Agent tự chạy trên 30 phút | opus · xhigh (hoặc `/effort ultracode`) | không | không |
| Opus ở effort cao vẫn chưa đạt; bài toán biên giới | fable · high, rồi fable · max | không | không |
| Cài skill, plugin, MCP của bên thứ ba | opus · high | không | vet-skill |
| Chạy test, tóm tắt lỗi | giữ nguyên | test-runner | không (kết quả ghi bằng `receipt.py`) |

Bảng đầy đủ, thang effort và căn cứ: `~/Documents/Claude/agent-stack/routing-table.md`. Lên bậc khi chưa đạt: hỏng vì bỏ sót thì tăng effort; đủ ngữ cảnh mà vẫn sai thì đổi model lớn hơn. Chỉ cần nghĩ sâu cho một lượt thì thêm `ultrathink` vào prompt thay vì đổi effort cả phiên.

## Subagent

- Subagent của agent-stack có tiền tố `agent-stack:`, ví dụ `agent-stack:reviewer`, `agent-stack:test-runner`.
- Giao cho subagent các việc đọc nhiều hoặc sinh output dài (log test, kết quả tìm kiếm), để context chính gọn.
- Subagent vẫn tính vào hạn mức. Không chia nhỏ việc nếu một model làm liền mạch thì tốt hơn.
