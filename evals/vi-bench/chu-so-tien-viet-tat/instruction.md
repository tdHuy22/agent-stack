Bên bán hàng online nhận tin nhắn khách ghi giá kiểu "500k", "1tr5", "2,5 triệu", "1 tỷ 2", "3 lít rưỡi" và cần đổi ra số đồng để lên đơn. Hàm `doc_tien(chuoi)` trong `/app/tien.py` mới chỉ đổi được vài kiểu đơn giản và còn sai số. Viết lại: nhận một chuỗi số tiền, trả về số đồng (kiểu `int`). Giữ nguyên tên hàm và tên file. Không đọc được thì ném `ValueError`.

Luật đọc:

1. Không phân biệt hoa thường; chuỗi có thể gõ dấu kiểu tách rời (chữ cái và dấu là hai ký tự riêng); khoảng trắng thừa ở đầu, cuối, giữa các phần không sao, và giữa số với đơn vị có hay không có khoảng trắng đều được ("500k" như "500 k").
2. Đơn vị: `k`, `nghìn`, `ngàn` là 1.000 đồng. `tr`, `triệu`, `củ` là 1.000.000 đồng. `tỷ`, `tỉ` là 1.000.000.000 đồng. `lít` là 100.000 đồng. `đ`, `đồng`, `vnd`, `vnđ` là 1 đồng.
3. Số: gồm chữ số; dấu chấm chỉ để ngăn nghìn và phải đứng trước đúng ba chữ số (`1.250.000`, `1.250k` là 1.250 nghìn); dấu phẩy là dấu thập phân (`2,5`, `1.250,5`). Dấu chấm kiểu khác (`2.5`, `1.25.000`) là `ValueError`.
4. Một số đứng riêng, hay kèm đơn vị tiền (`1.250.000đ`, `200.000 đồng`, `50000`), là số đồng.
5. Một chuỗi gồm một hay nhiều "mẩu" cộng lại với nhau. Mẩu là một số kèm đơn vị (`500k`, `2,5 triệu`, `1 tỷ`, `200 triệu`). Các mẩu có thể viết theo thứ tự bất kỳ.
6. Sau mẩu có thể có thêm phần lẻ, chỉ khi số của mẩu là số nguyên (không có dấu phẩy):
   - `rưỡi` là thêm nửa đơn vị: `2 triệu rưỡi` = 2,5 triệu, `3 lít rưỡi` = 3,5 lít, `1 củ rưỡi`;
   - hoặc một dãy chữ số đứng ngay sau mẩu (có hoặc không có khoảng trắng) mà sau nó không có đơn vị: đó là các chữ số thập phân của chính mẩu đó, viết liền theo thứ tự. `1tr5` = 1,5 triệu; `1tr05` = 1,05 triệu; `1 tỷ 2` = 1,2 tỷ; `1 lít 5` = 1,5 lít; `2 triệu 500` = 2,500 triệu. Còn `1 tỷ 2 triệu` là hai mẩu (1 tỷ cộng 2 triệu), vì `2` có đơn vị đi sau. Phần lẻ chỉ là chữ số liền nhau, không có dấu chấm hay phẩy: `1 triệu 200.000` là `ValueError`.
   Mỗi mẩu có tối đa một phần lẻ.
7. Kết quả phải là số nguyên đồng; ra số lẻ đồng (như `1,2345k`) hay mọi chuỗi không theo các luật trên thì ném `ValueError`.

Ví dụ:
- `doc_tien("1tr5")` -> `1500000`
- `doc_tien("1 tỷ 2")` -> `1200000000`, còn `doc_tien("1 tỷ 2 triệu")` -> `1002000000`
- `doc_tien("3 lít rưỡi")` -> `350000`
