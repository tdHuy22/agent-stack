Bên kế toán báo bảng lương tháng này tính thuế TNCN lệch ở nhiều người. Bạn sửa hàm `tinh_thue_tncn(luong_gop, so_nguoi_phu_thuoc=0)` trong `/app/luong/thue.py` cho đúng luật dưới, giữ nguyên tên hàm và tên tham số (bên bảng lương đang gọi theo tên). Hàm trả số nguyên là thuế phải nộp trong tháng, tính bằng đồng.

Luật tính, theo đúng thứ tự:

1. Bảo hiểm bắt buộc tính trên mức đóng bằng lương gộp, nhưng mức đóng tối đa là 36.000.000đ (lương gộp cao hơn thì vẫn chỉ đóng trên 36.000.000đ). Có ba khoản: BHXH 8%, BHYT 1,5%, BHTN 1%. Mỗi khoản làm tròn nửa lên tới đồng riêng (từ 0,5 trở lên thì lên), rồi cộng ba khoản lại.
2. Thu nhập chịu thuế = lương gộp trừ tổng bảo hiểm ở bước 1.
3. Thu nhập tính thuế = thu nhập chịu thuế trừ 11.000.000đ (giảm trừ bản thân) trừ tiếp 4.400.000đ cho mỗi người phụ thuộc. Nếu kết quả không dương thì thuế là 0.
4. Thuế lũy tiến từng phần: phần thu nhập tính thuế nằm trong bậc nào thì chịu thuế suất của bậc đó (không phải cả khoản chịu một thuế suất).

   | Phần thu nhập tính thuế | Thuế suất |
   |---|---|
   | đến 5.000.000đ | 5% |
   | trên 5.000.000đ đến 10.000.000đ | 10% |
   | trên 10.000.000đ đến 18.000.000đ | 15% |
   | trên 18.000.000đ đến 32.000.000đ | 20% |
   | trên 32.000.000đ đến 52.000.000đ | 25% |
   | trên 52.000.000đ đến 80.000.000đ | 30% |
   | trên 80.000.000đ | 35% |

5. Cộng thuế của các bậc lại (chưa làm tròn), rồi làm tròn nửa lên tới đồng một lần duy nhất ở cuối.

Lương gộp hay số người phụ thuộc là số âm thì báo `ValueError`. Lương gộp bằng 0 thì thuế là 0.

Trong `/app/luong/test_thue.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/luong`.
