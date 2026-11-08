"""Chấm viet-bien-ban-hop: biên bản đủ ba mục, quyết định cuối cùng, việc có người và hạn đúng, bỏ ý bị bác.

Số liệu đọc từ ghi-am.txt (họp thứ Ba 10/11/2026): tiền quảng cáo chốt 65 triệu (đã nêu 80 và 50); ra mắt 27/11 (cũ 20/11);
giữ nhà in An Phú (Hưng Phát bị bác); 500 tờ rơi (Quân nêu 1.000). Hạn: Thu ảnh thứ Sáu tuần này = 13/11 (Thu xin thứ Hai
tuần sau = 16/11); Minh đặt in thứ Năm này = 12/11 (giao Đạt rồi đổi cho Minh vì Đạt nghỉ phép); Quân trang đích thứ Tư tuần
sau = 18/11; Hạnh trình ngân sách thứ Ba tuần sau = 17/11. Câu hỏi mở: ai duyệt nội dung bài đăng; có thuê thêm người đóng gói.

Tiền chấp nhận "65 triệu", "65.000.000 đồng", "65tr"; số 500 tờ nằm ở mục Quyết định hoặc Việc cần làm; ngày viết 13/11 hay 13 tháng 11.

Fixture (solution/dat-khac, solution/truot) chạy trong selftest.py:
  ĐẠT    1 tiêu đề in đậm có số thứ tự, ngày "13 tháng 11", nhắc Đạt kèm Minh; 2 "65.000.000 đồng", "500 tờ" ở mục Quyết định; 3 "65tr",
         mở bằng câu sáo "Trong bối cảnh" và kết "Tóm lại" nhưng số liệu đủ (văn AI không còn làm trượt)
  TRƯỢT  1 ghi cả Hưng Phát, TikTok, 20/11 và hạn không đổi ra ngày; 2 ngân sách 80 triệu, hạn Thu 16/11, giao Đạt, thiếu Minh; 3 thiếu mục Câu hỏi còn mở
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

NAMES = {"Thu": "13/11", "Minh": "12/11", "Quân": "18/11", "Hạnh": "17/11"}
STALE = [r"Hưng\s*Phát", r"TikTok", r"(?<![\d.,])80\s*(triệu|tr\b)|(?<!\d)80000000", r"(?<![\d.,])50\s*(triệu|tr\b)|(?<!\d)50000000",
         r"(?<!\d)0?20\s*(/|tháng)\s*0?11(?!\d)", r"(?<!\d)1\s*000(?!\d)"]


def date_re(dm):
    d, m = dm.split("/")
    return rf"(?<!\d)0?{int(d)}\s*(/|-|tháng)\s*0?{int(m)}(?!\d)"


def sections(text, names):
    """{tên: nội dung}: tìm dòng tiêu đề (bỏ #, *, số thứ tự, dấu hai chấm) khớp tên, cắt tới tiêu đề kế."""
    lines = text.split("\n")
    pos = {}
    for i, ln in enumerate(lines):
        h = re.sub(r"^[\s#*\-\d.)]+|[\s*:]+$", "", ln).strip().lower()
        for n in names:
            if h == n.lower() and n not in pos:
                pos[n] = i
    out = {}
    order = sorted(pos.items(), key=lambda kv: kv[1])
    for k, (n, i) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(lines)
        out[n] = "\n".join(lines[i + 1:end])
    return out, [n for n, _ in order]


def main():
    text = vncheck.read("bien-ban.md")
    if text is None:
        vncheck.finish(["chưa có /app/bien-ban.md"])
    errs = vncheck.writing_checks(text, max_words=300, min_words=60)
    names = ["Quyết định", "Việc cần làm", "Câu hỏi còn mở"]
    sec, order = sections(text, names)
    miss = [n for n in names if n not in sec]
    if miss:
        errs.append("thiếu mục: " + ", ".join(miss))
    elif order != names:
        errs.append("ba mục không đúng thứ tự Quyết định, Việc cần làm, Câu hỏi còn mở")
    flat = vncheck.norm_num(text)
    for pat in STALE:
        if re.search(pat, flat, re.I):
            errs.append(f"có ý đã bị bác hay số đã đổi (khớp «{pat}»)")
    if "Quyết định" in sec:
        q = vncheck.norm_num(sec["Quyết định"])
        if not re.search(r"(?<![\d.,])65\s*(triệu|tr\b)|(?<!\d)65000000(?!\d)", q):
            errs.append("mục Quyết định thiếu ngân sách 65 triệu")
        if not re.search(date_re("27/11"), q):
            errs.append("mục Quyết định thiếu ngày ra mắt 27/11")
        if "An Phú" not in q:
            errs.append("mục Quyết định thiếu việc giữ nhà in An Phú")
    if "Việc cần làm" in sec:
        acts = [ln for ln in sec["Việc cần làm"].split("\n") if ln.strip()]
        for who, due in NAMES.items():
            mine = [ln for ln in acts if re.search(rf"(?<!\w){who}(?!\w)", ln)]
            if not mine:
                errs.append(f"mục Việc cần làm thiếu việc của {who}")
            elif not any(re.search(date_re(due), ln) for ln in mine):
                errs.append(f"việc của {who} sai hạn (cần {due})")
            elif any(re.search(date_re("16/11"), ln) for ln in mine):
                errs.append(f"việc của {who} còn ghi hạn 16/11 mà Hạnh đã bác")
        for ln in acts:
            if re.search(r"(?<!\w)Đạt(?!\w)", ln) and not re.search(r"(?<!\w)Minh(?!\w)", ln):
                errs.append("giao việc cho Đạt trong khi Đạt nghỉ phép và việc đã chuyển cho Minh")
        if not vncheck.has_number("\n".join(acts) + "\n" + sec.get("Quyết định", ""), 500):
            errs.append("thiếu số lượng 500 tờ rơi (ở mục Quyết định hoặc Việc cần làm)")
    if "Câu hỏi còn mở" in sec:
        o = sec["Câu hỏi còn mở"]
        if not re.search(r"duyệt", o, re.I):
            errs.append("câu hỏi mở thiếu việc ai duyệt nội dung bài đăng")
        if not re.search(r"đóng gói", o, re.I):
            errs.append("câu hỏi mở thiếu việc có thuê thêm người đóng gói không")
    vncheck.finish(errs)


main()
