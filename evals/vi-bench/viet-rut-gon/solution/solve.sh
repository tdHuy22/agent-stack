#!/bin/bash
# Lời giải mẫu: bản tin ngắn giữ đủ tiền, ngày, tên người và địa chỉ.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/ban-tin-ngan.txt" <<'TXT'
Công ty chuyển sang văn phòng mới ở Tầng 7, tòa nhà Sao Mai, 15 Nguyễn Văn Linh, Quận 7, vì chỗ cũ đã quá chật.

Chi phí: thuê 36 triệu đồng mỗi tháng, đặt cọc 72 triệu đồng, vận chuyển trọn gói 48.500.000 đồng.

Mốc thời gian:
- 12/11: chị Đỗ Minh Châu (kế toán) chuyển tiền đặt cọc.
- 14/11: mọi người gửi chị Lê Thị Hương (hành chính) danh sách đồ cá nhân.
- 21/11: các phòng bắt đầu đóng gói.
- 28/11: ngày chuyển, vì tòa nhà cũ chỉ cho dùng thang hàng vào thứ Bảy.
- 30/11: đi làm tại văn phòng mới. Anh Phạm Quốc Bảo (công nghệ thông tin) lo máy tính và mạng, xong trước giờ làm.
TXT
