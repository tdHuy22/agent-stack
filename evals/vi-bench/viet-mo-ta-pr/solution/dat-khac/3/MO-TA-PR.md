# Mô tả PR

Trong bối cảnh cửa hàng chạy nhiều mã giảm giá, PR này sửa ba lỗi tính tiền.

## Thay đổi

- `giam_gia.py`: thêm `ma_con_han`, sửa `ap_dung_ma`, xóa `tinh_giam_gia_cu`.
- `don_hang.py`: sửa `tinh_tong`.
- `cau_hinh.py`: ngưỡng miễn phí ship từ 300.000đ lên 500.000đ.
- `test_giam_gia.py`: thêm `test_ma_het_han`, `test_giam_khong_vuot_tien_hang`, `test_phi_ship_khong_tinh_giam`.

## Lý do

Đóng #87: tổng bị âm với mã LAN1, mã hết hạn vẫn dùng được, mã giảm luôn cả phí ship.

## Cách kiểm

Chạy `python3 -m unittest discover -s tests`. Ví dụ 10/11/2026: tiền hàng 420.000đ, ship 25.000đ, GIAM10 thì tổng 415.000đ.

Tóm lại, PR nhỏ và đã có test.
