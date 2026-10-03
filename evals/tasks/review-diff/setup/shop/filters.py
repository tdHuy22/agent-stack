"""Bộ lọc truy vấn đơn hàng."""


def build_filters(status=None, extra={}):
    """Bộ lọc mặc định, cộng thêm điều kiện trong `extra` nếu có."""
    extra["deleted"] = False
    if status is not None:
        extra["status"] = status
    return extra
