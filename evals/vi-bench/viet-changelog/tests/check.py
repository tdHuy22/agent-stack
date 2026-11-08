"""Chấm viet-changelog: đúng phạm vi bản 2.4.0, đủ 4 + 4 + 3 ý đặt đúng mục, bỏ việc nội bộ và thứ đã gỡ.

Từ git-log.txt, giữa dòng tag v2.3.0 và v2.4.0 (ngày chốt bản: 30/10/2026):
  Thêm (4): hạn mức theo danh mục, xuất CSV, giao dịch lặp lại, widget chi tiêu hôm nay.
  Sửa (4): thoát khi mở báo cáo trống, tổng sai USD sang VND, email mã đăng nhập gửi hai lần, nút bị cắt chữ.
  Thay đổi (3): cần Android 9, báo cáo lớn mở nhanh hơn, tab "Ví" thành "Tài khoản".
Bỏ: chế độ tối (thêm rồi revert), bump React Native, ghim Node (fix nhưng là CI), prettier, refactor, unit test, docs, sửa test
chập chờn; mục tiêu tiết kiệm và lỗi chính tả (sau tag 2.4.0); tìm kiếm và lỗi đồng bộ (trước tag 2.3.0).

Mỗi ý bắt buộc phải có trong đúng mục của nó, số ý có thể nhiều hơn (tách một ý thành hai không sao). Tiêu đề đánh số kiểu "## 1. Thêm" được.
Từ "tiết kiệm" chỉ bắt khi nói tới tính năng mục tiêu tiết kiệm; chỉ số "#" bắt khi dính liền số (#412).

Fixture (solution/dat-khac, solution/truot) chạy trong selftest.py:
  ĐẠT    1 gạch đầu dòng bằng dấu sao, tiêu đề in đậm, "tiện ích" thay cho widget; 2 tiêu đề đánh số "## 1. Thêm", tách ý lỗi báo cáo thành hai
         dòng, "tiết kiệm thời gian" trong ý CSV; 3 mở bằng câu sáo "Trong bối cảnh" nhưng đủ ý
  TRƯỢT  1 ghi chế độ tối, mục tiêu tiết kiệm, "Bump React Native", Node, #412; 2 lẫn tìm kiếm (trước 2.3.0), ghi "Wallets", thiếu Android 9 và ngày;
         3 xếp ý tốc độ vào Sửa, thiếu mục Thay đổi
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

EXPECT = {
    "Thêm": [r"hạn mức|giới hạn chi|ngân sách", r"CSV", r"lặp lại|định kỳ|hằng (tuần|tháng)|hàng (tuần|tháng)",
             r"widget|tiện ích|màn hình chính"],
    "Sửa": [r"(đóng|thoát|sập|dừng|treo|lỗi)[^.\n]*báo cáo|báo cáo[^.\n]*(đóng|thoát|sập|dừng|treo|lỗi)|(chưa|không) có giao dịch|trống",
            r"USD", r"đăng nhập|hai lần|2 lần", r"nút|nhãn|chữ|màn hình nhỏ"],
    "Thay đổi": [r"Android\s*9", r"nhanh|tốc độ|mượt|giây", r"Tài khoản"],
}
BANNED = [
    (r"chế độ tối|giao diện tối|dark", "chế độ tối đã thêm rồi gỡ trong cùng bản"),
    (r"mục tiêu tiết kiệm|tiết kiệm theo mục tiêu|đặt mục tiêu", "tính năng mục tiêu tiết kiệm thuộc bản sau 2.4.0"),
    (r"chính tả", "lỗi chính tả thuộc sau bản 2.4.0"),
    (r"tìm kiếm|đồng bộ", "việc thuộc bản 2.3.0 hay việc nội bộ"),
    (r"Node|prettier|React|gradle|pipeline|đóng góp|kiểm thử|unit test|Repository|refactor|commit|merge|bump|\bci\b|SDK|\bAPI\b",
     "việc nội bộ hay thuật ngữ lập trình"),
    (r"Wallets?|Accounts?", "dùng tên tiếng Anh của tab thay vì tên tiếng Việt trong app"),
    (r"(?<!#)#\d+", "có số # tham chiếu"),
    (r"\b(?=[0-9a-f]*\d)[0-9a-f]{7}\b", "có mã commit"),
]


def sections(text, names):
    lines = text.split("\n")
    pos = {}
    for i, ln in enumerate(lines):
        h = re.sub(r"^[\s#*\-\d.)]+|[\s*:]+$", "", ln).strip().lower()
        for n in names:
            if h == n.lower() and n not in pos:
                pos[n] = i
    order = sorted(pos.items(), key=lambda kv: kv[1])
    out = {}
    for k, (n, i) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(lines)
        out[n] = "\n".join(lines[i + 1:end])
    return out, [n for n, _ in order]


def bullets(block):
    return [re.sub(r"^\s*([-*•+]|\d+[.)])\s+", "", ln) for ln in block.split("\n") if re.match(r"^\s*([-*•+]|\d+[.)])\s+", ln)]


def main():
    text = vncheck.read("CHANGELOG.md")
    if text is None:
        vncheck.finish(["chưa có /app/CHANGELOG.md"])
    errs = vncheck.writing_checks(text, max_words=200, min_words=50)
    flat = vncheck.norm_num(text)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not (re.search(r"2\.4\.0", first) and re.search(r"(?<!\d)30\s*/\s*0?10\s*/\s*2026|(?<!\d)30\s*tháng\s*10", first)):
        errs.append("dòng đầu phải có bản 2.4.0 và ngày 30/10/2026")
    names = list(EXPECT)
    sec, order = sections(text, names)
    miss = [n for n in names if n not in sec]
    if miss:
        errs.append("thiếu mục: " + ", ".join(miss))
    elif order != names:
        errs.append("ba mục không đúng thứ tự Thêm, Sửa, Thay đổi")
    for n, pats in EXPECT.items():
        if n not in sec:
            continue
        bl = bullets(sec[n])
        if not bl:
            errs.append(f"mục {n} không có ý nào (dùng gạch đầu dòng)")
        for p in pats:
            if not any(re.search(p, b, re.I) for b in bl):
                errs.append(f"mục {n} thiếu ý khớp «{p}»")
    for pat, why in BANNED:
        m = re.search(pat, flat, re.I)
        if m:
            errs.append(f"{why}: «{m.group(0)}»")
    vncheck.finish(errs)


main()
