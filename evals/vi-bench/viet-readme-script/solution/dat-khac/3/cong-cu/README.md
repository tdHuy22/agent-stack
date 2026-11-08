# saoluu.py

Trong bối cảnh dữ liệu cần được bảo vệ, `saoluu.py` giúp nén một thư mục thành bản sao lưu.

## Yêu cầu

Python 3.9 trở lên.

## Cách dùng

```
python3 saoluu.py ~/du-an /mnt/sao-luu
```

Tên file là tên thư mục nguồn, dấu gạch, ngày giờ dạng YYYYMMDD-HHMMSS, rồi `.zip` (với `--nen tar` là `.tar.gz`).

## Tùy chọn

`--giu N` giữ N bản gần nhất, mặc định 7 và có thể đặt bằng biến `SAOLUU_GIU`; đặt 0 để không xóa bản cũ nào. `--nen` chọn zip (mặc định) hoặc tar. `--bo-qua MAU` bỏ thêm các tên khớp mẫu vào danh sách mặc định gồm .git, node_modules, __pycache__, dùng nhiều lần được. `--thu` chạy thử, không ghi và không xóa gì. `-v` in từng file.

## Mã thoát

Mã 2: không có thư mục nguồn. Mã 3: không ghi được vào thư mục đích. Mã 4: ổ đĩa đích còn trống dưới 1,2 lần dung lượng nguồn.

Tóm lại, script nhỏ nhưng đủ dùng.
