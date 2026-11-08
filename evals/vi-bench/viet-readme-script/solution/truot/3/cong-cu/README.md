# saoluu.py

Script sao lưu một thư mục thành file nén có đóng dấu ngày giờ, rồi dọn bớt các bản cũ để ổ đĩa không bị đầy dần.

## Yêu cầu
Cần Python 3.9 trở lên.

## Cách dùng
```
python3 saoluu.py NGUON DICH --giu 10
```
File kết quả đặt tên như du-an-20261108-093015.zip, riêng --nen tar thì đuôi là .tar.gz.

## Tùy chọn
- `--giu N`: số bản được giữ, mặc định 7. Có thể đặt trước bằng biến SAOLUU_GIU.
- `--nen zip|tar`: dạng nén, mặc định zip.
- `--bo-qua MAU`: thay cho danh sách bỏ qua mặc định, gồm .git, node_modules, __pycache__.
- `--thu`: chạy thử, không ghi và không xóa gì.
- `-v`: in chi tiết từng file.

## Mã thoát
- 2: thư mục đích không ghi được.
- 3: không thấy thư mục nguồn.
- 4: ổ đĩa đích hết chỗ, cần trống 1,2 lần dung lượng nguồn.
