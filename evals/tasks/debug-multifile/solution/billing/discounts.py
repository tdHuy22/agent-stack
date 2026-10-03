"""Áp mã giảm giá lên tạm tính (xu)."""
from decimal import ROUND_HALF_UP, Decimal


def apply_discount(subtotal_cents, code, catalog):
    """catalog: {mã: ("percent", p) hoặc ("fixed", xu)}. Trả về số tiền sau giảm (xu)."""
    if not code:
        return subtotal_cents
    if code not in catalog:
        raise ValueError(f"mã không hợp lệ: {code}")
    kind, value = catalog[code]
    if kind == "percent":
        off = (Decimal(subtotal_cents) * Decimal(str(value)) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return max(0, subtotal_cents - int(off))
    if kind == "fixed":
        return max(0, subtotal_cents - value)
    raise ValueError(f"loại giảm giá lạ: {kind}")
