"""Chấm reuse-stdlib: ca đối chứng, thư viện chuẩn là đủ (hashlib, os/pathlib, filecmp).

Bản sửa của reuse-best không được làm skill đẩy việc nhỏ sang thêm phụ thuộc. Đạt khi câu trả lời cuối chọn cách
dùng thư viện chuẩn, và không chốt việc thêm gói hay công cụ ngoài (lệnh cài, hoặc "thêm … vào requirements").
Câu có phủ định ("không cần pip install gì thêm") không tính là chốt cài.
"""
import re

FLAGS = re.IGNORECASE
# Một ký tự trong cùng mệnh đề (xem reuse-gap/check.py).
C = r"(?:(?![.;,]\s|\s(?:nhưng|but|while|whereas|tuy nhiên|however)\b)[^\n])"
STDLIB = r"\b(hashlib|filecmp|sha-?256|sha1|blake2b?|md5)\b"
# Câu quyết định có thể nói thẳng "bằng thư viện chuẩn" mà chữ hashlib nằm xa ở phần cách làm (eval 07/10/2026).
STDLIB_CHOICE = r"(\b(hashlib|filecmp|sha-?256|sha1|blake2b?|md5)\b|thư viện chuẩn|standard library|\bstdlib\b)"
REJECT_STDLIB = r"(không|chẳng|đừng) (dùng|chọn) (thư viện chuẩn|stdlib|hashlib)"
DECIDE = (r"(quyết định|decision|chọn|khuyến nghị|đề xuất|recommend|nên dùng|nên tự viết|tự viết|"
          r"dùng thư viện chuẩn)")
DEP_ADD = (r"(pip install|uv add|poetry add|pipx install|brew install|apt(-get)? install|npm install|cargo install|"
           r"(thêm|add)( dependency| phụ thuộc| gói| thư viện)?" + C + r"{0,40}(vào|to) (requirements|pyproject|"
           r"dependencies|package\.json))")
NEGATED = r"(không|chưa|đừng|chẳng|không phải|not|no need to|without|khỏi)( cần| nên| phải)?( dùng| chạy)?\s*$"
# Ứng viên được nhắc rồi bị loại ngay trong mệnh đề đó thì không phải quyết định cài.
REJECTED = r"^" + C + r"{0,60}(bị loại|loại vì|không chọn|rejected|ruled out|trái (luật|quy định))"


def near(text: str, a: str, b: str, window: int) -> bool:
    spans_a = [m.start() for m in re.finditer(a, text, FLAGS)]
    spans_b = [m.start() for m in re.finditer(b, text, FLAGS)]
    return any(abs(x - y) <= window for x in spans_a for y in spans_b)


def decides_to_add_dependency(text: str) -> bool:
    """Trên cùng một dòng có chữ quyết định, rồi trong 120 ký tự sau đó là việc thêm gói không bị phủ định.
    Nhắc fdupes như một ứng viên bị loại (trước chữ quyết định) thì không tính."""
    for line in text.splitlines():
        for decide in re.finditer(DECIDE, line, FLAGS):
            tail = line[decide.end():decide.end() + 120]
            for add in re.finditer(DEP_ADD, tail, FLAGS):
                if re.search(NEGATED, line[:decide.end() + add.start()], FLAGS):
                    continue
                if re.search(REJECTED, tail[add.end():], FLAGS):
                    continue
                return True
    return False


def check(workdir, answer):
    text = answer or ""
    missing = []
    if not re.search(STDLIB, text, FLAGS):
        missing.append("không dùng cách của thư viện chuẩn (hashlib, filecmp)")
    elif not near(text, DECIDE, STDLIB_CHOICE, 250) or re.search(REJECT_STDLIB, text, FLAGS):
        missing.append("có nhắc hashlib/filecmp nhưng quyết định không chọn thư viện chuẩn")
    if decides_to_add_dependency(text):
        missing.append("quyết định thêm gói ngoài cho một việc thư viện chuẩn làm được")
    return (not missing), ("đạt" if not missing else "; ".join(missing))
