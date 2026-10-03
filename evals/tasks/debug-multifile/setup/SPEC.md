# Quy tắc tính hóa đơn

1. Giá là chuỗi thập phân không âm, tối đa 2 chữ số lẻ: `"19.99"`, `"5"`, `"0.5"`. Mọi phép tính dùng số nguyên
   xu; kết quả không được lệch vì sai số số thực. Giá âm, sai định dạng hoặc nhiều hơn 2 chữ số lẻ: `ValueError`.
2. Tạm tính (`subtotal`) = tổng của số lượng × đơn giá trên mọi dòng.
3. Mã giảm giá áp lên tạm tính, cho ra `discounted`:
   - `percent` p: tiền giảm = tạm tính × p / 100, **làm tròn nửa lên** tới xu (0,5 xu thành 1 xu);
   - `fixed` x: trừ thẳng x xu; số tiền sau giảm không bao giờ âm (thấp nhất là 0);
   - không có mã: `discounted` = `subtotal`; mã không có trong danh mục: `ValueError`.
4. Thuế (`tax`) tính **một lần** trên `discounted` (không tính theo từng dòng), thuế suất tính bằng phần trăm và
   có thể lẻ (ví dụ 8.25), **làm tròn nửa lên** tới xu.
5. Tổng (`total`) = `discounted` + `tax`.
