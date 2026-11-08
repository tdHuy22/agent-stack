#!/bin/bash
# Lời giải mẫu: chuẩn hóa chuỗi, tách thứ, thử lần lượt kiểu tương đối, ngày số, ngày chữ; kiểm thứ bằng date.weekday().
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/ngay.py" <<'PY'
"""Đọc ngày viết tự do trong đơn từ."""
import re
import unicodedata
from datetime import date, timedelta

THANG = {"giêng": 1, "một": 1, "hai": 2, "ba": 3, "tư": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9,
         "mười": 10, "mười một": 11, "mười hai": 12, "chạp": 12}
THU = {"hai": 0, "ba": 1, "tư": 2, "năm": 3, "sáu": 4, "bảy": 5, "2": 0, "3": 1, "4": 2, "5": 3, "6": 4, "7": 5}
TUONG_DOI = {"hôm nay": 0, "ngày mai": 1, "ngày kia": 2, "hôm qua": -1, "hôm kia": -2}
TEN_THANG = "|".join(sorted(THANG, key=len, reverse=True))
RE_THU = re.compile(r"(?:thứ (hai|ba|tư|năm|sáu|bảy|[2-7])|(chủ nhật))(?:\s*,\s*|\s+)(.+)")
RE_SO = re.compile(r"(?:(ngày|mùng|mồng) )?(\d{1,2})([/.-])(\d{1,2})\3(\d{4}|\d{2})")
RE_CHU = re.compile(r"(?:(ngày|mùng|mồng) )?(\d{1,2}) tháng (\d{1,2}|" + TEN_THANG + r")(?: năm (\d{4}|\d{2}))?")


def _nam(s):
    n = int(s)
    if len(s) == 2:
        return 2000 + n if n < 70 else 1900 + n
    return n


def doc_ngay(chuoi, hom_nay=None):
    """Đổi ngày viết tự do thành chuỗi ISO 'YYYY-MM-DD'."""
    if not isinstance(chuoi, str):
        raise ValueError("không phải chuỗi")
    hom_nay = hom_nay or date.today()
    s = " ".join(unicodedata.normalize("NFC", chuoi).lower().split())
    thu = None
    m = RE_THU.fullmatch(s)
    if m:
        thu = 6 if m.group(2) else THU[m.group(1)]
        s = m.group(3)
    if s in TUONG_DOI:
        d = hom_nay + timedelta(days=TUONG_DOI[s])
    else:
        m = RE_SO.fullmatch(s)
        if m:
            tien_to, ngay, thang, nam = m.group(1), int(m.group(2)), int(m.group(4)), _nam(m.group(5))
        else:
            m = RE_CHU.fullmatch(s)
            if not m:
                raise ValueError(f"không đọc được ngày: {chuoi!r}")
            tien_to, ngay = m.group(1), int(m.group(2))
            thang = THANG[m.group(3)] if m.group(3) in THANG else int(m.group(3))
            nam = _nam(m.group(4)) if m.group(4) else hom_nay.year
        if tien_to in ("mùng", "mồng") and not 1 <= ngay <= 10:
            raise ValueError("mùng chỉ dùng cho ngày 1 đến 10")
        d = date(nam, thang, ngay)
    if thu is not None and d.weekday() != thu:
        raise ValueError("thứ không khớp ngày")
    return d.isoformat()


if __name__ == "__main__":
    print(doc_ngay("7/11/2026"))
PY
