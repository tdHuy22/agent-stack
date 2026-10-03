"""Cổng thanh toán."""


class PaymentTimeout(Exception):
    """Cổng không trả lời kịp. KHÔNG biết lệnh thu đã được thực hiện hay chưa."""


def charge(order_id, amount, idempotency_key=None):
    """Gửi lệnh thu tiền. Gọi lại với cùng idempotency_key thì cổng chỉ thu đúng một lần;
    không có idempotency_key thì mỗi lần gọi là một lệnh thu mới."""
    raise NotImplementedError("gọi cổng thanh toán thật")
