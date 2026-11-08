"""Tính tiền đơn hàng."""
from datetime import date

from . import cau_hinh, giam_gia


def tinh_tong(tien_hang, phi_ship, ma=None, hom_nay=None):
    """Tổng khách phải trả: tiền hàng trừ giảm giá (tính trên tiền hàng) cộng phí ship."""
    hom_nay = hom_nay or date.today()
    ship = 0 if tien_hang >= cau_hinh.MIEN_PHI_SHIP_TU else phi_ship
    giam = giam_gia.ap_dung_ma(tien_hang, ma, hom_nay) if ma else 0
    return tien_hang - giam + ship
