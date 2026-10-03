`pool.py` là pool kết nối bất đồng bộ (asyncio) dùng chung cho nhiều tác vụ. Trên production thỉnh thoảng pool
"cạn" dù chẳng còn ai dùng kết nối, có tác vụ chờ mãi, và `close()` đóng cả kết nối đang được dùng. Sửa `pool.py`
để đúng đặc tả sau (giữ tên lớp, tên hàm và chữ ký; có thể thêm tham số tùy chọn):

- `acquire(timeout=None)`: trả kết nối rảnh nếu có; không có mà số kết nối đã tạo (`created`) còn dưới `size` thì
  tạo mới bằng `connect()`; không thì chờ. Quá `timeout` giây: `asyncio.TimeoutError`. Pool đã đóng, kể cả khi
  đang chờ: `PoolClosed`.
- Mọi đường lỗi (`connect()` ném lỗi, tác vụ bị hủy khi đang kết nối hay đang chờ, hết giờ) không được làm mất sức
  chứa: `created` và `in_use` luôn đúng.
- `connection(timeout=None)` (async context manager): luôn trả kết nối về pool khi ra khỏi khối, kể cả khi có ngoại
  lệ hay bị hủy. Nếu ngoại lệ là `ConnectionBroken`: gọi `conn.close()`, không đưa kết nối lại vào pool, giảm
  `created` để lần sau tạo kết nối mới, và vẫn ném tiếp ngoại lệ.
- Khi sức chứa được giải phóng (kết nối được trả về hoặc bị bỏ), tác vụ đang chờ phải được đánh thức.
- `close()`: từ chối `acquire` mới và làm mọi tác vụ đang chờ nhận `PoolClosed` ngay; chờ mọi kết nối đang dùng
  được trả về; rồi đóng mọi kết nối. Kết nối trả về sau khi đã gọi `close()` thì bị đóng luôn.
- Chạy được trên Python 3.9 trở lên.
