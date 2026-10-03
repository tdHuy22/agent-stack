LỖI 1: shop/orders.py:list_orders — offset tính sai, bỏ qua trang đầu
Trang đánh số từ 1 nhưng PR đổi `offset = (page - 1) * size` thành `page * size`: page=1 trả về trang thứ hai,
20 đơn đầu không bao giờ hiện. Sửa: giữ `(page - 1) * size`.

LỖI 2: shop/orders.py:order_summary — cache bỏ qua kiểm tra quyền
Cache khóa theo order_id và trả kết quả trước khi kiểm `order["user_id"] != user_id`, nên sau khi chủ đơn xem một
lần, người dùng khác gọi với cùng order_id trong 60 giây sẽ đọc được đơn của người khác. Sửa: kiểm quyền trước khi
trả từ cache (hoặc khóa cache theo (user_id, order_id)).

LỖI 3: shop/checkout.py:pay — thử lại lệnh thu tiền không có idempotency key, có thể thu hai lần
PaymentTimeout nghĩa là không biết lệnh thu đã chạy chưa; gọi lại `charge` không có idempotency_key là một lệnh thu
mới, nên khách có thể bị trừ tiền nhiều lần. Sửa: tạo một idempotency_key cho đơn và truyền nó ở mọi lần thử.

LỖI 4: shop/filters.py:build_filters — tham số mặc định `extra={}` bị sửa và dùng chung giữa các lần gọi
Dict mặc định được tạo một lần; gọi `build_filters("paid")` rồi `build_filters()` vẫn còn status="paid". Sửa:
`extra=None` rồi `extra = dict(extra or {})`.
