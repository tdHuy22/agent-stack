#!/bin/bash
# Lời giải mẫu: biên bản đủ ba mục, ngày đã đổi ra ngày cụ thể, bỏ ý bị bác.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/bien-ban.md" <<'MD'
# Biên bản họp nhóm ra mắt cửa hàng online, 10/11/2026

## Quyết định

- Tiền quảng cáo: 65 triệu đồng.
- Ngày ra mắt: thứ Sáu 27/11.
- Giữ nhà in An Phú cho tờ rơi, số lượng 500 tờ.

## Việc cần làm

- Thu: chụp ảnh sản phẩm, hạn 13/11.
- Minh: lấy giá và đặt in 500 tờ rơi, hạn 12/11.
- Quân: dựng trang đích, hạn 18/11.
- Hạnh: trình mức 65 triệu cho anh Toàn, hạn 17/11.

## Câu hỏi còn mở

- Ai duyệt nội dung bài đăng trước khi lên trang? Chị Hạnh sẽ hỏi anh Toàn.
- Có thuê thêm người đóng gói cho ngày ra mắt không? Chờ số đơn đặt trước.
MD
