"""Chấm chu-viet-hoa-ten-rieng: so với văn bản viết hoa tay theo luật trong đề.

Bài chấm tự ghi lại ten_rieng.txt (danh sách riêng, khác bản gửi kèm: thêm "Lạng Sơn", "Nam Định", bớt "Huế"…) trước khi nạp bài làm.

Các cách làm sai hay gặp mà bài chấm này bắt:
  - dùng title()/capitalize() hay viết hoa từng chữ ("Thành Phố Hồ Chí Minh Đông Dân");
  - ghi sẵn danh sách trong code, không đọc file (tên chỉ có trong danh sách của bài chấm không được viết hoa);
  - khớp phân biệt hoa thường ("HÀ NỘI", "hÀ nỘi"), không chịu dấu tách rời (NFD), không chịu nhiều khoảng trắng hay xuống dòng giữa các chữ;
  - lấy chỗ khớp ngắn nhất thay vì nhiều chữ nhất ("việt nam airlines" thành "Việt Nam airlines" khi danh sách có cả "Việt Nam"
    lẫn "Việt Nam Airlines"); coi mọi dấu chấm là hết câu ("a.nguyen@vd.com");
  - khớp cả khi dính chữ cái liền trước hay liền sau ("lạng sơnx", "xsa pa"), hoặc không khớp khi sát chữ số, dấu câu;
  - quên viết hoa chữ cái đầu câu (kể cả đầu dòng, chữ đ, tên không thuộc danh sách, chữ thường đầu tên như "sông Hồng"),
    hay viết hoa sau dấu chấm trong số ("2.5"), hay viết hoa chữ số/ký tự lạ.
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


# Danh sách khi chấm: có dòng trống, dòng thừa khoảng trắng, dòng NFD. Không có "Huế" riêng, "Hà Nam", "tây ninh".
LIST = ("Hà Nội\nHồ Chí Minh\nthành phố Hồ Chí Minh\nĐà Nẵng\nViệt Nam\nViệt Nam Airlines\nNgân hàng Nhà nước Việt Nam\n"
        "Đại học Quốc gia Hà Nội\nĐại học Bách khoa Hà Nội\nBộ Giáo dục và Đào tạo\nsông Hồng\nnúi Bà Đen\n"
        "Thừa Thiên Huế\nQuảng Nam\nLạng Sơn\nSa Pa\n\n   Nam Định   \n" + nfd("Cần Thơ") + "\n")

# (văn bản vào, văn bản đúng). Viết tay theo luật trong đề, soát lại ngày 08/11/2026.
CASES = [
    ("thành phố hồ chí minh", "Thành phố Hồ Chí Minh"),
    ("tôi sống ở thành phố hồ chí minh.", "Tôi sống ở thành phố Hồ Chí Minh."),
    ("thành phố hồ chí minh đông dân", "Thành phố Hồ Chí Minh đông dân"),
    ("chủ tịch hồ chí minh", "Chủ tịch Hồ Chí Minh"),
    ("anh ấy đi hà nội rồi vào đà nẵng", "Anh ấy đi Hà Nội rồi vào Đà Nẵng"),
    ("HÀ NỘI VÀ ĐÀ NẴNG", "Hà Nội VÀ Đà Nẵng"),
    ("hÀ nỘi", "Hà Nội"),
    ("quảng NAM", "Quảng Nam"),
    (nfd("hà nội"), "Hà Nội"),
    (nfd("sông hồng và núi bà đen"), "Sông Hồng và núi Bà Đen"),
    ("đi  hồ   chí\nminh nhé", "Đi  Hồ Chí Minh nhé"),
    ("ngân hàng nhà nước việt nam công bố", "Ngân hàng Nhà nước Việt Nam công bố"),
    ("đi ngân hàng nhà nước việt nam", "Đi Ngân hàng Nhà nước Việt Nam"),
    ("đại học quốc gia hà nội và đại học bách khoa hà nội", "Đại học Quốc gia Hà Nội và Đại học Bách khoa Hà Nội"),
    ("bộ giáo dục và đào tạo thông báo", "Bộ Giáo dục và Đào tạo thông báo"),
    ("sông hồng chảy qua hà nội. núi bà đen ở tây ninh.", "Sông Hồng chảy qua Hà Nội. Núi Bà Đen ở tây ninh."),
    ("miền nam việt nam", "Miền nam Việt Nam"),
    ("hà nội hà nội", "Hà Nội Hà Nội"),
    ("bay với việt nam airlines, không phải việt nam", "Bay với Việt Nam Airlines, không phải Việt Nam"),
    ("gửi email a.nguyen@vd.com về hà nội", "Gửi email a.nguyen@vd.com về Hà Nội"),
    ("(hà nội), \"đà nẵng\"; việt nam!", "(Hà Nội), \"Đà Nẵng\"; Việt Nam!"),
    ("hà nội2026", "Hà Nội2026"),
    ("lạng sơn, lạng sơnx", "Lạng Sơn, lạng sơnx"),
    ("đi xsa pa và sa pa", "Đi xsa pa và Sa Pa"),
    ("hà-nội và hà, nội", "Hà-nội và hà, nội"),
    ("đi huế", "Đi huế"),
    ("thừa thiên huế", "Thừa Thiên Huế"),
    ("đến thừa thiên huế rồi huế", "Đến Thừa Thiên Huế rồi huế"),
    ("thành phố hà nội", "Thành phố Hà Nội"),
    ("cần thơ", "Cần Thơ"),
    ("đi cần thơ và nam định", "Đi Cần Thơ và Nam Định"),
    ("NASA ở hà nội", "NASA ở Hà Nội"),
    ("Hà Nội là thủ đô của Việt Nam.", "Hà Nội là thủ đô của Việt Nam."),
    ("hôm nay mưa! ngày mai nắng? hà nội lạnh.\nđà nẵng nóng", "Hôm nay mưa! Ngày mai nắng? Hà Nội lạnh.\nĐà Nẵng nóng"),
    ("hà nội\nđà nẵng\nhuế", "Hà Nội\nĐà Nẵng\nHuế"),
    ("giá 2.5 triệu, mua ở sa pa", "Giá 2.5 triệu, mua ở Sa Pa"),
    ("tp. hồ chí minh", "Tp. Hồ Chí Minh"),
    ("xe số 5. 5 giờ đi hà nội", "Xe số 5. 5 giờ đi Hà Nội"),
    ("đi đâu?! đà nẵng.. rồi hết...  xong", "Đi đâu?! Đà Nẵng.. Rồi hết...  Xong"),
    ("  hà nội  ", "  Hà Nội  "),
    ("\n\nđà nẵng", "\n\nĐà Nẵng"),
    ("\"hà nội\" nói. \"đà nẵng\" đáp.", "\"Hà Nội\" nói. \"Đà Nẵng\" đáp."),
    ("", ""),
    ("   ", "   "),
]


def main():
    app = vncheck.app_dir()
    (app / "ten_rieng.txt").write_text(LIST, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("viet_hoa_check", app / "viet_hoa.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được viet_hoa.py: {exc!r}"])
    errs = []
    for vao, dung in CASES:
        try:
            got = mod.viet_hoa(vao)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"viet_hoa({vao!r}) lỗi {exc!r}")
            continue
        if got != unicodedata.normalize("NFC", dung):
            errs.append(f"viet_hoa({vao!r}): được {got!r}, đúng là {dung!r}")
    vncheck.finish(errs[:12])


main()
