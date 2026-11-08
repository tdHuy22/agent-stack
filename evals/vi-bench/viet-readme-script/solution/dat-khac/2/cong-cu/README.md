# saoluu.py

Sao lưu một thư mục thành file nén có ngày giờ trong tên.

## Yêu cầu

Python 3.9 trở lên.

## Cách dùng

```
python3 saoluu.py NGUON DICH [tùy chọn]
```

File kết quả tên là `<tên thư mục nguồn>-YYYYMMDD-HHMMSS.zip` (hoặc `.tar.gz` khi dùng `--nen tar`).

## Tùy chọn

- `--giu N`: giữ N bản gần nhất, mặc định 7 (đổi bằng biến môi trường `SAOLUU_GIU`). N bằng 0 là giữ hết, không xóa bản nào.
- `--nen zip` hoặc `--nen tar`: dạng nén, mặc định zip.
- `--bo-qua MAU`: bỏ qua thêm các tên khớp mẫu, ngoài danh sách mặc định `.git`, `node_modules`, `__pycache__`; dùng được nhiều lần.
- `--thu`: chạy thử, chỉ in việc sẽ làm, không ghi và không xóa gì.
- `-v` hoặc `--chi-tiet`: in từng file được thêm.

## Mã thoát

| Mã | Ý nghĩa |
|---|---|
| 0 | Xong |
| 2 | Không thấy thư mục nguồn |
| 3 | Không ghi được vào thư mục đích |
| 4 | Ổ đĩa đích hết chỗ trống (cần ít nhất 1,2 lần dung lượng nguồn) |
