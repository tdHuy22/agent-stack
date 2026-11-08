# saoluu.py

Script sao lưu một thư mục thành file nén có đóng dấu ngày giờ, rồi dọn bớt các bản cũ để ổ đĩa không bị đầy dần theo thời gian.

## Yêu cầu
Cần Python 3.9 trở lên.

## Cách dùng
```
python3 saoluu.py NGUON DICH --giu 5
```
File kết quả có dạng ten-YYYYMMDD-HHMMSS.zip.

## Tùy chọn
- `--giu N`: giữ 5 bản gần nhất.
- `--nen zip|tar`: dạng nén, mặc định zip.
- `--exclude MAU`: bỏ qua các mẫu tên file.
- `--thu`: chạy thử, không ghi gì.
- `-v`: in chi tiết.
