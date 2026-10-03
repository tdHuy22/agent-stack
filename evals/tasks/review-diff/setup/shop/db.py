"""Lớp truy cập dữ liệu (giả lập). Đơn hàng: dict id, user_id, amount (xu), status, deleted."""
ORDERS = []


def fetch_orders(user_id, offset, limit, filters=None):
    filters = filters or {}
    rows = [o for o in ORDERS if o["user_id"] == user_id
            and all(o.get(k) == v for k, v in filters.items())]
    return rows[offset:offset + limit]


def count_orders(user_id):
    return sum(1 for o in ORDERS if o["user_id"] == user_id)


def fetch_order(order_id):
    return next((o for o in ORDERS if o["id"] == order_id), None)
