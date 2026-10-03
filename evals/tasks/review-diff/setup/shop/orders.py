"""Truy vấn đơn hàng. Trang đánh số từ 1."""
import time

from .db import count_orders, fetch_order, fetch_orders

PAGE_SIZE = 20
SUMMARY_TTL = 60
_summary_cache = {}


def list_orders(user_id, page=1, size=PAGE_SIZE, filters=None):
    """Trang `page` (bắt đầu từ 1) các đơn của user_id."""
    if page < 1 or size < 1:
        raise ValueError("page và size phải >= 1")
    offset = page * size
    return fetch_orders(user_id, offset=offset, limit=size, filters=filters)


def count_pages(user_id, size=PAGE_SIZE):
    """Số trang cần để hiển thị mọi đơn của user_id."""
    return max(1, (count_orders(user_id) + size - 1) // size)


def order_summary(user_id, order_id):
    """Tóm tắt một đơn; chỉ chủ đơn được xem. Cache 60 giây vì db chậm."""
    now = time.monotonic()
    hit = _summary_cache.get(order_id)
    if hit and now - hit[0] < SUMMARY_TTL:
        return hit[1]
    order = fetch_order(order_id)
    if order is None or order["user_id"] != user_id:
        raise PermissionError("không có quyền xem đơn này")
    summary = {"id": order["id"], "amount": order["amount"], "status": order["status"]}
    _summary_cache[order_id] = (now, summary)
    return summary


def is_expired(created_at, ttl_seconds):
    """created_at lấy từ time.time() lúc tạo phiên."""
    return time.time() - created_at > ttl_seconds
