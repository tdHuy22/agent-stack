import subprocess, sys, textwrap
from pathlib import Path

# Đáp án đã đối chiếu với một bản duyệt từng phút (brute force) độc lập.
CASES = [
    ("*/15 * * * *", (2026, 3, 10, 10, 7, 30), (2026, 3, 10, 10, 15)),
    ("*/15 * * * *", (2026, 3, 10, 10, 15, 0), (2026, 3, 10, 10, 30)),
    ("*/15 * * * *", (2026, 3, 10, 10, 14, 59, 999999), (2026, 3, 10, 10, 15)),
    ("0 9 * * 1-5", (2026, 10, 2, 9, 0), (2026, 10, 5, 9, 0)),
    ("30 8 1 * *", (2026, 1, 31, 12, 0), (2026, 2, 1, 8, 30)),
    ("0 0 29 2 *", (2026, 3, 1), (2028, 2, 29, 0, 0)),
    ("0 0 31 * *", (2026, 4, 1), (2026, 5, 31, 0, 0)),
    ("0 12 13 * 5", (2026, 10, 3), (2026, 10, 9, 12, 0)),
    ("0 12 13 * *", (2026, 10, 3), (2026, 10, 13, 12, 0)),
    ("0 0 * * 7", (2026, 10, 3), (2026, 10, 4, 0, 0)),
    ("0 0 * * 0", (2026, 10, 3), (2026, 10, 4, 0, 0)),
    ("5-20/5 * * * *", (2026, 10, 3, 10, 20), (2026, 10, 3, 11, 5)),
    ("0 6,18 * * *", (2026, 10, 3, 18, 0), (2026, 10, 4, 6, 0)),
    ("0 0 1 1 *", (2026, 12, 31, 23, 59), (2027, 1, 1, 0, 0)),
    ("0 0 31 2 1", (2027, 1, 31), (2027, 2, 1, 0, 0)),
    ("0 0 1-7 * 1", (2026, 10, 3), (2026, 10, 4, 0, 0)),
    ("0 0 */10 * *", (2026, 10, 3), (2026, 10, 11, 0, 0)),
    ("59 23 31 12 *", (2026, 12, 31, 23, 59), (2027, 12, 31, 23, 59)),
    ("0 0 29 2 1", (2027, 3, 2), (2028, 2, 7, 0, 0)),
    ("1,2,3-5/2 4 * 2 *", (2026, 10, 3), (2027, 2, 1, 4, 1)),
]
INVALID = ["60 * * * *", "* * *", "* * * * * *", "*/0 * * * *", "5-1 * * * *", "* * 0 * *", "* * * 13 *",
           "* * * * 8", "a * * * *", "1-2-3 * * * *", "5/2 * * * *", "* * * JAN *", "* * ? * *", "", "1,,2 * * * *"]
NEVER = ["0 0 30 2 *", "0 0 31 4,6,9,11 *"]

PROBE = textwrap.dedent("""
    import json, sys, time
    from datetime import datetime
    sys.path.insert(0, ".")
    from cron import next_run
    cases, invalid, never = json.loads(sys.stdin.read())
    wrong, slow = [], 0.0
    for expr, after, want in cases:
        start = time.time()
        try:
            got = next_run(expr, datetime(*after))
            got = list(got.timetuple()[:5]) if got.second == 0 and got.microsecond == 0 else repr(got)
        except Exception as exc:
            got = repr(exc)
        slow = max(slow, time.time() - start)
        if got != list(want):
            wrong.append(f"{expr!r} sau {datetime(*after)}: {got}, cần {datetime(*want)}")
    for expr in invalid + never:
        start = time.time()
        try:
            next_run(expr, datetime(2026, 1, 1))
            wrong.append(f"{expr!r} phải ném ValueError")
        except ValueError:
            pass
        except Exception as exc:
            wrong.append(f"{expr!r} ném {type(exc).__name__} thay vì ValueError")
        slow = max(slow, time.time() - start)
    if slow > 0.5:
        wrong.append(f"chậm: một lần gọi mất {slow:.2f} giây (cần < 0,5)")
    print(json.dumps(wrong, ensure_ascii=False))
""")


def check(workdir, answer):
    import json
    workdir = Path(workdir)
    data = json.dumps([[list(c) for c in CASES], INVALID, NEVER])
    try:
        out = subprocess.run([sys.executable, "-c", PROBE], cwd=str(workdir), input=data, capture_output=True,
                             text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return False, "quá 60 giây (vòng lặp vô hạn?)"
    try:
        wrong = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return False, "không chạy được: " + (out.stderr or out.stdout)[-200:]
    tests = subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=str(workdir), capture_output=True,
                           text=True, timeout=60)
    if tests.returncode != 0:
        wrong.append("test mẫu chưa đạt")
    return not wrong, f"sai {len(wrong)}: " + "; ".join(wrong[:4]) if wrong else "đạt"
