# Sửa tổng tiền khi dùng mã giảm giá

## Thay đổi

- `cua_hang/giam_gia.py`: thêm `ma_con_han`, sửa `ap_dung_ma` để trả 0 khi mã hết hạn và không giảm quá tiền hàng.
- `cua_hang/don_hang.py`: sửa `tinh_tong`, giảm giá tính trên tiền hàng.
- `cua_hang/cau_hinh.py`: nâng ngưỡng miễn phí ship.
- `tests/test_giam_gia.py`: thêm `test_ma_het_han` và `test_phi_ship_khong_tinh_giam`.

## Lý do

Mã LAN1 làm tổng tiền âm, mã hết hạn vẫn dùng được, mã giảm cả phí ship.

## Cách kiểm

Chạy `python3 -m unittest discover -s tests`. Ví dụ: tiền hàng 420.000đ, ship 25.000đ, mã GIAM10 thì tổng là 390.000đ.
