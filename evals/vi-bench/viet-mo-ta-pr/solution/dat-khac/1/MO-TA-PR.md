## Sửa tổng tiền sai khi dùng mã giảm giá

### Thay đổi

| File | Nội dung |
|---|---|
| `cua_hang/giam_gia.py` | Thêm `ma_con_han(ma, hom_nay)`. Sửa `ap_dung_ma`: nhận thêm ngày, trả 0 nếu mã sai hay hết hạn, không giảm quá tiền hàng. Xóa `tinh_giam_gia_cu` (không ai gọi). |
| `cua_hang/don_hang.py` | `tinh_tong` tính giảm giá trên tiền hàng, phí ship cộng sau. |
| `cua_hang/cau_hinh.py` | `MIEN_PHI_SHIP_TU` từ 300.000đ lên 500.000đ. |
| `tests/test_giam_gia.py` | Thêm `test_ma_het_han`, `test_giam_khong_vuot_tien_hang`, `test_phi_ship_khong_tinh_giam`. |

### Lý do

Lỗi trong issue: đơn nhỏ dùng mã LAN1 ra tổng âm, mã hết hạn vẫn dùng được, mã phần trăm giảm cả trên phí ship. Mức miễn phí ship đổi kèm theo ghi chú của anh Sơn. Đóng #87.

### Cách kiểm

```
python3 -m unittest discover -s tests
```

Kiểm tay (10/11/2026): tiền hàng 420.000đ chưa đủ 500.000đ nên mất ship 25.000đ; GIAM10 giảm tối đa 30.000đ. Khách trả 415.000đ.
