"""Lập hóa đơn từ các dòng hàng."""
from .discounts import apply_discount
from .money import to_cents
from .tax import tax_cents


def build_invoice(lines, code=None, catalog=None, tax_rate=10):
    """lines: danh sách (mã hàng, số lượng, đơn giá dạng chuỗi).
    Trả về dict subtotal, discounted, tax, total (đều là xu)."""
    catalog = catalog or {}
    subtotal = 0
    tax = 0
    for _sku, qty, price in lines:
        line = qty * to_cents(price)
        subtotal += line
        tax += tax_cents(line, tax_rate)
    discounted = apply_discount(subtotal, code, catalog)
    return {"subtotal": subtotal, "discounted": discounted, "tax": tax, "total": discounted + tax}
