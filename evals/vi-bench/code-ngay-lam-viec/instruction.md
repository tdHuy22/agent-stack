Phòng nhân sự dùng hàm đếm ngày làm việc để tính ngày phép và hạn giao hàng, nhưng số đếm ra hay lệch 1–2 ngày, nhất là quanh dịp lễ. Bạn sửa hàm `dem_ngay_lam_viec(tu_ngay, den_ngay, file_le)` trong `/app/lich/ngay_lam_viec.py` cho đúng luật dưới. Giữ nguyên tên hàm và tên tham số, hàm trả số nguyên.

Đầu vào:

- `tu_ngay`, `den_ngay` là chuỗi dạng dd/mm/yyyy; ngày và tháng viết một hay hai chữ số đều được (`1/5/2022` và `01/05/2022` như nhau). Tính cả hai đầu. Ngày không có thật (như `30/02/2024`) hay sai dạng (như `2024-03-01`) thì báo `ValueError`; `tu_ngay` sau `den_ngay` cũng báo `ValueError`.
- `file_le` là đường dẫn file ngày lễ, mã hóa UTF-8, người ta lưu từ Notepad nên có thể có BOM ở đầu file và xuống dòng kiểu Windows. Mỗi dòng bắt đầu bằng một ngày dạng dd/mm/yyyy (cũng cho phép bỏ số 0 đầu), sau đó có thể có khoảng trắng hay tab rồi tên ngày lễ (tên có thể chứa chữ số và dấu `/`, vd. `30/04/2022 Giải phóng miền Nam 30/4`). Dòng trống và dòng bắt đầu bằng `#` bỏ qua. Một ngày có thể bị liệt kê hai lần, chỉ tính một lần.

Luật:

1. Ngày làm việc là thứ Hai đến thứ Sáu, không phải ngày nghỉ.
2. Ngày nghỉ gồm các ngày lễ trong file và các ngày nghỉ bù.
3. Lễ rơi vào thứ Bảy hay Chủ nhật thì được nghỉ bù: xét các ngày lễ theo thứ tự ngày tăng dần, mỗi lễ cuối tuần được bù vào ngày đầu tiên sau nó mà đồng thời (a) là thứ Hai đến thứ Sáu, (b) không phải ngày lễ nào có trong file, (c) chưa là ngày nghỉ bù của lễ khác. Ví dụ lễ rơi vào thứ Bảy và Chủ nhật liền nhau thì được bù thứ Hai và thứ Ba; lễ rơi vào thứ Bảy mà thứ Hai kế tiếp cũng là lễ thì bù vào thứ Ba.
4. Lễ rơi vào ngày thường chỉ nghỉ đúng ngày đó, không bù gì thêm.
5. Ngày lễ và ngày nghỉ bù không bị giới hạn trong khoảng đang đếm: lễ cuối tuần trước `tu_ngay` vẫn có thể có ngày bù rơi vào trong khoảng.

Trong `/app/lich/test_ngay_lam_viec.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/lich`.
