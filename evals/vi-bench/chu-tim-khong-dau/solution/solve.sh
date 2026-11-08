#!/bin/bash
# Lời giải mẫu: chuẩn hóa NFC thường, so từng chữ cái (không dấu khớp theo chữ gốc, có dấu khớp đúng), chấm điểm theo luật.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/danh_ba.py" <<'PY'
"""Tìm người trong danh bạ công ty."""
import unicodedata


def _chuan(s):
    return unicodedata.normalize("NFC", s).lower()


def _goc(c):
    """Chữ cái gốc không dấu của một ký tự; đ tính là d."""
    return "d" if c == "đ" else unicodedata.normalize("NFD", c)[0]


def _khop_tu(tu_khoa, chu):
    if len(tu_khoa) > len(chu):
        return False
    return all(_goc(e) == q if "a" <= q <= "z" else q == e for q, e in zip(tu_khoa, chu))


def _diem(tu_khoa, chu):
    if tu_khoa == chu:
        return 3
    return 2 if len(tu_khoa) == len(chu) else 1


def tim(danh_ba, truy_van):
    """Trả về các tên trong danh bạ khớp với truy vấn."""
    tu_khoa = _chuan(truy_van).split()
    if not tu_khoa:
        return []
    xep = []
    for vt, ten in enumerate(danh_ba):
        chu = _chuan(ten).split()
        tong = 0
        for tk in tu_khoa:
            diem = [_diem(tk, c) for c in chu if _khop_tu(tk, c)]
            if not diem:
                break
            tong += max(diem)
        else:
            xep.append((-tong, len(chu), vt, ten))
    return [ten for _, _, _, ten in sorted(xep, key=lambda x: x[:3])]


if __name__ == "__main__":
    ds = ["Nguyễn Văn An", "Lê Thị Ân", "Hoàng Văn Dũng"]
    print(tim(ds, "an"))
PY
