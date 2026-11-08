#!/bin/bash
# Lời giải mẫu: README đúng cờ, mặc định và mã thoát theo code của saoluu.py.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/cong-cu/README.md" <<'MD'
# saoluu.py

Sao lưu một thư mục thành một file nén có đóng dấu thời gian, rồi xóa bớt các bản quá cũ.

## Yêu cầu

Python 3.9 trở lên. Không cần cài thêm gói nào.

## Cách dùng

```
python3 saoluu.py NGUON DICH [tùy chọn]
python3 saoluu.py ~/du-an /mnt/sao-luu --giu 10 --bo-qua "*.log"
```

`NGUON` là thư mục cần sao lưu, `DICH` là thư mục chứa các bản sao lưu (tự tạo nếu chưa có). File kết quả đặt tên theo mẫu `tên-thư-mục-nguồn-YYYYMMDD-HHMMSS.zip`, ví dụ `du-an-20261108-093015.zip`. Nếu chọn `--nen tar` thì đuôi là `.tar.gz`.

## Tùy chọn

- `--giu N`: số bản gần nhất được giữ lại, mặc định 7. Đặt 0 thì không xóa bản nào. Có thể đổi mặc định bằng biến môi trường `SAOLUU_GIU`.
- `--nen zip|tar`: dạng nén, mặc định `zip`.
- `--bo-qua MAU`: bỏ qua file hay thư mục có tên khớp mẫu, dùng được nhiều lần. Mẫu này được cộng thêm vào danh sách mặc định gồm `.git`, `node_modules`, `__pycache__`.
- `--thu`: chạy thử, chỉ in việc sẽ làm, không ghi và không xóa gì.
- `-v`, `--chi-tiet`: in từng file được thêm vào bản sao lưu.

## Mã thoát

- 0: xong.
- 2: không thấy thư mục nguồn.
- 3: không ghi được vào thư mục đích.
- 4: ổ đĩa đích không đủ chỗ, cần trống ít nhất 1,2 lần dung lượng nguồn.
MD
