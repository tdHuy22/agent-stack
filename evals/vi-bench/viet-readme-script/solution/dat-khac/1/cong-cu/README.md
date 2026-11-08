# saoluu.py

Script nhỏ để sao lưu một thư mục: nó nén thư mục thành một file mang ngày giờ lúc chạy, rồi dọn các bản cũ quá số lượng cho phép.

## Yêu cầu

Python từ bản 3.9 trở lên, không cần cài gói nào khác.

## Cách dùng

```
python3 saoluu.py NGUON DICH [tùy chọn]
```

Ví dụ `python3 saoluu.py ~/du-an /mnt/sao-luu --nen tar`. Tên file kết quả là tên thư mục nguồn, một dấu gạch, ngày giờ dạng YYYYMMDD-HHMMSS rồi tới đuôi `.zip`; với `--nen tar` đuôi là `.tar.gz`.

## Tùy chọn

| Cờ | Mặc định | Tác dụng |
|---|---|---|
| `--giu N` | 7 (hoặc giá trị biến môi trường `SAOLUU_GIU`) | Giữ N bản gần nhất, bản cũ hơn bị xóa. Cho N bằng 0 thì giữ tất cả, không xóa gì. |
| `--nen zip` hoặc `--nen tar` | zip | Chọn dạng nén. |
| `--bo-qua MAU` | `.git`, `node_modules`, `__pycache__` | Bỏ thêm các tên khớp mẫu, ngoài ba mẫu mặc định. Lặp lại cờ để thêm nhiều mẫu. |
| `--thu` | tắt | Chỉ in việc sẽ làm, không ghi file và không xóa gì. |
| `-v` hoặc `--chi-tiet` | tắt | In từng file được thêm vào. |

## Mã thoát

Chương trình thoát với mã 0 khi thành công. Mã 2: không có thư mục nguồn. Mã 3: không ghi được vào thư mục đích. Mã 4: ổ đĩa đích còn trống ít hơn 1,2 lần dung lượng nguồn.
