"""Chấm chu-dau-thanh: so với văn bản chuyển tay theo luật trong đề.

Các cách làm sai hay gặp mà bài chấm này bắt:
  - làm bảng thay thế vài chữ (hoà, thuỷ…) hay regex "uỷ" thành "ủy" không loại trừ q: "quỷ", "quý" bị đổi thành "qủy", "qúy";
  - đổi cả khi chữ còn tiếp ("hoàn" thành "hòan", "xoáy" thành "xóay", "khoèo" thành "khòeo"): không neo vào cuối chữ;
  - đổi cả vần khác cũng hai nguyên âm không phụ âm cuối ("quà" thành "qùa", "giá" thành "gía", "của" thành "cũa");
  - chỉ xử lý chữ thường (bỏ sót "HOÀ", "Thuỷ"), không nhận dấu tách rời (NFD) hay không trả kết quả NFC;
  - coi chữ số, gạch dưới là một phần của chữ nên không thấy cuối chữ ("hoà_bình"); chỉ làm oa mà bỏ oe, uy.
"""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def nfd(s):
    return unicodedata.normalize("NFD", s)


# (văn bản vào, văn bản đúng). Chuyển tay theo luật trong đề, soát lại ngày 08/11/2026.
CASES = [
    ("Hoà bình", "Hòa bình"),
    ("hoà hoá hoả hoã hoạ", "hòa hóa hỏa hõa họa"),
    ("xoè loé khoẻ khoẽ khoẹ", "xòe lóe khỏe khõe khọe"),
    ("tuỳ tuý tuỷ tuỹ tuỵ", "tùy túy tủy tũy tụy"),
    ("hoá đơn điện tử", "hóa đơn điện tử"),
    ("Chúc bạn khoẻ", "Chúc bạn khỏe"),
    ("toà án nhân dân", "tòa án nhân dân"),
    ("thuỷ điện Hoà Bình", "thủy điện Hòa Bình"),
    ("tuỳ chọn", "tùy chọn"),
    ("huỷ đơn hàng", "hủy đơn hàng"),
    ("Thuý Kiều và Thuỵ Sĩ", "Thúy Kiều và Thụy Sĩ"),
    ("luỹ thừa", "lũy thừa"),
    ("hoạ sĩ, hoả hoạn", "họa sĩ, hỏa hoạn"),
    ("HOÀ BÌNH, THUỶ TIÊN", "HÒA BÌNH, THỦY TIÊN"),
    ("HOÁ ĐƠN", "HÓA ĐƠN"),
    ("Quý khách, quỷ, quỳ, quỹ, quỵ", "Quý khách, quỷ, quỳ, quỹ, quỵ"),
    ("QUÝ KHÁCH QUỲNH", "QUÝ KHÁCH QUỲNH"),
    ("Quý Thuỷ", "Quý Thủy"),
    ("toán, hoàn, hoạt, huỳnh, khoẻ mạnh", "toán, hoàn, hoạt, huỳnh, khỏe mạnh"),
    ("ngoài, xoáy, khoèo, loạt, thuở, hoài", "ngoài, xoáy, khoèo, loạt, thuở, hoài"),
    ("quà, quả, giá, già, giả, của, mùa, múa", "quà, quả, giá, già, giả, của, mùa, múa"),
    ("Hòa, hóa, thủy, tùy, khỏe", "Hòa, hóa, thủy, tùy, khỏe"),
    ("hoa, hoe, huy, Hoa Kỳ, Huy", "hoa, hoe, huy, Hoa Kỳ, Huy"),
    ("Windows 11, Toyota, queue", "Windows 11, Toyota, queue"),
    ("Dòng 1: hoà\nDòng 2: tuỳ", "Dòng 1: hòa\nDòng 2: tùy"),
    ("hoà-bình_thuỷ-điện", "hòa-bình_thủy-điện"),
    ("hoà_bình thuỷ_điện hoá2 3tuỳ", "hòa_bình thủy_điện hóa2 3tùy"),
    ("(hoà), \"thuỷ\"; hoá!", "(hòa), \"thủy\"; hóa!"),
    ("Công ty thuỷ sản Hoà Phát tuỳ ý hoá giá, quý vị hoà đồng khoẻ khoắn.",
     "Công ty thủy sản Hòa Phát tùy ý hóa giá, quý vị hòa đồng khỏe khoắn."),
    (nfd("hoà bình, thuỷ điện"), "hòa bình, thủy điện"),
    (nfd("Quý khách khoẻ, QUỶ, HOÀ"), "Quý khách khỏe, QUỶ, HÒA"),
    (nfd("toán hoàn ngoài xoáy"), "toán hoàn ngoài xoáy"),
    ("", ""),
    ("   \n", "   \n"),
]


def main():
    spec = importlib.util.spec_from_file_location("dau_thanh_check", vncheck.app_dir() / "dau_thanh.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được dau_thanh.py: {exc!r}"])
    errs = []
    for vao, dung in CASES:
        try:
            got = mod.chuan_hoa_dau(vao)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"chuan_hoa_dau({vao!r}) lỗi {exc!r}")
            continue
        if got != unicodedata.normalize("NFC", dung):
            errs.append(f"chuan_hoa_dau({vao!r}): được {got!r}, đúng là {dung!r}")
    vncheck.finish(errs[:12])


main()
