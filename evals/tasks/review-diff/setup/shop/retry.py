"""Tiện ích chờ giữa các lần thử lại."""


def retry_delay(attempt, base=0.5, cap=8.0):
    """Thời gian chờ (giây) trước lần thử thứ attempt (bắt đầu từ 1): lũy thừa 2, có trần."""
    return min(cap, base * (2 ** (attempt - 1)))
