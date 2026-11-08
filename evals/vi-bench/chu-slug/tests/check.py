"""Chấm chu-slug: so với slug tính tay theo luật trong đề.

Các cách làm sai hay gặp mà bài chấm này bắt:
  - bỏ dấu bằng unicodedata nhưng quên "đ" (không tách được thành d + dấu), hay mã hóa ASCII bỏ qua làm mất cả chữ;
  - không chuẩn hóa NFD trước nên chuỗi dựng sẵn bị coi là ký tự lạ ("hu-ng-d-n");
  - coi dấu nháy đơn là ký tự phân cách ("o-brien" thay vì "obrien");
  - cắt cứng slug[:toi_da] làm đứt giữa từ, hay dùng "<" thay "<=" khi vừa đúng giới hạn;
  - để gạch nối thừa ở đầu, cuối hay hai gạch liền nhau; tiêu đề rỗng không trả "bai-viet";
  - chữ Hán, ký hiệu (như "²"), dấu chấm trong số không thành gạch nối (bỏ qua thay vì tách từ, hay NFKD làm "²" thành "2").
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


# (đối số, đáp án). Đáp án viết tay theo luật trong đề và soát lại ngày 08/11/2026.
CASES = [
    (("Hướng dẫn cài đặt Python",), "huong-dan-cai-dat-python"),
    (("Đường Điện Biên Phủ",), "duong-dien-bien-phu"),
    ((nfd("Nguyễn Thị Minh Khai"),), "nguyen-thi-minh-khai"),
    ((nfd("ĐỖ THỊ ƯỚT"),), "do-thi-uot"),
    ((nfd("đồng hồ"),), "dong-ho"),
    (("Quán cà phê O'Brien – Hà Nội!",), "quan-ca-phe-obrien-ha-noi"),
    (("Rock’n’roll đêm Sài Gòn",), "rocknroll-dem-sai-gon"),
    (("‘Mưa’ trên phố",), "mua-tren-pho"),
    (("Don't Stop Believin'",), "dont-stop-believin"),
    (("  Thứ Bảy:   100% vui  ",), "thu-bay-100-vui"),
    (("Giá 1.500.000đ/tháng",), "gia-1-500-000d-thang"),
    (("Phiên bản 2.0.1",), "phien-ban-2-0-1"),
    (("Café crème brûlée",), "cafe-creme-brulee"),
    (("Müller và Ångström",), "muller-va-angstrom"),
    (("---Hello___World---",), "hello-world"),
    (("Hà-Nội",), "ha-noi"),
    (("Tom & Jerry: Cuộc rượt đuổi",), "tom-jerry-cuoc-ruot-duoi"),
    (("Dòng một\nDòng hai\tDòng ba",), "dong-mot-dong-hai-dong-ba"),
    (("Hà Nội 河内 2026",), "ha-noi-2026"),
    (("Ơ kìa!",), "o-kia"),
    (("Xin chào世界Việt",), "xin-chao-viet"),
    (("Diện tích 50m²",), "dien-tich-50m"),
    (("đ",), "d"),
    (("ĐĐ",), "dd"),
    (("",), "bai-viet"),
    (("!!! ???",), "bai-viet"),
    (("河内 ’ ‘",), "bai-viet"),
    (("Học tiếng Việt – Bài 1: Chào hỏi",), "hoc-tieng-viet-bai-1-chao-hoi"),
    # vừa đúng giới hạn 60 (ký tự thứ 60 là chữ cuối của "bua"), rồi vượt giới hạn giữa một từ
    (("Cách làm bánh xèo miền Tây giòn rụm không cần bột nở cho bữa sáng cuối tuần của gia đình",),
     "cach-lam-banh-xeo-mien-tay-gion-rum-khong-can-bot-no-cho-bua"),
    (("Cách làm bánh xèo miền Tây giòn rụm không cần bột nở cho buổi sáng cuối tuần",),
     "cach-lam-banh-xeo-mien-tay-gion-rum-khong-can-bot-no-cho"),
    (("Hướng dẫn cài đặt và cấu hình máy chủ web Nginx trên Ubuntu 22.04 cho người mới bắt đầu",),
     "huong-dan-cai-dat-va-cau-hinh-may-chu-web-nginx-tren-ubuntu"),
    (("Mùa thu ở Hà Nội", 11), "mua-thu-o"),
    (("Mùa thu ở Hà Nội", 12), "mua-thu-o-ha"),
    (("Mùa thu ở Hà Nội", 9), "mua-thu-o"),
    (("Mùa thu ở Hà Nội", 8), "mua-thu"),
    (("Mùa thu ở Hà Nội", 100), "mua-thu-o-ha-noi"),
    (("Việt Nam", 8), "viet-nam"),
    (("Việt Nam", 7), "viet"),
    (("Việt Nam", 4), "viet"),
    (("Việt Nam", 3), "vie"),
    (("Điệnthoạithôngminhsiêucấp Mới", 12), "dienthoaitho"),
    (("Điện thoại thông minh siêu cấp", 20), "dien-thoai-thong"),
    (("Điện thoại thông minh siêu cấp", 21), "dien-thoai-thong-minh"),
    (("Điện thoại thông minh siêu cấp", 22), "dien-thoai-thong-minh"),
    (("Điện thoại thông minh siêu cấp", 26), "dien-thoai-thong-minh-sieu"),
]


def main():
    spec = importlib.util.spec_from_file_location("slug_check", vncheck.app_dir() / "slug.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được slug.py: {exc!r}"])
    errs = []
    for args, dung in CASES:
        try:
            got = mod.tao_slug(*args)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"tao_slug{args!r} lỗi {exc!r}")
            continue
        if got != dung:
            errs.append(f"tao_slug{args!r}: được {got!r}, đúng là {dung!r}")
    vncheck.finish(errs[:12])


main()
