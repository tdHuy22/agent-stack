Hóa đơn xuất ra đang sai VAT, khách bên viễn thông gửi lại hóa đơn báo lệch mấy đồng. Bạn sửa `tinh_hoa_don(dong_hang)` trong `/app/hoa_don/tinh_hoa_don.py` cho đúng luật dưới. Giữ nguyên tên hàm, tên tham số và kiểu kết quả: trả `dict` có ba khóa `tien_hang`, `vat`, `tong`, mỗi giá trị là số nguyên đồng. `thue_suat(nhom)` trong file (trả 0.08 hoặc 0.1) cũng đang dùng nơi khác, nên cứ giữ lại.

Mỗi dòng hàng là một `dict` gồm:

- `ten` (chuỗi), `nhom` (chuỗi, nhóm hàng), `don_gia` (số nguyên đồng, không âm);
- `so_luong`: số (`int` hay `float`) hoặc chuỗi viết kiểu Việt Nam như `"0,75"` hay `"1.250"` (dấu phẩy là thập phân, dấu chấm là ngăn cách nghìn, nên `"1.250"` là một nghìn hai trăm năm mươi). Số lượng phải lớn hơn 0;
- `giam_gia` (tùy chọn, mặc định 0): phần trăm giảm giá của dòng, từ 0 đến 100, có thể lẻ như `12.5`.

Luật tính cho từng dòng, theo thứ tự:

1. `thanh_tien` = `don_gia` × `so_luong`, làm tròn nửa lên tới đồng (từ 0,5 trở lên thì lên). Tính chính xác theo số thập phân như người ta nhập (số lượng `0.29` là đúng 0,29), không để sai số của số thực làm lệch.
2. Tiền giảm = `thanh_tien` × `giam_gia` / 100, làm tròn nửa lên tới đồng. `sau_giam` = `thanh_tien` trừ tiền giảm.
3. VAT của dòng = `sau_giam` × thuế suất, làm tròn nửa lên tới đồng ngay ở từng dòng.

Thuế suất theo nhóm hàng: 10% cho năm nhóm "viễn thông", "tài chính", "bất động sản", "hóa chất", "khai khoáng"; mọi nhóm khác (kể cả nhóm trống hay lạ) là 8%. Tên nhóm do nhân viên gõ tay nên phải so khớp không phân biệt chữ hoa thường, bỏ khoảng trắng thừa ở đầu, cuối và giữa các chữ, và chấp nhận chữ có dấu ở dạng tách rời. Riêng "hóa chất" có người gõ "hoá chất" (dấu thanh đặt trên chữ a); hai cách đều là một nhóm.

Cả hóa đơn: `tien_hang` = tổng `sau_giam` của các dòng, `vat` = tổng VAT đã làm tròn của từng dòng (không tính lại VAT trên cả hóa đơn), `tong` = `tien_hang` + `vat`. Danh sách rỗng thì cả ba bằng 0.

Dòng nào có `don_gia` âm, `so_luong` không dương, hay `giam_gia` ngoài khoảng 0–100 thì báo `ValueError`.

Trong `/app/hoa_don/test_hoa_don.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/hoa_don`.
