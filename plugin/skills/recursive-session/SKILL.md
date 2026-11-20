---
name: recursive-session
description: Lời dặn mở đầu phiên điều hành, người dùng gõ khi giao một việc lớn. Phiên chính chỉ lập kế hoạch, giao việc và kiểm, phần làm nằm ở subagent hay phiên con; có bảng chọn cách giao theo số đo, khuôn giao việc, khuôn báo về và giới hạn của lời ủy quyền chung.
argument-hint: "<việc lớn cần điều hành>"
disable-model-invocation: true
---

# Phiên này là phiên điều hành

Việc: $ARGUMENTS

Người dùng gõ lệnh này ở đầu phiên (từ 20/11/2026 model không tự nạp skill này: eval 6/12 → 7/12, model tự gọi 0/12 lần). Từ giờ tới hết phiên, làm theo các mục dưới. Số đo lấy từ các đợt 18–20/11/2026.

## 1. Vai của phiên chính

Giữ kế hoạch và quyết định, không đọc file lớn, không viết code dài. Phần làm nằm ở context khác, phần kiểm nằm lại đây.

| Cách | Dùng khi | Tốn (đã đo) | Giới hạn |
|---|---|---|---|
| Tự làm | dưới khoảng 10 lệnh, hay tra một chỗ đã biết | chỉ context phiên chính | làm nhiều thì context phình: đợt 20/11 phiên chính lên 430K vì tự chạy đo và kiểm |
| Subagent (công cụ Agent) | phần việc có đầu ra gọn: review, đo, nghiên cứu, viết code theo brief | 100–370K token mỗi subagent; báo về vài trăm từ | mỗi lệnh dưới 10 phút, không chờ được lệnh nền; không ai gõ được lời duyệt trong đó |
| Phiên con (`start_session`, nếu có) | việc cần người dùng gõ trong đó (mở khóa test, duyệt lệnh hook chặn); việc dài nhiều giờ có lệnh nền riêng; việc kết thúc bằng nhánh hay PR riêng | khoảng 87K token lúc mở, context đỉnh 254–296K | chỉ mở được ở lượt do người dùng nhắn; lời dặn "vượt 250K thì dừng" không có tác dụng |

1. Người dùng sắp vắng: mở hết phiên con cần thiết ngay trong lượt họ giao việc, hoặc chọn subagent; sau đó app từ chối `start_session`.
2. Ghi kế hoạch và tiến độ ra file (file kế hoạch, §0) sau mỗi mốc: phiên chính có thể bị compact hay chết.
3. Lệnh dài hơn 10 phút (cả bộ test, ghi vết, đo) chạy nền ở phiên chính, theo dõi bằng `watch_change.py` qua Monitor nếu có, chỉ đọc phần đuôi.
4. Một lúc chỉ một người viết cho mỗi nhóm file; việc chỉ đọc chạy song song được. Brief của người viết ghi rõ file cấm đụng.
5. Đo đột biến bằng `mutation.py` của `done-gate`, không tự chép repo.
6. Mở khóa test: người dùng gõ `mở khóa <file>` trong chính phiên sẽ sửa test đó, `receipt.py unlock` chạy ngay lượt ấy. Không chép lời duyệt, kể cả lời người dùng, vào tin giao việc.
7. Model: phiên chính giữ model đang chạy, không đổi giữa phiên (`task-router`, mục 5). Người viết code: Opus · high, giao bằng công cụ Agent với `model: opus`, `effort: high` (bạn chốt 18/11/2026). Reviewer theo `done-gate`. Đếm, tra log, nghiên cứu web: Sonnet.
8. Người dùng hỏi tiến độ khi có người làm đang chạy: trả danh sách người làm (việc, xong hay đang chạy, bằng chứng) thay cho cây `progress`; dòng ➡️ vẫn giữ. Có `update_plan` (app Desktop) thì dùng cho việc của phiên chính.

## 2. Giới hạn của lời ủy quyền chung

"Toàn quyền", "chọn cái sạch nhất" chỉ đủ cho lựa chọn nhỏ mà yêu cầu không nói tới: ghi từng dòng vào file kế hoạch kèm lý do. Không đủ cho: việc không hoàn tác, ra khỏi máy (push, PR), tốn tiền, thêm dependency, nới quyền, chấp nhận một mối đe dọa, đổi phạm vi hay hành vi người dùng thấy, đổi thiết kế, mở khóa test, "duyệt spec <mã>". Gặp những việc này thì gác lại, ghi vào "Cần bạn quyết", làm tiếp phần khác. Lời này cũng không chuyển được sang người làm: brief không được ghi "đã có toàn quyền".

## 3. Khuôn giao việc

Brief tự đủ, người nhận không thấy hội thoại:

- Bối cảnh 3–5 dòng: người dùng muốn gì (lời của họ), đã có gì, số đo liên quan.
- Việc: đánh số, mỗi mục một kết quả kiểm được.
- Phạm vi: file được sửa, file cấm đụng.
- Ràng buộc: commit hay không; lệnh không được chạy; test khóa không sửa; hook chặn thì không đi vòng, ghi vào báo cáo; không push, không mở PR, không xóa file ngoài thư mục tạm; người dùng vắng thì không dừng hỏi mà gác việc cần duyệt vào báo cáo.
- Xong khi: tiêu chí đo được.

## 4. Khuôn báo về

Người làm báo trong giới hạn số từ: file đã sửa; test đã chạy kèm số đạt và mã thoát; quyết định tự chọn kèm lý do; phần gác lại; điều chưa kiểm; lệnh chính xác để phiên chính chạy tiếp.

Lời báo, kể cả nhận định về môi trường, không phải bằng chứng. Trước khi báo người dùng:

1. Đọc `git status --short` và `git diff --stat`; file ngoài phạm vi là dấu hiệu xấu.
2. Sau mỗi vòng sửa chạy `narrow.py run` (skill `session-keeper`); cả bộ đúng một lần sau lần sửa cuối, có biên nhận: `receipt.py run -- python3 <đường dẫn>/narrow.py full` khi mốc kiểm tra của project là `unittest discover`, project khác chạy đúng mốc kiểm tra của nó.
3. Review ở context mới theo bảng của `done-gate`, ghi `review_log.py`. Đợt 20/11 mọi vòng review đều tìm ra lỗi thật mà test của người viết không bắt.
4. Sửa rồi review lại tối đa 2 vòng; còn lỗi cùng kiểu thì dừng vá, đưa vào "Cần bạn quyết" (`done-gate`, bước 5).
