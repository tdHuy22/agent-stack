# Thể loại bài báo & cách điều chỉnh "kiến trúc"/"phương pháp" theo ngành

"Kiến trúc" và "phương pháp đề xuất" mang nghĩa khác nhau tùy thể loại. Trước khi giải phẫu,
hãy nhận diện bài thuộc loại nào, vì điều đó quyết định *cái gì đáng coi là lõi*.

## 1. Lý thuyết / chứng minh (theoretical / proof)
- **Lõi**: định lý/mệnh đề chính và điều nó khẳng định.
- **Tinh hoa**: ý tưởng then chốt của phép chứng minh (bổ đề bản lề, phép biến đổi, cấu trúc khéo).
- **Kiến trúc**: chuỗi định nghĩa → bổ đề → định lý; phụ thuộc logic giữa chúng.
- **Phương pháp**: kỹ thuật chứng minh (quy nạp, phản chứng, xây dựng, đối ngẫu...).
- Chú ý giả thiết (assumptions) — đó thường là "triết lý" của bài.

## 2. Thực nghiệm / quan sát (empirical / experimental — ML, y sinh, tâm lý, kinh tế lượng...)
- **Lõi**: giả thuyết được kiểm định + phát hiện chính.
- **Tinh hoa**: thiết kế thí nghiệm/biến điều khiển làm cho kết luận đứng vững.
- **Kiến trúc**: thiết kế nghiên cứu — biến độc lập/phụ thuộc, nhóm đối chứng, quy trình, đo lường.
- **Phương pháp**: pipeline thu thập dữ liệu, mô hình thống kê, kiểm định, ablation.
- Chú ý hiệu lực nội tại/ngoại tại (validity), cỡ mẫu, thước đo.

## 3. Hệ thống / kỹ thuật (systems / engineering)
- **Lõi**: cái được xây + vấn đề kỹ thuật nó giải.
- **Tinh hoa**: quyết định thiết kế tạo nên khác biệt (đánh đổi mấu chốt).
- **Kiến trúc**: các thành phần, luồng dữ liệu, giao diện giữa chúng (vẽ được sơ đồ khối).
- **Phương pháp**: cơ chế hoạt động + cách đánh giá (benchmark, tải, độ trễ...).

## 4. Mô hình/thuật toán mới (method paper — phổ biến trong CS/AI)
- **Lõi**: thuật toán/mô hình đề xuất + bài toán nó nhắm tới.
- **Tinh hoa**: trực giác cốt lõi khiến nó hoạt động ("vì sao cái này thắng cái cũ").
- **Kiến trúc**: cấu trúc mô hình (các khối, đầu vào→đầu ra, hàm mất mát, vòng huấn luyện).
- **Phương pháp**: tái dựng thuật toán theo từng bước (pseudo-code đọc được), kèm công thức chính.

## 5. Khảo sát / tổng quan (survey / review)
- **Lõi**: cách bài tổ chức & phân loại lĩnh vực (taxonomy).
- **Tinh hoa**: lăng kính/khung phân loại mà tác giả áp lên lĩnh vực.
- **Kiến trúc**: trục phân loại và quan hệ giữa các nhánh.
- **Phương pháp**: tiêu chí chọn tài liệu, cách so sánh.

## 6. Quan điểm / lý thuyết nhân văn (position / humanities / philosophy)
- **Lõi**: luận điểm trung tâm tác giả bảo vệ.
- **Tinh hoa**: bước lập luận then chốt (hoặc phản ví dụ) chống đỡ luận điểm.
- **Kiến trúc**: mạch lập luận — tiền đề → bước trung gian → kết luận; các phản biện được lường trước.
- **Phương pháp**: kiểu lập luận (phân tích khái niệm, diễn giải văn bản, biện chứng...).

## 7. Dữ liệu / tài nguyên (dataset / resource / benchmark)
- **Lõi**: tài nguyên được tạo + khoảng trống nó lấp.
- **Tinh hoa**: lựa chọn thiết kế dữ liệu đáng giá (cách gán nhãn, độ phủ, kiểm soát chất lượng).
- **Kiến trúc**: cấu trúc dữ liệu, schema, quy trình tạo.
- **Phương pháp**: quy trình thu thập/annotate + thí nghiệm baseline.

---
**Lưu ý chung**: nhiều bài lai (hybrid) — ví dụ vừa đề xuất phương pháp vừa có cả lý thuyết và thực nghiệm.
Khi đó nhận diện *cả hai trục* và nói rõ trục nào là đóng góp chính theo lời tác giả (neo trang).
