Kế toán đang phải mở file CSV ra cắt tay từng tháng trước khi chạy báo cáo. Bạn thêm hai cờ lọc ngày vào script `/app/bao_cao/bao_cao.py`:

```
python3 bao_cao.py FILE.csv [--tu-ngay dd/mm/yyyy] [--den-ngay dd/mm/yyyy]
```

Cả hai cờ đều tùy chọn và có thể đứng trước hoặc sau `FILE.csv`; chấp nhận cả dạng `--tu-ngay=01/03/2024`. Chỉ lấy các giao dịch có ngày từ `--tu-ngay` đến `--den-ngay`, tính cả hai đầu. Thiếu cờ nào thì không giới hạn phía đó. Ngày trong file CSV và trong cờ đều dạng dd/mm/yyyy, nhưng ngày và tháng có thể viết một hay hai chữ số (`5/3/2024` và `05/03/2024` là cùng một ngày), nên phải so sánh theo ngày chứ không so chuỗi.

Giữ nguyên cách in hiện tại (mỗi sản phẩm một dòng `tên: số tiền`, rồi dòng `Tổng: ...`, tiền có dấu chấm ngăn nghìn) và giữ các hàm `doc_giao_dich`, `tong_hop`, `dinh_dang_tien`, `main(argv=None)` (test có sẵn và chỗ khác đang dùng). `main` vẫn trả mã thoát (số nguyên) cho `sys.exit`.

Hành vi mới, nguyên văn, mọi thông báo lỗi in ra **stderr** đúng một dòng (có dấu chấm cuối như bên dưới), không in gì ra stdout, không in thêm gì khác (không có đoạn "usage" của argparse, không có traceback):

| Tình huống | Mã thoát | Thông báo |
|---|---|---|
| Không có giao dịch nào trong khoảng ngày | 0 | in ra **stdout** dòng `Không có giao dịch trong khoảng ngày đã chọn.` (không in dòng `Tổng`) |
| Giá trị của `--tu-ngay` sai dạng hay không có thật, vd. `30/02/2024`, `2024-03-31` | 2 | `Lỗi: --tu-ngay không hợp lệ: 30/02/2024 (cần dạng dd/mm/yyyy).` (thay giá trị bạn đã nhận) |
| Giá trị của `--den-ngay` sai | 2 | `Lỗi: --den-ngay không hợp lệ: 2024-03-31 (cần dạng dd/mm/yyyy).` |
| `--tu-ngay` sau `--den-ngay` | 2 | `Lỗi: --tu-ngay không được sau --den-ngay.` |
| Không tìm thấy file | 3 | `Lỗi: không tìm thấy file: <đường dẫn như người dùng gõ>` (không có dấu chấm cuối) |
| Thiếu `FILE.csv`, thừa đối số, có cờ lạ (kể cả `-h`), hoặc cờ thiếu giá trị | 2 | `Cách dùng: python3 bao_cao.py FILE.csv [--tu-ngay dd/mm/yyyy] [--den-ngay dd/mm/yyyy]` |

Thứ tự kiểm tra: cách dùng trước, rồi giá trị `--tu-ngay`, rồi giá trị `--den-ngay`, rồi quan hệ giữa hai ngày, và cuối cùng mới mở file (nên ngày sai và file không tồn tại cùng lúc thì báo ngày sai).

Trong `/app/bao_cao/test_bao_cao.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/bao_cao`.
