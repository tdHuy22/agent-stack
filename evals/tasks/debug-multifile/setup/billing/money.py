"""Tiền tính bằng xu (số nguyên)."""


def to_cents(text):
    """'19.99' -> 1999. Chấp nhận '5', '5.5', '5.50'."""
    value = float(text)
    if value < 0:
        raise ValueError(f"giá âm: {text}")
    return int(value * 100)


def fmt(cents):
    """1999 -> '19.99'."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"
