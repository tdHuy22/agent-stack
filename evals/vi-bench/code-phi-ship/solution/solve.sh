#!/bin/bash
# Lời giải mẫu: viết lại hàm theo đúng luật trong đề.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/shop/phi_ship.py" <<'PY'
"""Phí ship của shop."""
import unicodedata

MIEN_PHI_TU = 500_000
PHI_NOI_THANH = 20_000
PHI_TINH_KHAC = 35_000


def _chuan_hoa(tinh):
    s = unicodedata.normalize("NFD", tinh).replace("đ", "d").replace("Đ", "D")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = " ".join(s.split())
    for tien_to in ("tp.", "thanh pho"):
        if s.startswith(tien_to):
            s = s[len(tien_to):].strip()
            break
    return s


def tinh_phi_ship(tong_tien, tinh):
    """Trả phí ship (đồng) cho đơn có tổng tiền `tong_tien` (đồng) giao tới tỉnh `tinh`."""
    if tong_tien < 0:
        raise ValueError("tổng tiền âm")
    if tong_tien >= MIEN_PHI_TU:
        return 0
    if _chuan_hoa(tinh) == "ha noi":
        return PHI_NOI_THANH
    return PHI_TINH_KHAC
PY
