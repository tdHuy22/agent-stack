#!/bin/bash
# Lời giải mẫu: NFC, bỏ qua chữ không toàn ASCII hay có trong tu_giu.txt; tách phím thanh, đổi cặp phím, đặt dấu theo cụm nguyên âm.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/telex.py" <<'PY'
"""Sửa chữ Telex còn sót trong văn bản nhập từ bộ gõ lỗi."""
import re
import unicodedata
from pathlib import Path

FILE_GIU = Path(__file__).with_name("tu_giu.txt")
CAP = {"aa": "â", "aw": "ă", "ee": "ê", "oo": "ô", "ow": "ơ", "uw": "ư", "dd": "đ"}
THANH = {"f": "\u0300", "s": "\u0301", "r": "\u0309", "x": "\u0303", "j": "\u0323"}
NGUYEN_AM = "aăâeêioôơuưy"
CO_DAU_PHU = "ăâêôơư"
CHU = re.compile(r"[^\W\d_]+")


def _doc_tu_giu():
    return {unicodedata.normalize("NFC", d).strip().lower() for d in FILE_GIU.read_text(encoding="utf-8").splitlines()
            if d.strip()}


def _cum_nguyen_am(c):
    """Vị trí các nguyên âm của cụm nguyên âm đầu tiên, sau khi bỏ qu, gi."""
    bat_dau = 0
    if c[:2] == ["q", "u"]:
        bat_dau = 2
    elif c[:2] == ["g", "i"] and len(c) > 2 and c[2] in NGUYEN_AM:
        bat_dau = 2
    i = bat_dau
    while i < len(c) and c[i] not in NGUYEN_AM:
        i += 1
    cum = []
    while i < len(c) and c[i] in NGUYEN_AM:
        cum.append(i)
        i += 1
    return cum


def _sua_chu(w):
    thuong = w.lower()
    thanh = None
    if thuong[-1] in THANH and any(x in "aeiouy" for x in thuong[:-1]):
        thanh, thuong = thuong[-1], thuong[:-1]
    c, i = [], 0
    while i < len(thuong):
        if thuong[i:i + 2] in CAP:
            c.append(CAP[thuong[i:i + 2]])
            i += 2
        else:
            c.append(thuong[i])
            i += 1
    if thanh:
        cum = _cum_nguyen_am(c)
        if cum:
            co_mu = [k for k in cum if c[k] in CO_DAU_PHU]
            if co_mu:
                vt = co_mu[-1]
            elif len(cum) == 1:
                vt = cum[0]
            elif len(cum) == 2:
                vt = cum[1] if cum[-1] + 1 < len(c) else cum[0]
            else:
                vt = cum[1]
            c[vt] = unicodedata.normalize("NFC", c[vt] + THANH[thanh])
    kq = "".join(c)
    if len(w) > 1 and w.isupper():
        return kq.upper()
    if w[0].isupper():
        return kq[0].upper() + kq[1:]
    return kq


def sua_telex(van_ban):
    """Đổi các chữ gõ Telex thô (như 'vieetj') thành chữ tiếng Việt."""
    giu = _doc_tu_giu()

    def doi(m):
        w = m.group(0)
        if not w.isascii() or w.lower() in giu:
            return w
        return _sua_chu(w)

    return CHU.sub(doi, unicodedata.normalize("NFC", van_ban))


if __name__ == "__main__":
    print(sua_telex("Tooi ddang hocj tieengs Vieetj"))
PY
