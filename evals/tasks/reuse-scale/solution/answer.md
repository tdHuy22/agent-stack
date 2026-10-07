Quyết định: không dùng lại app/ratelimit.py; đếm trong Redis mà project đã có.

- SlidingWindowLimiter giữ số đếm trong bộ nhớ của từng tiến trình. Production chạy 4 worker gunicorn × 3 replica, nên mỗi key thực tế được tới 1.200 request/phút thay vì 100.
- Redis đã có sẵn (app/cache.py, deploy/docker-compose.yml). Thư viện `limits` (alisaifee/limits, MIT) có kho Redis và cửa sổ trượt; slowapi bọc nó cho FastAPI. Cũng có thể tự viết vài dòng bằng INCR + EXPIRE nếu chấp nhận cửa sổ cố định.

Phần còn phải làm: gắn limiter vào dependency `api_key`, trả 429 kèm Retry-After, và thêm test chạy với nhiều worker.
