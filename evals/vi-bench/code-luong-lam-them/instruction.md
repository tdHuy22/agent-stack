Bảng lương tháng trước, tiền làm thêm giờ của mấy bạn trực cuối tuần, ngày lễ và ca đêm đều bị tính sai. Test có sẵn chạy ra sai một chỗ, nhưng mình nghĩ lỗi không chỉ có chỗ đó: phần tính giờ và phần hệ số cũng có vấn đề (code nằm ở `/app/luong/gio_cong.py`, `/app/luong/he_so.py` và `/app/luong/tinh_luong.py`). Bạn sửa cho hàm `tinh_tien_lam_them(luong_thang, ca_lam, ngay_le=())` trong `/app/luong/tinh_luong.py` ra đúng luật dưới. Giữ nguyên tên hàm, tên tham số và các `import` kiểu hiện tại (các file nằm cùng thư mục, chạy test từ trong `/app/luong`). Hàm trả số nguyên là tổng tiền làm thêm giờ, đơn vị đồng.

Đầu vào:

- `luong_thang`: lương tháng, số nguyên đồng. Âm thì báo `ValueError`.
- `ca_lam`: danh sách các ca, mỗi ca là bộ ba `(ngay, bat_dau, ket_thuc)`: `ngay` là ngày bắt đầu ca dạng dd/mm/yyyy (ngày, tháng có thể bỏ số 0 đầu), `bat_dau` và `ket_thuc` dạng 24 giờ `"HH:MM"`. Giờ hay ngày không đọc được thì báo `ValueError`. Nếu `ket_thuc` nhỏ hơn `bat_dau` thì ca qua nửa đêm và kết thúc vào sáng hôm sau (vd. `"22:00"` tới `"02:00"`; `"22:00"` tới `"00:00"` là 2 giờ). `bat_dau` bằng `ket_thuc` thì báo `ValueError`.
- `ngay_le`: các ngày lễ, danh sách chuỗi dd/mm/yyyy (cũng có thể bỏ số 0 đầu), mặc định rỗng.

Luật tính:

1. Tiền lương một giờ = `luong_thang` / 26 / 8 (26 ngày công chuẩn một tháng, 8 giờ một ngày), tính chính xác, không làm tròn giữa chừng.
2. Mỗi phút làm thêm được trả theo hệ số của ngày lịch chứa phút đó. Một ca qua nửa đêm được tách làm hai phần: phần trước 00:00 tính theo loại của ngày bắt đầu, phần từ 00:00 tính theo loại của ngày hôm sau.
3. Hệ số: ngày thường (thứ Hai đến thứ Sáu không phải lễ) 150%; thứ Bảy và Chủ nhật không phải lễ 200%; ngày lễ 300%, kể cả khi lễ rơi vào thứ Bảy hay Chủ nhật (không cộng dồn hệ số, ngày lễ luôn là 300%).
4. Tiền của một phút = tiền lương một giờ / 60 × hệ số. Tổng tiền là tổng của mọi phút trong mọi ca; chỉ làm tròn nửa lên tới đồng (từ 0,5 trở lên thì lên) một lần duy nhất ở cuối, không làm tròn từng ca.

Trong `/app/luong/test_tinh_luong.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/luong`.
