Dữ liệu địa chỉ giao hàng khách tự gõ nên tên tỉnh, thành lộn xộn (TP.HCM, Tp Hồ Chí Minh, Sài Gòn, hn…). Bạn sửa hàm `chuan_hoa_tinh(dia_chi)` trong `/app/dia_chi/chuan_hoa.py` cho thay tên tỉnh, thành bằng tên chuẩn theo bảng bí danh, đúng luật dưới. Giữ nguyên tên hàm và tên tham số; hàm nhận chuỗi, trả chuỗi.

Bảng bí danh nằm ở file `bi_danh.tsv` cạnh `chuan_hoa.py` (cùng thư mục `/app/dia_chi`). Mã hóa UTF-8, người ta lưu từ Notepad nên có thể có BOM ở đầu file và xuống dòng kiểu Windows. Mỗi dòng gồm tên chuẩn, một ký tự TAB, rồi các bí danh cách nhau bằng dấu `|` (bỏ khoảng trắng đầu cuối của mỗi bí danh). Dòng trống và dòng chú thích (bắt đầu bằng `#`, kể cả khi có khoảng trắng trước `#`) bỏ qua. Tên chuẩn cũng tự là một bí danh của chính nó. Bảng sẽ được bên pháp chế bổ sung thường xuyên, nên phải đọc bảng từ file, đừng chép cứng vào code; và hàm phải tìm file theo vị trí của `chuan_hoa.py`, không theo thư mục đang chạy chương trình (dịch vụ chạy từ thư mục khác).

Cách so khớp: "khóa" của một chuỗi là chuỗi đó sau khi bỏ dấu (kể cả `đ` thành `d`), đổi hết sang chữ thường và bỏ mọi ký tự không phải chữ cái hay chữ số (khoảng trắng, dấu chấm, gạch ngang…). Hai chuỗi khớp nhau khi khóa của chúng bằng nhau trên cả chuỗi (không phải một phần). Chữ có dấu ở dạng tách rời (NFD) cũng phải được nhận.

Luật chuẩn hóa một địa chỉ:

1. Đổi cả địa chỉ sang dạng NFC. Tách thành các phần theo dấu phẩy, bỏ khoảng trắng ở đầu và cuối mỗi phần, bỏ các phần rỗng. Địa chỉ không còn phần nào thì trả chuỗi rỗng.
2. Phần tên tỉnh là phần cuối cùng. Riêng khi phần cuối có khóa là `vietnam` hay `vn` ("Việt Nam", "VN"…) và địa chỉ có từ hai phần trở lên thì phần tên tỉnh là phần liền trước nó.
3. Nếu khóa của phần tên tỉnh khớp khóa của một bí danh (hay tên chuẩn) trong bảng thì thay cả phần đó bằng tên chuẩn của dòng ấy (ở dạng NFC); không khớp thì giữ nguyên chữ.
4. Chỉ phần tên tỉnh bị thay. Các phần khác giữ nguyên chữ (kể cả khoảng trắng ở giữa phần), kể cả khi chúng trùng với một bí danh, vd. tên đường "Sài Gòn" hay tên quận "Huế" không được đổi.
5. Nối các phần lại bằng `", "` (dấu phẩy và một dấu cách).

Trong `/app/dia_chi/test_chuan_hoa.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/dia_chi`.
