#!/bin/bash
# Lời giải mẫu: một đoạn gửi anh Thành, đủ ba con số (đã cộng dòng bị sót).
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/tom-tat.txt" <<'TXT'
Anh Thành, em gửi anh tóm tắt quý 3 (tháng 7 đến tháng 9) của hai chi nhánh. Tổng doanh thu đạt 975,5 triệu đồng, tăng 7,7% so với quý 2 (905,7 triệu đồng). Thủ Đức tăng mạnh hơn, lên 10,8%, còn Quận 1 tăng 5,1%. Số liệu đã cộng thêm 49,9 triệu đồng giao hàng tháng 9 của Thủ Đức mà file còn sót, theo ghi chú của kế toán. Doanh thu chưa gồm thuế.
TXT
