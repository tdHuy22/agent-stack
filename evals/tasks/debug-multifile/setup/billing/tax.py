"""Thuế."""


def tax_cents(amount_cents, rate_percent):
    """Thuế của một khoản (xu), làm tròn tới xu."""
    return round(amount_cents * rate_percent / 100)
