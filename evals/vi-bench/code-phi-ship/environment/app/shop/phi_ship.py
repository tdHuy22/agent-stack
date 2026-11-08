"""Phí ship của shop."""

MIEN_PHI_TU = 500
PHI_NOI_THANH = 20000
PHI_TINH_KHAC = 35000


def tinh_phi_ship(tong_tien, tinh):
    """Trả phí ship (đồng) cho đơn có tổng tiền `tong_tien` (đồng) giao tới tỉnh `tinh`."""
    if tong_tien > MIEN_PHI_TU:
        return 0
    if tinh == "Hà Nội":
        return PHI_NOI_THANH
    return PHI_TINH_KHAC
