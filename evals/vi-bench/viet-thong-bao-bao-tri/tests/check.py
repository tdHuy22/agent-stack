"""Chấm viet-thong-bao-bao-tri: đổi UTC sang giờ Việt Nam đúng (qua ngày), thời lượng, đủ ảnh hưởng, không thuật ngữ.

Từ ghi-chu-ky-thuat.txt (bản chốt; bản nháp 16:00-19:00 UTC đã hủy): 17:30 UTC ngày 14/11 = 00:30 ngày 15/11 (Chủ nhật) giờ Việt
Nam (UTC+7, qua ngày); 20:15 UTC = 03:15 ngày 15/11; thời lượng 2 giờ 45 phút. Thẻ, ví điện tử, chuyển khoản QR không dùng được;
đơn thanh toán khi nhận hàng vẫn đặt được; đăng nhập bình thường; email xác nhận chậm tối đa 30 phút; điểm thưởng cộng chậm nhất
00:00 UTC ngày 15/11 = 07:00 ngày 15/11; hotline 1900 6868. Xưng "chúng mình", gọi "bạn". Tiêu đề dòng đầu tối đa 12 chữ.

Ngày 15/11 hay "Chủ nhật" có thể nằm ở câu khác với giờ 00:30; chỉ sai khi giờ bắt đầu đi với ngày 14/11 mà không có 15/11. Giờ cộng điểm thưởng nằm
ở câu nói về điểm thưởng hoặc câu liền sau. "Tiền mặt khi nhận hàng" và "mail" được. Dấu hiệu văn AI không còn làm trượt.

Fixture (solution/dat-khac, solution/truot) chạy trong selftest.py:
  ĐẠT    1 giờ viết "0 giờ 30 đến 3 giờ 15", tiêu đề không có chữ "bảo trì"; 2 ngày 15/11 ở tiêu đề và câu riêng, "0h30", "2 tiếng 45 phút", "mail",
         điểm thưởng và giờ 7 giờ ở hai câu liền nhau; 3 mở bằng "Trong bối cảnh" nhưng đủ số liệu (văn AI không còn làm trượt)
  TRƯỢT  1 giữ giờ UTC, nhắc "failover" và "payments-svc"; 2 quên qua ngày (14/11), 3 tiếng, "quý khách", thiếu điểm thưởng, hotline;
         3 nói chung "thanh toán online", thiếu điểm thưởng và hotline, tiêu đề dài
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

JARGON = ["utc", "gmt", "failover", "postgres", "database", "downtime", "api", "server", "svc", "queue", "gateway", "cdn",
          "cache", "cluster", "cod", "maintenance", "uptime", "service", "payments", "auth", "loyalty", "orders", "notify"]
START = r"(?<!\d)0{1,2}\s*(:|h|giờ)\s*30(?!\d)"
END = r"(?<!\d)0?3\s*(:|h|giờ)\s*15(?!\d)"


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", vncheck.norm_num(text)) if s.strip()]


def main():
    text = vncheck.read("thong-bao.txt")
    if text is None:
        vncheck.finish(["chưa có /app/thong-bao.txt"])
    errs = vncheck.writing_checks(text, max_words=180, min_words=60)
    flat = vncheck.norm_num(text)
    low = vncheck.prose(text).lower()
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if len(vncheck.words(first)) > 12:
        errs.append(f"tiêu đề dòng đầu dài {len(vncheck.words(first))} chữ, tối đa 12")
    if not re.search(START, flat):
        errs.append("thiếu giờ bắt đầu theo giờ Việt Nam (00:30)")
    else:
        # sai khi câu có giờ bắt đầu chỉ gắn với ngày 14/11 (quên qua ngày); ngày 15/11 hay Chủ nhật có thể nằm ở câu khác
        for s in (s for s in sentences(text) if re.search(START, s)):
            if re.search(r"(?<!\d)0?14\s*(/|tháng)\s*0?11(?!\d)", s) and not re.search(r"(?<!\d)15\s*(/|tháng)\s*0?11|chủ nhật|rạng sáng", s, re.I):
                errs.append("giờ bắt đầu 00:30 đi kèm ngày 14/11, phải là ngày 15/11 (đã qua ngày mới)")
    if not re.search(END, flat):
        errs.append("thiếu giờ kết thúc theo giờ Việt Nam (03:15)")
    if not re.search(r"(?<!\d)15\s*(/|tháng)\s*0?11", flat):
        errs.append("thiếu ngày 15/11")
    if not re.search(r"(?<!\d)2\s*(giờ|tiếng|h)\s*45|(?<!\d)165\s*phút|2[.,]75\s*(giờ|tiếng)|hai\s*(giờ|tiếng)\s*(rưỡi\s*cộng\s*)?bốn mươi lăm", flat, re.I):
        errs.append("thiếu thời lượng đúng (2 giờ 45 phút)")
    if re.search(r"(?<!\d)(17|20)\s*(:|h|giờ)\s*(30|15)(?!\d)", flat):
        errs.append("còn giờ UTC (17:30 hay 20:15)")
    for kw, why in ((r"thẻ", "thẻ"), (r"ví điện tử", "ví điện tử"), (r"chuyển khoản|QR", "chuyển khoản QR")):
        if not re.search(kw, text, re.I):
            errs.append(f"không nói rõ cách thanh toán không dùng được: {why}")
    if not re.search(r"khi nhận hàng|tiền mặt", text, re.I):
        errs.append("không nói đơn thanh toán khi nhận hàng vẫn đặt được")
    if not re.search(r"đăng nhập", text, re.I):
        errs.append("không nói đăng nhập vẫn dùng bình thường")
    if not (re.search(r"e-?mail|(?<!\w)mail|thư điện tử", text, re.I) and re.search(r"(?<!\d)30\s*phút", flat)):
        errs.append("thiếu chuyện email xác nhận đến chậm tối đa 30 phút")
    if not re.search(r"điểm\s*thưởng", text, re.I):
        errs.append("không nhắc điểm thưởng")
    else:
        ss = sentences(text)
        ok = any(re.search(r"điểm\s*thưởng", s, re.I) and any(re.search(r"(?<!\d)0?7\s*(:\s*00|h|giờ)", x) for x in ss[i:i + 2])
                 for i, s in enumerate(ss))
        if not ok:
            errs.append("câu về điểm thưởng thiếu giờ cộng điểm theo giờ Việt Nam (07:00 ngày 15/11)")
    if not re.search(r"1900\s*6868", flat):
        errs.append("thiếu số hotline 1900 6868")
    used = [j for j in JARGON if re.search(rf"(?<![\w-]){re.escape(j)}(?![\w-])", low)]
    if used:
        errs.append("có thuật ngữ kỹ thuật hay tên dịch vụ: " + ", ".join(used))
    if not re.search(r"chúng mình", text, re.I):
        errs.append('không xưng "chúng mình"')
    if not re.search(r"(?<!\w)bạn(?!\w)", text, re.I):
        errs.append('không gọi khách là "bạn"')
    for pat in (r"quý khách", r"chúng tôi", r"(?<!\w)tôi(?!\w)", r"(?<!\w)anh/chị"):
        if re.search(pat, text, re.I):
            errs.append(f"sai xưng hô (khớp «{pat}»)")
    vncheck.finish(errs)


main()
