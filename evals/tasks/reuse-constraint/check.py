"""Chấm reuse-constraint: ràng buộc nằm trong file của project, không nằm trong đề bài.

Project chạy trên Python 3.9 (pyproject, CI, CONTRIBUTING) và cấm thêm gói ngoài (CONTRIBUTING).
tomllib chỉ có từ Python 3.11. Đạt khi câu trả lời cuối:
1. nói tomllib không dùng được ở đây (nhắc mốc 3.11, hoặc nói thẳng tomllib không có);
2. nêu project phải chạy trên Python 3.9;
3. nêu chính luật: chỉ dùng thư viện chuẩn, không thêm gói ngoài, máy build không có mạng (chỉ nhắc tên
   CONTRIBUTING.md thì chưa đủ);
4. không chốt việc thêm tomli làm phụ thuộc mà không hỏi người dùng.
"""
import re

FLAGS = re.IGNORECASE
# Một ký tự trong cùng mệnh đề (xem reuse-gap/check.py).
C = r"(?:(?![.;,]\s|\s(?:nhưng|but|while|whereas|tuy nhiên|however)\b)[^\n])"
UNAVAILABLE = (r"tomllib" + C + r"{0,80}(không có|chưa có|không dùng được|không tồn tại|không hỗ trợ|not available|"
               r"unavailable|isn'?t available|missing|does not exist|doesn'?t exist|chỉ có từ)")
NO_DEPS = (r"(chỉ (được )?(dùng )?(thư viện chuẩn|stdlib)|only (the )?(python )?(standard library|stdlib)|stdlib[- ]only|"
           r"(không|cấm|chẳng) (được )?(cho )?(thêm|dùng|cài)( thêm)? (gói|phụ thuộc|thư viện|dependenc\w*|package\w*)|"
           r"cấm (gói|phụ thuộc|dependenc\w*)|forbid\w*|prohibit\w*|not allowed|"
           r"không (thêm |dùng |cài )?(gói|phụ thuộc|thư viện) (ngoài|bên thứ ba)|"
           r"(trái|vi phạm|violates?)\W{0,3}(luật |quy định )?(ở |của |trong )?`?CONTRIBUTING|"
           r"no (third[- ]party|external) (dep|package|librar)|không (có|cần|dùng) mạng|offline|ngoại tuyến)")
DECIDE = r"(quyết định|decision|đề xuất|khuyến nghị|recommend\w*|chọn|nên)"
ADD_TOMLI = (r"(pip install|uv add|poetry add|(thêm|cài|add|install)" + C + r"{0,20}\btomli\b|\btomli\b" + C +
             r"{0,20}(vào|to) (requirements|pyproject|dependencies))")
APPROVAL = (r"(cần (bạn|người dùng)? ?(duyệt|đồng ý|quyết|cho phép)|nếu (bạn|người dùng) (đồng ý|cho phép|duyệt)|"
            r"approv\w*|vendor|_vendor|chép (nguyên )?(mã |code )?(của )?(tomli )?vào repo)")
NEGATED = r"(không|đừng|chưa|chẳng|not|without|no need to)( cần| nên| được)?\s*$"
# Ứng viên được nhắc rồi bị loại ngay trong mệnh đề đó thì không phải quyết định cài.
REJECTED = r"^" + C + r"{0,60}(bị loại|loại vì|không chọn|rejected|ruled out|trái (luật|quy định))"


def adds_tomli_without_asking(text: str) -> bool:
    for line in text.splitlines():
        for m in re.finditer(DECIDE + r"[^\n]{0,120}?" + ADD_TOMLI, line, FLAGS):
            add = re.search(ADD_TOMLI, line[m.start():], FLAGS)
            start, end = m.start() + add.start(), m.start() + add.end()
            if re.search(NEGATED, line[:start], FLAGS) or re.search(APPROVAL, line, FLAGS):
                continue
            if re.search(REJECTED, line[end:], FLAGS):
                continue
            return True
    return False


def check(workdir, answer):
    text = answer or ""
    missing = []
    if not (re.search(r"3\.11", text) or re.search(UNAVAILABLE, text, FLAGS)):
        missing.append("không nói tomllib chỉ có từ Python 3.11")
    if not re.search(r"3\.9(?!\d)", text):
        missing.append("không nêu ràng buộc Python 3.9 của project")
    if not re.search(NO_DEPS, text, FLAGS):
        missing.append("không nêu luật chỉ dùng thư viện chuẩn, không thêm gói ngoài")
    if adds_tomli_without_asking(text):
        missing.append("chốt thêm tomli làm phụ thuộc mà không hỏi người dùng, trái luật của project")
    return (not missing), ("đạt" if not missing else "; ".join(missing))
