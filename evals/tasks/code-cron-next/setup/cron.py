"""Tính lần chạy kế tiếp của biểu thức cron 5 trường."""
from datetime import datetime


def next_run(expr: str, after: datetime) -> datetime:
    raise NotImplementedError
