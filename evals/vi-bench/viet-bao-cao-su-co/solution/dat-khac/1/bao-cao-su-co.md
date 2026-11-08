# Báo cáo sự cố chiều 7/11

Chị Lan,

Trang đặt hàng ngừng hoạt động lúc 2 giờ 5 chiều. Sau 18 phút trang mới chạy lại. Trong thời gian đó có 37 đơn không đặt được; con số lượt khách vào trang khoảng 1.240 là lượt vào xem, không phải số đơn.

Có 2 vị khách bị trừ tiền hai lần do bấm thanh toán lại lúc trang treo, mỗi người 459.000đ. Cả hai đã được hoàn đủ lúc gần 16 giờ.

Nguyên nhân: đợt khuyến mãi 11/11 mở sớm lúc 14:00 nên lượng khách tăng gấp sáu lần, trong khi kho dữ liệu đơn hàng chỉ nhận 50 yêu cầu cùng lúc. Bên kỹ thuật đã nâng lên 200.

## Việc sẽ làm

- Minh (kỹ thuật): thử tải trước mỗi đợt khuyến mãi, hạn 10 tháng 11.
- Hà (vận hành): cảnh báo qua điện thoại khi kho dữ liệu đầy quá 80%, hạn 15 tháng 11.
- Tuấn (thanh toán): chặn bấm thanh toán hai lần cho một đơn, hạn 20 tháng 11.
