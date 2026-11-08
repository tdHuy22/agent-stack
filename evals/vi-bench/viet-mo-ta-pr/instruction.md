Mình vừa làm xong một thay đổi cho thư viện tính tiền `cua_hang` và cần mô tả để gửi người review. Diff nằm ở `/app/pr/thay-doi.diff`, mã sau khi sửa ở `/app/pr/kho/` (có README của dự án), yêu cầu gốc ở `/app/pr/issue-87.txt`. Viết giúp mình mô tả PR vào file `/app/MO-TA-PR.md`.

Yêu cầu:

- Viết bằng tiếng Việt có dấu, tối đa 250 chữ (đếm theo từng tiếng, không kể code trong dấu huyền), người review là lập trình viên đã biết dự án.
- Có ba mục, tên đúng như sau và theo thứ tự này: "Thay đổi", "Lý do", "Cách kiểm".
- Mục "Thay đổi": liệt kê theo từng file đã đổi (ghi tên file), mọi hàm được thêm, sửa hay xóa (ghi đúng tên hàm trong dấu huyền), mức cấu hình nào đổi thì ghi giá trị cũ và mới, và tên các test mới thêm.
- Mục "Lý do": đóng issue nào, và các lỗi nào được sửa.
- Mục "Cách kiểm": lệnh chạy test của dự án, kèm một ví dụ kiểm tay tính theo ngày 10/11/2026: đơn tiền hàng 420.000đ, phí ship 25.000đ, mã GIAM10; ghi tổng khách phải trả sau thay đổi này.
- Chỉ nhắc tên hàm, tên file, tên test có thật trong diff và mã.
