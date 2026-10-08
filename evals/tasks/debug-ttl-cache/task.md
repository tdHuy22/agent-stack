`cache.py` là bộ nhớ đệm TTL + LRU dùng trong dịch vụ của chúng tôi. Người dùng báo: "thỉnh thoảng đọc ra dữ liệu
cũ", "mục còn hạn bị đẩy mất dù đệm toàn mục hết hạn", "giá trị 0 hay chuỗi rỗng cứ bị nạp lại", "số thống kê vô lý".
Test `tests/test_cache.py` đang đỏ ở vài ca, nhưng không bao quát hết. Sửa `cache.py` cho đúng đặc tả sau; rà toàn bộ
lớp theo đặc tả, vì còn chỗ sai chưa ai báo. Không sửa test, giữ nguyên tên và chữ ký công khai (có thể thêm tham số
tùy chọn).

Đặc tả `TTLCache(capacity, ttl=None, clock=time.monotonic)`:

- `capacity` phải >= 1, không thì `ValueError`. `ttl` là `None` (không bao giờ hết hạn) hoặc số > 0, không thì `ValueError`.
- `set(key, value, ttl=None)`: `ttl` riêng của mục; `None` thì dùng ttl mặc định của đệm. Ghi đè khóa đã có thì thay
  giá trị, tính lại hạn từ lúc ghi và đưa mục thành "dùng gần nhất".
- Mục hết hạn khi `clock() >= hạn` (đúng thời điểm hạn là đã hết).
- `get(key, default=None)`: mục còn hạn thì trả giá trị (kể cả giá trị `None`, `0`, `""`) và đưa thành "dùng gần
  nhất"; mục hết hạn thì bị xóa khỏi đệm và coi như không có.
- `len(cache)` là số mục còn hạn. `key in cache` kiểm tra mục còn hạn, không đổi thứ tự LRU, không đổi thống kê.
- Khi thêm khóa mới mà đệm đầy: trước hết bỏ mọi mục đã hết hạn; nếu vẫn đầy thì đẩy mục còn hạn dùng lâu nhất.
- `pop(key, default=None)`: gỡ và trả giá trị nếu còn hạn; hết hạn hay không có thì trả `default` (mục hết hạn vẫn bị gỡ).
- `get_or_load(key, loader)`: còn hạn thì trả giá trị (tính một hit); không thì gọi `loader()` đúng một lần, lưu, trả
  về (tính một miss). `loader` ném lỗi thì không lưu gì, lỗi được ném tiếp, vẫn tính một miss.
- `stats` là dict `hits`, `misses`, `evictions` (chỉ đẩy vì đầy, không tính hết hạn), `expirations` (mỗi mục hết
  hạn bị gỡ tính đúng một lần). `get` hit/miss tính như trên; `in`, `len`, `pop` không đổi `hits`/`misses`.
