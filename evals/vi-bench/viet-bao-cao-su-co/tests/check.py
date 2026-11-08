"""Chấm viet-bao-cao-su-co: đủ số liệu đúng, đúng người đọc, không văn AI, có mục việc sẽ làm."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

# Số liệu tính tay từ app.log và ghi-chu.txt: sập 14:05:12, chạy lại 14:23:40 (18 phút 28 giây, làm tròn xuống 18);
# 37 dòng order_failed (đơn 88414 tới 88450); 2 khách trừ tiền hai lần, hoàn 2 × 459.000đ = 918.000đ.
JARGON = ["connection", "pool", "timeout", "database", "server", "restart", "health", "db", "log", "refund", "web-1",
          "max_connections", "order_failed", "double_charge"]


def date_re(d, m):
    """Ngày/tháng viết 10/11, 10-11 hay 10 tháng 11 (cho phép số 0 đứng trước)."""
    return rf"(?<!\d)0?{d}\s*(/|-|tháng)\s*0?{m}(?!\d)"


def main():
    text = vncheck.read("bao-cao-su-co.md")
    if text is None:
        vncheck.finish(["chưa có /app/bao-cao-su-co.md"])
    errs = vncheck.writing_checks(text, max_words=250, min_words=60)
    flat = vncheck.norm_num(text)
    if not re.search(r"14\s*(:|giờ|h)\s*0?5(?!\d)|(?<!\d)0?2\s*(:|giờ|h)\s*0?5(\s*phút)?\s*(chiều|pm)", flat, re.I):
        errs.append("thiếu giờ sập (14:05)")
    if not re.search(r"(?<!\d)18\s*phút|mười tám phút", flat, re.I):
        errs.append("thiếu thời gian sập đúng (18 phút)")
    if re.search(r"\b(19|20|17)\s*phút", flat):
        errs.append("có số phút sai (17, 19 hay 20 phút)")
    if not vncheck.has_number(text, 37):
        errs.append("thiếu số đơn không đặt được (37)")
    if vncheck.has_number(text, 38) or vncheck.has_number(text, 36):
        errs.append("có số đơn sai (36 hay 38)")
    if not re.search(r"(?<!\d)(2|hai)\s+(vị\s+|bạn\s+)?(khách|người)|(?<!\d)(2|hai)\s+trường hợp", text, re.I):
        errs.append("thiếu số khách bị trừ tiền hai lần (2 khách)")
    if not (vncheck.has_number(text, 459000) or vncheck.has_number(text, 918000)
            or re.search(r"(?<!\d)(459|918)\s*(nghìn|ngàn)", flat, re.I)):
        errs.append("thiếu số tiền đã hoàn (459.000đ mỗi khách hay 918.000đ tổng)")
    if not re.search(r"hoàn", text, re.I):
        errs.append("không nói đã hoàn tiền")
    if vncheck.has_number(text, 1240) and not re.search(r"(vào|truy cập|ghé|xem)[^.\n]{0,40}1240|1240[^.\n]{0,40}(vào|truy cập|lượt|ghé)", flat):
        errs.append("dùng 1.240 mà không nói đó là lượt khách vào trang (không phải số đơn)")
    low = vncheck.prose(text).lower()
    used = [j for j in JARGON if re.search(rf"(?<![\w-]){re.escape(j)}(?![\w-])", low)]
    if used:
        errs.append("có thuật ngữ kỹ thuật tiếng Anh: " + ", ".join(used))
    m = re.search(r"việc sẽ làm", text, re.I)
    if not m:
        errs.append('thiếu mục "Việc sẽ làm"')
    else:
        tail = text[m.end():]
        for who, (d, mth) in (("Minh", (10, 11)), ("Hà", (15, 11)), ("Tuấn", (20, 11))):
            due = f"{d}/{mth}"
            if who not in tail or not re.search(date_re(d, mth), tail):
                errs.append(f"mục Việc sẽ làm thiếu việc của {who} (hạn {due})")
        if re.search(r"^\s*#", tail, re.M):
            errs.append("mục Việc sẽ làm phải ở cuối báo cáo (sau nó còn mục khác)")
    vncheck.finish(errs)


main()
