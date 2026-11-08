#!/bin/bash
# Lời giải mẫu: dùng số nguyên, làm tròn nửa lên đúng chỗ, tính lũy tiến từng phần.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/luong/thue.py" <<'PY'
"""Tính thuế thu nhập cá nhân (TNCN) hằng tháng cho người làm công ăn lương."""

GIAM_TRU_BAN_THAN = 11_000_000
GIAM_TRU_PHU_THUOC = 4_400_000
TRAN_DONG_BAO_HIEM = 36_000_000

# (tử số, mẫu số) của từng khoản bảo hiểm: BHXH 8%, BHYT 1,5%, BHTN 1%
BAO_HIEM = [(8, 100), (15, 1000), (1, 100)]

# (trần của bậc, thuế suất theo phần trăm); bậc cuối không có trần
BIEU_THUE = [
    (5_000_000, 5),
    (10_000_000, 10),
    (18_000_000, 15),
    (32_000_000, 20),
    (52_000_000, 25),
    (80_000_000, 30),
    (None, 35),
]


def _nua_len(tu, mau):
    """Làm tròn nửa lên phân số tu/mau (số không âm) bằng số nguyên."""
    return (2 * tu + mau) // (2 * mau)


def tinh_thue_tncn(luong_gop, so_nguoi_phu_thuoc=0):
    """Trả thuế TNCN phải nộp trong tháng (đồng) từ lương gộp `luong_gop` (đồng)."""
    if luong_gop < 0 or so_nguoi_phu_thuoc < 0:
        raise ValueError("lương gộp và số người phụ thuộc không được âm")
    muc_dong = min(luong_gop, TRAN_DONG_BAO_HIEM)
    bao_hiem = sum(_nua_len(muc_dong * tu, mau) for tu, mau in BAO_HIEM)
    tinh_thue = (luong_gop - bao_hiem - GIAM_TRU_BAN_THAN
                 - GIAM_TRU_PHU_THUOC * so_nguoi_phu_thuoc)
    if tinh_thue <= 0:
        return 0
    thue_x100 = 0
    tu = 0
    for tran, ty_le in BIEU_THUE:
        den = tinh_thue if tran is None else min(tinh_thue, tran)
        if den > tu:
            thue_x100 += (den - tu) * ty_le
        if tran is None or tinh_thue <= tran:
            break
        tu = tran
    return _nua_len(thue_x100, 100)
PY
