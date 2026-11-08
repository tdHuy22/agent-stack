"""Chấm viet-tra-loi-ticket: ba bản trả lời đúng tài liệu, đúng tên nút, không bịa tính năng.

Từ faq.txt và tickets.txt (hôm nay 06/11/2026):
  #2041 chị Mai: mã gửi 14:10, giờ 14:35 là 25 phút > 15 phút nên hết hạn; "Quên mật khẩu?" rồi "Gửi mã" lấy mã mới.
  #2042 anh Phúc: gói Cơ bản tối đa 3 (không tính chủ), đã đủ 3, muốn thêm 2 là 5 người; nâng lên "Chuyên nghiệp" (10 người, 199.000đ):
        Cài đặt > "Gói dịch vụ" > "Nâng cấp".
  #2043 chị Oanh: xóa ngày 28/09, 39 ngày > 30 ngày nên KHÔNG khôi phục được, tạo mới bằng "Thêm sản phẩm"; MISA chưa hỗ trợ, chỉ
        cách "Báo cáo" > kỳ "Tháng trước" (tháng 10) > "Xuất file" > "Excel".

Câu giải thích chính sách ("chỉ khôi phục được trong vòng 30 ngày", "Tài liệu cho khôi phục trong 30 ngày, còn sản phẩm của chị xóa 39 ngày") và
"để dùng với MISA, chị làm như sau" không bị coi là hứa; chỉ bắt khi chỉ thao tác không có (bấm/chọn "Khôi phục" cho sản phẩm quá hạn,
"em sẽ khôi phục", chọn/xuất thẳng sang MISA mà không đi qua Excel). Kỳ báo cáo chấp nhận "Tháng trước" hay "Tùy chọn".

Fixture (solution/dat-khac, solution/truot) chạy trong selftest.py:
  ĐẠT    1 tiêu đề in đậm kèm tên khách, nói "39 ngày", đặt giá trước; 2 câu giải thích chính sách không phủ định, "để dùng với MISA, chị làm như sau",
         tháng 10 chọn "Tùy chọn"; 3 mở bằng "Chắc chắn rồi!" (văn AI không còn làm trượt) nhưng đúng mọi nút, số và phủ định
  TRƯỢT  1 hứa nút "Xuất MISA", chỉ "Khôi phục", gói "Doanh nghiệp", giá 250.000đ, đếm 6 nhân viên; 2 chỉ cách khôi phục sản phẩm 39 ngày, nói 6 nhân viên,
         không nói kỳ báo cáo; 3 thiếu "Gửi mã", không nêu giá 199.000đ, thiếu tên chị Oanh và kỳ báo cáo
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

NEG = re.compile(r"không|chưa|chẳng|quá|hết|vĩnh viễn|tiếc", re.I)


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", vncheck.norm_num(text)) if s.strip()]


def split_tickets(text):
    pos = {}
    for tid in ("2041", "2042", "2043"):
        m = re.search(rf"#?\s?{tid}(?!\d)", text)
        if m:
            pos[tid] = m.start()
    order = sorted(pos.items(), key=lambda kv: kv[1])
    out = {}
    for k, (tid, i) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(text)
        out[tid] = text[i:end]
    return out


def need(errs, sec, pat, why, flags=0, tid=""):
    if not re.search(pat, sec, flags):
        errs.append(f"#{tid}: {why}")


def main():
    text = vncheck.read("tra-loi-ticket.md")
    if text is None:
        vncheck.finish(["chưa có /app/tra-loi-ticket.md"])
    errs = vncheck.writing_checks(text, max_words=330, min_words=90)
    secs = split_tickets(text)
    for tid in ("2041", "2042", "2043"):
        if tid not in secs:
            errs.append(f"thiếu mục cho ticket #{tid}")
    if len(secs) == 3:
        a, b, c = secs["2041"], secs["2042"], secs["2043"]
        flat_a, flat_b, flat_c = (vncheck.norm_num(x) for x in (a, b, c))
        # 2041
        need(errs, a, "chị Mai", "không gọi chị Mai", tid="2041")
        need(errs, a, "Quên mật khẩu", 'thiếu nút/liên kết "Quên mật khẩu?"', tid="2041")
        need(errs, a, "Gửi mã", 'thiếu nút "Gửi mã" để lấy mã mới', tid="2041")
        need(errs, flat_a, r"(?<!\d)15\s*phút", "thiếu thời hạn mã 15 phút", tid="2041")
        # 2042
        need(errs, b, "anh Phúc", "không gọi anh Phúc", tid="2042")
        for pat, why in (("Gói dịch vụ", 'thiếu mục "Gói dịch vụ"'), ("Nâng cấp", 'thiếu nút "Nâng cấp"'),
                         ("Chuyên nghiệp", 'thiếu gói "Chuyên nghiệp"')):
            need(errs, b, pat, why, tid="2042")
        if not (vncheck.has_number(b, 3) and vncheck.has_number(b, 10)):
            errs.append("#2042: thiếu giới hạn 3 nhân viên của gói Cơ bản và 10 của gói Chuyên nghiệp")
        if not vncheck.has_number(b, 199000):
            errs.append("#2042: khách hỏi giá, thiếu 199.000đ")
        if re.search(r"(?<!\d)(6|sáu)\s*(nhân viên|người|bạn)", flat_b, re.I):
            errs.append("#2042: đếm sai, 3 nhân viên hiện có cộng 2 là 5, không phải 6")
        # 2043
        need(errs, c, "chị Oanh", "không gọi chị Oanh", tid="2043")
        for pat, why in (("Xuất file", 'thiếu nút "Xuất file"'), ("Excel", 'thiếu lựa chọn "Excel"'),
                         ("Tháng trước|Tùy chọn", 'thiếu kỳ "Tháng trước" (hay "Tùy chọn") cho tháng 10'), ("Thêm sản phẩm", 'thiếu nút "Thêm sản phẩm" để tạo lại')):
            need(errs, c, pat, why, tid="2043")
        if not vncheck.has_number(c, 30):
            errs.append("#2043: thiếu hạn khôi phục 30 ngày")
        for s in sentences(c):
            neg = NEG.search(s)
            # chỉ bắt khi chỉ thao tác không có: bấm/chọn "Khôi phục" cho sản phẩm quá hạn, hứa tự khôi phục, hay xuất thẳng sang MISA
            if not neg and re.search(r"(bấm|chọn|nhấn|vào)[^.\n]{0,30}Khôi phục|(em|bên em|chúng em|hỗ trợ)[^.\n]{0,20}sẽ\s+khôi phục", s):
                errs.append(f"#2043: chỉ cách khôi phục hay hứa khôi phục sản phẩm đã quá 30 ngày: «{s.strip()[:70]}»")
            if not neg and not re.search(r"Excel|nhập", s, re.I) and (
                    re.search(r"(bấm|chọn|nhấn)[^.\n]{0,30}(MISA|Google Sheets)", s)
                    or re.search(r"xuất\s+(thẳng\s+|trực tiếp\s+)?(sang|ra|qua|vào)\s+(file\s+)?(MISA|Google Sheets)", s, re.I)):
                errs.append(f"#2043: có vẻ nói xuất thẳng sang MISA được: «{s.strip()[:70]}»")
    # không bịa gói, giá, nút
    if re.search(r"gói\s+(Doanh nghiệp|Premium|Nâng cao|Cao cấp|Pro|Miễn phí|Plus|VIP)\b", text, re.I):
        errs.append("bịa tính năng: gói không có trong tài liệu")
    for s in sentences(text):
        if re.search(r"Xuất MISA", s) and not NEG.search(s):
            errs.append('bịa tính năng: nút "Xuất MISA" không tồn tại')
        if re.search(r"Thùng rác", s) and not NEG.search(s):
            errs.append('bịa tính năng: mục "Thùng rác" không có')
    for m in re.finditer(r"(\d{1,3}(?:[.,]\d{3})+)\s*(?:đ|đồng|VND)", text):
        if vncheck.norm_num(m.group(1)) != "199000":
            errs.append(f"có giá không có trong tài liệu: {m.group(0)}")
    vncheck.finish(errs)


main()
