import re

HEADER = re.compile(r"^[ \t#>*_`-]*l[ỗo]i\s*\d+\s*[:.)]", re.IGNORECASE | re.MULTILINE)
REAL = {
    "list_orders (offset bỏ qua trang đầu)": (r"list_orders",
                                             r"offset|page\s*\*\s*size|page\s*-\s*1|bỏ qua|skip|trang đầu|first page|off.by.one|lệch"),
    "order_summary (cache bỏ qua kiểm quyền)": (r"order_summary|_summary_cache",
                                               r"user|người dùng|quyền|permission|authori|chủ đơn|người khác|kiểm tra"),
    "pay (thử lại thu tiền không idempotency)": (r"\bpay\b|checkout\.py|\bcharge\b",
                                                 r"idempot|hai lần|2 lần|trùng|double|twice|duplicate|nhiều lần|thu lại"),
    "build_filters (tham số mặc định có thể đổi)": (r"build_filters|filters\.py",
                                                   r"mutable|mặc định|default|extra|dùng chung|shared|rò|tích lũy|leak|giữa các lần"),
}
DECOYS = ("count_pages", "format_amount", "retry_delay", "is_expired")


def items(answer):
    starts = [m.start() for m in HEADER.finditer(answer)]
    return [answer[a:b] for a, b in zip(starts, starts[1:] + [len(answer)])]


def check(workdir, answer):
    found = items(answer)
    if not found:
        return False, "không có mục nào đúng dạng 'LỖI <số>: <file>:<hàm> — …'"
    missing = []
    for name, (where, why) in REAL.items():
        if not any(re.search(where, it, re.I) and re.search(why, it, re.I) for it in found):
            missing.append(name)
    flagged = sorted({d for it in found for d in DECOYS if d in it.strip().splitlines()[0]})
    problems = []
    if missing:
        problems.append("bỏ sót: " + ", ".join(missing))
    if flagged:
        problems.append("báo nhầm thay đổi đúng: " + ", ".join(flagged))
    return not problems, "; ".join(problems) or f"đạt ({len(found)} mục)"
