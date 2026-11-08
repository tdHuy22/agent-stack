"""Chấm chu-tim-khong-dau: so với danh sách kết quả xếp tay theo luật trong đề.

Các cách làm sai hay gặp mà bài chấm này bắt:
  - bỏ dấu cả hai phía bằng unicodedata nhưng quên "đ" ("dung" không ra "Đặng Đức Dung", "đung"/"dung" lẫn lộn);
  - bỏ dấu cả hai phía nên truy vấn có dấu vẫn khớp tên khác dấu ("dũng" ra cả "Dung", "ân" ra cả "An", "Anh");
  - tìm chuỗi con (in) thay vì phần đầu của chữ ("oang" ra "Hoàng", "an" ra "Hoàng"), hay chỉ khớp phần đầu cả tên;
  - không chuẩn hóa NFC (tên hay truy vấn gõ dấu tách rời không khớp), phân biệt hoa thường;
  - chỉ khớp một từ khóa thay vì mọi từ khóa; bắt hai từ khóa phải khớp hai chữ khác nhau ("an an");
  - xếp hạng sai: không phân biệt điểm 3/2/1, không đặt tên ít chữ hơn lên trước, đảo thứ tự ban đầu khi bằng điểm;
  - trả về chuỗi đã chuẩn hóa thay vì chuỗi gốc, sửa danh bạ đầu vào, bỏ tên trùng.
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


NGHIA = nfd("Lê Hữu Nghĩa")
DB = [
    "Nguyễn Văn An",        # 0
    "Nguyên Văn Ân",        # 1
    "Lê Thị Ân",            # 2
    "Lê Anh",               # 3
    "Lê An",                # 4
    "Hoàng Văn Dũng",       # 5
    "Đặng Đức Dung",        # 6
    "Phạm Dũng",            # 7
    "Đỗ Thị Đào",           # 8
    "Dương Văn Đạo",        # 9
    "Trần Thị Bích Hạnh",   # 10
    "Tạ Thị Hạnh",          # 11
    "Hạnh Nguyễn",          # 12
    "Ngô Thị Hanh",         # 13
    "Võ Văn An",            # 14
    "An",                   # 15
    "Ân",                   # 16
    "Lê Văn Ánh",           # 17
    NGHIA,                  # 18 (dấu tách rời)
    "Lê An",                # 19 (trùng tên 4)
]

AN = ["An", "Lê An", "Lê An", "Nguyễn Văn An", "Võ Văn An", "Ân", "Nguyên Văn Ân", "Lê Thị Ân", "Lê Anh", "Lê Văn Ánh"]
DUNG = ["Phạm Dũng", "Hoàng Văn Dũng"]

# (truy vấn, kết quả đúng). Xếp tay theo luật trong đề (điểm 3/2/1, rồi ít chữ hơn, rồi thứ tự gốc), soát lại ngày 08/11/2026.
CASES = [
    ("an", AN),
    ("AN", AN),
    ("  An  ", AN),
    ("an an", AN),
    ("ân", ["Ân", "Nguyên Văn Ân", "Lê Thị Ân"]),
    ("Ân", ["Ân", "Nguyên Văn Ân", "Lê Thị Ân"]),
    (nfd("ân"), ["Ân", "Nguyên Văn Ân", "Lê Thị Ân"]),
    ("anh", ["Lê Anh", "Lê Văn Ánh"]),
    ("ánh", ["Lê Văn Ánh"]),
    ("dung", ["Đặng Đức Dung", "Phạm Dũng", "Hoàng Văn Dũng"]),
    ("DUNG", ["Đặng Đức Dung", "Phạm Dũng", "Hoàng Văn Dũng"]),
    ("dũng", DUNG),
    (nfd("dũng"), DUNG),
    (nfd("DŨNG"), DUNG),
    ("đung", []),
    ("đức", ["Đặng Đức Dung"]),
    ("duc", ["Đặng Đức Dung"]),
    ("dao", ["Đỗ Thị Đào", "Dương Văn Đạo"]),
    ("đào", ["Đỗ Thị Đào"]),
    ("do", ["Đỗ Thị Đào"]),
    ("đo", ["Đỗ Thị Đào"]),
    ("d", ["Phạm Dũng", "Hoàng Văn Dũng", "Đặng Đức Dung", "Đỗ Thị Đào", "Dương Văn Đạo"]),
    ("đ", ["Đặng Đức Dung", "Đỗ Thị Đào", "Dương Văn Đạo"]),
    ("le an", ["Lê An", "Lê An", "Lê Thị Ân", "Lê Anh", "Lê Văn Ánh"]),
    ("lê an", ["Lê An", "Lê An", "Lê Thị Ân", "Lê Anh", "Lê Văn Ánh"]),
    ("lé an", []),
    ("nguyễn an", ["Nguyễn Văn An"]),
    ("nguyen an", ["Nguyễn Văn An", "Nguyên Văn Ân"]),
    ("nguyen", ["Hạnh Nguyễn", "Nguyễn Văn An", "Nguyên Văn Ân"]),
    ("nguyên", ["Nguyên Văn Ân"]),
    ("hanh", ["Ngô Thị Hanh", "Hạnh Nguyễn", "Tạ Thị Hạnh", "Trần Thị Bích Hạnh"]),
    ("hạnh", ["Hạnh Nguyễn", "Tạ Thị Hạnh", "Trần Thị Bích Hạnh"]),
    ("hành", []),
    ("thi hanh", ["Ngô Thị Hanh", "Tạ Thị Hạnh", "Trần Thị Bích Hạnh"]),
    ("hoang", ["Hoàng Văn Dũng"]),
    ("oang", []),
    ("ho", ["Hoàng Văn Dũng"]),
    ("nghia", [NGHIA]),
    ("nghĩa", [NGHIA]),
    ("huu", [NGHIA]),
    ("hữu", [NGHIA]),
    ("zzz", []),
    ("", []),
    ("   ", []),
]


def main():
    spec = importlib.util.spec_from_file_location("danh_ba_check", vncheck.app_dir() / "danh_ba.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được danh_ba.py: {exc!r}"])
    errs = []
    goc = list(DB)
    for vao, dung in CASES:
        try:
            got = mod.tim(list(DB), vao)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"tim(danh_ba, {vao!r}) lỗi {exc!r}")
            continue
        if not isinstance(got, list) or got != dung:
            errs.append(f"tim(danh_ba, {vao!r}): được {got!r}, đúng là {dung!r}")
    ban = list(DB)
    try:
        mod.tim(ban, "an")
        if ban != goc:
            errs.append("tim đã sửa danh_ba đầu vào")
    except Exception as exc:  # noqa: BLE001
        errs.append(f"tim lỗi: {exc!r}")
    vncheck.finish(errs[:12])


main()
