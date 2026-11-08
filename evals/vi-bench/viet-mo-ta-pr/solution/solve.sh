#!/bin/bash
# Lời giải mẫu: mô tả PR đủ file, hàm, ngưỡng cũ/mới, test, issue và ví dụ kiểm tay.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/MO-TA-PR.md" <<'MD'
# Sửa tổng tiền sai khi dùng mã giảm giá

## Thay đổi

- `cua_hang/giam_gia.py`: thêm `ma_con_han`; sửa `ap_dung_ma` (nhận tiền hàng và ngày, trả 0 khi mã sai hay hết hạn, không giảm quá tiền hàng); xóa `tinh_giam_gia_cu` vì không còn nơi nào gọi.
- `cua_hang/don_hang.py`: sửa `tinh_tong`, tính giảm giá trên tiền hàng, không tính phí ship.
- `cua_hang/cau_hinh.py`: ngưỡng miễn phí ship `MIEN_PHI_SHIP_TU` tăng từ 300.000đ lên 500.000đ.
- `tests/test_giam_gia.py`: thêm `test_ma_het_han`, `test_giam_khong_vuot_tien_hang`, `test_phi_ship_khong_tinh_giam`; sửa hai test cũ cho khớp chữ ký mới.

## Lý do

Đóng #87. Mã LAN1 làm tổng tiền bị âm khi đơn nhỏ hơn mức giảm, mã hết hạn vẫn dùng được, và mã phần trăm giảm luôn cả phí ship. Ngưỡng miễn phí ship tăng theo ghi chú của anh Sơn ngày 03/11 vì phí ship đã tăng.

## Cách kiểm

Chạy `python3 -m unittest discover -s tests`. Kiểm tay ngày 10/11/2026: tiền hàng 420.000đ chưa tới 500.000đ nên vẫn tính ship 25.000đ; GIAM10 giảm 10% là 42.000đ nhưng chạm trần 30.000đ. Tổng phải trả 415.000đ.
MD
