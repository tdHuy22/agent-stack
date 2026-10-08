Module `rankings/` dựng bảng xếp hạng giải bóng đá từ danh sách đội và kết quả trận. Người dùng báo: "cùng một dữ
liệu mà chạy lần này ra bảng khác lần kia", "đội chưa đá trận nào biến mất", và "có đội đá hòa mà điểm lệch". Test
`tests/test_table.py` đang đỏ ở vài ca nhưng không bao quát hết; chạy nhiều lần cũng có thể lúc xanh lúc đỏ.

Sửa code trong `rankings/` cho đúng đặc tả sau; rà toàn bộ module theo đặc tả, vì còn chỗ sai chưa ai báo. Không sửa
test, giữ nguyên tên và chữ ký công khai. Kiểm tra bằng `python3 -m unittest discover -s tests -q`.

- `build_table(roster, matches)`: `roster` là danh sách tên đội; `matches` là danh sách `(đội_nhà, bàn_nhà, đội_khách, bàn_khách)`.
  Trả về danh sách `Row(name, played, won, drawn, lost, gf, ga, gd, points)` đã sắp xếp. Mọi đội trong `roster`
  đều có dòng, kể cả chưa đá trận nào (toàn số 0). Trận có đội ngoài `roster` thì `ValueError`.
- Thắng 3 điểm, hòa 1 điểm **cho mỗi đội**, thua 0. `gf`/`ga` là bàn thắng/thua của chính đội đó, `gd = gf - ga`.
- Thứ tự: điểm giảm dần, rồi hiệu số `gd` giảm dần, rồi `gf` giảm dần, rồi tên tăng dần không phân biệt hoa thường
  (`casefold`). Hai đội giống nhau cả bốn tiêu chí thì giữ thứ tự xuất hiện trong `roster`.
- `render(rows)` trả về chuỗi nhiều dòng, mỗi dòng `f"{rank:>2}. {name:<12}{played:>3}{points:>4}"`. Các đội bằng
  nhau về điểm, `gd` và `gf` cùng hạng; hạng kế tiếp nhảy cóc (1, 1, 3). Các dòng nối bằng `"\n"`, không có dòng trống ở cuối.
