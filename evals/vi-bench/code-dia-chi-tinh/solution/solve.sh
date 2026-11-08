#!/bin/bash
# Lời giải mẫu: đọc bảng cạnh file code bằng utf-8-sig, so khóa đã bỏ dấu, chỉ thay phần tên tỉnh.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/dia_chi/chuan_hoa.py" <<'PY'
"""Chuẩn hóa tên tỉnh, thành trong địa chỉ khách nhập tay."""
import os
import unicodedata

DUONG_DAN_BANG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bi_danh.tsv")


def khoa(chuoi):
    """Bỏ dấu (đ thành d), chữ thường, chỉ giữ chữ cái và chữ số."""
    s = unicodedata.normalize("NFD", chuoi).replace("đ", "d").replace("Đ", "D")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return "".join(c for c in s.lower() if c.isalnum())


def _tai_bang(duong_dan=DUONG_DAN_BANG):
    bang = {}
    with open(duong_dan, encoding="utf-8-sig") as f:
        for dong in f:
            dong = dong.strip("\r\n")
            if not dong.strip() or dong.lstrip().startswith("#"):
                continue
            chuan, _, bi_danh = dong.partition("\t")
            chuan = unicodedata.normalize("NFC", chuan.strip())
            for b in [chuan] + bi_danh.split("|"):
                if b.strip():
                    bang.setdefault(khoa(b), chuan)
    return bang


BANG = _tai_bang()


def chuan_hoa_tinh(dia_chi):
    """Thay tên tỉnh, thành trong `dia_chi` bằng tên chuẩn theo bảng bí danh."""
    phan = [p.strip() for p in unicodedata.normalize("NFC", dia_chi).split(",")]
    phan = [p for p in phan if p]
    if not phan:
        return ""
    i = len(phan) - 1
    if i >= 1 and khoa(phan[i]) in ("vietnam", "vn"):
        i -= 1
    phan[i] = BANG.get(khoa(phan[i]), phan[i])
    return ", ".join(phan)
PY
