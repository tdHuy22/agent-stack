Phòng nhân sự nhận đơn xin nghỉ viết ngày đủ kiểu ("ngày 7 tháng 11 năm 2026", "7/11/26", "mùng 7 tháng 11", "thứ Bảy, 07-11-2026", "ngày mai"…) và hàm đọc ngày hiện chỉ biết một kiểu. Viết lại hàm `doc_ngay(chuoi, hom_nay=None)` trong `/app/ngay.py`: nhận chuỗi ngày, trả về chuỗi ISO `"YYYY-MM-DD"`. `hom_nay` là một `datetime.date`, dùng cho các kiểu viết không có năm hoặc viết tương đối; để trống thì lấy ngày hôm nay của máy. Giữ nguyên tên hàm, tên file và tham số.

Gặp chuỗi không đọc được, ngày không có thật, hoặc thứ không khớp ngày, thì ném `ValueError` (không ném loại lỗi khác).

Cách đọc:

1. Không phân biệt hoa thường; khoảng trắng thừa ở đầu, cuối và giữa các chữ không sao; chuỗi có thể gõ dấu kiểu tách rời (chữ cái và dấu là hai ký tự riêng).
2. Thứ ở đầu chuỗi (không bắt buộc): "thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy" (thứ Hai là thứ hai trong tuần), cũng viết "thứ 2" đến "thứ 7", hoặc "Chủ nhật". Sau thứ có thể có dấu phẩy. Nếu có thứ thì ngày đọc ra phải đúng là thứ đó, không thì `ValueError`.
3. Ngày tương đối (đúng nguyên cụm, tính từ `hom_nay`): "hôm nay", "ngày mai" (hôm nay cộng 1), "ngày kia" (cộng 2), "hôm qua" (trừ 1), "hôm kia" (trừ 2).
4. Ngày số: `ngày/tháng/năm` hoặc `ngày-tháng-năm` hoặc `ngày.tháng.năm`, hai dấu ngăn phải giống nhau, ngày và tháng 1 hoặc 2 chữ số. Thứ tự luôn là ngày trước tháng. Ngày số bắt buộc có năm: "7/11" là `ValueError`.
5. Ngày chữ: `[ngày|mùng|mồng] D tháng M [năm Y]`. Chữ "ngày" ở đầu cũng được dùng với ngày số (như "ngày 7/11/2026"). "mùng", "mồng" chỉ dùng cho ngày 1 đến 10, ngoài ra là `ValueError`. Tháng viết bằng số, hoặc bằng chữ: "Giêng" (1), "Một", "Hai", "Ba", "Tư", "Năm", "Sáu", "Bảy", "Tám", "Chín", "Mười", "Mười một", "Mười hai", "Chạp" (12). Không có "tháng Bốn". Không viết năm thì lấy năm của `hom_nay`.
6. Năm có 4 chữ số, hoặc 2 chữ số: từ 00 đến 69 là 2000 đến 2069, từ 70 đến 99 là 1970 đến 1999. Số chữ số khác (1, 3, 5…) là `ValueError`.
7. Ngày phải có thật, tính cả năm nhuận (29/2 chỉ có ở năm chia hết cho 4, trừ năm chia hết cho 100 mà không chia hết cho 400).

Ví dụ (`hom_nay` là 7/11/2026, thứ Bảy):
- `doc_ngay("thứ Bảy, 07-11-2026")` -> `"2026-11-07"`
- `doc_ngay("mùng 5 tháng Giêng")` -> `"2026-01-05"`
- `doc_ngay("ngày kia", hom_nay)` -> `"2026-11-09"`
- `doc_ngay("Chủ nhật, 7/11/26")` -> ném `ValueError` (7/11/2026 là thứ Bảy)
