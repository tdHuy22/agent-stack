"""Chấm chu-so-tien-viet-tat: so với số đồng tính tay theo luật trong đề.

Các cách làm sai hay gặp mà bài chấm này bắt:
  - dùng số thực (float) nên "4,1 triệu" ra 4099999, "2,3 lít" ra 229999 khi cắt về int;
  - dấu chấm hiểu là dấu thập phân ("1.250k" thành 1,25k = 1250 thay vì 1.250.000);
  - gặp "tr" trước "triệu" nên "2 triệu" còn dư "iệu"; không biết "lít", "củ", "rưỡi", "tỉ", "ngàn", "vnđ";
  - "1 tỷ 2" bị hiểu là 1 tỷ + 2 đồng (hay 2 triệu), "1 tỷ 2 triệu" bị hiểu là 1,2 tỷ; "1tr50" hiểu thành 1 triệu 50 nghìn;
  - dãy chữ số lẻ đọc như số nguyên ("2 triệu 500" ra 2.000.500); "rưỡi" cộng nửa đồng thay vì nửa đơn vị;
  - không chịu chữ HOA hay dấu tách rời (NFD); không báo ValueError với "2.5 triệu", số lẻ đồng, chuỗi vô nghĩa.
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


# (chuỗi vào, số đồng đúng). Tính tay theo luật trong đề, soát lại ngày 08/11/2026.
CASES = [
    ("500k", 500000),
    ("500K", 500000),
    ("500 k", 500000),
    ("1k5", 1500),
    ("1tr5", 1500000),
    ("1TR5", 1500000),
    ("1Tr5", 1500000),
    ("1tr 5", 1500000),
    ("2tr35", 2350000),
    ("1tr05", 1050000),
    ("1tr50", 1500000),
    ("12tr345", 12345000),
    ("8tr2", 8200000),
    ("2,5 triệu", 2500000),
    ("2,5tr", 2500000),
    ("0,5 triệu", 500000),
    ("4,1 triệu", 4100000),
    ("8,11tr", 8110000),
    ("1 triệu", 1000000),
    ("2 TRIỆU", 2000000),
    (nfd("2 triệu rưỡi"), 2500000),
    (nfd("3 lít"), 300000),
    ("1 tỷ 2", 1200000000),
    ("1 tỷ 2 triệu", 1002000000),
    ("1 tỷ 200 triệu", 1200000000),
    ("1 tỷ 250", 1250000000),
    ("4 tỷ 1", 4100000000),
    ("2,11 tỷ", 2110000000),
    ("1 tỉ", 1000000000),
    ("1,5 tỉ", 1500000000),
    ("2 tỷ rưỡi", 2500000000),
    ("3 lít", 300000),
    ("2,5 lít", 250000),
    ("2,3 lít", 230000),
    ("0,29 lít", 29000),
    ("1,15 lít", 115000),
    ("1 lít 5", 150000),
    ("3 lít rưỡi", 350000),
    ("2 triệu rưỡi", 2500000),
    ("1 củ", 1000000),
    ("2 củ rưỡi", 2500000),
    ("2 triệu 500", 2500000),
    ("1 triệu 5", 1500000),
    ("1.250.000", 1250000),
    ("1.250.000đ", 1250000),
    ("200.000 đồng", 200000),
    ("1.000.000 VNĐ", 1000000),
    ("300000vnd", 300000),
    ("50000", 50000),
    ("0", 0),
    ("100đ", 100),
    ("1.250k", 1250000),
    ("1.250,5k", 1250500),
    ("1 nghìn", 1000),
    ("5 ngàn", 5000),
    ("1 ngàn rưỡi", 1500),
    ("1k rưỡi", 1500),
    ("1 triệu 200 nghìn", 1200000),
    ("1tr 200k", 1200000),
    ("500k 1 triệu", 1500000),
    ("2 tỷ 500 triệu 30 nghìn", 2500030000),
    ("5 triệu 3 nghìn 2", 5003200),
    ("  1  tỷ   2  ", 1200000000),
    ("1 lít 55 đồng", 100055),
]
LOI = [
    "2.5 triệu",
    "1.25.000",
    "1.2500",
    "1,2,3 triệu",
    "abc",
    "",
    "   ",
    "triệu",
    "k",
    "rưỡi",
    "1 tỷ 2,5",
    "1,5 triệu rưỡi",
    "1tr5 rưỡi",
    "1 triệu rưỡi 5",
    "2 5",
    "1 tỷ 2 3",
    "1,2345k",
    "1,5 đồng",
    "2,0001 triệu rưỡi",
    "5 trăm",
    "500kg",
    "-500k",
    "1,5,",
    "k500",
    "1 triệu 2,5",
    "1,5 triệu 2",
    "2,5 tỷ 3",
    "1 triệu 200.000",
]


def main():
    spec = importlib.util.spec_from_file_location("tien_check", vncheck.app_dir() / "tien.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được tien.py: {exc!r}"])
    errs = []
    for vao, dung in CASES:
        try:
            got = mod.doc_tien(vao)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"doc_tien({vao!r}) lỗi {exc!r}, đúng là {dung}")
            continue
        if got != dung or not isinstance(got, int) or isinstance(got, bool):
            errs.append(f"doc_tien({vao!r}): được {got!r}, đúng là {dung}")
    for vao in LOI:
        try:
            got = mod.doc_tien(vao)
            errs.append(f"doc_tien({vao!r}) phải ném ValueError, được {got!r}")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            errs.append(f"doc_tien({vao!r}) phải ném ValueError, được {exc!r}")
    vncheck.finish(errs[:12])


main()
