"""Sinh unified diff giữa hai văn bản."""

NO_EOL = "\\ No newline at end of file\n"


def _myers(a, b):
    """Dãy thao tác tối thiểu ('=', '-', '+') biến a thành b (thuật toán Myers O((N+M)D))."""
    n, m = len(a), len(b)
    offset = n + m
    v = [0] * (2 * offset + 2)
    trace = []
    for d in range(offset + 1):
        trace.append(v[:])
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v[offset + k - 1] < v[offset + k + 1]):
                x = v[offset + k + 1]
            else:
                x = v[offset + k - 1] + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            v[offset + k] = x
            if x >= n and y >= m:
                return _backtrack(trace, a, b, offset, d)
    return []


def _backtrack(trace, a, b, offset, d_end):
    x, y = len(a), len(b)
    ops = []
    for d in range(d_end, -1, -1):
        v = trace[d]
        k = x - y
        if d == 0:
            ops.extend("=" * x)
            break
        if k == -d or (k != d and v[offset + k - 1] < v[offset + k + 1]):
            prev_k = k + 1
        else:
            prev_k = k - 1
        prev_x = v[offset + prev_k]
        prev_y = prev_x - prev_k
        while x > prev_x and y > prev_y:
            ops.append("=")
            x -= 1
            y -= 1
        ops.append("+" if x == prev_x else "-")
        x, y = prev_x, prev_y
    ops.reverse()
    return ops


def _lines(text):
    return text.splitlines(keepends=True) if text else []


def _fmt(prefix, line):
    return prefix + line if line.endswith("\n") else prefix + line + "\n" + NO_EOL


def _range(start, count):
    """start là chỉ số 0 của dòng đầu hunk."""
    if count == 0:
        return f"{start},0"
    if count == 1:
        return f"{start + 1}"
    return f"{start + 1},{count}"


def unified_diff(a, b, a_name="a", b_name="b", context=3):
    la, lb = _lines(a), _lines(b)
    # Cắt phần đầu và đuôi chung để Myers chỉ chạy trên phần giữa.
    pre = 0
    while pre < len(la) and pre < len(lb) and la[pre] == lb[pre]:
        pre += 1
    suf = 0
    while suf < len(la) - pre and suf < len(lb) - pre and la[-1 - suf] == lb[-1 - suf]:
        suf += 1
    middle = _myers(la[pre:len(la) - suf], lb[pre:len(lb) - suf])
    ops = ["="] * pre + middle + ["="] * suf
    if all(op == "=" for op in ops):
        return ""
    # Gán chỉ số dòng cho từng thao tác.
    rows, i, j = [], 0, 0
    for op in ops:
        rows.append((op, i, j))
        if op in "=-":
            i += 1
        if op in "=+":
            j += 1
    changed = [idx for idx, r in enumerate(rows) if r[0] != "="]
    # Gom các thay đổi thành hunk theo khoảng cách ngữ cảnh.
    groups, start, last = [], changed[0], changed[0]
    for idx in changed[1:]:
        if idx - last - 1 > 2 * context:
            groups.append((start, last))
            start = idx
        last = idx
    groups.append((start, last))
    out = [f"--- {a_name}\n", f"+++ {b_name}\n"]
    for first, end in groups:
        lo, hi = max(0, first - context), min(len(rows) - 1, end + context)
        body, a_count, b_count = [], 0, 0
        k = lo
        while k <= hi:
            if rows[k][0] == "=":
                body.append(_fmt(" ", la[rows[k][1]]))
                a_count += 1
                b_count += 1
                k += 1
                continue
            minus, plus = [], []
            while k <= hi and rows[k][0] != "=":
                if rows[k][0] == "-":
                    minus.append(_fmt("-", la[rows[k][1]]))
                else:
                    plus.append(_fmt("+", lb[rows[k][2]]))
                k += 1
            body += minus + plus
            a_count += len(minus)
            b_count += len(plus)
        a0, b0 = rows[lo][1], rows[lo][2]
        out.append(f"@@ -{_range(a0, a_count)} +{_range(b0, b_count)} @@\n")
        out += body
    return "".join(out)
