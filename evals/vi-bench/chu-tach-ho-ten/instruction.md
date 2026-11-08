Phần mềm nhân sự của công ty tách họ tên sai ở các họ kép (Tôn Nữ Thị Hạnh bị tách thành họ "Tôn", đệm "Nữ Thị"), và dữ liệu nhập từ nhiều nguồn nên hay lộn xộn. Sửa hàm `tach_ho_ten(ho_va_ten)` trong `/app/ho_ten.py`. Giữ nguyên tên hàm và tên file.

Hàm nhận một chuỗi họ tên đầy đủ, trả về dict có đúng ba khóa `"ho"`, `"dem"`, `"ten"`, giá trị là chuỗi.

Luật tách:

1. Dữ liệu có thể viết thường, viết HOA, hoặc hoa thường lẫn lộn, có khoảng trắng thừa (cả tab, xuống dòng) ở đầu, cuối và giữa các chữ, và có chữ gõ dấu kiểu tách rời (chữ cái và dấu là hai ký tự riêng). Mỗi chữ trong kết quả ở dạng dựng sẵn (NFC), viết hoa chữ cái đầu, các chữ cái sau viết thường ("ĐẶNG" thành "Đặng"). Các chữ trong mỗi giá trị cách nhau đúng một dấu cách.
2. Tên là chữ cuối cùng. Họ là chữ đầu tiên, trừ khi họ kép: danh sách họ kép nằm trong file `ho_kep.txt` cạnh `ho_ten.py`, mỗi dòng một họ kép (có thể có dòng trống, khoảng trắng thừa; viết hoa hay thường, dấu tách rời hay dựng sẵn không quan trọng khi so). Đệm là mọi chữ nằm giữa họ và tên (chuỗi rỗng nếu không có).
3. Họ kép khớp khi các chữ đầu của họ tên bằng đúng từng chữ của họ kép (so từng chữ nguyên vẹn, không phải so từng ký tự: "Tôn Nữa" không khớp "Tôn Nữ"). Nếu nhiều họ kép cùng khớp thì lấy họ kép nhiều chữ nhất. Họ kép chỉ được dùng khi sau nó còn ít nhất một chữ để làm tên; nếu không thì thử họ kép ngắn hơn khớp được, và nếu không còn họ kép nào dùng được thì họ là một chữ đầu như bình thường.
4. Họ tên chỉ có một chữ thì họ và đệm là chuỗi rỗng, tên là chữ đó. Chuỗi rỗng hay chỉ có khoảng trắng thì ném `ValueError`.
5. Danh sách họ kép có thể được sửa bất cứ lúc nào để thêm họ mới, nên mỗi lần gọi hàm phải đọc đúng nội dung hiện tại của `ho_kep.txt`: sửa file là có hiệu lực ngay, không phải chạy lại chương trình, và không ghi sẵn danh sách vào code.

Ví dụ (với `ho_kep.txt` như đang có trong `/app`):
- `tach_ho_ten("  nguyễn   VĂN  an ")` -> `{"ho": "Nguyễn", "dem": "Văn", "ten": "An"}`
- `tach_ho_ten("TÔN NỮ THỊ HẠNH")` -> `{"ho": "Tôn Nữ", "dem": "Thị", "ten": "Hạnh"}`
- `tach_ho_ten("Âu Dương")` -> `{"ho": "Âu", "dem": "", "ten": "Dương"}`
