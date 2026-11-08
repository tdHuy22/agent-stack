"""Thư viện chấm chung cho bộ bài tiếng Việt (vi-bench). Chỉ thư viện chuẩn.

Mỗi bài chép nguyên file này vào tests/vncheck.py (selftest.py kiểm bản chép giống hệt bản gốc ở _lib/), vì lúc chấm Harbor
chỉ đưa thư mục tests/ của bài vào container. Đường dẫn bài làm lấy từ biến APP_DIR (mặc định /app), để selftest.py chạy
được trên máy không có Docker.

Mẫu "văn AI" (TELLS) chép cố định từ plugin/skills/writing-voice/scripts/tells.py ngày 08/11/2026, chỉ phần tiếng Việt và chỉ
regex: bộ đo không đổi theo skill, nên kết quả các đợt so được với nhau. TELLS KHÔNG quyết định đạt hay trượt (bạn chốt
08/11/2026): ba cấu hình có agent-stack thấy đúng danh sách này qua skill writing-voice, bản trơn thì không, nên chấm trượt theo
nó là chấm vòng. Số lần gặp được ghi thành chỉ số phụ "van_ai" (record_metrics) để so riêng giữa các cấu hình.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from pathlib import Path

TELLS = [
    ('vi-mo-bai-sao', 'mở bài sáo',
     '^\\s*(trong bối cảnh|trong thời đại|ngày nay,|trong thế giới[^.]{0,40}ngày nay|hãy cùng (khám phá|tìm hiểu))'),
    ('vi-khong-chi-ma-con', 'cấu trúc khuôn mẫu',
     'không (chỉ|những)[^.]{1,80}mà còn'),
    ('vi-thoi-phong', 'thổi phồng',
     'đóng (một )?vai trò (vô cùng |cực kỳ |hết sức )?(quan trọng|then chốt|chủ chốt|thiết yếu)|không thể phủ nhận|vô cùng quan trọng|mang lại (những )?(giá trị|lợi ích) (to lớn|vượt trội)|đa dạng và phong phú|nâng tầm|bước ngoặt|giải pháp toàn diện|tối ưu hóa (tối đa|hiệu quả)|một cách (hiệu quả|toàn diện|sâu sắc|tối ưu)'),
    ('vi-hanh-trinh', 'ẩn dụ sáo',
     '\\bhành trình\\b|\\bkhám phá\\b|\\bchìa khóa\\b|\\bngọn hải đăng\\b|\\bbức tranh toàn cảnh\\b'),
    ('vi-ket-sao', 'kết bài sáo',
     '^\\s*(tóm lại|nhìn chung|tổng kết lại|có thể nói|như vậy,? có thể thấy|nói tóm lại)\\b'),
    ('vi-thach-thuc', 'kết bài khuôn mẫu',
     '\\b(mặc dù|dù|bất chấp) (vẫn )?(còn )?(tồn tại )?(nhiều|những|không ít|một số) (thách thức|khó khăn|hạn chế)|(tương lai|triển vọng)[^.\\n]{0,40}(đầy hứa hẹn|hứa hẹn|tươi sáng|rộng mở)|tiềm năng (to lớn|vô hạn|phát triển mạnh mẽ)'),
    ('vi-dieu-nay', 'câu nối rỗng',
     '\\b(điều này cho thấy|điều đáng chú ý là|đáng chú ý,|không những thế|hơn thế nữa)\\b'),
    ('vi-ben-canh-do', 'câu nối rỗng',
     '(^|[.!?]\\s+)(bên cạnh đó|ngoài ra|thêm vào đó|mặt khác),'),
    ('vi-menh-de-duoi', 'phân tích hời hợt',
     ',\\s*(góp phần|qua đó|từ đó|nhờ đó|thể hiện|khẳng định|phản ánh|minh chứng cho|mở ra|tạo nên|tạo tiền đề|đặt nền móng|hứa hẹn)\\b'),
    ('vi-ne-la', 'né chữ "là"',
     '\\b(đóng vai trò (là|như)|được (xem|coi) (là|như)|là minh chứng (cho|sống)|đánh dấu (một )?(bước tiến|cột mốc))'),
    ('vi-sot-chatbot', 'sót từ chatbot',
     'hy vọng (rằng )?(thông tin|bài viết|những chia sẻ|câu trả lời|nội dung|gợi ý) (này|trên) (sẽ )?(hữu ích|giúp ích)|\\bchắc chắn rồi[!.,]|^\\s*(đây là )?(một )?câu hỏi (rất )?hay[!.]|(nếu|khi) bạn cần (thêm|hỗ trợ|giúp)[^.\\n]{0,50}(hãy|cứ) (cho (tôi|mình) biết|hỏi|nhắn)|dưới đây là (phiên bản|bản) (đã )?(được )?(chỉnh sửa|viết lại|sửa)|với tư cách (là )?(một )?(mô hình ngôn ngữ|trợ lý ảo|trợ lý AI)|(theo|tính đến) (lần )?(cập nhật|dữ liệu) (kiến thức )?(cuối cùng|gần nhất) của (tôi|mình)'),
]

# Từ phổ biến viết thiếu dấu. Chỉ gồm chữ mà dạng không dấu không phải một từ tiếng Việt đúng ("trong", "cua", "chung",
# "nhung", "voi" đều là từ đúng nên không có ở đây).
NO_ACCENT = {"khong", "duoc", "nguoi", "viec", "nhieu", "truoc", "neu", "hom", "tien", "duong", "dieu", "tuan", "hien"}
ENGLISH = {"the", "and", "of", "is", "are", "with", "for", "this", "that", "will", "we", "our", "you", "please", "should",
           "have", "has", "been", "was", "were", "from", "into", "after", "before", "because", "which"}
CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
IDENT_RE = re.compile(r"\b\w*_\w*\b")      # tên hàm, tên test viết trần (test_giam_khong_vuot): không phải chữ tiếng Việt
WORD_RE = re.compile(r"[^\W\d_]+", re.U)


def app_dir() -> Path:
    return Path(os.environ.get("APP_DIR", "/app"))


def read(path) -> str | None:
    p = Path(path)
    if not p.is_absolute():
        p = app_dir() / p
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def prose(text: str) -> str:
    """Bỏ khối code, code trong dòng và định danh có dấu gạch dưới: chỉ chấm phần chữ."""
    return IDENT_RE.sub(" ", CODE_RE.sub(" ", text))


def words(text: str) -> list:
    return WORD_RE.findall(unicodedata.normalize("NFC", prose(text)))


def tells(text: str) -> list:
    """[(mã, đoạn khớp)] theo TELLS, trên văn bản NFC, không phân biệt hoa thường, ^ khớp đầu dòng."""
    t = unicodedata.normalize("NFC", prose(text))
    out = []
    for code, _group, rx in TELLS:
        for m in re.finditer(rx, t, re.I | re.M):
            out.append((code, m.group(0).strip()))
    return out


def no_accent_words(text: str) -> list:
    return [w for w in words(text) if w in NO_ACCENT]


def english_words(text: str) -> list:
    return [w for w in words(text) if w.lower() in ENGLISH]


def accent_ratio(text: str) -> float:
    ws = words(text)
    if not ws:
        return 0.0
    plain = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return sum(1 for w in ws if any(c not in plain for c in w)) / len(ws)


def is_nfc(text: str) -> bool:
    return unicodedata.normalize("NFC", text) == text


def norm_num(text: str) -> str:
    """Bỏ dấu phân cách nghìn (chấm, phẩy, khoảng trắng, khoảng trắng hẹp, gạch dưới kiểu Python) giữa các nhóm 3 chữ số:
    1.240, 1 240 và 1_240 đều thành 1240."""
    return re.sub(r"(?<=\d)[.,_\u00a0\u202f ](?=\d{3}(?!\d))", "", unicodedata.normalize("NFC", text))


def has_number(text: str, n: int) -> bool:
    """Số n đứng riêng (không là một phần của số dài hơn), chấp nhận mọi kiểu phân cách nghìn."""
    return re.search(rf"(?<![\d]){n}(?![\d])", norm_num(text)) is not None


def writing_checks(text: str, max_words: int | None = None, min_words: int = 0) -> list:
    """Các kiểm chung cho bài viết: NFC, đủ dấu, không chữ Anh thừa, độ dài. Ghi số dấu hiệu văn AI thành chỉ số phụ."""
    errs = []
    if not is_nfc(text):
        errs.append("văn bản không ở dạng NFC (dấu tách rời)")
    bad = no_accent_words(text)
    if bad:
        errs.append(f"có chữ viết thiếu dấu: {', '.join(sorted(set(bad))[:8])}")
    if accent_ratio(text) < 0.3:
        errs.append(f"quá ít chữ có dấu ({accent_ratio(text):.0%}): có thể viết không dấu hay viết tiếng Anh")
    en = english_words(text)
    if len(en) > 2:
        errs.append(f"có câu tiếng Anh: {', '.join(sorted(set(en))[:8])}")
    record_metrics(van_ai=len(tells(text)))
    n = len(words(text))
    if max_words is not None and n > max_words:
        errs.append(f"dài {n} chữ, quá giới hạn {max_words}")
    if n < min_words:
        errs.append(f"chỉ {n} chữ, dưới {min_words}")
    return errs


def record_metrics(**values) -> None:
    """Ghi chỉ số phụ (số) vào vi-metrics.json; tests/test.sh gộp chúng vào reward.json cạnh "reward". Không đổi đạt/trượt.
    Đường dẫn lấy từ VI_METRICS (selftest.py trỏ vào thư mục tạm), mặc định /logs/verifier/vi-metrics.json."""
    path = Path(os.environ.get("VI_METRICS", "/logs/verifier/vi-metrics.json"))
    try:
        old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        old = {}
    old.update({k: v for k, v in values.items() if isinstance(v, (int, float))})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(old), encoding="utf-8")
    except OSError:
        pass


def finish(errors: list) -> None:
    """In từng lỗi và thoát 1 nếu có lỗi; thoát 0 nếu đạt."""
    errors = [e for e in errors if e]
    for e in errors:
        print("TRƯỢT:", e)
    if not errors:
        print("ĐẠT")
    sys.exit(1 if errors else 0)
