Kế toán xuất báo cáo bán hàng từ Excel bản tiếng Việt ra CSV rồi đưa cho chương trình tổng hợp doanh thu theo tháng, nhưng file thật thì chương trình báo lỗi hoặc cộng ra số lạ. Bạn sửa hàm `tong_doanh_thu_theo_thang(duong_dan)` trong `/app/bao_cao/doc_csv.py` cho đọc được file thật. Giữ nguyên tên hàm và tên tham số.

Hàm trả `dict` có khóa là chuỗi `"yyyy-mm"` (vd. `"2024-03"`) và giá trị là tổng doanh thu của tháng đó, kiểu `decimal.Decimal` (không dùng số thực vì đây là tiền). Tháng không có dòng nào thì không có khóa; file chỉ có dòng tiêu đề thì trả `{}`.

Định dạng file, như Excel tiếng Việt xuất ra:

- Mã hóa UTF-8, có thể có BOM ở đầu file hoặc không. Xuống dòng kiểu Windows (`\r\n`) hoặc Unix.
- Các ô cách nhau bằng dấu chấm phẩy `;`. Ô có chứa `;`, xuống dòng hoặc dấu nháy kép được bọc trong dấu nháy kép (nháy kép trong ô viết đôi `""`). Ô có xuống dòng bên trong vẫn là một dòng dữ liệu.
- Dòng đầu là tiêu đề. Cần hai cột: cột ngày có tiêu đề `Ngày`, cột doanh thu có tiêu đề `Doanh thu` hoặc `Doanh thu (đồng)`. Tìm cột theo tiêu đề, bỏ khoảng trắng đầu cuối, không phân biệt chữ hoa thường, chữ có dấu ở dạng tách rời cũng nhận. Thứ tự cột và số cột khác nhau giữa các file. Thiếu một trong hai cột thì báo `ValueError`.
- Ngày dạng dd/mm/yyyy (ngày, tháng viết một hay hai chữ số: `5/3/2024` là ngày 5 tháng 3), có thể kèm giờ sau một khoảng trắng như `05/03/2024 14:30`; chỉ lấy phần ngày. Ô ngày trống thì bỏ cả dòng đó (thường là dòng "Tổng cộng" ở cuối). Ô ngày có nội dung mà sai dạng hay không có thật (`31/04/2024`, `2024-03-05`) thì báo `ValueError`.
- Số tiền kiểu Việt Nam: dấu chấm ngăn cách nghìn, dấu phẩy là dấu thập phân. Ví dụ `1.234.567,5` là 1234567,5; `1.500` là 1500; `1,5` là 1,5; `1500` là 1500. Số âm viết `-100.000,25` hoặc trong ngoặc tròn kiểu kế toán `(250.000)`. Sau số có thể có đơn vị `₫`, `đ`, `VND` hay `VNĐ` (hoa hay thường), cách số một khoảng trắng thường hoặc khoảng trắng không ngắt (U+00A0). Ô doanh thu trống thì bỏ cả dòng đó. Ô có nội dung không đọc được thành số thì báo `ValueError`.

Trong `/app/bao_cao/test_doc_csv.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/bao_cao`.
