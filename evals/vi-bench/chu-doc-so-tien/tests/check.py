"""Chấm chu-doc-so-tien: so với cách đọc viết tay theo luật trong đề.

Các cách làm sai hay gặp mà bài chấm này bắt:
  - đọc "hai mươi một", "hai mươi bốn", "hai mươi năm" (quên mốt, tư, lăm), hay dùng mốt/tư sau "mười" (mười mốt, mười tư);
  - bỏ "không trăm" ở nhóm nghìn, triệu giữa số (1.250.005, 1.001.000), hay thêm "linh" vào nhóm đứng đầu;
  - dùng "lẻ" thay "linh", "ngàn" thay "nghìn", "tỉ" thay "tỷ";
  - đọc đơn vị của nhóm toàn số 0 ("một triệu không nghìn");
  - chỉ biết bốn nhóm (đến trăm tỷ), sai ở "nghìn tỷ" và ở phần tỷ có nhóm "không trăm";
  - chuỗi có dấu chấm ngăn nghìn, số 0, báo lỗi với số âm và số quá lớn.
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

# Đáp án viết tay theo luật trong đề (không tính bằng code), soát lại ngày 08/11/2026.
# Nhóm đầu bỏ hàng trăm 0; nhóm sau đọc đủ "không trăm"; "linh" chỉ khi hàng trăm được đọc; phần tỷ đọc như số thường.
CASES = [
    (0, "Không đồng"),
    (1, "Một đồng"),
    (4, "Bốn đồng"),
    (5, "Năm đồng"),
    (10, "Mười đồng"),
    (11, "Mười một đồng"),
    (14, "Mười bốn đồng"),
    (15, "Mười lăm đồng"),
    (20, "Hai mươi đồng"),
    (21, "Hai mươi mốt đồng"),
    (24, "Hai mươi tư đồng"),
    (25, "Hai mươi lăm đồng"),
    (34, "Ba mươi tư đồng"),
    (91, "Chín mươi mốt đồng"),
    (95, "Chín mươi lăm đồng"),
    (100, "Một trăm đồng"),
    (101, "Một trăm linh một đồng"),
    (104, "Một trăm linh bốn đồng"),
    (105, "Một trăm linh năm đồng"),
    (110, "Một trăm mười đồng"),
    (111, "Một trăm mười một đồng"),
    (114, "Một trăm mười bốn đồng"),
    (115, "Một trăm mười lăm đồng"),
    (121, "Một trăm hai mươi mốt đồng"),
    (224, "Hai trăm hai mươi tư đồng"),
    (305, "Ba trăm linh năm đồng"),
    (999, "Chín trăm chín mươi chín đồng"),
    (1000, "Một nghìn đồng"),
    (1001, "Một nghìn không trăm linh một đồng"),
    (1010, "Một nghìn không trăm mười đồng"),
    (1015, "Một nghìn không trăm mười lăm đồng"),
    (1100, "Một nghìn một trăm đồng"),
    (2024, "Hai nghìn không trăm hai mươi tư đồng"),
    (10000, "Mười nghìn đồng"),
    (10005, "Mười nghìn không trăm linh năm đồng"),
    (15000, "Mười lăm nghìn đồng"),
    (21000, "Hai mươi mốt nghìn đồng"),
    (24500, "Hai mươi tư nghìn năm trăm đồng"),
    (105000, "Một trăm linh năm nghìn đồng"),
    (250000, "Hai trăm năm mươi nghìn đồng"),
    (1000000, "Một triệu đồng"),
    (1250005, "Một triệu hai trăm năm mươi nghìn không trăm linh năm đồng"),
    (1005000, "Một triệu không trăm linh năm nghìn đồng"),
    (1000001, "Một triệu không trăm linh một đồng"),
    (1001000, "Một triệu không trăm linh một nghìn đồng"),
    (1010000, "Một triệu không trăm mười nghìn đồng"),
    (4000004, "Bốn triệu không trăm linh bốn đồng"),
    (12345678, "Mười hai triệu ba trăm bốn mươi lăm nghìn sáu trăm bảy mươi tám đồng"),
    (21021021, "Hai mươi mốt triệu không trăm hai mươi mốt nghìn không trăm hai mươi mốt đồng"),
    (100000000, "Một trăm triệu đồng"),
    (1000000000, "Một tỷ đồng"),
    (1000000005, "Một tỷ không trăm linh năm đồng"),
    (1000005000, "Một tỷ không trăm linh năm nghìn đồng"),
    (1500000000, "Một tỷ năm trăm triệu đồng"),
    (2004000014, "Hai tỷ không trăm linh bốn triệu không trăm mười bốn đồng"),
    (45000000000, "Bốn mươi lăm tỷ đồng"),
    (101101101101, "Một trăm linh một tỷ một trăm linh một triệu một trăm linh một nghìn một trăm linh một đồng"),
    (10 ** 12, "Một nghìn tỷ đồng"),
    (1005 * 10 ** 9, "Một nghìn không trăm linh năm tỷ đồng"),
    (1021 * 10 ** 9, "Một nghìn không trăm hai mươi mốt tỷ đồng"),
    (10 ** 12 + 5, "Một nghìn tỷ không trăm linh năm đồng"),
    (12345 * 10 ** 9, "Mười hai nghìn ba trăm bốn mươi lăm tỷ đồng"),
    (10 ** 14, "Một trăm nghìn tỷ đồng"),
    (250000 * 10 ** 9 + 1500000, "Hai trăm năm mươi nghìn tỷ không trăm linh một triệu năm trăm nghìn đồng"),
    (10 ** 15 - 1, "Chín trăm chín mươi chín nghìn chín trăm chín mươi chín tỷ chín trăm chín mươi chín triệu "
                   "chín trăm chín mươi chín nghìn chín trăm chín mươi chín đồng"),
    ("1.250.005", "Một triệu hai trăm năm mươi nghìn không trăm linh năm đồng"),
    ("21.015", "Hai mươi mốt nghìn không trăm mười lăm đồng"),
    ("1000", "Một nghìn đồng"),
    ("0", "Không đồng"),
    ("45", "Bốn mươi lăm đồng"),
    ("1.005.000.000.000", "Một nghìn không trăm linh năm tỷ đồng"),
]
LOI = [-1, 10 ** 15, "abc", "12a", "-5", ""]


def main():
    spec = importlib.util.spec_from_file_location("doc_so_check", vncheck.app_dir() / "doc_so.py")
    mod = importlib.util.module_from_spec(spec)
    errs = []
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được doc_so.py: {exc!r}"])
    for vao, dung in CASES:
        try:
            got = mod.doc_so_tien(vao)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"doc_so_tien({vao!r}) lỗi {exc!r}")
            continue
        if got != unicodedata.normalize("NFC", dung):
            errs.append(f"doc_so_tien({vao!r}): được {got!r}, đúng là {dung!r}")
    for vao in LOI:
        try:
            got = mod.doc_so_tien(vao)
            errs.append(f"doc_so_tien({vao!r}) phải ném ValueError, được {got!r}")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            errs.append(f"doc_so_tien({vao!r}) phải ném ValueError, được {exc!r}")
    vncheck.finish(errs[:12])


main()
