Ngân hàng đối tác phàn nàn lịch trả nợ mình gửi cho khách bị lệch vài đồng và tháng cuối còn dư nợ lẻ. Bạn sửa hàm `lap_lich_tra_no(so_tien_vay, lai_suat_nam, so_thang)` trong `/app/vay/lich_tra_no.py` cho đúng luật dưới. Giữ nguyên tên hàm, tên tham số, và dạng kết quả: danh sách mỗi tháng một `dict` có các khóa `ky`, `goc`, `lai`, `tong`, `du_no_cuoi`, tất cả là số nguyên đồng (`ky` đếm từ 1).

Đầu vào:

- `so_tien_vay`: số tiền vay, số nguyên đồng, hoặc chuỗi người dùng gõ trong form theo kiểu Việt Nam với dấu chấm ngăn cách nghìn, vd. `"1.200.000.000"`.
- `lai_suat_nam`: lãi suất một năm tính theo phần trăm. Là số (`10.5`) hoặc chuỗi kiểu Việt Nam dùng dấu phẩy thập phân (`"10,5"`). Lãi suất `0` là hợp lệ.
- `so_thang`: số tháng vay, số nguyên từ 1 trở lên.

Số tiền vay không dương, lãi suất âm, số tháng nhỏ hơn 1, hay chuỗi không đọc được thành số thì báo `ValueError`.

Luật tính, dư nợ giảm dần (gốc trả đều, lãi tính trên dư nợ đầu kỳ):

1. Gốc mỗi tháng = `so_tien_vay` chia nguyên cho `so_thang`, bỏ phần lẻ. Riêng tháng cuối trả hết toàn bộ dư nợ còn lại, nên phần lẻ của phép chia dồn vào tháng cuối. Tổng gốc các tháng phải đúng bằng số tiền vay và `du_no_cuoi` tháng cuối bằng 0.
2. Lãi mỗi tháng = dư nợ đầu tháng × `lai_suat_nam` / 100 / 12, làm tròn nửa lên tới đồng (từ 0,5 trở lên thì lên). Tính chính xác theo số thập phân như người ta nhập (lãi suất `9.9` là đúng 9,9%, không để sai số của số thực làm lệch), chỉ làm tròn ở cuối phép tính từng tháng, không làm tròn lãi suất tháng.
3. `tong` = `goc` + `lai`; `du_no_cuoi` = dư nợ đầu tháng trừ `goc` của tháng.

Trong `/app/vay/test_lich_tra_no.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/vay`.
