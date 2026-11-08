"""Chấm viet-tom-tat-so-lieu: ba con số tính đúng (đã cộng dòng bị sót), làm tròn theo đề, một đoạn, ≤150 chữ.

Tính tay từ doanh-thu.csv và ghi-chu.txt (dòng sót: Thủ Đức, 2026-09, giao-hang, 49.901.000đ):
  Quý 2 (tháng 4-6): 905.692.000đ. Quý 3 (tháng 7-9) đủ: 975.492.000đ = 975,5 triệu. Tăng 975,492 / 905,692 - 1 = 7,7068% = 7,7%.
  Quận 1: quý 3 517.113.000đ, tăng 5,1036% = 5,1%. Thủ Đức: quý 3 đủ 458.379.000đ, tăng 10,8028% = 10,8%, mạnh hơn.
  Quên dòng sót: quý 3 là 925.591.000đ = 925,6 triệu, tăng 2,2%, Thủ Đức giảm 1,3% và Quận 1 (5,1%) thành chi nhánh tăng mạnh hơn.
Mọi con số cách biên làm tròn (x,x5) hơn 0,04 điểm phần trăm nên làm tròn không mơ hồ.

Chỉ bắt khi nói Quận 1 TĂNG mạnh hơn; "Quận 1 vẫn có doanh thu cao hơn, 517,1 triệu đồng" là đúng (quý 3 Quận 1 517,1 triệu, Thủ Đức 458,4 triệu).
Tiền chấp nhận "975,5 triệu" hay "975,5 tr"; phần trăm chấp nhận "7,7%" hay "7,7 phần trăm".

Fixture (solution/dat-khac, solution/truot) chạy trong selftest.py:
  ĐẠT    1 Thủ Đức nêu trước, không nhắc Quận 1; 2 "Quận 1 vẫn có doanh thu cao hơn, 517,1 triệu đồng", "phần trăm", "975,5 tr"; 3 câu sáo
         "Trong bối cảnh... đóng vai trò quan trọng" trong đoạn nhưng đúng số liệu (văn AI không còn làm trượt)
  TRƯỢT  1 quên dòng sót (925,6 triệu, tăng 2,2%, Quận 1 mạnh hơn), nhiều đoạn, gạch đầu dòng, tiêu đề; 2 quên dòng sót, quá ngắn;
         3 đúng số nhưng xưng "tôi", mở "Chào anh Thành", hai đoạn
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", vncheck.norm_num(text)) if s.strip()]


def num(s):
    return rf"(?<![\d.,]){s}(?![\d])"


PCT = r"\s*(%|phần trăm)"


def main():
    text = vncheck.read("tom-tat.txt")
    if text is None:
        vncheck.finish(["chưa có /app/tom-tat.txt"])
    errs = vncheck.writing_checks(text, max_words=150, min_words=40)
    flat = vncheck.norm_num(text)
    body = text.strip()
    if not body.startswith("Anh Thành,"):
        errs.append('phải mở đầu bằng "Anh Thành,"')
    if not re.search(r"(?<!\w)em(?!\w)", text, re.I):
        errs.append('không xưng "em"')
    if re.search(r"(?<!\w)tôi(?!\w)", text, re.I):
        errs.append('xưng "tôi" thay vì "em"')
    if re.search(r"\n\s*\n", body):
        errs.append("phải là đúng một đoạn văn, đang có nhiều đoạn")
    if re.search(r"^\s*([-*•|#]|\d+[.)]\s)", text, re.M):
        errs.append("có gạch đầu dòng, bảng hay tiêu đề, đề bắt một đoạn văn liền")
    if not re.search(num(r"975[.,]5") + r"\s*(triệu|tr\b)", flat):
        errs.append("thiếu tổng doanh thu quý 3 đúng: 975,5 triệu đồng")
    if re.search(num(r"925[.,]6"), flat):
        errs.append("tổng 925,6 triệu là số khi quên dòng bị sót của Thủ Đức")
    pct = [s for s in sentences(text) if re.search(num(r"7[.,]7") + PCT, s)]
    if not pct:
        errs.append("thiếu phần trăm tổng đúng: 7,7%")
    elif any(re.search(r"giảm|sụt|thấp hơn|lùi", s, re.I) and not re.search(r"tăng", s, re.I) for s in pct):
        errs.append("nói 7,7% là giảm trong khi doanh thu tăng")
    if re.search(num(r"2[.,]2") + PCT, flat):
        errs.append("2,2% là số khi quên dòng bị sót")
    td = [s for s in sentences(text) if re.search(num(r"10[.,]8") + PCT, s)]
    if not td:
        errs.append("thiếu phần trăm tăng của Thủ Đức: 10,8%")
    elif not any("Thủ Đức" in s for s in td):
        errs.append("10,8% phải đi kèm tên chi nhánh Thủ Đức trong cùng câu")
    if re.search(num(r"1[.,]3") + PCT, flat):
        errs.append("giảm 1,3% của Thủ Đức là số khi quên dòng bị sót")
    for s in sentences(text):
        if re.search(r"Quận 1[^.\n]{0,60}tăng[^.\n]{0,40}(mạnh|nhanh|cao|nhiều) hơn(?![^.\n]{0,15}Quận 1)|Quận 1[^.\n]{0,40}(mạnh|nhanh) hơn", s) \
                and not re.search(r"kém|chậm|thấp|ít hơn", s, re.I):
            errs.append("nói Quận 1 tăng mạnh hơn, trong khi chi nhánh tăng mạnh hơn là Thủ Đức (nói doanh thu Quận 1 cao hơn thì không sao)")
    vncheck.finish(errs)


main()
