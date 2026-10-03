"""Tính lần chạy kế tiếp của biểu thức cron 5 trường."""
import re
from datetime import datetime, timedelta

RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
ITEM = re.compile(r"^(?:(\*)|(\d+)(?:-(\d+))?)(?:/(\d+))?$")


def _field(text, lo, hi):
    values = set()
    for part in text.split(","):
        m = ITEM.match(part)
        if not m:
            raise ValueError(f"phần tử lạ: {part!r}")
        star, a, b, step = m.groups()
        if star:
            start, end = lo, hi
        else:
            start = int(a)
            end = int(b) if b is not None else start
            if step is not None and b is None:
                raise ValueError(f"dạng a/n không được hỗ trợ: {part!r}")
        n = int(step) if step is not None else 1
        if n < 1 or start > end or start < lo or end > hi:
            raise ValueError(f"ngoài miền: {part!r}")
        values.update(range(start, end + 1, n))
    return values


def next_run(expr: str, after: datetime) -> datetime:
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("cần đúng 5 trường")
    minutes, hours, doms, months, dows = (_field(f, lo, hi) for f, (lo, hi) in zip(fields, RANGES))
    dows = {d % 7 for d in dows}
    dom_star, dow_star = fields[2] == "*", fields[4] == "*"

    def day_ok(day):
        dom_hit = day.day in doms
        dow_hit = (day.isoweekday() % 7) in dows
        if dom_star or dow_star:
            return dom_hit and dow_hit
        return dom_hit or dow_hit

    start = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    day = start.replace(hour=0, minute=0)
    limit = after + timedelta(days=366 * 8 + 2)
    hour_list, minute_list = sorted(hours), sorted(minutes)
    while day <= limit:
        if day.month in months and day_ok(day):
            for h in hour_list:
                for m in minute_list:
                    cand = day.replace(hour=h, minute=m)
                    if cand >= start:
                        return cand
        day += timedelta(days=1)
    raise ValueError("không có thời điểm nào khớp trong 8 năm")
