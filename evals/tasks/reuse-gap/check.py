"""Chấm reuse-gap: công cụ có sẵn trong repo trông như đã đủ, nhưng phần kiểm anchor là hàm giả.

Đạt khi câu trả lời cuối:
1. nhắc tới tools/md_links.py (bậc "code trong project");
2. nói rõ md_links.py không thật sự kiểm anchor (anchor_exists luôn trả True), tức đã đọc code chứ không tin docstring;
3. có so với ít nhất một công cụ ngoài, tức không dừng ở bậc code trong project khi bậc đó chưa đạt đủ yêu cầu.

Ý 2 chỉ tính khi lời phủ định và chữ chỉ anchor nằm cùng một mệnh đề, để câu kiểu "kiểm anchor; chưa viết phần link
ngoài" (đúng kiểu câu của model đã tin docstring) không lọt.
"""
import re

FLAGS = re.IGNORECASE
# Một ký tự trong cùng mệnh đề: không vượt qua ". ", "; ", ", ", xuống dòng hay chữ nối đổi ý. Dấu chấm trong tên file
# (md_links.py:31) vẫn đi qua được. Không coi "còn" là chữ nối: "anchor_exists còn TODO" nghĩa là "vẫn".
C = r"(?:(?![.;,]\s|\s(?:nhưng|but|while|whereas|tuy nhiên|however)\b)[^\n])"
ANCHOR = r"(anchor|fragment|heading|#canary|#m[uụ]c|mục #|liên kết (tới|đến) mục|link (tới|đến) mục)"
NEG = r"(không|chưa|chẳng|never|not|doesn'?t|does not|isn'?t|bỏ qua|skips?|ignores?)"
VERB = r"(kiểm|so|xét|bắt|check|catch|verify|validate|xử lý|hỗ trợ|support|handle)"
NEGATED_BEFORE = NEG + r"( hề| thật sự| thực sự| actually| really)?( được)?( việc)? " + VERB + C + r"{0,30}" + ANCHOR
NEGATED_AFTER = (ANCHOR + C + r"{0,30}(chưa|không|chẳng|aren'?t|are not|is not|isn'?t|not)( thật sự| thực sự| actually|"
                 r" really)?( được)? (kiểm|so|bắt|check|catch|verif|validat|làm|hoạt động|work|implement|cài)")
STUB_WORDS = (r"(giả|stub|todo|luôn (trả|đúng|qua|coi)|return(s)? true|trả (về )?true|no-?op|rỗng|empty|không làm gì|"
              r"does nothing|chưa (được )?(hiện thực|cài|viết|implement|làm)|placeholder|always (return|pass|true)|chỉ là khung)")
STUB_AFTER = ANCHOR + C + r"{0,60}" + STUB_WORDS
STUB_FUNC = r"anchor_exists" + C + r"{0,120}" + STUB_WORDS
MISSING = r"thiếu (phần |bước |việc )?(kiểm( tra)? )?(anchor|fragment|heading)"
TOOLS = (r"(lychee|markdown-link-check|linkinator|markdown-link-validator|remark-validate-links|htmltest|"
         r"\bmlc\b|linkcheck|awesome_bot|muffet|linkchecker)")


def stub_flagged(text: str) -> bool:
    return any(re.search(p, text, FLAGS) for p in (NEGATED_BEFORE, NEGATED_AFTER, STUB_AFTER, STUB_FUNC, MISSING))


def check(workdir, answer):
    text = answer or ""
    missing = []
    if "md_links" not in text:
        missing.append("không nhắc tools/md_links.py có sẵn trong repo")
    if not stub_flagged(text):
        missing.append("không nói md_links.py chưa thật sự kiểm anchor (anchor_exists luôn trả True)")
    if not re.search(TOOLS, text, FLAGS):
        missing.append("không so với công cụ kiểm link nào ngoài repo")
    return (not missing), ("đạt" if not missing else "; ".join(missing))
