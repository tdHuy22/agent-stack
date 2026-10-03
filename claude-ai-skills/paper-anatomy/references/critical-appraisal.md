# Phản biện: tuyên bố có đứng vững không

Dùng cho chế độ phản biện, và cho mục 6–7 của mọi bản giải phẫu. Mục tiêu không phải chấm điểm bài, mà là cho
người đọc biết **mỗi tuyên bố được chứng minh tới đâu**. Đánh giá công trình, không đánh giá con dấu: hội nghị
danh tiếng hay số trích dẫn chỉ là tín hiệu yếu.

## 1. Tuyên bố so với điều đã chứng minh

1. Liệt kê tuyên bố của tác giả ở tóm tắt, mở đầu, kết luận (có neo, có dấu vết). Tóm tắt thường tuyên bố rộng
   hơn phần thân chứng minh.
2. Với từng tuyên bố, tìm bằng chứng cụ thể: bảng, hình, định lý, thí nghiệm nào; thiết lập nào; thước đo nào.
3. Chấm mức chống đỡ:
   - **mạnh**: bằng chứng trực tiếp, đúng phạm vi tuyên bố, có đối chứng hợp lý, lặp lại được;
   - **vừa**: có bằng chứng nhưng hẹp hơn tuyên bố (ít dữ liệu, một mô hình, một miền, một lần chạy);
   - **yếu**: bằng chứng gián tiếp, giai thoại, ví dụ chọn lọc, hoặc thước đo không đo đúng điều tuyên bố;
   - **chưa có**: tuyên bố không được kiểm ở đâu trong bài.
4. Ghi khoảng cách: tuyên bố nói X, bằng chứng chỉ cho thấy X' hẹp hơn. Đây thường là phát hiện giá trị nhất.

Bảng mẫu:

| Tuyên bố | Bằng chứng (ở đâu) | Mức | Khoảng cách / lưu ý |
|---|---|---|---|
| "… giảm tỉ lệ tấn công xuống dưới 2%" 【§1 · tr.2 · "…"】 | Bảng 3, 4 mô hình, tấn công cố định 【§5.1 · tr.9 · Bảng 3】 | vừa | chưa thử tấn công thích nghi |

## 2. Mỗi điểm yếu: cái gì, ở đâu, vì sao quan trọng

Viết từng điểm yếu theo ba ý: **cái gì** (vấn đề cụ thể), **ở đâu** (neo), **vì sao quan trọng** (nó làm tuyên bố
nào lung lay, tới mức nào). Thêm cách kiểm hay cách sửa nếu nghĩ ra. Gắn [suy luận] cho mọi đánh giá của người
phân tích. Điểm yếu tác giả tự thừa nhận thì neo vào chỗ họ thừa nhận, tách khỏi điểm yếu người phân tích thấy.

**Trước khi kết luận bài thiếu, mâu thuẫn hay không giải thích điều gì**, tìm trong cả bài, kể cả phụ lục và chú
thích bảng (`--find` với vài từ khóa, tên bảng, tên phương pháp). Hai con số "mâu thuẫn" thường đo ở hai thiết lập
khác nhau mà bài đã nói rõ ở chỗ khác. Phê bình một điều bài đã trả lời làm mất uy tín của cả bản phản biện. Nếu tìm
rồi vẫn không thấy, ghi rõ "không thấy trong bài (đã tìm …)".

## 3. Dấu hiệu cần soi

Thống kê và thực nghiệm:
- không có phương sai, khoảng tin cậy, số seed hay số lần lặp; khác biệt nhỏ hơn nhiễu;
- so sánh nhiều cấu hình, chỉ báo cấu hình tốt nhất; chọn siêu tham số trên tập kiểm tra;
- baseline không được tinh chỉnh ngang phương pháp mới, hoặc lấy số từ bài khác với thiết lập khác;
- dữ liệu kiểm tra có thể đã rò vào dữ liệu huấn luyện (nhất là với LLM và benchmark công khai);
- ví dụ minh họa được chọn lọc; thất bại không được báo;
- thước đo thay thế (proxy) không đo đúng điều tuyên bố;
- cỡ mẫu nhỏ, một miền, một mô hình, mà kết luận tổng quát.

Lý thuyết: giả thiết mạnh hay khó kiểm; định lý về trường hợp khác với thứ được dùng trong thực nghiệm; chứng
minh quan trọng nằm hết ở phụ lục mà phần thân không nêu ý chính.

Bảo mật: chỉ thử tấn công cố định, không thử kẻ tấn công biết phòng thủ; mô hình mối đe dọa loại bỏ đúng những
tấn công khó nhất; đổi bảo mật lấy tiện ích mà không đo tiện ích.

Hệ thống: tải thử không giống tải thật; chi phí ẩn (bộ nhớ, độ trễ đuôi, công vận hành) không được báo.

## 4. Khả năng tái lập

Đánh dấu có hay không (có neo): mã nguồn; dữ liệu hay cách lấy dữ liệu; siêu tham số và cách chọn; số lần chạy và
cách tổng hợp; phần cứng và thời gian tính; phiên bản mô hình hay API (với bài dùng LLM thương mại, phiên bản mô
hình thay đổi theo thời gian). Thiếu những thứ này thì kết quả là giả thuyết cần lặp lại, chưa phải phát hiện.

## 5. Điều gì sẽ bác bỏ tuyên bố

Với tuyên bố trung tâm, nêu một thí nghiệm hay một phản ví dụ mà nếu xảy ra thì tuyên bố sai [suy luận]. Nếu
không nghĩ ra cách nào bác bỏ được, tuyên bố có thể quá mơ hồ để kiểm.

## 6. Câu hỏi cho tác giả

3–5 câu hỏi mà câu trả lời sẽ thay đổi đánh giá. Không hỏi những gì bài đã trả lời (tra bằng `--find` trước).

## 7. Khi người dùng muốn chấm điểm kiểu phản biện hội nghị

Chỉ làm khi được yêu cầu. Chấm 1–5 cho: tính đúng đắn (soundness), tính mới, độ chặt của thiết kế thí nghiệm, độ
chặt thống kê, khả năng tái lập, phạm vi áp dụng. Mỗi điểm kèm một câu lý do có neo.

Nguồn ý tưởng: S. Keshav, "How to Read a Paper" (đọc ba lượt, lượt ba là dựng lại bài trong đầu để lộ giả định
ẩn); danh sách tái lập của J. Pineau cho NeurIPS 2019; mẫu phản biện academic-paper-review của bytedance/deer-flow
(bảng tuyên bố–bằng chứng, cái gì/ở đâu/vì sao).
