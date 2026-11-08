"""Chấm viet-rut-gon: rút từ ~900 chữ xuống ≤200 chữ mà giữ đủ tiền, ngày, tên, địa chỉ và không thêm số lạ.

Từ thong-bao-chuyen-van-phong.txt: tiền thuê mới 36 triệu/tháng; đặt cọc 72 triệu (hai tháng); chuyển trọn gói 48.500.000đ (báo giá đầu
55 triệu đã đổi); ngày 12/11 (đặt cọc, chị Đỗ Minh Châu), 14/11 (danh sách đồ cá nhân, chị Lê Thị Hương), 21/11 (bắt đầu đóng gói),
28/11 (chuyển; ngày dự kiến đầu 22/11 đã đổi), 30/11 (đi làm; anh Phạm Quốc Bảo lo máy tính và mạng); văn phòng mới Tầng 7, tòa
nhà Sao Mai, 15 Nguyễn Văn Linh, Quận 7. Số lớn (từ 100 trở lên) trong bản rút phải có trong văn bản gốc (hay là số triệu × 1.000.000).

Tiền chấp nhận "36 triệu", "36tr", "36.000.000"; 48,5 triệu hay "48 triệu 500"; ngày viết 12/11 hay 12 tháng 11. Dấu hiệu văn AI không còn làm trượt.

Fixture (solution/dat-khac, solution/truot) chạy trong selftest.py:
  ĐẠT    1 văn xuôi, "48,5 triệu đồng", "ngày 12 tháng 11", gọi "chị Hương", "anh Bảo", "chị Châu"; 2 gạch đầu dòng, "36tr", "72tr", "48,5tr", ngày 12/11;
         3 mở bằng "Trong bối cảnh" và có "đóng vai trò quan trọng" nhưng đủ mọi mục (văn AI không còn làm trượt)
  TRƯỢT  1 còn báo giá cũ 55 triệu và ngày chuyển cũ 22/11, thiếu tên anh Bảo; 2 làm tròn "gần 50 triệu", thiếu ngày 14/11 và 21/11, thêm số 432;
         3 đủ mọi ý nhưng dài 205 chữ, quá giới hạn 200
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def date_re(d, m):
    return rf"(?<!\d)0?{d}\s*(/|-|tháng)\s*0?{m}(?!\d)"


def amount_re(trieu, full):
    return rf"(?<![\d.,]){trieu}\s*(triệu|tr\b)|(?<!\d){full}(?!\d)"


def main():
    text = vncheck.read("ban-tin-ngan.txt")
    if text is None:
        vncheck.finish(["chưa có /app/ban-tin-ngan.txt"])
    errs = vncheck.writing_checks(text, max_words=200, min_words=50)
    flat = vncheck.norm_num(text)
    for (d, m), why in (((12, 11), "hạn đặt cọc"), ((14, 11), "hạn nộp danh sách đồ cá nhân"), ((21, 11), "ngày bắt đầu đóng gói"),
                        ((28, 11), "ngày chuyển"), ((30, 11), "ngày đi làm tại văn phòng mới")):
        if not re.search(date_re(d, m), flat):
            errs.append(f"thiếu {d}/{m} ({why})")
    if re.search(date_re(22, 11), flat):
        errs.append("còn ngày chuyển cũ 22/11 (đã đổi sang 28/11)")
    if not re.search(amount_re(r"36", "36000000"), flat):
        errs.append("thiếu tiền thuê mới 36 triệu đồng mỗi tháng")
    if not re.search(amount_re(r"72", "72000000"), flat):
        errs.append("thiếu tiền đặt cọc 72 triệu đồng")
    if not re.search(r"(?<![\d.,])48[.,]5\s*(triệu|tr\b)|(?<![\d.,])48\s*triệu\s*500|(?<!\d)48500000(?!\d)", flat):
        errs.append("thiếu chi phí chuyển 48.500.000 đồng (48,5 triệu)")
    if re.search(r"(?<![\d.,])55\s*(triệu|tr\b)|(?<!\d)55000000(?!\d)", flat):
        errs.append("còn báo giá cũ 55 triệu (đã chốt 48,5 triệu)")
    for pat, who in ((r"Hương", "chị Lê Thị Hương"), (r"Quốc Bảo|Phạm Bảo|(?<!\w)Bảo(?!\w)", "anh Phạm Quốc Bảo"),
                     (r"Minh Châu|Đỗ Châu|(?<!\w)Châu(?!\w)", "chị Đỗ Minh Châu")):
        if not re.search(pat, text):
            errs.append(f"thiếu tên {who}")
    if not (re.search(r"Sao Mai", text) and re.search(r"Nguyễn Văn Linh", text)):
        errs.append("thiếu địa chỉ văn phòng mới (tòa nhà Sao Mai, Nguyễn Văn Linh)")
    # không thêm số lớn lạ
    # văn bản gốc chép sẵn trong tests/, không đọc từ /app (agent có thể sửa hay xóa)
    src = (Path(__file__).resolve().parent / "nguon.txt").read_text(encoding="utf-8")
    allowed = set()
    for n in re.findall(r"\d+", vncheck.norm_num(src)):
        allowed.add(int(n))
        allowed.add(int(n) * 1_000_000)
    for n in re.findall(r"\d+", flat):
        if int(n) >= 100 and int(n) not in allowed:
            errs.append(f"có số {n} không có trong văn bản gốc")
    vncheck.finish(errs)


main()
