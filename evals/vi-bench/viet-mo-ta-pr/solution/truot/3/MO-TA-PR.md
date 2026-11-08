# Sửa tổng tiền khi dùng mã giảm giá

## Thay đổi

- `cua_hang/giam_gia.py`: thêm `ma_con_han`, sửa `ap_dung_ma`, xóa `tinh_giam_gia_cu` vì không còn ai gọi.
- `cua_hang/don_hang.py`: sửa `tinh_tong`.
- `cua_hang/cau_hinh.py`: ngưỡng miễn phí ship từ 300.000đ lên 500.000đ.
- `tests/test_giam_gia.py`: thêm test cho mã hết hạn.

## Lý do

Đóng #87: tổng tiền bị âm, mã hết hạn vẫn dùng được, mã giảm cả phí ship.
