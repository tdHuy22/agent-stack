Bản tin của đài được chuyển từ giọng nói sang chữ nên toàn chữ thường: "thành phố hồ chí minh", "ngân hàng nhà nước việt nam". Hàm `viet_hoa(van_ban)` trong `/app/viet_hoa.py` hiện dùng `title()` nên viết hoa tràn lan ("Thành Phố Hồ Chí Minh Đông Dân"). Viết lại để viết hoa đúng tên riêng. Giữ nguyên tên hàm và tên file.

Các tên riêng cần viết hoa nằm trong file `ten_rieng.txt` cạnh `viet_hoa.py`, mỗi dòng một tên, đúng cách viết chuẩn (như "Hà Nội", "Đại học Quốc gia Hà Nội", "Ngân hàng Nhà nước Việt Nam", "sông Hồng"). Dòng trống bỏ qua, khoảng trắng thừa trong dòng không tính. File do nhiều người gõ nên có dòng gõ dấu kiểu tách rời (chữ cái và dấu là hai ký tự riêng), như văn bản đầu vào. Danh sách sẽ được bổ sung thường xuyên, nên đọc nó từ file, không ghi sẵn vào code.

Luật:

1. Văn bản vào có thể gõ dấu kiểu dựng sẵn hoặc kiểu tách rời (chữ cái và dấu là hai ký tự riêng); đổi về dạng dựng sẵn (NFC) trước khi xử lý, kết quả cũng ở dạng NFC.
2. Một tên trong danh sách "xuất hiện" trong văn bản khi các chữ của nó có mặt liền nhau, đúng thứ tự, không phân biệt hoa thường, và giữa các chữ có một hay nhiều khoảng trắng (dấu cách, tab, xuống dòng). Ký tự đứng liền ngay trước chữ đầu và liền ngay sau chữ cuối của chỗ khớp không được là chữ cái (có thể là dấu câu, chữ số, khoảng trắng hoặc đầu, cuối văn bản). Gạch nối hay dấu câu giữa các chữ thì không khớp.
3. Mỗi chỗ khớp được thay nguyên cụm, kể cả khoảng trắng bên trong, bằng đúng cách viết chuẩn trong danh sách, các chữ cách nhau một dấu cách.
4. Quét từ trái sang phải. Tại một vị trí mà nhiều tên cùng khớp thì lấy tên có nhiều chữ nhất, rồi tiếp tục sau chỗ khớp đó (nên "ngân hàng nhà nước việt nam" thành "Ngân hàng Nhà nước Việt Nam", chứ không phải "ngân hàng nhà nước Việt Nam").
5. Sau đó viết hoa chữ cái đầu câu: câu bắt đầu ở ký tự đầu tiên không phải khoảng trắng của văn bản, ở ký tự đầu tiên không phải khoảng trắng sau một dấu `.`, `!` hay `?` (một hay nhiều dấu liền nhau) đứng ngay trước một khoảng trắng, và ở đầu mỗi dòng. Nếu ký tự đó là chữ cái thì viết hoa nó, còn không (chữ số, dấu ngoặc, dấu nháy…) thì thôi. Dấu chấm không có khoảng trắng đi sau (như trong "2.5") không kết thúc câu.
6. Mọi chữ khác giữ nguyên, kể cả chữ đã viết hoa sẵn ("NASA").

Ví dụ:
- `viet_hoa("thành phố hồ chí minh đông dân")` -> `"Thành phố Hồ Chí Minh đông dân"` (thành phố là chữ thường vì "thành phố Hồ Chí Minh" có trong danh sách với "thành phố" viết thường; chữ đầu câu luôn viết hoa)
- `viet_hoa("bộ giáo dục và đào tạo vừa thông báo. sông hồng chảy qua hà nội.")` -> `"Bộ Giáo dục và Đào tạo vừa thông báo. Sông Hồng chảy qua Hà Nội."`
- `viet_hoa("giá 2.5 triệu, mua ở đà nẵng")` -> `"Giá 2.5 triệu, mua ở Đà Nẵng"`
