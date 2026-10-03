Khách hàng báo hai chuyện với module hóa đơn trong `billing/`: vài hóa đơn lệch 1 xu so với tính tay, và đơn dùng
mã giảm giá cố định lớn ra tổng âm. Test `tests/test_invoice.py` đang đỏ. Quy tắc đúng nằm ở `SPEC.md`.

Tìm nguyên nhân gốc và sửa code trong `billing/` cho đúng `SPEC.md`. Rà toàn bộ module theo SPEC, vì có thể còn
chỗ sai chưa ai báo. Không sửa test, không sửa `SPEC.md`, giữ nguyên tên và chữ ký các hàm công khai.
Kiểm tra bằng `python3 -m unittest discover -s tests -q`.
