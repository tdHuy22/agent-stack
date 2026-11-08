"""Chấm code-csv-excel: đọc các file CSV dựng tại chỗ giống file Excel tiếng Việt, đối chiếu tổng tính tay.

Các cách làm sai đã thử, đều phải trượt:
  - mở file bằng utf-8 thường nên tiêu đề đầu tiên thành "\\ufeffNgày" và không tìm thấy cột;
  - đọc số bằng cách bỏ dấu phẩy rồi Decimal/float ("1.234.567,5" thành sai hay lỗi), coi "1.500" là 1,5, không đọc
    được "(250.000)", "1.500.000 ₫" hay đơn vị cách bằng khoảng trắng không ngắt;
  - lấy tháng bằng cắt chuỗi cố định (hỏng với "5/3/2024" và "05/03/2024 14:30"), hoặc hiểu ngày/tháng ngược;
  - mở file không có newline="" hay tách dòng bằng split("\\n") nên ô có xuống dòng bên trong dấu nháy kép bị vỡ,
    tách ô bằng split(";") nên ô có dấu chấm phẩy trong nháy kép bị vỡ;
  - cộng cả dòng "Tổng cộng" (ô ngày trống), mặc định cột doanh thu là cột cuối, trả float thay vì Decimal.
"""
import importlib.util
import os
import sys
import tempfile
import unicodedata
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

BOM = "\ufeff"
NBSP = " "

# File như Excel xuất: BOM, \r\n, cột ngày ở đầu, cột doanh thu ở cuối, có dòng Tổng cộng và dòng rỗng.
FILE_A = BOM + "\r\n".join([
    "Ngày;Khách hàng;Ghi chú;Doanh thu (đồng)",
    '05/03/2024;"Cửa hàng Hòa; Bình";Đợt 1;1.234.567,5',
    '5/3/2024 14:30;Anh Nam;"Giao\r\ntận nơi";2.000.000',
    "31/03/2024;Chị Lan;;(250.000)",
    "20/03/2024;Ông Bảy;;",
    '01/04/2024;"Quán ""Sài Gòn""";;1.500.000 ₫',
    f"03/04/2024;Bà Tư;;750.000{NBSP}đ",
    "10/04/2024;Chú Tám;;1500",
    "11/04/2024;Cô Chín;;1.500",
    "12/04/2024;Cậu Mười;;1,5",
    "02/06/2024;Dì Hai;;2.000 VND",
    "03/06/2024;Dì Ba;;3.000 vnđ",
    "12/12/2023;Ông Sáu;;-100.000,25",
    "15/12/2023;Bà Năm;;0,5",
    "",
    ";;;",
    ";Tổng cộng;;9.999.999",
]) + "\r\n"
WANT_A = {
    "2024-03": D("2984567.5"),     # 1.234.567,5 + 2.000.000 - 250.000
    "2024-04": D("2253001.5"),     # 1.500.000 + 750.000 + 1.500 + 1.500 + 1,5
    "2024-06": D("5000"),
    "2023-12": D("-99999.75"),     # -100.000,25 + 0,5
}

# File không BOM, xuống dòng \n, cột doanh thu đứng trước, tiêu đề viết thường / chữ tách dấu.
FILE_B = "\n".join([
    "doanh thu;" + unicodedata.normalize("NFD", "NGÀY") + ";Mã",
    "1.000.000;15/01/2025;A",
    "2.000.000;31/01/2025;B",
    "3.000.000;1/2/2025;C",
    "0,1;20/02/2025;D",
    "0,2;21/02/2025;E",
]) + "\n"
WANT_B = {"2025-01": D("3000000"), "2025-02": D("3000000.3")}

FILE_C = BOM + "Ngày;Doanh thu\r\n"
WANT_C = {}
FILE_D = "Ngày;Doanh thu\r\n29/02/2024;1.000"   # ngày nhuận, không có xuống dòng cuối file
WANT_D = {"2024-02": D("1000")}

CASES = [("file Excel đầy đủ", FILE_A, WANT_A), ("file không BOM, đảo cột, tiêu đề NFD", FILE_B, WANT_B),
         ("chỉ có tiêu đề", FILE_C, WANT_C), ("29/02 năm nhuận, không xuống dòng cuối", FILE_D, WANT_D)]
BAD = [
    ("thiếu cột Doanh thu", "Ngày;Khách hàng\r\n05/03/2024;An\r\n"),
    ("thiếu cột Ngày", "Khách hàng;Doanh thu\r\nAn;1.000\r\n"),
    ("ngày không có thật 31/04/2024", "Ngày;Doanh thu\r\n31/04/2024;1.000\r\n"),
    ("ngày dạng yyyy-mm-dd", "Ngày;Doanh thu\r\n2024-03-05;1.000\r\n"),
    ("số tiền không đọc được", "Ngày;Doanh thu\r\n05/03/2024;abc\r\n"),
]


def main():
    path = vncheck.app_dir() / "bao_cao" / "doc_csv.py"
    spec = importlib.util.spec_from_file_location("doc_csv_check", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        f = mod.tong_doanh_thu_theo_thang
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được bao_cao/doc_csv.py: {exc!r}"])
    errs = []
    with tempfile.TemporaryDirectory(prefix="vi-csv-") as tmp:
        os.chdir(tmp)

        def ghi(ten, noi_dung):
            p = os.path.join(tmp, ten)
            with open(p, "wb") as fh:
                fh.write(noi_dung.encode("utf-8"))
            return p

        for i, (note, noi_dung, want) in enumerate(CASES):
            try:
                got = f(ghi(f"c{i}.csv", noi_dung))
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{note}: lỗi {exc!r}")
                continue
            if not isinstance(got, dict) or set(got) != set(want):
                errs.append(f"{note}: các tháng được {sorted(got) if isinstance(got, dict) else got!r}, "
                            f"đúng là {sorted(want)}")
                continue
            for k, v in want.items():
                if type(got[k]) is not D or got[k] != v:
                    errs.append(f"{note}: tháng {k} được {got[k]!r}, đúng là Decimal('{v}')")
        for i, (note, noi_dung) in enumerate(BAD):
            try:
                f(ghi(f"b{i}.csv", noi_dung))
                errs.append(f"{note}: phải báo ValueError")
            except ValueError:
                pass
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{note}: phải báo ValueError, đang báo {exc!r}")
        try:
            f(duong_dan=ghi("kw.csv", FILE_C))
        except TypeError:
            errs.append("đã đổi tên tham số của hàm")
        except Exception:  # noqa: BLE001
            pass
        os.chdir("/")
    vncheck.finish(errs)


main()
