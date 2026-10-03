"""Áp mã giảm giá lên tạm tính (xu)."""


def apply_discount(subtotal_cents, code, catalog):
    """catalog: {mã: ("percent", p) hoặc ("fixed", xu)}. Trả về số tiền sau giảm (xu)."""
    if not code:
        return subtotal_cents
    if code not in catalog:
        raise ValueError(f"mã không hợp lệ: {code}")
    kind, value = catalog[code]
    if kind == "percent":
        return subtotal_cents - subtotal_cents * value // 100
    if kind == "fixed":
        return subtotal_cents - value
    raise ValueError(f"loại giảm giá lạ: {kind}")
