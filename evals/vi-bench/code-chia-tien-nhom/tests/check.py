"""Chấm code-chia-tien-nhom: gọi chia_tien với các nhóm tính tay theo luật trong đề (danh sách chuyển khoản đầy đủ).

Các cách làm sai đã thử, đều phải trượt:
  - round() của Python (nửa về số chẵn): 1.001.000 / 2 = 500.500 phải lên 501.000, round cho 500.000;
  - số thực thay vì số nguyên; để phần lẻ cho người đầu danh sách hay người cuối thay vì người trả nhiều nhất;
  - không cộng dồn các khoản của cùng một người (ghi đè), hoặc chọn người trả nhiều nhất theo từng khoản lẻ;
  - coi tên khác chữ hoa thường, khoảng trắng, NFD, "Hòa"/"Hoà", "Thủy"/"Thuỷ" là người khác nhau;
  - bỏ dấu khi so tên nên gộp nhầm Lan với Lân;
  - ghép người nợ với người nhận theo thứ tự danh sách thay vì lớn nhất ghép lớn nhất; hòa không theo thứ tự đã cho;
  - ghi tên người trong kết quả không phải NFC, hay không dùng cách viết của lần đầu trong thanh_vien;
  - không báo ValueError, đổi tên tham số.
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


# (ghi chú, khoan_tra, thanh_vien, kết quả đúng). Kết quả ghi tay theo từng bước ghép trong đề.
CASES = [
    ("An trả 1.000.000, Bình trả 300.000, 4 người: mỗi phần 325.000",
     [("An", 1_000_000), ("Bình", 300_000)], ["An", "Bình", "Chi", "Dũng"],
     [("Chi", "An", 325_000), ("Dũng", "An", 325_000), ("Bình", "An", 25_000)]),
    ("1.000.000 chia 3 = 333.333 → 333.000; Minh gánh phần lẻ nên phần của Minh là 334.000",
     [("Minh", 1_000_000)], ["Hà", "Minh", "Nam"],
     [("Hà", "Minh", 333_000), ("Nam", "Minh", 333_000)]),
    ("đúng giữa hai bội của nghìn: 500.500 lên 501.000, Lan gánh phần 500.000",
     [("Lan", 1_001_000)], ["Lan", "Mai"], [("Mai", "Lan", 501_000)]),
    ("hai người trả bằng nhau: người đứng trước (B) gánh phần lẻ; A chuyển cho C (167.000) rồi cho B (166.000)",
     [("B", 500_000), ("C", 500_000)], ["A", "B", "C"], [("A", "C", 167_000), ("A", "B", 166_000)]),
    ("tên viết khác nhau, Lan khác Lân, Hòa = Hoà, Thủy = Thuỷ",
     [("nguyễn  văn an", 2_000_000), ("Lê Thị Hòa", 600_000), ("TRẦN THUỶ", 400_000), ("LÂN", 150_000)],
     ["Nguyễn Văn An", "  lê thị HOÀ ", nfd("Trần Thủy"), "Lan", "Lân"],
     [("Lan", "Nguyễn Văn An", 630_000), ("Lân", "Nguyễn Văn An", 480_000),
      ("Trần Thủy", "Nguyễn Văn An", 230_000), ("lê thị HOÀ", "Nguyễn Văn An", 30_000)]),
    ("sáu người, Cúc trả hai lần (cộng dồn 1.345.678), phần lẻ về Cúc: 2.345.678 / 6 → 391.000",
     [("Cúc", 1_000_000), ("Giang", 1_000_000), ("Cúc", 345_678)], ["Anh", "Bảo", "Cúc", "Dương", "Giang", "Hạnh"],
     [("Anh", "Cúc", 391_000), ("Bảo", "Giang", 391_000), ("Dương", "Cúc", 391_000), ("Hạnh", "Giang", 218_000),
      ("Hạnh", "Cúc", 173_000)]),
    ("tên trùng trong thanh_vien chỉ tính một người, hiện cách viết đầu tiên",
     [("AN", 100_000)], ["An", "an ", "Bình"], [("Bình", "An", 50_000)]),
    ("không ai trả", [], ["An", "Bình"], []),
    ("một người", [("An", 500_000)], ["An"], []),
    ("đã cân bằng", [("An", 600_000), ("Bình", 600_000)], ["An", "Bình"], []),
]
BAD = [
    ("không có thành viên", [("An", 1000)], []),
    ("người trả không thuộc nhóm", [("Zed", 1000)], ["An", "Bình"]),
    ("Lan không phải Lân", [("Lan", 1000)], ["Lân", "Bình"]),
    ("số tiền âm", [("An", -1000)], ["An", "Bình"]),
]


def main():
    path = vncheck.app_dir() / "nhom" / "chia_tien.py"
    spec = importlib.util.spec_from_file_location("chia_tien_check", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        f = mod.chia_tien
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được nhom/chia_tien.py: {exc!r}"])
    errs = []
    for note, tra, tv, want in CASES:
        try:
            got = f(tra, tv)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{note}: lỗi {exc!r}")
            continue
        try:
            got_t = [tuple(x) for x in got]
            ok = got_t == want and all(type(x[2]) is int for x in got_t)
        except TypeError:
            ok = False
        if not ok:
            errs.append(f"{note}: được {got!r}, đúng là {want!r}")
    for note, tra, tv in BAD:
        try:
            f(tra, tv)
            errs.append(f"{note}: phải báo ValueError")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{note}: phải báo ValueError, đang báo {exc!r}")
    try:
        f(khoan_tra=[("An", 300_000)], thanh_vien=["An", "Bình", "Chi"])
    except TypeError:
        errs.append("đã đổi tên tham số của hàm")
    except Exception:  # noqa: BLE001
        pass
    vncheck.finish(errs)


main()
