Shop đang tính phí ship sai, khách phàn nàn mấy hôm nay. Sửa hàm `tinh_phi_ship` trong `/app/shop/phi_ship.py` cho đúng luật dưới, đừng đổi tên hay tham số của hàm (chỗ khác đang gọi).

Luật tính phí (tiền tính bằng đồng, số nguyên):

- Đơn từ 500.000đ trở lên: miễn phí ship (0đ).
- Đơn dưới 500.000đ giao trong Hà Nội: 20.000đ.
- Đơn dưới 500.000đ giao tỉnh khác: 35.000đ.
- Tổng tiền âm thì báo `ValueError`.

Tên tỉnh khách gõ tay nên lộn xộn. Coi là Hà Nội nếu sau khi bỏ dấu, bỏ phân biệt hoa thường, bỏ khoảng trắng thừa ở đầu, cuối và giữa các chữ, và bỏ tiền tố "TP." hay "Thành phố" (nếu có) thì còn lại đúng chữ "ha noi". Ví dụ "  TP. Hà Nội", "ha noi", "HÀ  NỘI" đều là Hà Nội; "Hà Nam" thì không.

Trong `/app/shop/test_phi_ship.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/shop`.
