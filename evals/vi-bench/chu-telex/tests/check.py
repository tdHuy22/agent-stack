"""Chấm chu-telex: so với văn bản sửa tay theo luật Telex và luật đặt dấu trong đề.

Bài chấm tự ghi lại tu_giu.txt (danh sách riêng, khác bản gửi kèm) trước khi nạp bài làm.

Các cách làm sai hay gặp mà bài chấm này bắt:
  - ghi sẵn danh sách từ tiếng Anh vào code hay bỏ qua file ("tool", "cool" không có trong danh sách phải bị đổi thành "tôl", "côl");
  - quên qu, gi là phụ âm đầu: "quas" thành "qúa", "giaf" thành "gìa", "giaos" thành "gíao";
  - đặt dấu sai chỗ: cụm hai nguyên âm ở cuối chữ phải lên chữ thứ nhất (hòa, của), có phụ âm cuối lên chữ thứ hai (toàn);
    "ươ" phải lên ơ (được, người), ba nguyên âm lên chữ giữa (ngoài);
  - coi mọi s f r x j cuối chữ là phím thanh ("It's" thành "Ít's"), không kiểm có nguyên âm;
  - không giữ kiểu hoa thường ("VIEETJ" phải là "VIỆT", "Ddaats" phải là "Đất"); chữ đã có dấu ("Việtj") bị đổi;
  - không đổi về NFC trước khi xử lý; đổi "dd", "uw", "ow" nhưng sót "aw", "uw" hay đổi chồng lấn.
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


# Danh sách từ giữ nguyên dùng khi chấm (không phân biệt hoa thường, có dòng trống). "tool", "cool", "yes" cố ý không có.
TU_GIU = "Windows\nfacebook\n\nGood\nmeeting\nfix\nis\nas\nof\nboss\ntext\nGoogle\ngif\nemail\n"

# (văn bản vào, văn bản đúng). Sửa tay theo luật trong đề, soát lại ngày 08/11/2026.
CASES = [
    ("Tooi ddang hocj tieengs Vieetj", "Tôi đang học tiếng Việt"),
    ("VIEETJ NAM", "VIỆT NAM"),
    ("Haf Nooij, nguwowif Windows", "Hà Nội, người Windows"),
    ("HAF NOOIJ", "HÀ NỘI"),
    ("Hoaf Binhf", "Hòa Bình"),
    ("toanf hoatj khoer thuyr", "toàn hoạt khỏe thủy"),
    ("ngoaif xoays loaij hoaj cuar muaf", "ngoài xoáy loại họa của mùa"),
    ("dduwowcj nguwowif nuwowcs mowis thuwr", "được người nước mới thử"),
    ("huwowng huwowngs dduwowngf", "hương hướng đường"),
    ("muoons yeeus chuyeenj tuyeenr khuyeens", "muốn yếu chuyện tuyển khuyến"),
    ("quyeenf quas quaf quys quoocs", "quyền quá quà quý quốc"),
    ("gias giaf giaos gieengs giuwax gir", "giá già giáo giếng giữa gỉ"),
    ("QUYEENF GIAOS", "QUYỀN GIÁO"),
    ("Quas Giaf", "Quá Già"),
    ("ddaats ddaauj ddiaj mawtj", "đất đậu địa mặt"),
    ("Ddaats nuwowcs", "Đất nước"),
    ("DDAATS NUWOWCS", "ĐẤT NƯỚC"),
    ("Ddoongf Ddi DDI ddi", "Đồng Đi ĐI đi"),
    ("tieengs Tieengs TIEENGS", "tiếng Tiếng TIẾNG"),
    ("Việtj tiếngs hocj", "Việtj tiếngs học"),
    (nfd("Việtj hocj"), "Việtj học"),
    (nfd("Tooi yeeu Việt Nam"), "Tôi yêu Việt Nam"),
    ("Tooi dung Windows va Facebook", "Tôi dung Windows va Facebook"),
    ("the meeting is good", "the meeting is good"),
    ("Good boss, FIX the TEXT of gif", "Good boss, FIX the TEXT of gif"),
    ("cool tool", "côl tôl"),
    ("It's boss's text", "It's boss's text"),
    ("ms xs rs s f", "ms xs rs s f"),
    ("www wifi", "www wifi"),
    ("Hoom nay toois ddi lamf vieecj, gap boss va hop meeting luc 9h.",
     "Hôm nay tối đi làm việc, gap boss va hop meeting luc 9h."),
    ("Haf Nooij\nddi hocj", "Hà Nội\nđi học"),
    ("Vieetj Nam, 2026; hocj!", "Việt Nam, 2026; học!"),
    ("tuwf", "từ"),
    ("hoaf-binhf_hoaj", "hòa-bình_họa"),
]


def main():
    app = vncheck.app_dir()
    (app / "tu_giu.txt").write_text(TU_GIU, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("telex_check", app / "telex.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được telex.py: {exc!r}"])
    errs = []
    for vao, dung in CASES:
        try:
            got = mod.sua_telex(vao)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"sua_telex({vao!r}) lỗi {exc!r}")
            continue
        if got != unicodedata.normalize("NFC", dung):
            errs.append(f"sua_telex({vao!r}): được {got!r}, đúng là {dung!r}")
    vncheck.finish(errs[:12])


main()
