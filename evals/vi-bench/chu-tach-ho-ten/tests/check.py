"""Chấm chu-tach-ho-ten: so với kết quả tách tính tay theo luật trong đề.

Bài chấm tự ghi lại ho_kep.txt (danh sách riêng, khác bản gửi kèm) trước khi nạp bài làm, rồi ghi đè lần nữa sau khi nạp.

Các cách làm sai hay gặp mà bài chấm này bắt:
  - ghi sẵn danh sách họ kép vào code, hay đọc file một lần lúc nạp rồi nhớ lại (sửa file không có hiệu lực);
  - so họ kép phân biệt hoa thường hay dấu tách rời/dựng sẵn ("tôn nữ thị hạnh", họ tên NFD, dòng NFD trong file);
  - so theo ký tự (startswith) thay vì từng chữ: "Tôn Nữa An" bị coi là họ "Tôn Nữ";
  - lấy họ kép khớp đầu tiên trong file thay vì dài nhất ("Công Tằng Tôn Nữ Mỹ Linh");
  - để họ kép nuốt hết tên ("Âu Dương" thành họ "Âu Dương", tên rỗng), hay không thử họ kép ngắn hơn ("Công Tằng Tôn Nữ");
  - tìm họ kép ở giữa tên thay vì ở đầu; một chữ không xử lý; chữ không về NFC hay không viết hoa đúng.
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


def kq(ho, dem, ten):
    return {"ho": ho, "dem": dem, "ten": ten}


# Danh sách đợt 1: dòng thường, dòng có khoảng trắng thừa, dòng trống, dòng NFD; không có Tôn Thất, Nguyễn Phúc.
LIST_A = ("Âu Dương\ntôn   nữ\n\nHoàng Phủ   \n" + nfd("Ngô Đình") + "\nCông Tằng Tôn Nữ\nCông Tằng\nDương Đình\n")
# Danh sách đợt 2 (ghi sau khi đã nạp bài làm): họ kép ngắn đứng trước họ kép dài.
LIST_B = "Nguyễn Phúc\nTôn Thất\nCông Tằng\nCông Tằng Tôn Nữ\n"
LIST_C = ""

# (họ tên vào, kết quả đúng) — tính tay theo luật trong đề, soát lại ngày 08/11/2026.
CASES_A = [
    ("Nguyễn Văn An", kq("Nguyễn", "Văn", "An")),
    ("  nguyễn   VĂN  an ", kq("Nguyễn", "Văn", "An")),
    ("NGUYỄN VĂN AN", kq("Nguyễn", "Văn", "An")),
    (nfd("Lê Thị Hồng Nhung"), kq("Lê", "Thị Hồng", "Nhung")),
    ("Lê\tVăn\nTám", kq("Lê", "Văn", "Tám")),
    ("Âu Dương Phong", kq("Âu Dương", "", "Phong")),
    ("âu dương phong", kq("Âu Dương", "", "Phong")),
    ("ÂU DƯƠNG PHONG", kq("Âu Dương", "", "Phong")),
    (nfd("Âu Dương Phong"), kq("Âu Dương", "", "Phong")),
    ("Tôn Nữ Thị Hạnh", kq("Tôn Nữ", "Thị", "Hạnh")),
    ("tôn nữ thị hạnh", kq("Tôn Nữ", "Thị", "Hạnh")),
    ("TÔN NỮ THỊ HẠNH", kq("Tôn Nữ", "Thị", "Hạnh")),
    ("Tôn Thất Tùng", kq("Tôn", "Thất", "Tùng")),
    ("Nguyễn Phúc Vĩnh Thụy", kq("Nguyễn", "Phúc Vĩnh", "Thụy")),
    ("Hoàng Phủ Ngọc Tường", kq("Hoàng Phủ", "Ngọc", "Tường")),
    ("Ngô Đình Diệm", kq("Ngô Đình", "", "Diệm")),
    (nfd("Ngô Đình Nhu"), kq("Ngô Đình", "", "Nhu")),
    ("Công Tằng Tôn Nữ Mỹ Linh", kq("Công Tằng Tôn Nữ", "Mỹ", "Linh")),
    ("Công Tằng Tôn Nữ", kq("Công Tằng", "Tôn", "Nữ")),
    ("Công Tằng Tôn", kq("Công Tằng", "", "Tôn")),
    ("Công Tằng", kq("Công", "", "Tằng")),
    ("Âu Dương", kq("Âu", "", "Dương")),
    ("Tôn Nữ", kq("Tôn", "", "Nữ")),
    ("Hoàng Phủ", kq("Hoàng", "", "Phủ")),
    ("Dương Đình Nghệ", kq("Dương Đình", "", "Nghệ")),
    ("Dương Đình", kq("Dương", "", "Đình")),
    ("Tôn Nữa An", kq("Tôn", "Nữa", "An")),
    ("Nguyễn Công Tằng", kq("Nguyễn", "Công", "Tằng")),
    ("Nguyễn Tôn Nữ Hạnh", kq("Nguyễn", "Tôn Nữ", "Hạnh")),
    ("An", kq("", "", "An")),
    ("  trần  ", kq("", "", "Trần")),
    ("ĐỖ", kq("", "", "Đỗ")),
    ("Trần Anh", kq("Trần", "", "Anh")),
    ("Đỗ Thị Ánh Tuyết Mai", kq("Đỗ", "Thị Ánh Tuyết", "Mai")),
    ("ĐẶNG THÙY TRÂM", kq("Đặng", "Thùy", "Trâm")),
    ("lý hải", kq("Lý", "", "Hải")),
    (nfd("đỗ  thị  ưng"), kq("Đỗ", "Thị", "Ưng")),
]
CASES_B = [
    ("Tôn Thất Tùng", kq("Tôn Thất", "", "Tùng")),
    ("Âu Dương Phong", kq("Âu", "Dương", "Phong")),
    ("Nguyễn Phúc Vĩnh Thụy", kq("Nguyễn Phúc", "Vĩnh", "Thụy")),
    ("Công Tằng Tôn Nữ Mỹ Linh", kq("Công Tằng Tôn Nữ", "Mỹ", "Linh")),
    ("Công Tằng Tôn Nữ", kq("Công Tằng", "Tôn", "Nữ")),
    ("Tôn Nữ Thị Hạnh", kq("Tôn", "Nữ Thị", "Hạnh")),
    ("Nguyễn Phúc", kq("Nguyễn", "", "Phúc")),
]
CASES_C = [
    ("Tôn Thất Tùng", kq("Tôn", "Thất", "Tùng")),
    ("Nguyễn Phúc Vĩnh Thụy", kq("Nguyễn", "Phúc Vĩnh", "Thụy")),
    ("Công Tằng Tôn Nữ Mỹ Linh", kq("Công", "Tằng Tôn Nữ Mỹ", "Linh")),
]
LOI = ["", "   ", "\t\n"]


def chay(mod, cases, errs, nhan):
    for vao, dung in cases:
        try:
            got = mod.tach_ho_ten(vao)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"[{nhan}] tach_ho_ten({vao!r}) lỗi {exc!r}")
            continue
        if got != {k: unicodedata.normalize("NFC", v) for k, v in dung.items()}:
            errs.append(f"[{nhan}] tach_ho_ten({vao!r}): được {got!r}, đúng là {dung!r}")


def main():
    app = vncheck.app_dir()
    kep = app / "ho_kep.txt"
    kep.write_text(LIST_A, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("ho_ten_check", app / "ho_ten.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được ho_ten.py: {exc!r}"])
    errs = []
    chay(mod, CASES_A, errs, "danh sách 1")
    for vao in LOI:
        try:
            got = mod.tach_ho_ten(vao)
            errs.append(f"tach_ho_ten({vao!r}) phải ném ValueError, được {got!r}")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            errs.append(f"tach_ho_ten({vao!r}) phải ném ValueError, được {exc!r}")
    kep.write_text(LIST_B, encoding="utf-8")
    chay(mod, CASES_B, errs, "sau khi sửa file lần 1")
    kep.write_text(LIST_C, encoding="utf-8")
    chay(mod, CASES_C, errs, "sau khi sửa file lần 2 (file rỗng)")
    vncheck.finish(errs[:12])


main()
