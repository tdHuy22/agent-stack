#!/bin/bash
# Lời giải mẫu: tách chữ bằng dãy chữ cái, xét hai chữ cái cuối của chữ, chuyển dấu thanh lên chữ cái đầu, trừ vần uy sau q.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/dau_thanh.py" <<'PY'
"""Chuẩn hóa vị trí dấu thanh trong văn bản trước khi in."""
import re
import unicodedata

THANH = "\u0323\u0300\u0301\u0309\u0303"   # nặng, huyền, sắc, hỏi, ngã
CHU = re.compile(r"[^\W\d_]+")
VAN = {("o", "a"), ("o", "e"), ("u", "y")}


def _tach(c):
    """Chữ cái -> (chữ cái bỏ dấu thanh, dấu thanh)."""
    d = unicodedata.normalize("NFD", c)
    thanh = "".join(x for x in d if x in THANH)
    goc = unicodedata.normalize("NFC", "".join(x for x in d if x not in THANH))
    return goc, thanh


def _doi_chu(m):
    w = m.group(0)
    if len(w) < 2:
        return w
    a, ta = _tach(w[-2])
    b, tb = _tach(w[-1])
    if ta or not tb or (a.lower(), b.lower()) not in VAN:
        return w
    if (a.lower(), b.lower()) == ("u", "y") and len(w) >= 3 and w[-3].lower() == "q":
        return w
    return w[:-2] + unicodedata.normalize("NFC", a + tb) + b


def chuan_hoa_dau(van_ban):
    """Đổi dấu thanh kiểu cũ sang kiểu mới."""
    return CHU.sub(_doi_chu, unicodedata.normalize("NFC", van_ban))


if __name__ == "__main__":
    print(chuan_hoa_dau("Hoà bình, thuỷ điện"))
PY
