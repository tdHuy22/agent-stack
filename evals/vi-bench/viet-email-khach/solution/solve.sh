#!/bin/bash
# Lời giải mẫu: thư trả lời đúng ba khoản bồi thường, từ chối nhẹ các đòi hỏi ngoài chính sách.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/tra-loi.txt" <<'TXT'
Chào anh Tùng,

Em là Vy bên chăm sóc khách hàng. Em xin lỗi anh vì đơn K-20931 đến muộn và còn gửi nhầm thớt, làm anh lỡ buổi tân gia.

Theo chính sách, đơn hẹn giao 02/11 mà đến 08/11 anh mới nhận, trễ 6 ngày nên em bồi thường cho anh:
- Giao trễ: mức tối đa 10% tiền hàng 1.600.000đ, tức 160.000đ.
- Hoàn phí vận chuyển: 35.000đ.
- Hoàn tiền thớt gỗ gửi nhầm: 260.000đ.
Tổng cộng 455.000đ, về đúng tài khoản anh đã chuyển khoản trong 5 ngày làm việc kể từ hôm nay.

Anh vui lòng gửi trả thớt nhựa bằng mã vận đơn em sẽ gửi qua email, phí gửi trả bên em chịu.

Rất tiếc em chưa thể hoàn toàn bộ đơn hay đền thêm ngoài mức trên, vì anh vẫn giữ máy xay và bộ dao đúng như đặt.

Em cảm ơn anh đã cho em cơ hội sửa lỗi.

Vy
TXT
