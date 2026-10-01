import re

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
ORDER = "dhms"


def parse_duration(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("chuỗi rỗng")
    parts = re.findall(r"\s*(\d+)([a-z])\s*", text)
    if "".join(n + u for n, u in parts) != re.sub(r"\s+", "", text):
        raise ValueError(f"định dạng không hợp lệ: {text!r}")
    total, last = 0, -1
    for number, unit in parts:
        if unit not in UNITS:
            raise ValueError(f"đơn vị lạ: {unit}")
        pos = ORDER.index(unit)
        if pos <= last:
            raise ValueError("đơn vị lặp lại hoặc sai thứ tự")
        last = pos
        total += int(number) * UNITS[unit]
    return total
