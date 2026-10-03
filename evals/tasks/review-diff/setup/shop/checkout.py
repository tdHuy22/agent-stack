"""Thanh toán đơn hàng."""
import time
from decimal import Decimal

from .payments import PaymentTimeout, charge
from .retry import retry_delay


def pay(order, attempts=3):
    """Thu tiền cho đơn. Cổng thanh toán hay quá giờ, nên thử lại tối đa `attempts` lần."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return charge(order["id"], order["amount"])
        except (PaymentTimeout, ConnectionError) as exc:
            last = exc
            time.sleep(retry_delay(attempt))
    raise last


def format_amount(cents):
    """1999 -> '19.99'."""
    return str((Decimal(cents) / 100).quantize(Decimal("0.01")))
