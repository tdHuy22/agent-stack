# Đóng góp cho relkit

## Phụ thuộc

relkit chỉ dùng thư viện chuẩn của Python. Không thêm gói ngoài: script chạy trên máy build không có mạng, bằng `/usr/bin/python3` có sẵn của macOS, hiện là Python 3.9.

## Kiểm tra

    python3 -m unittest

CI chạy test trên cả Python 3.9 và 3.12 (`.github/workflows/ci.yml`).
