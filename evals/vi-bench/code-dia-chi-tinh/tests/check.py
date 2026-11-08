"""Chấm code-dia-chi-tinh: thay bảng bí danh bằng bảng riêng của bài chấm rồi gọi chuan_hoa_tinh với các địa chỉ cho sẵn.

Bài chấm ghi đè dia_chi/bi_danh.tsv bằng một bảng khác bảng ban đầu (có BOM, xuống dòng kiểu Windows, tên chuẩn ở dạng
NFD, bí danh có khoảng trắng quanh dấu |) rồi chạy từ một thư mục khác. Các cách làm sai đã thử, đều phải trượt:
  - chép cứng bảng ban đầu vào code, hay mở "bi_danh.tsv" theo thư mục đang chạy;
  - không bỏ BOM nên dòng đầu của bảng mất bí danh, không bỏ "\\r" cuối dòng;
  - dùng str.replace trên cả địa chỉ nên đổi cả tên đường "Sài Gòn" và tên quận "Huế";
  - so khớp có phân biệt chữ hoa thường hay dấu, quên chữ tách dấu (NFD), quên bỏ dấu chấm / gạch ngang khi so;
  - coi "Việt Nam" là tên tỉnh, hoặc bỏ mất phần "Việt Nam", "VN" ở cuối;
  - trả kết quả không phải NFC, gộp khoảng trắng giữa phần của địa chỉ, không bỏ phần rỗng sau dấu phẩy cuối.
"""
import importlib.util
import os
import sys
import tempfile
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


BANG = (
    "\ufeffThành phố Hồ Chí Minh\tTP.HCM|TPHCM|Tp Hồ Chí Minh|Sài Gòn | Hồ Chí Minh|HCM\r\n"
    "# Bảng bí danh tỉnh, thành\r\n"
    "Hà Nội\tHN|Thủ đô|Ha Noi\r\n"
    + nfd("Đà Nẵng") + "\tTp Đà Nẵng|Đà nẵng\r\n"
    "Thừa Thiên Huế\tHuế|TT Huế\r\n"
    "\r\n"
    "Cần Thơ\tTP Cần Thơ|Can Tho|Xà no\r\n"
    "   # dòng chú thích có thụt đầu dòng\r\n"
    "Bà Rịa - Vũng Tàu\tBR-VT|Vũng Tàu|Ba Ria Vung Tau\r\n"
    "Quảng Ninh\tQN\r\n"
)

# (địa chỉ vào, địa chỉ đúng). Kết quả mong đợi ghi tay, ở dạng NFC.
CASES = [
    ("12 Nguyễn Huệ, Bến Nghé, Quận 1, TP.HCM", "12 Nguyễn Huệ, Bến Nghé, Quận 1, Thành phố Hồ Chí Minh"),
    ("số 5 đường Sài Gòn, phường 3, hà nội", "số 5 đường Sài Gòn, phường 3, Hà Nội"),
    ("Sài Gòn", "Thành phố Hồ Chí Minh"),
    ("  45 Lê Lợi ,  Tp Hồ Chí Minh  ", "45 Lê Lợi, Thành phố Hồ Chí Minh"),
    (nfd("12 Nguyễn Huệ, Bến Nghé, hồ chí minh"), "12 Nguyễn Huệ, Bến Nghé, Thành phố Hồ Chí Minh"),
    ("7 Trần Hưng Đạo, TP. HCM, Việt Nam", "7 Trần Hưng Đạo, Thành phố Hồ Chí Minh, Việt Nam"),
    ("HN, VN", "Hà Nội, VN"),
    ("Sài Gòn, Việt Nam", "Thành phố Hồ Chí Minh, Việt Nam"),
    ("Hà Nội, Việt Nam", "Hà Nội, Việt Nam"),
    ("Việt Nam", "Việt Nam"),
    ("3 Hùng Vương, Huế, TT Huế", "3 Hùng Vương, Huế, Thừa Thiên Huế"),
    ("3 Hùng Vương, Phú Nhuận, Huế", "3 Hùng Vương, Phú Nhuận, Thừa Thiên Huế"),
    ("Ba Ria-Vung Tau", "Bà Rịa - Vũng Tàu"),
    (nfd("8 Hạ Long, VŨNG TÀU"), "8 Hạ Long, Bà Rịa - Vũng Tàu"),
    ("9 Bạch Đằng, đà nẵng", "9 Bạch Đằng, Đà Nẵng"),
    ("9 Bạch Đằng, Da Nang", "9 Bạch Đằng, Đà Nẵng"),
    ("4 Hòa Bình, xà no", "4 Hòa Bình, Cần Thơ"),
    ("4 Hòa Bình, tp cần thơ", "4 Hòa Bình, Cần Thơ"),
    ("10 Phố Huế, Hà Giang", "10 Phố Huế, Hà Giang"),
    (nfd("2  Lý Thường Kiệt , Lạng Sơn "), "2  Lý Thường Kiệt, Lạng Sơn"),
    ("Hà Nội, Lào Cai", "Hà Nội, Lào Cai"),
    ("5 Lê Duẩn, Hà Nội,", "5 Lê Duẩn, Hà Nội"),
    ("5 Lê Duẩn,, ,HCM", "5 Lê Duẩn, Thành phố Hồ Chí Minh"),
    ("Q3, hcm", "Q3, Thành phố Hồ Chí Minh"),
    ("1 Hạ Long, QN", "1 Hạ Long, Quảng Ninh"),
    ("", ""),
    ("   ", ""),
]


def main():
    thu_muc = vncheck.app_dir() / "dia_chi"
    try:
        with open(thu_muc / "bi_danh.tsv", "wb") as fh:
            fh.write(BANG.encode("utf-8"))
    except OSError as exc:
        vncheck.finish([f"không ghi được bảng thử vào {thu_muc}: {exc!r}"])
    spec = importlib.util.spec_from_file_location("chuan_hoa_check", thu_muc / "chuan_hoa.py")
    mod = importlib.util.module_from_spec(spec)
    errs = []
    with tempfile.TemporaryDirectory(prefix="vi-dc-") as tmp:
        os.chdir(tmp)   # chạy từ thư mục khác thư mục chứa code
        try:
            spec.loader.exec_module(mod)
            f = mod.chuan_hoa_tinh
        except Exception as exc:  # noqa: BLE001
            vncheck.finish([f"không nạp được dia_chi/chuan_hoa.py: {exc!r}"])
        for vao, want in CASES:
            try:
                got = f(vao)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"chuan_hoa_tinh({vao!r}) lỗi {exc!r}, đúng là {want!r}")
                continue
            if got != want:
                errs.append(f"chuan_hoa_tinh({vao!r}) = {got!r}, đúng là {want!r}")
        try:
            if f(dia_chi="HN") != "Hà Nội":
                errs.append("gọi theo tên tham số cho kết quả sai")
        except TypeError:
            errs.append("đã đổi tên tham số của hàm")
        except Exception:  # noqa: BLE001
            pass
        os.chdir("/")
    vncheck.finish(errs)


main()
