#!/bin/bash
# Lời giải mẫu: ghi chú phát hành 2.4.0 cho người dùng cuối.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/CHANGELOG.md" <<'MD'
# Phiên bản 2.4.0 (30/10/2026)

## Thêm

- Đặt hạn mức chi tiêu theo tháng cho từng danh mục.
- Xuất giao dịch ra file CSV ngay từ màn hình báo cáo.
- Giao dịch lặp lại hằng tuần hoặc hằng tháng.
- Tiện ích hiện chi tiêu hôm nay trên màn hình chính (chỉ Android).

## Sửa

- Ứng dụng không còn tự đóng khi mở báo cáo lúc chưa có giao dịch nào.
- Tổng tiền không còn sai khi đổi đơn vị tiền từ USD sang VND.
- Email mã đăng nhập không còn bị gửi hai lần.
- Chữ trên nút không còn bị cắt ở màn hình nhỏ.

## Thay đổi

- Cần Android 9 trở lên. Máy dùng Android 8 vẫn ở lại bản 2.3.
- Báo cáo có nhiều giao dịch mở nhanh hơn.
- Thẻ "Ví" đổi tên thành "Tài khoản".
MD
