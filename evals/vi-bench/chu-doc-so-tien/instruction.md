Kế toán nhờ sửa hàm `doc_so_tien(n)` trong `/app/doc_so.py`: nhận một số tiền và trả về cách đọc bằng chữ để in lên phiếu chi. Bản hiện tại đọc sai nhiều chỗ (hai mươi một, năm trăm lẻ…), phiếu in ra bị trả về suốt. Giữ nguyên tên hàm và tên file.

`n` là số nguyên không âm, hoặc chuỗi chỉ có chữ số và dấu chấm ngăn nghìn (như `"1.250.005"`). Nhỏ hơn 10^15. Nếu `n` âm, từ 10^15 trở lên hay không đọc được thành số thì ném `ValueError`.

Luật đọc (đúng như kế toán ở công ty quy định, đừng đọc theo thói quen):

1. Kết quả viết hoa chữ cái đầu, các chữ còn lại viết thường, các chữ cách nhau đúng một dấu cách, kết thúc bằng " đồng". Số 0 đọc là "Không đồng".
2. Chia số từ phải sang trái thành các nhóm ba chữ số: đơn vị, nghìn, triệu, rồi phần tỷ. Dùng "nghìn" (không dùng "ngàn"), "tỷ" (không dùng "tỉ"). Nhóm toàn số 0 thì bỏ qua cả nhóm, không đọc đơn vị của nó. Phần tỷ (mọi chữ số từ hàng tỷ trở lên) đọc như một số nguyên bình thường theo chính các luật này rồi thêm "tỷ", ví dụ 1.005 tỷ đọc là "một nghìn không trăm linh năm tỷ".
3. Trong một nhóm ba chữ số: hàng trăm đọc "X trăm". Nhóm đứng đầu (nhóm cao nhất khác 0 của cả số) mà hàng trăm là 0 thì bỏ qua hàng trăm. Mọi nhóm khác 0 không phải nhóm đứng đầu đều phải đọc đủ hàng trăm, kể cả "không trăm".
4. Hàng chục: 1 đọc "mười"; từ 2 đến 9 đọc "hai mươi", "ba mươi"… Hàng chục là 0 mà hàng đơn vị khác 0: đọc "linh" trước chữ số đơn vị (chỉ khi hàng trăm được đọc; nếu hàng trăm bị bỏ qua theo luật 3 thì không có "linh").
5. Hàng đơn vị: 1 đọc "mốt" nếu đứng sau "mươi" (hai mươi mốt), còn lại đọc "một" (mười một, linh một, một). 4 đọc "tư" nếu đứng sau "mươi" (hai mươi tư), còn lại đọc "bốn" (mười bốn, linh bốn, bốn). 5 đọc "lăm" nếu đứng sau "mười" hay "mươi" (mười lăm, hai mươi lăm), còn lại đọc "năm" (linh năm, năm).

Ví dụ:
- `doc_so_tien(1250005)` -> `"Một triệu hai trăm năm mươi nghìn không trăm linh năm đồng"`
- `doc_so_tien("21.015")` -> `"Hai mươi mốt nghìn không trăm mười lăm đồng"`
- `doc_so_tien(4_000_004)` -> `"Bốn triệu không trăm linh bốn đồng"`
