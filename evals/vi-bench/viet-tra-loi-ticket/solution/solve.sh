#!/bin/bash
# Lời giải mẫu: ba bản trả lời đúng tài liệu.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/tra-loi-ticket.md" <<'MD'
## Ticket #2041

Chào chị Mai, mã chị nhận lúc 14:10 chỉ dùng được trong 15 phút nên giờ đã hết hạn. Chị vào màn hình đăng nhập, bấm "Quên mật khẩu?", nhập email rồi bấm "Gửi mã" để nhận mã mới (mã cũ mất hiệu lực). Chị nhập mã mới trong vòng 15 phút, rồi đặt mật khẩu mới.

## Ticket #2042

Chào anh Phúc, gói Cơ bản chỉ cho tối đa 3 nhân viên (không tính chủ cửa hàng), mà quầy mới cần thêm 2 người, tức 5 người. Anh cần nâng lên gói "Chuyên nghiệp", cho tối đa 10 nhân viên, giá 199.000đ mỗi tháng. Anh vào Cài đặt > Gói dịch vụ > bấm "Nâng cấp", chọn "Chuyên nghiệp" rồi thanh toán. Xong anh vào Cài đặt > Nhân viên > "Thêm nhân viên" để mời hai bạn mới.

## Ticket #2043

Chào chị Oanh, em trả lời hai việc của chị.

Việc 1: sản phẩm bị xóa ngày 28/09, đến nay đã hơn 30 ngày, mà sản phẩm đã xóa chỉ giữ 30 ngày nên em không khôi phục được. Chị tạo lại sản phẩm bằng nút "Thêm sản phẩm".

Việc 2: KhoNhanh chưa xuất thẳng sang MISA. Chị vào Báo cáo, ở ô "Kỳ báo cáo" chọn "Tháng trước" (tức tháng 10), bấm "Xuất file", chọn "Excel", rồi nhập file đó vào MISA.
MD
