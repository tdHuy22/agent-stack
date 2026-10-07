@~/Documents/Claude/agent-stack/global/AGENTS.global.md

# Riêng Claude Code

## Bảng chọn cho dòng ➡️

Luật của dòng ➡️ ở phần chung phía trên. Trong Claude Code, Model là `sonnet`, `opus`, `haiku` hoặc `fable`; Effort từ `low` tới `max`. Khi không có gợi ý `[agent-stack]` hay `[router]`, chọn theo bảng:

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
| Xong một thay đổi, kiểm trước khi báo xong hay commit | sonnet · high | reviewer khi rủi ro vừa hoặc cao | chot-viec |
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

## Kế hoạch có nhiều phương án

- Kế hoạch có từ hai phương án đáng so sánh hoặc từ ba quyết định cần chốt: ngoài tóm tắt trong chat, đăng một trang Artifact riêng tư đặt các phương án cạnh nhau (kèm ví dụ hoặc sơ đồ) và các câu cần chốt; đọc bình luận của người dùng bằng `ArtifactComments` rồi mới làm; người dùng trả lời trong chat thì theo đó. Kế hoạch một hướng, hoặc không có công cụ Artifact, thì giữ trong chat.

## Subagent

- Subagent của agent-stack có tiền tố `agent-stack:`, ví dụ `agent-stack:reviewer`, `agent-stack:test-runner`.
- Giao cho subagent các việc đọc nhiều hoặc sinh output dài (log test, kết quả tìm kiếm), để context chính gọn.
- Subagent vẫn tính vào hạn mức. Không chia nhỏ việc nếu một model làm liền mạch thì tốt hơn.
