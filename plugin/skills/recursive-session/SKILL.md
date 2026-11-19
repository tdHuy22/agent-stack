---
name: recursive-session
description: Điều hành một việc lớn bằng phiên chính nhỏ gọn. Phiên chính chỉ lập kế hoạch và kiểm, giao phần làm cho subagent hay phiên con. Có bảng chọn theo số đo thật, khuôn giao việc, khuôn báo về, giới hạn của lời ủy quyền chung. Dùng khi việc có từ hai phần độc lập, khi người dùng sắp vắng (chạy qua đêm), khi context phiên chính đã lớn, hoặc khi người dùng nói điều hành, chia việc, mở phiên con.
when_to_use: điều hành, chia việc, mở phiên con, sub-session, orchestrate, chạy qua đêm, phiên chính chỉ điều hành
---

# Điều hành việc lớn: phiên chính nhỏ, người làm ở context riêng

Phiên chính giữ kế hoạch và quyết định, không đọc file lớn, không viết code dài. Phần làm nằm ở context khác, phần kiểm nằm lại ở phiên chính. Số đo lấy từ các đợt 18–20/11/2026.

## 1. Chọn cách giao

| Cách | Dùng khi | Tốn (đã đo) | Giới hạn |
|---|---|---|---|
| Tự làm | dưới khoảng 10 lệnh, hay tra một chỗ đã biết | chỉ context phiên chính | làm nhiều thì context phình: đợt 20/11 phiên chính lên 430K vì tự chạy đo và kiểm |
| Subagent (công cụ Agent) | một phần việc có đầu ra gọn: review, đo, nghiên cứu, viết code theo brief | 100–370K token mỗi subagent; báo về vài trăm từ | mỗi lệnh dưới 10 phút, không chờ được lệnh nền; không ai gõ được lời duyệt trong đó; chỉ làm đúng phạm vi brief ghi |
| Phiên con (`start_session`, nếu có) | việc cần người dùng gõ trong đó (mở khóa test, duyệt lệnh hook chặn); việc dài nhiều giờ có lệnh nền riêng; việc kết thúc bằng nhánh hay PR riêng | khoảng 87K token lúc mở, context đỉnh 254–296K | chỉ mở được ở lượt do người dùng nhắn; lời dặn "vượt 250K thì dừng" không có tác dụng |

- Người dùng sắp vắng: mở hết phiên con cần thiết ngay trong lượt họ giao việc, hoặc chọn subagent. Sau đó app từ chối `start_session`.
- Mở khóa test: người dùng gõ `mở khóa <file>` trong phiên sẽ sửa test đó, và `receipt.py unlock` chạy ngay lượt ấy (lời duyệt chỉ có hiệu lực trong lượt). Không chép lời duyệt, kể cả lời người dùng, vào tin giao việc cho phiên con hay subagent. Chưa có lời duyệt thì gác phần đó.

## 2. Phiên chính làm gì

1. Ghi kế hoạch và tiến độ ra file (file kế hoạch, §0) sau mỗi mốc: phiên chính có thể bị compact hay chết.
2. Lệnh dài hơn 10 phút (cả bộ test, ghi vết, đo) do phiên chính chạy nền, theo dõi bằng `watch_change.py` qua Monitor nếu có, chỉ đọc phần đuôi.
3. Một lúc chỉ một người viết cho mỗi nhóm file. Việc chỉ đọc (review, đo, nghiên cứu) chạy song song với người viết được. Brief của người viết ghi rõ file cấm đụng khi có người khác đang làm.
4. Đo đột biến: dùng `mutation.py` của `done-gate`, không tự chép repo (bản chép trong thư mục tạm làm các test về thư mục tạm trượt).
5. Lời ủy quyền chung ("toàn quyền", "chọn cái sạch nhất") chỉ đủ cho lựa chọn nhỏ mà yêu cầu không nói tới: ghi từng dòng vào file kế hoạch kèm lý do. Không đủ cho: việc không hoàn tác, ra khỏi máy (push, PR), tốn tiền, thêm dependency, nới quyền, chấp nhận một mối đe dọa, đổi phạm vi hay hành vi người dùng thấy, đổi thiết kế, mở khóa test, "duyệt spec <mã>". Gặp những việc này thì gác lại, ghi vào "Cần bạn quyết", làm tiếp phần khác.

## 3. Khuôn giao việc

Brief tự đủ, người nhận không thấy hội thoại:

- Bối cảnh 3–5 dòng: người dùng muốn gì (lời của họ), đã có gì, số đo liên quan.
- Việc: đánh số, mỗi mục một kết quả kiểm được.
- Phạm vi: file được sửa, file cấm đụng.
- Ràng buộc: commit hay không; lệnh nào không được chạy; test khóa không sửa; hook chặn thì không đi vòng, ghi vào báo cáo; không push, không mở PR, không xóa file ngoài thư mục tạm; người dùng vắng thì không dừng hỏi mà gác việc cần duyệt vào báo cáo.
- Xong khi: tiêu chí đo được.
- Báo về: giới hạn số từ; file đã sửa; test đã chạy kèm số đạt; quyết định tự chọn; phần gác lại; điều chưa kiểm; lệnh chính xác để phiên chính chạy tiếp.

## 4. Kiểm lại trước khi báo

Lời báo của người làm, kể cả nhận định về môi trường, không phải bằng chứng.

1. Đọc `git status --short` và `git diff --stat`; file ngoài phạm vi là dấu hiệu xấu.
2. Sau mỗi vòng sửa chạy `narrow.py run` (skill `session-keeper`). Cả bộ đúng một lần, sau lần sửa cuối, có biên nhận: `receipt.py run -- python3 <đường dẫn>/narrow.py full` (project có mốc kiểm tra là `unittest discover`).
3. Review ở context mới theo bảng của `done-gate`, ghi `review_log.py`. Đợt 20/11 mọi vòng review đều tìm ra lỗi thật mà test của người viết không bắt.
4. Sửa rồi review lại tối đa 2 vòng. Còn lỗi cùng một kiểu sau 2 vòng thì dừng vá: đưa lỗi còn lại và các vòng đã sửa vào "Cần bạn quyết" (`done-gate`, bước 5). Đổi thiết kế là quyết định của người dùng; họ vắng thì gác phần đó.

## 5. Tiến độ và model

- Tiến độ: khi có người làm đang chạy, người dùng hỏi tiến độ thì trả danh sách người làm (việc, xong hay đang chạy, bằng chứng) thay cho cây `progress`; dòng ➡️ vẫn giữ. Có `update_plan` (app Desktop) thì dùng cho việc của phiên chính, và ghi mục "Tiến độ" trong file kế hoạch.
- Model: phiên chính giữ model đang chạy, chỉ lập kế hoạch và quyết định; không đổi model giữa phiên (`task-router`, mục 5). Người viết code: Opus · high, đè lên bảng việc lẻ của `task-router` (bạn chốt 18/11/2026); giao bằng công cụ Agent với `model: opus`, `effort: high`. Reviewer theo `done-gate`. Đếm, tra log, nghiên cứu web: Sonnet.
