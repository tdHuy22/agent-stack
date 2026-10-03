"""Tiền tính bằng xu (số nguyên)."""
import re

_PRICE = re.compile(r"^\s*(\d+)(?:\.(\d{1,2}))?\s*$")


def to_cents(text):
    """'19.99' -> 1999. Chấp nhận '5', '5.5', '5.50'."""
    m = _PRICE.match(str(text))
    if not m:
        raise ValueError(f"giá không hợp lệ: {text}")
    whole, frac = m.group(1), (m.group(2) or "").ljust(2, "0")
    return int(whole) * 100 + int(frac)


def fmt(cents):
    """1999 -> '19.99'."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"
