Ô tìm kiếm danh bạ của công ty tìm sai: gõ "dung" không ra "Dũng" và "Đức", gõ "an" lại ra "Hoàng" (vì có "oan" bên trong), và thứ tự kết quả lung tung. Viết lại hàm `tim(danh_ba, truy_van)` trong `/app/danh_ba.py`: `danh_ba` là list tên (chuỗi), `truy_van` là chuỗi người dùng gõ; trả về list các tên khớp, đã xếp hạng, mỗi tên là chuỗi gốc đúng như trong `danh_ba` (không sửa, không loại tên trùng, không đổi `danh_ba`). Giữ nguyên tên hàm và tên file.

Luật:

1. Không phân biệt hoa thường. Đổi cả tên lẫn truy vấn về dạng dựng sẵn (NFC) trước khi so (dữ liệu có chỗ gõ dấu kiểu tách rời, tức chữ cái và dấu là hai ký tự riêng). Chữ là các phần của tên cách nhau bằng khoảng trắng; từ khóa là các phần của truy vấn cách nhau bằng khoảng trắng.
2. So từng chữ cái của từ khóa với chữ cái ở cùng vị trí của chữ. Chữ cái trong từ khóa là chữ không dấu `a` đến `z` (kể cả `d`) thì khớp với mọi chữ có cùng chữ cái gốc: `a` khớp a, à, á, ả, ã, ạ, ă, ắ, â, ấ, ậ…; `d` khớp cả `d` lẫn `đ`. Chữ cái trong từ khóa có bất kỳ dấu nào (dấu thanh, mũ, móc, trăng, gạch ngang của đ) hoặc là ký tự khác (chữ số…) thì chỉ khớp đúng chính ký tự đó: `ũ` chỉ khớp `ũ`, `đ` chỉ khớp `đ`, `ê` chỉ khớp `ê` (không khớp `ế` hay `e`).
3. Một từ khóa khớp một chữ nếu từ khóa không dài hơn chữ và từng chữ cái của từ khóa khớp với chữ cái cùng vị trí ở đầu chữ (khớp phần đầu của chữ, không tìm ở giữa chữ).
4. Một tên khớp truy vấn khi mọi từ khóa đều khớp ít nhất một chữ của tên (hai từ khóa được khớp cùng một chữ). Truy vấn rỗng hay chỉ có khoảng trắng thì không khớp tên nào.
5. Xếp hạng. Với mỗi từ khóa, lấy chữ của tên cho điểm cao nhất trong các chữ nó khớp, điểm của một chữ là: 3 nếu từ khóa giống hệt chữ (sau khi bỏ hoa thường); 2 nếu cùng số chữ cái nhưng không giống hệt (khớp nhờ chữ không dấu); 1 nếu từ khóa ngắn hơn chữ. Điểm của tên là tổng điểm các từ khóa. Xếp điểm giảm dần; bằng điểm thì tên có ít chữ hơn đứng trước; vẫn bằng thì giữ thứ tự trong `danh_ba`.

Ví dụ với `danh_ba = ["Lê Anh", "Lê Ân", "Hoàng Văn An", "An"]`:
- `tim(danh_ba, "an")` -> `["An", "Hoàng Văn An", "Lê Ân", "Lê Anh"]`
- `tim(danh_ba, "ân")` -> `["Lê Ân"]`
- `tim(danh_ba, "le an")` -> `["Lê Ân", "Lê Anh"]`
