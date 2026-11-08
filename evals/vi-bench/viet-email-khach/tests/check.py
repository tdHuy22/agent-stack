"""Chấm viet-email-khach: đúng ba khoản bồi thường, xưng hô, không hứa ngoài chính sách.

Tính tay từ don-hang.txt và chinh-sach.txt: hẹn giao 02/11, nhận 08/11 là trễ 6 ngày (tính ngày lịch); 6 × 2% = 12% vượt trần,
còn 10% × tiền hàng 1.600.000 = 160.000đ; trễ hơn 3 ngày nên hoàn phí vận chuyển 35.000đ; hoàn tiền thớt gỗ theo giá trên đơn
260.000đ (không phải 90.000đ của thớt nhựa). Tổng 455.000đ, hoàn trong 5 ngày làm việc. Khách đòi hoàn 1.635.000đ, đền 500.000đ,
mã giảm 20%: chính sách không cho, chỉ được nhắc tới khi có từ chối.
Số sai hay gặp: 192.000đ (quên trần 10%), 487.000đ (192+35+260), 285.000đ (hoàn 90.000 thay vì 260.000), 7 ngày trễ (theo email khách).

Chữ ký "Vy" chấp nhận trong 3 dòng cuối (chữ ký hai dòng); không bắt buộc ghi "6 ngày"; chỉ bắt câu nói tiền về sớm hơn 5 ngày làm việc,
không bắt "kể từ email xác nhận em gửi ngay hôm nay" hay "em bồi thường thêm phí vận chuyển". Dấu hiệu văn AI không còn làm trượt.

Fixture (solution/dat-khac, solution/truot) chạy trong selftest.py:
  ĐẠT    1 bản đúng khác lời giải mẫu (chỉ nêu tổng, nhắc voucher trong câu từ chối, "năm ngày làm việc"); 2 chữ ký hai dòng, "bồi thường
         thêm phí vận chuyển", "gửi ngay hôm nay"; 3 chữ ký ba dòng, mở bằng câu sáo nhưng đủ số liệu
  TRƯỢT  1 hứa hoàn toàn bộ 1.635.000đ, đền 500.000đ, mã giảm 20%, xưng "tôi/quý khách"; 2 quên trần 10% (192.000đ, tổng 487.000đ), hứa 24 giờ;
         3 thiếu cách gửi trả thớt và thời hạn 5 ngày làm việc, ký sai
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

NEG = re.compile(r"không|chưa|rất tiếc|tiếc|chẳng", re.I)


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", vncheck.norm_num(text)) if s.strip()]


def main():
    text = vncheck.read("tra-loi.txt")
    if text is None:
        vncheck.finish(["chưa có /app/tra-loi.txt"])
    errs = vncheck.writing_checks(text, max_words=200, min_words=70)
    flat = vncheck.norm_num(text)
    parts = all(vncheck.has_number(text, n) for n in (160000, 35000, 260000))
    if not (vncheck.has_number(text, 455000) or parts):
        errs.append("thiếu số tiền bồi thường đúng (160.000 giao trễ + 35.000 phí vận chuyển + 260.000 thớt = 455.000)")
    for n, why in ((192000, "quên trần 10%"), (487000, "tổng sai do quên trần 10%"), (285000, "hoàn 90.000 thay vì giá trên đơn 260.000")):
        if vncheck.has_number(text, n):
            errs.append(f"có số sai {n:,}đ ({why})".replace(",", "."))
    if re.search(r"trễ\s*(7|bảy)\s*ngày|(7|bảy)\s*ngày\s*trễ", flat, re.I):
        errs.append("ghi trễ 7 ngày theo lời khách, số đúng là 6 ngày")
    if not re.search(r"(5|năm)\s*ngày\s*làm\s*việc", flat, re.I):
        errs.append("thiếu thời gian hoàn tiền 5 ngày làm việc")
    fast = (r"(trong|sau|trước)\s*(24|48)\s*(giờ|tiếng)|(?<!\d)[1-4]\s*ngày\s*làm\s*việc|"
            r"(tiền|hoàn)[^.\n]{0,50}ngay\s*(hôm nay|ngày mai|lập tức)|ngay\s*lập\s*tức")
    for s in sentences(text):
        if re.search(fast, s, re.I) and not re.search(r"(5|năm)\s*ngày\s*làm\s*việc|kể từ|tính từ", s, re.I):
            errs.append(f"hứa tiền về sớm hơn 5 ngày làm việc: «{s.strip()[:80]}»")
    if not re.search(r"gửi\s*(trả|lại)|trả\s*lại\s*(món|thớt|hàng|sản phẩm)", flat, re.I):
        errs.append("không nói khách cần gửi trả thớt nhựa")
    if not re.search(r"thớt", text, re.I):
        errs.append("không nhắc món gửi nhầm (thớt)")
    if not re.search(r"xin lỗi|rất tiếc|áy náy", text, re.I):
        errs.append("không có lời xin lỗi")
    # xưng hô
    if "anh Tùng" not in text:
        errs.append('không gọi khách là "anh Tùng"')
    if not re.search(r"(?<!\w)em(?!\w)", text, re.I):
        errs.append('không xưng "em"')
    for pat in (r"(?<!\w)tôi(?!\w)", r"(?<!\w)bạn(?!\w)", r"quý khách", r"chúng tôi", r"(?<!\w)(chị|ông|bác|cô|chú) Tùng"):
        if re.search(pat, text, re.I):
            errs.append(f"sai xưng hô (khớp «{pat}»)")
    last = [ln for ln in text.splitlines() if ln.strip()]
    if not any(re.search(r"(?<!\w)Vy(?!\w)", ln) for ln in last[-3:]):
        errs.append("không ký tên Vy ở cuối thư (trong 3 dòng cuối)")
    # không hứa ngoài chính sách: câu nhắc tới thứ chính sách cấm mà không kèm từ chối
    promised = (r"voucher|mã giảm giá|phiếu quà|quà tặng|mã ưu đãi|giảm\s*20\s*%|20\s*%", r"(?<!\d)500000(?!\d)",
                r"(hoàn|bồi thường|trả lại|đền)[^.\n]{0,60}(?<!\d)1635000(?!\d)|(?<!\d)1635000(?!\d)[^.\n]{0,60}(hoàn|bồi thường|trả lại|đền)",
                r"thiệt hại tinh thần")
    for s in sentences(text):
        if any(re.search(p, s, re.I) for p in promised) and not NEG.search(s):
            errs.append(f"có vẻ hứa điều ngoài chính sách: «{s.strip()[:80]}»")
    vncheck.finish(errs)


main()
