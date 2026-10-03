`bank.py` là sổ cái chuyển khoản được gọi từ nhiều luồng cùng lúc. Chạy `python3 stress.py` thì thỉnh thoảng tổng
tiền của ngân hàng không còn bảo toàn. Sửa `bank.py` để `transfer` đúng khi chạy đồng thời:

- tổng tiền luôn bảo toàn, không tài khoản nào âm, không bao giờ treo;
- chuyển tiền giữa các cặp tài khoản không liên quan nhau vẫn phải chạy song song được (không dùng một khóa chung
  cho cả ngân hàng, vì `_audit` là I/O chậm);
- chuyển cho chính mình là hợp lệ: số dư không đổi, nhưng vẫn phải đủ tiền (không đủ thì `InsufficientFunds`);
- giữ nguyên tên lớp, tên hàm, chữ ký và các ngoại lệ hiện có; `_audit` vẫn được gọi như cũ.
