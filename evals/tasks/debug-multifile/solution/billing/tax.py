"""Thuế."""
from decimal import ROUND_HALF_UP, Decimal


def tax_cents(amount_cents, rate_percent):
    """Thuế của một khoản (xu), làm tròn nửa lên tới xu."""
    exact = Decimal(amount_cents) * Decimal(str(rate_percent)) / 100
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))
