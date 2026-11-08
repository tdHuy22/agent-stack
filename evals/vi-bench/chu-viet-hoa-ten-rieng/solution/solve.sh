#!/bin/bash
# Lời giải mẫu: NFC, một regex gộp mọi tên (nhiều chữ nhất xếp trước, không phân biệt hoa thường, biên là chữ cái), rồi viết hoa đầu câu.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/viet_hoa.py" <<'PY'
"""Viết hoa tên riêng trong bản tin gõ từ giọng nói."""
import re
import unicodedata
from pathlib import Path

FILE_TEN = Path(__file__).with_name("ten_rieng.txt")
CHU_CAI = r"[^\W\d_]"
HET_CAU = re.compile(r"[.!?]+(?=\s)|\n")


def _doc_ten():
    ten = []
    for dong in FILE_TEN.read_text(encoding="utf-8").splitlines():
        t = " ".join(unicodedata.normalize("NFC", dong).split())
        if t:
            ten.append(t)
    return ten


def viet_hoa(van_ban):
    """Viết hoa đúng địa danh, tên tổ chức trong văn bản."""
    s = unicodedata.normalize("NFC", van_ban)
    ten = _doc_ten()
    if ten:
        ten.sort(key=lambda t: (-len(t.split()), -len(t)))
        chuan = {t.lower(): t for t in ten}
        mau = "|".join(r"\s+".join(re.escape(w) for w in t.split()) for t in ten)
        rx = re.compile("(?<!" + CHU_CAI + ")(?:" + mau + ")(?!" + CHU_CAI + ")", re.I)
        s = rx.sub(lambda m: chuan[" ".join(m.group(0).lower().split())], s)
    dau = set()
    for m in HET_CAU.finditer(s):
        k = m.end()
        while k < len(s) and s[k].isspace():
            k += 1
        if k < len(s):
            dau.add(k)
    k = 0
    while k < len(s) and s[k].isspace():
        k += 1
    if k < len(s):
        dau.add(k)
    ra = list(s)
    for k in dau:
        if ra[k].isalpha():
            ra[k] = ra[k].upper()
    return "".join(ra)


if __name__ == "__main__":
    print(viet_hoa("thành phố hồ chí minh đông dân"))
PY
