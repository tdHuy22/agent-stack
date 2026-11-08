#!/bin/bash
# Lời giải mẫu: một báo cáo đạt mọi yêu cầu của đề.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/bao-cao-su-co.md" <<'MD'
# Báo cáo sự cố trang đặt hàng chiều 7/11

Chị Lan,

Lúc 14:05 chiều nay trang đặt hàng ngừng nhận đơn, 18 phút sau mới chạy lại bình thường. Trong lúc đó có 37 đơn không đặt được. Khoảng 1.240 khách đã vào trang trong lúc sập; con số này là lượt khách vào trang, không phải số đơn.

Có 2 khách bị trừ tiền hai lần vì bấm thanh toán lại khi trang treo, mỗi lần 459.000đ. Bộ phận thanh toán đã hoàn đủ cho cả hai khách lúc gần 16 giờ.

Nguyên nhân: chương trình khuyến mãi 11/11 mở sớm lúc 14:00 nên lượng khách vào trang tăng gấp sáu lần. Kho dữ liệu đơn hàng chỉ phục vụ được 50 yêu cầu cùng lúc; khi đầy thì đơn mới phải chờ rồi hỏng. Bên kỹ thuật đã nâng mức này lên 200 nên trang chạy lại.

## Việc sẽ làm

- Anh Minh (kỹ thuật): đặt mức phục vụ theo lượng khách dự kiến và chạy thử trước mỗi đợt khuyến mãi, xong trước 10/11.
- Chị Hà (vận hành): cài báo động gửi điện thoại khi kho dữ liệu dùng quá 80% sức chứa, xong trước 15/11.
- Anh Tuấn (thanh toán): chặn bấm thanh toán hai lần cho cùng một đơn, xong trước 20/11.
MD
