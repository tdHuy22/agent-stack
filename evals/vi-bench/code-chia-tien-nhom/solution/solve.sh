#!/bin/bash
# Lời giải mẫu: gộp tên theo khóa, chia bằng số nguyên làm tròn nửa lên tới nghìn, ghép tham lam theo luật trong đề.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/nhom/chia_tien.py" <<'PY'
"""Chia tiền ăn nhóm: ai trả trước thì được hoàn lại bằng chuyển khoản từ những người còn lại."""
import unicodedata

DAU_THANH = "̣̀́̉̃"   # huyền, sắc, hỏi, ngã, nặng


def _gon(ten):
    return " ".join(unicodedata.normalize("NFC", ten).split())


def _khoa(ten):
    """Khóa nhận diện một người: chữ thường, dấu thanh chuyển xuống cuối từng chữ."""
    tu = []
    for w in _gon(ten).casefold().split(" "):
        d = unicodedata.normalize("NFD", w)
        goc = "".join(c for c in d if c not in DAU_THANH)
        thanh = "".join(c for c in d if c in DAU_THANH)
        tu.append(unicodedata.normalize("NFC", goc) + thanh)
    return " ".join(tu)


def chia_tien(khoan_tra, thanh_vien):
    """Trả danh sách chuyển khoản [(người chuyển, người nhận, số tiền đồng)].

    `khoan_tra`: danh sách (tên, số tiền) những khoản đã trả; `thanh_vien`: danh sách tên mọi người cùng chia.
    """
    hien_thi = {}          # khóa -> tên ghi trong kết quả; dict giữ thứ tự xuất hiện đầu tiên
    for ten in thanh_vien:
        hien_thi.setdefault(_khoa(ten), _gon(ten))
    if not hien_thi:
        raise ValueError("cần ít nhất một thành viên")
    da_tra = {k: 0 for k in hien_thi}
    for ten, tien in khoan_tra:
        k = _khoa(ten)
        if k not in da_tra:
            raise ValueError(f"người trả không thuộc nhóm: {ten!r}")
        if tien < 0:
            raise ValueError("số tiền âm")
        da_tra[k] += tien
    n = len(hien_thi)
    tong = sum(da_tra.values())
    phan = (2 * tong + n * 1000) // (2 * n * 1000) * 1000
    nguoi_tra_nhieu = max(da_tra, key=lambda k: da_tra[k])    # max giữ phần tử đầu khi hòa
    phai_chiu = {k: phan for k in hien_thi}
    phai_chiu[nguoi_tra_nhieu] = tong - (n - 1) * phan
    so_du = {k: da_tra[k] - phai_chiu[k] for k in hien_thi}
    ket_qua = []
    while True:
        no = [k for k in hien_thi if so_du[k] < 0]
        nhan = [k for k in hien_thi if so_du[k] > 0]
        if not no or not nhan:
            return ket_qua
        a = min(no, key=lambda k: so_du[k])
        b = max(nhan, key=lambda k: so_du[k])
        chuyen = min(-so_du[a], so_du[b])
        ket_qua.append((hien_thi[a], hien_thi[b], chuyen))
        so_du[a] += chuyen
        so_du[b] -= chuyen
PY
