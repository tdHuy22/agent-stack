@~/Documents/Claude/agent-stack/global/SHARED.global.md

# Riêng Claude Code

## Bảng chọn cho dòng ➡️

Model (mới nhất, kiểm 08/10/2026): `sonnet` (Sonnet 5.5), `opus` (Opus 5.5), `fable` (Fable 5.1), `claude-haiku-5-5` (Haiku 5.5; alias `haiku` còn trỏ Haiku 4.5, đừng dùng); Effort: `low` tới `max`, mọi model kể cả Haiku 5.5. Bảng dùng khi không có gợi ý `[agent-stack]` hay `[router]` (– nghĩa là ghi `không`; * là chỉ dùng khi đã cài):

| Việc | Model·Effort | Subagent | Skill |
|---|---|---|---|
| Hỏi nhanh, tra cú pháp, sửa vài dòng, tin nhắn ngắn | sonnet·low | – | – (giong-van khi viết tin nhắn) |
| Xem tiến độ; lưu tiến độ, bàn giao | sonnet·low | – | tien-do; session-keeper |
| Tìm, đọc nhiều file | giữ nguyên | Explore (explore-lite chạy Haiku 5.5, rẻ hơn) | – |
| Việc cơ học hàng loạt có kiểm tra tự động, dịch tài liệu | claude-haiku-5-5·low | oc-worker | – |
| Nghiên cứu web, so sánh công cụ | sonnet·medium | researcher | reuse-best |
| Nghiên cứu sâu nhiều nguồn, sai thì đắt | opus·medium | researcher | – |
| Đọc sâu bài báo; phản biện bài báo | sonnet·medium; sonnet·high | – | paper-anatomy |
| Tính năng, viết test, lỗi có traceback rõ, khi project có test | claude-haiku-5-5·low; test trượt thì sonnet·medium | test-runner khi chạy test | reuse-best nếu không tầm thường |
| Như trên mà không có test; refactor | sonnet·medium | test-runner khi chạy test | reuse-best nếu không tầm thường |
| Debug nhiều file, race, lỗi lúc được lúc không | opus·medium, chưa ra thì high | – | – |
| Lỗi chỉ có trên production, không tái hiện được | opus·high | – | – |
| Debug thử hai lần ở mức cao vẫn bế tắc | opus·xhigh, rồi fable·high | – | – |
| Kiểm thay đổi trước khi báo xong hay commit | sonnet·high | reviewer khi rủi ro vừa, cao | chot-viec |
| Review PR lớn; review bảo mật code thường | opus·high | reviewer | differential-review* |
| Review bảo mật mã hóa, token, thanh toán, sandbox | opus·xhigh | reviewer | differential-review* |
| Audit bảo mật cả repo trước phát hành | opus·max | reviewer | security-review |
| Kế hoạch việc vừa; văn bản dài | sonnet·high | Plan khi lập kế hoạch | reuse-best; giong-van |
| Thiết kế kiến trúc; refactor lớn nhiều module | opus·high (hoặc opusplan) | Plan | reuse-best |
| Quyết định khó đảo ngược (schema dữ liệu thật, giao thức) | opus·xhigh | Plan | reuse-best |
| Agent tự chạy trên 30 phút | opus·xhigh (hoặc `/effort ultracode`) | – | – |
| Opus effort cao vẫn chưa đạt; bài toán biên giới | fable·high, rồi fable·max | – | – |
| Cài skill, plugin, MCP bên thứ ba | opus·high | – | vet-skill |
| Chạy test, tóm tắt lỗi | giữ nguyên | test-runner | – (ghi kết quả bằng `receipt.py`) |

Bảng đầy đủ, thang effort, căn cứ: `~/Documents/Claude/agent-stack/routing-table.md`. Chưa đạt thì lên bậc: hỏng vì bỏ sót thì tăng effort; đủ ngữ cảnh mà vẫn sai thì đổi model lớn hơn. Chỉ cần nghĩ sâu một lượt thì thêm `ultrathink` vào prompt, đừng đổi effort cả phiên.

## Kế hoạch có nhiều phương án

- Kế hoạch có từ hai phương án đáng so sánh hoặc từ ba quyết định cần chốt: ngoài tóm tắt trong chat, đăng trang Artifact riêng tư đặt phương án cạnh nhau (kèm ví dụ hoặc sơ đồ) và các câu cần chốt; đọc bình luận bằng `ArtifactComments` rồi mới làm, còn người dùng trả lời trong chat thì theo đó. Kế hoạch một hướng, hay không có công cụ Artifact, thì giữ trong chat.

## Subagent

- Subagent của agent-stack có tiền tố `agent-stack:`, ví dụ `agent-stack:reviewer`. Giao subagent việc đọc nhiều hay sinh output dài (log test, kết quả tìm kiếm) cho context chính gọn; subagent vẫn tính vào hạn mức, nên đừng chia nhỏ việc mà một model làm liền mạch tốt hơn.
