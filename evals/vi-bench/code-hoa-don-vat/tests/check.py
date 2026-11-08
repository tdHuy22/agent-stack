"""Chấm code-hoa-don-vat: gọi tinh_hoa_don với các hóa đơn tính tay theo luật trong đề.

Các cách làm sai đã thử, đều phải trượt:
  - so khớp tên nhóm nguyên văn (không nhận " VIỄN THÔNG ", chữ tách dấu, "hoá chất");
  - tính VAT trên cả hóa đơn (hay làm tròn tổng) thay vì làm tròn từng dòng;
  - round() của Python (nửa về số chẵn) hay số thực: 0,29 × 1.450 ra 420,4999… nên bị làm tròn xuống 420;
  - làm tròn tiền sau giảm giá một lần thay vì làm tròn tiền giảm rồi trừ;
  - coi chuỗi "1.250" là 1,25, hay không đọc được chuỗi số kiểu Việt Nam; không báo ValueError.
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


def dong(nhom, don_gia, so_luong, giam_gia=None, ten="Hàng"):
    d = {"ten": ten, "nhom": nhom, "don_gia": don_gia, "so_luong": so_luong}
    if giam_gia is not None:
        d["giam_gia"] = giam_gia
    return d


# (ghi chú, danh sách dòng, tien_hang, vat, tong). Tính tay theo đề, soát lại bằng chương trình riêng dùng phân số
# ngày 08/11/2026.
CASES = [
    ("một dòng 8%: 19.990 × 3 = 59.970, VAT 4.797,6 lên 4.798",
     [dong("Thực phẩm", 19990, 3)], 59970, 4798, 64768),
    ("VAT 10% đúng nửa đồng ở từng dòng: 1.234,5 → 1.235 và 2.222,5 → 2.223 (cộng lại rồi mới tròn sẽ ra 3.457)",
     [dong("Viễn thông", 12345, 1), dong("Hoá chất", 22225, 1)], 34570, 3458, 38028),
    ("ba dòng 1.010đ, VAT 80,8 → 81 mỗi dòng (tròn trên tổng sẽ ra 242)",
     [dong("Thực phẩm", 1010, 1)] * 3, 3030, 243, 3273),
    ("tên nhóm lộn xộn nhưng cùng nhóm 10%; 'Điện tử' là 8%; 'khoáng' không bị sửa",
     [dong(" VIỄN THÔNG ", 10000, 1), dong(nfd("Tài chính"), 10000, 1), dong("bất  động  sản", 10000, 1),
      dong("HÓA CHẤT", 10000, 1), dong("Khai Khoáng", 10000, 1), dong("Điện tử", 10000, 1)], 60000, 5800, 65800),
    ("giảm 12,5%: 500.000 → 437.500, VAT 8% đúng 35.000",
     [dong("Điện tử", 250000, 2, 12.5)], 437500, 35000, 472500),
    ("giảm giá đúng nửa đồng: 10.010 × 5% = 500,5 lên 501, còn 9.509 (không phải 9.510)",
     [dong("Hóa chất", 10010, 1, 5)], 9509, 951, 10460),
    ("0,29 × 1.450 = 420,5 lên 421 (số thực cho 420,49999…)",
     [dong("Thực phẩm", 1450, 0.29)], 421, 34, 455),
    ("0,5 × 25.001 = 12.500,5 lên 12.501 (không phải 12.500)",
     [dong("Thực phẩm", 25001, 0.5)], 12501, 1000, 13501),
    ("số lượng là chuỗi kiểu Việt Nam: '2,5', '1.250' (một nghìn hai trăm năm mươi), '0,75'",
     [dong("Thực phẩm", 19990, "2,5"), dong("Gạch", 40, "1.250"), dong("Thực phẩm", 12000, "0,75")], 108975, 8718, 117693),
    ("hóa đơn nhiều dòng trộn đủ loại",
     [dong("Viễn thông", 99000, 3, 10), dong("Điện tử", 45500, 2.5, 0), dong(nfd("Tài chính"), 1234567, 1),
      dong("hoá chất", 86500, 0.35, 15), dong("Thực phẩm", 125000, "1,35"), dong("Khai khoáng", 333, 777)],
     2068842, 201234, 2270076),
    ("danh sách rỗng", [], 0, 0, 0),
]
BAD = [
    ("đơn giá âm", [dong("Thực phẩm", -1, 1)]),
    ("số lượng 0", [dong("Thực phẩm", 1000, 0)]),
    ("số lượng âm dạng chuỗi", [dong("Thực phẩm", 1000, "-1,5")]),
    ("giảm giá trên 100", [dong("Thực phẩm", 1000, 1, 101)]),
    ("giảm giá âm", [dong("Thực phẩm", 1000, 1, -5)]),
]


def main():
    path = vncheck.app_dir() / "hoa_don" / "tinh_hoa_don.py"
    spec = importlib.util.spec_from_file_location("hoa_don_check", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        f = mod.tinh_hoa_don
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được hoa_don/tinh_hoa_don.py: {exc!r}"])
    errs = []
    for note, lines, th, vat, tong in CASES:
        try:
            got = f(lines)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{note}: lỗi {exc!r}")
            continue
        want = {"tien_hang": th, "vat": vat, "tong": tong}
        try:
            ok = all(got[k] == v and type(got[k]) is int for k, v in want.items())
        except (KeyError, TypeError):
            ok = False
        if not ok:
            errs.append(f"{note}: được {got!r}, đúng là {want} (ba số nguyên)")
    for note, lines in BAD:
        try:
            f(lines)
            errs.append(f"{note}: phải báo ValueError")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{note}: phải báo ValueError, đang báo {exc!r}")
    try:
        if not hasattr(mod, "thue_suat") or mod.thue_suat("Viễn thông") != 0.1 or mod.thue_suat("Thực phẩm") != 0.08:
            errs.append("hàm thue_suat phải còn và trả 0.1 cho 'Viễn thông', 0.08 cho 'Thực phẩm'")
        f(dong_hang=[dong("Thực phẩm", 1000, 1)])
    except TypeError:
        errs.append("đã đổi tên tham số của hàm")
    except Exception as exc:  # noqa: BLE001
        errs.append(f"gọi theo tên tham số lỗi {exc!r}")
    vncheck.finish(errs)


main()
