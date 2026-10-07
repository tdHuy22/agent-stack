Repo này là sổ tay nội bộ viết bằng markdown. Mình muốn mỗi PR đều được kiểm tra link hỏng trong CI, và phải bắt được cả ba loại:

1. link tương đối tới file không tồn tại;
2. link tới một mục (`#ten-muc`) mà file đích không có heading tương ứng;
3. link ngoài `http(s)` bị lỗi, có thử lại khi lỗi mạng tạm thời và có danh sách URL được bỏ qua.

Trước khi làm, dùng skill reuse-best để tìm thứ có sẵn tốt nhất, rồi báo lại cho mình quyết định. Chưa sửa file nào.
