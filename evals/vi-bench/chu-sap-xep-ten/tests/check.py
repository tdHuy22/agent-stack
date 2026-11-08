"""Chấm chu-sap-xep-ten: so với thứ tự tính tay theo luật trong đề."""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


# Thứ tự đúng, xếp tay theo luật trong đề và soát lại ngày 08/11/2026 (không tính bằng code, để lời giải và bài chấm không
# chung một lỗi). Ví dụ: "Anh" < "Ánh" (cùng chữ cái, thanh ngang trước sắc) < "Anhh" (chữ ngắn là phần đầu của chữ dài);
# "Nga" < "Ngà" < "Ngân" (a < â); "Tâm" < "Thư" (â < h); trùng tên "Dũng" thì "Hồ" < "Lê". Có chuỗi NFD, có khoảng trắng thừa.
WANT = [
    'Đỗ Thị Anh',
    'Phạm Anh',
    nfd('Bùi Ánh'),
    'Nguyễn Thị Ánh',
    'Lê Văn Ảnh',
    'Vũ Anhh',
    'Hoàng Ăn',
    'Trần Ân',
    'Đinh Ấn',
    'Trần Văn Bình',
    'Ngô Bính',
    'Lý Văn Cường',
    'Mai Dung',
    'Hồ Dũng',
    'Lê Dũng',
    'Nguyễn Dương',
    'Lê Minh Đức',
    '  Tạ Đức ',
    'Kiều Giang',
    'Trịnh Hà',
    'Châu Hạ',
    'Phan Khang',
    'Quách Long',
    'Vương Lộc',
    'Đàm Minh',
    'Phùng Minh',
    'Hứa Nga',
    'Ông Ngà',
    'Lâm Ngân',
    'Tô Oanh',
    'Lã Ơn',
    'Võ Phúc',
    'Tăng Quang',
    'Âu Sơn',
    'Đoàn Tâm',
    'Dương Thư',
    'Lục Uyên',
    'Hà Ưng',
    'Viên Vy',
    'Mạc Yến',
]
INPUT = [WANT[i] for i in (17, 3, 25, 0, 39, 11, 30, 7, 22, 34, 1, 14, 28, 9, 36, 5, 19, 32, 2, 26, 13, 38, 6, 21, 33,
                           10, 16, 29, 4, 37, 24, 12, 35, 8, 20, 31, 18, 27, 15, 23)]


def main():
    assert sorted(INPUT) == sorted(WANT) and len(set(map(id, INPUT))) == len(INPUT)
    spec = importlib.util.spec_from_file_location("danh_sach_check", vncheck.app_dir() / "danh_sach.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        got = mod.sap_xep(list(INPUT))
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"sap_xep lỗi: {exc!r}"])
    errs = []
    if got != WANT:
        if sorted(got) != sorted(WANT):
            errs.append("kết quả không giữ nguyên các chuỗi đầu vào (đã sửa, thêm hay bớt chuỗi)")
        else:
            bad = next(i for i, (a, b) in enumerate(zip(got, WANT)) if a != b)
            errs.append(f"sai thứ tự từ vị trí {bad}: được {got[bad:bad + 3]!r}, đúng là {WANT[bad:bad + 3]!r}")
    # hai chuỗi giống hệt nhau theo luật: giữ thứ tự đầu vào
    twin_a, twin_b = "Trần Ân", nfd("trần ân")
    try:
        got2 = mod.sap_xep([twin_b, "Lê Ba", twin_a])
        if got2 != [twin_b, twin_a, "Lê Ba"]:
            errs.append(f"hai họ tên giống nhau phải giữ thứ tự đầu vào: được {got2!r}")
    except Exception as exc:  # noqa: BLE001
        errs.append(f"sap_xep lỗi ở ca trùng tên: {exc!r}")
    vncheck.finish(errs)


main()
