# Thể loại bài báo và cách chỉnh "kiến trúc", "phương pháp", "bằng chứng" theo thể loại

"Kiến trúc", "phương pháp" và "bằng chứng" mang nghĩa khác nhau tùy thể loại. Nhận diện thể loại trước, vì nó
quyết định *cái gì đáng coi là lõi* và *bằng chứng nào cần soi*. Nhiều bài lai (vừa đề xuất phương pháp vừa có
lý thuyết và thực nghiệm): khi đó nhận diện đủ các trục và nói rõ trục nào là đóng góp chính theo lời tác giả.

## 1. Lý thuyết / chứng minh
- **Lõi**: định lý hay mệnh đề chính và điều nó khẳng định.
- **Tinh hoa**: ý then chốt của phép chứng minh (bổ đề bản lề, phép biến đổi, cấu trúc khéo).
- **Kiến trúc**: chuỗi định nghĩa → bổ đề → định lý và phụ thuộc logic giữa chúng.
- **Phương pháp**: kỹ thuật chứng minh (quy nạp, phản chứng, xây dựng, đối ngẫu, xác suất…).
- **Soi bằng chứng**: giả thiết của định lý (đó thường là "triết lý" của bài); giả thiết có thỏa trong thực tế
  không; chặn có chặt không; điều kiện nào bị đẩy xuống phụ lục; định lý nói về đại lượng nào (trường hợp xấu
  nhất, kỳ vọng, xác suất cao).

## 2. Thực nghiệm / quan sát (ML, y sinh, tâm lý, kinh tế lượng…)
- **Lõi**: giả thuyết được kiểm định và phát hiện chính.
- **Tinh hoa**: thiết kế thí nghiệm hay biến điều khiển làm kết luận đứng vững.
- **Kiến trúc**: thiết kế nghiên cứu: biến độc lập và phụ thuộc, nhóm đối chứng, quy trình, đo lường.
- **Phương pháp**: thu thập dữ liệu, mô hình thống kê, kiểm định, ablation.
- **Soi bằng chứng**: hiệu lực nội tại và ngoại tại, cỡ mẫu, thước đo có đo đúng điều tuyên bố không, phương sai
  và khoảng tin cậy, so sánh nhiều lần, nhiễu (confounder).

## 3. Hệ thống / kỹ thuật
- **Lõi**: cái được xây và vấn đề kỹ thuật nó giải.
- **Tinh hoa**: quyết định thiết kế tạo khác biệt (đánh đổi mấu chốt).
- **Kiến trúc**: thành phần, luồng dữ liệu, giao diện giữa chúng (vẽ được sơ đồ khối).
- **Phương pháp**: cơ chế hoạt động và cách đánh giá (benchmark, tải, độ trễ…).
- **Soi bằng chứng**: tải thử có giống tải thật; so với baseline được cấu hình công bằng; chi phí (bộ nhớ, độ
  trễ, công vận hành) có được báo; điều gì xảy ra khi giả định thiết kế bị vi phạm.

## 4. Mô hình / thuật toán mới (phổ biến trong CS và AI)
- **Lõi**: thuật toán hay mô hình đề xuất và bài toán nó nhắm tới.
- **Tinh hoa**: trực giác cốt lõi khiến nó hoạt động ("vì sao cái này thắng cái cũ").
- **Kiến trúc**: cấu trúc mô hình (các khối, đầu vào → đầu ra, hàm mất mát, vòng huấn luyện hay suy luận).
- **Phương pháp**: tái dựng thuật toán từng bước (pseudo-code đọc được), kèm công thức chính.
- **Soi bằng chứng**: ablation có tách được đóng góp của ý then chốt; baseline có được tinh chỉnh như phương
  pháp mới; nhiều seed hay một lần chạy; dữ liệu kiểm tra có bị rò vào dữ liệu huấn luyện.

## 5. Khảo sát / tổng quan / SoK
- **Lõi**: cách bài tổ chức và phân loại lĩnh vực (taxonomy).
- **Tinh hoa**: lăng kính hay khung phân loại tác giả áp lên lĩnh vực.
- **Kiến trúc**: các trục phân loại và quan hệ giữa các nhánh.
- **Phương pháp**: tiêu chí chọn tài liệu, cách so sánh.
- **Soi bằng chứng**: tiêu chí chọn bài có nêu rõ và tái lập được; trục phân loại có loại trừ lẫn nhau; kết luận
  "khoảng trống nghiên cứu" có dựa trên độ phủ đủ rộng.

## 6. Quan điểm / nhân văn / triết học / pháp lý
- **Lõi**: luận điểm trung tâm tác giả bảo vệ.
- **Tinh hoa**: bước lập luận then chốt (hoặc phản ví dụ) chống đỡ luận điểm.
- **Kiến trúc**: mạch lập luận: tiền đề → bước trung gian → kết luận; các phản biện được lường trước.
- **Phương pháp**: kiểu lập luận (phân tích khái niệm, diễn giải văn bản, biện chứng, phân tích quy phạm…).
- **Soi bằng chứng**: tiền đề nào không được bảo vệ; bước nào nhảy cóc; phản biện mạnh nhất có được trả lời.

## 7. Dữ liệu / tài nguyên / benchmark
- **Lõi**: tài nguyên được tạo và khoảng trống nó lấp.
- **Tinh hoa**: lựa chọn thiết kế dữ liệu đáng giá (cách gán nhãn, độ phủ, kiểm soát chất lượng).
- **Kiến trúc**: cấu trúc dữ liệu, schema, quy trình tạo.
- **Phương pháp**: quy trình thu thập, gán nhãn và thí nghiệm baseline.
- **Soi bằng chứng**: độ đồng thuận giữa người gán nhãn; benchmark đo đúng năng lực tuyên bố hay đo đường tắt;
  nguy cơ rò rỉ vào dữ liệu huấn luyện; chỉ số có bão hòa.

## 8. Tấn công / phòng thủ (bảo mật)
- **Lõi**: tấn công mới (và hệ thống nạn nhân) hoặc phòng thủ mới (và lớp tấn công nó chặn).
- **Tinh hoa**: lỗ hổng gốc mà tấn công khai thác, hoặc bất biến mà phòng thủ giữ được.
- **Kiến trúc**: **mô hình mối đe dọa** (kẻ tấn công biết gì, chạm được vào đâu, muốn gì) cộng các thành phần
  của hệ thống. Mô hình mối đe dọa là bộ giả định nền của cả bài.
- **Phương pháp**: cách tấn công được dựng hoặc cách phòng thủ được thực thi và huấn luyện.
- **Soi bằng chứng**: phòng thủ có được thử với **tấn công thích nghi** (kẻ tấn công biết phòng thủ) hay chỉ với
  tấn công cố định; cái giá về tiện ích (utility) và chi phí; đảm bảo là chứng minh được hay thực nghiệm; mô
  hình mối đe dọa có loại bỏ đúng những tấn công mạnh nhất không.
