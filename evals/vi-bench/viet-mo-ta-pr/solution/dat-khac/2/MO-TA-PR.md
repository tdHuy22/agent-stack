# Sửa tổng tiền sai khi dùng mã giảm giá

## 1. Thay đổi

- `cua_hang/giam_gia.py`: thêm `ma_con_han`. Sửa `ap_dung_ma` để trả 0 khi mã sai hoặc hết hạn và không giảm quá tiền hàng. Bỏ hàm `tinh_giam_gia_cu` vì không còn nơi gọi.
- `cua_hang/don_hang.py`: `tinh_tong` giảm giá trên tiền hàng, cộng phí ship sau.
- `cua_hang/cau_hinh.py`: `MIEN_PHI_SHIP_TU` từ 300.000đ lên 500.000đ.
- `tests/test_giam_gia.py`: thêm test_ma_het_han, test_giam_khong_vuot_tien_hang, test_phi_ship_khong_tinh_giam.

## 2. Lý do

Đóng #87: đơn nhỏ dùng mã LAN1 ra tổng âm, mã hết hạn vẫn dùng được, mã phần trăm giảm cả phí ship.

## 3. Cách kiểm

```
python3 -m unittest discover -s tests
```

Ngày 10/11/2026, tiền hàng 420.000đ, ship 25.000đ, mã GIAM10 (giảm tối đa 30.000đ): khách trả 415.000đ.
