#!/bin/bash
# Lời giải mẫu: thông báo bảo trì giờ Việt Nam, lời thường.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/thong-bao.txt" <<'TXT'
Tạm dừng thanh toán online rạng sáng Chủ nhật 15/11

Chào bạn,

Để cửa hàng chạy ổn định hơn, chúng mình sẽ bảo trì hệ thống từ 00:30 đến 03:15 ngày 15/11 (Chủ nhật), tổng cộng 2 giờ 45 phút.

Trong thời gian này:
- Bạn vẫn đăng nhập, xem hàng và thêm vào giỏ như thường.
- Bạn đặt được đơn thanh toán khi nhận hàng. Thanh toán bằng thẻ, ví điện tử và chuyển khoản QR tạm thời không dùng được.

Sau bảo trì, email xác nhận đơn có thể đến chậm tối đa 30 phút. Điểm thưởng của đơn đặt trong lúc bảo trì sẽ được cộng chậm nhất lúc 07:00 sáng 15/11.

Chúng mình xin lỗi vì sự bất tiện này. Cần hỗ trợ, bạn gọi hotline 1900 6868 (8:00 đến 22:00).
TXT
