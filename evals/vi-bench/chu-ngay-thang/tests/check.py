"""Chấm chu-ngay-thang: so với kết quả đọc tay theo luật trong đề (hom_nay = 07/11/2026, thứ Bảy).

Các cách làm sai hay gặp mà bài chấm này bắt:
  - đọc theo thứ tự tháng/ngày (kiểu Mỹ), hoặc dùng strptime chỉ một khuôn;
  - năm hai chữ số lấy cứng 20xx ("1/1/70" phải là 1970), hay chốt mốc sai (69 → 2069, 70 → 1970);
  - năm nhuận: bỏ sót 2100 (không nhuận), 2000 (nhuận), hoặc 29/2 với năm hai chữ số;
  - đảo "ngày kia" (+2) với "hôm kia" (-2); thứ Hai tính nhầm là 0 với Chủ nhật, "thứ 2" lệch một;
  - không kiểm thứ với ngày; bỏ "Chủ nhật"; "mùng 11" không bị loại;
  - tháng chữ: "mười một" bị đọc là "mười" rồi dư chữ, "tháng Năm năm 2026" nhầm chữ năm, thiếu "Giêng", "Chạp", "Tư";
  - không có năm thì không lấy năm của hom_nay; hai dấu ngăn khác nhau (7/11-2026) vẫn được nhận;
  - không chịu NFD, chữ HOA, khoảng trắng thừa; ném lỗi khác ValueError (KeyError, AttributeError…).
"""
import importlib.util
import os
import sys
import unicodedata
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


HOM_NAY = date(2026, 11, 7)  # thứ Bảy

# (chuỗi vào, kết quả đúng). Đọc tay theo luật trong đề và lịch, soát lại ngày 08/11/2026.
# 07/11/2026 thứ Bảy; 08/11 Chủ nhật; 09/11 thứ Hai; 10/11 thứ Ba; 11/11 thứ Tư; 12/11 thứ Năm; 06/11 thứ Sáu.
CASES = [
    ("ngày 7 tháng 11 năm 2026", "2026-11-07"),
    ("7/11/26", "2026-11-07"),
    ("07-11-2026", "2026-11-07"),
    ("7.11.2026", "2026-11-07"),
    ("ngày 7/11/2026", "2026-11-07"),
    ("mùng 7 tháng 11", "2026-11-07"),
    ("mồng 10 tháng 12", "2026-12-10"),
    ("mùng 1 tháng 1", "2026-01-01"),
    ("mùng 7 tháng 11 năm 2025", "2025-11-07"),
    ("mùng 5 tháng Giêng", "2026-01-05"),
    ("12 tháng 3", "2026-03-12"),
    ("07 tháng 01 năm 2026", "2026-01-07"),
    ("thứ Bảy, 07-11-2026", "2026-11-07"),
    ("Thứ 7, 7/11/2026", "2026-11-07"),
    ("thứ bảy ngày 7 tháng 11 năm 2026", "2026-11-07"),
    ("CHỦ NHẬT, ngày 8 tháng 11 năm 2026", "2026-11-08"),
    ("Chủ nhật 8/11/26", "2026-11-08"),
    ("thứ Hai ngày 9 tháng 11", "2026-11-09"),
    ("thứ 2, 9/11/2026", "2026-11-09"),
    ("thứ 3, 10/11/2026", "2026-11-10"),
    ("thứ Tư, 11/11/2026", "2026-11-11"),
    ("thứ Năm 12/11/2026", "2026-11-12"),
    ("thứ Sáu, ngày 6 tháng 11", "2026-11-06"),
    (nfd("THỨ BẢY, NGÀY 7 THÁNG 11 NĂM 2026"), "2026-11-07"),
    ("  ngày   7  tháng  11  năm  2026  ", "2026-11-07"),
    (nfd("mùng 5 tháng Giêng"), "2026-01-05"),
    ("hôm nay", "2026-11-07"),
    ("ngày mai", "2026-11-08"),
    ("ngày kia", "2026-11-09"),
    ("hôm qua", "2026-11-06"),
    ("hôm kia", "2026-11-05"),
    ("Hôm Nay", "2026-11-07"),
    ("Chủ nhật, ngày mai", "2026-11-08"),
    ("thứ Hai, ngày kia", "2026-11-09"),
    ("thứ Sáu, hôm qua", "2026-11-06"),
    ("1/1/69", "2069-01-01"),
    ("1/1/70", "1970-01-01"),
    ("31/12/99", "1999-12-31"),
    ("1/1/00", "2000-01-01"),
    ("1/1/2026", "2026-01-01"),
    ("29/2/2024", "2024-02-29"),
    ("29/2/2000", "2000-02-29"),
    ("29/2/00", "2000-02-29"),
    ("29/2/96", "1996-02-29"),
    ("29/2/68", "2068-02-29"),
    ("11/7/2026", "2026-07-11"),
    ("ngày 1 tháng Giêng năm 2027", "2027-01-01"),
    ("ngày 30 tháng Chạp", "2026-12-30"),
    ("ngày 4 tháng Tư năm 2026", "2026-04-04"),
    ("5 tháng Năm năm 2026", "2026-05-05"),
    ("ngày 5 tháng Năm", "2026-05-05"),
    ("2 tháng Hai", "2026-02-02"),
    ("15 tháng Mười năm 2026", "2026-10-15"),
    ("15 tháng Mười một năm 2026", "2026-11-15"),
    ("3 tháng Mười hai", "2026-12-03"),
    ("ngày 9 tháng Chín", "2026-09-09"),
    ("thứ Sáu, ngày 1 tháng Giêng năm 2027", "2027-01-01"),
]
LOI = [
    "thứ Bảy, 8/11/2026",
    "Chủ nhật, 7/11/26",
    "thứ Sáu, 7/11/2026",
    "thứ 2, 7/11/2026",
    "thứ Bảy, ngày mai",
    "thứ Hai, hôm qua",
    "29/2/2026",
    "29/2/2100",
    "29/2/70",
    "30/2/2026",
    "31/4/2026",
    "0/1/2026",
    "32/1/2026",
    "15/13/2026",
    "1/0/2026",
    "mùng 11 tháng 11",
    "mồng 15 tháng Giêng",
    "mùng 0 tháng 3",
    "1/1/202",
    "1/1/20260",
    "1/1/2",
    "7/11-2026",
    "7/11",
    "7 tháng 11 năm",
    "tháng 11 năm 2026",
    "ngày 2 tháng bốn năm 2026",
    "ngày 2 tháng 4 năm 2026 thêm",
    "ngày kia kia",
    "hôm nay ngày mai",
    "thứ Bảy",
    "thứ 8, 7/11/2026",
    "",
    "   ",
    "abc",
    "ngày mốt",
]


def main():
    spec = importlib.util.spec_from_file_location("ngay_check", vncheck.app_dir() / "ngay.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được ngay.py: {exc!r}"])
    errs = []
    for vao, dung in CASES:
        try:
            got = mod.doc_ngay(vao, HOM_NAY)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"doc_ngay({vao!r}) lỗi {exc!r}, đúng là {dung!r}")
            continue
        if got != dung:
            errs.append(f"doc_ngay({vao!r}): được {got!r}, đúng là {dung!r}")
    for vao in LOI:
        try:
            got = mod.doc_ngay(vao, HOM_NAY)
            errs.append(f"doc_ngay({vao!r}) phải ném ValueError, được {got!r}")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            errs.append(f"doc_ngay({vao!r}) phải ném ValueError, được {exc!r}")
    vncheck.finish(errs[:12])


main()
