#!/bin/bash
# Lời giải mẫu: tách từ vựng (số, đơn vị, rưỡi), ghép thành các mẩu, cộng bằng Fraction để không sai số.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/tien.py" <<'PY'
"""Đọc số tiền viết tắt trong tin nhắn đặt hàng."""
import re
import unicodedata
from fractions import Fraction

DON_VI = {"k": 1000, "nghìn": 1000, "ngàn": 1000, "tr": 10 ** 6, "triệu": 10 ** 6, "củ": 10 ** 6, "tỷ": 10 ** 9,
          "tỉ": 10 ** 9, "lít": 10 ** 5, "đ": 1, "đồng": 1, "vnd": 1, "vnđ": 1}
TOKEN = re.compile(r"\s*(?:(?P<so>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)|(?P<dv>" +
                   "|".join(sorted(DON_VI, key=len, reverse=True)) + r")|(?P<ruoi>rưỡi))")


def _tach(s):
    toks, i = [], 0
    while s[i:].strip():
        m = TOKEN.match(s, i)
        if not m:
            raise ValueError(f"không đọc được: {s[i:].strip()!r}")
        toks.append(("so", m.group("so")) if m.group("so") else ("dv", m.group("dv")) if m.group("dv") else ("ruoi", ""))
        i = m.end()
    return toks


def _gia_tri(so):
    return Fraction(so.replace(".", "").replace(",", "."))


def doc_tien(chuoi):
    """Đổi số tiền viết tắt ('500k', '1tr5', '2,5 triệu') thành số đồng."""
    if not isinstance(chuoi, str):
        raise ValueError("không phải chuỗi")
    toks = _tach(unicodedata.normalize("NFC", chuoi).lower())
    if not toks:
        raise ValueError("rỗng")
    if len(toks) <= 2 and toks[0][0] == "so" and (len(toks) == 1 or (toks[1][0] == "dv" and DON_VI[toks[1][1]] == 1)):
        tong = _gia_tri(toks[0][1])
    else:
        tong, i = Fraction(0), 0
        while i < len(toks):
            if i + 1 >= len(toks) or toks[i][0] != "so" or toks[i + 1][0] != "dv":
                raise ValueError("cần số kèm đơn vị")
            so, dv = toks[i][1], DON_VI[toks[i + 1][1]]
            mau = _gia_tri(so) * dv
            i += 2
            if i < len(toks) and toks[i][0] == "ruoi":
                if re.search(r"[.,]", so):
                    raise ValueError("rưỡi chỉ đi với số nguyên")
                mau += Fraction(dv, 2)
                i += 1
            elif i < len(toks) and toks[i][0] == "so" and (i + 1 == len(toks) or toks[i + 1][0] != "dv"):
                le = toks[i][1]
                if re.search(r"[.,]", so) or not le.isdigit():
                    raise ValueError("phần lẻ không hợp lệ")
                mau += Fraction(int(le), 10 ** len(le)) * dv
                i += 1
            tong += mau
    if tong.denominator != 1:
        raise ValueError("ra số lẻ đồng")
    return int(tong)


if __name__ == "__main__":
    print(doc_tien("500k"))
PY
