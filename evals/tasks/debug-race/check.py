import subprocess, sys, textwrap
from pathlib import Path

# Mỗi phép thử chạy trong tiến trình con có hạn giờ: lời giải bị deadlock sẽ treo luồng mãi mãi.
PRELUDE = textwrap.dedent("""
    import random, sys, threading, time
    sys.path.insert(0, ".")
    from bank import Bank, InsufficientFunds
""")

STRESS = PRELUDE + textwrap.dedent("""
    names = ["a", "b", "c", "d", "e", "f"]
    bank = Bank({n: 1000 for n in names})
    def worker(seed):
        rnd = random.Random(seed)
        for _ in range(300):
            src, dst = rnd.choice(names), rnd.choice(names)
            try:
                bank.transfer(src, dst, rnd.randint(1, 60))
            except InsufficientFunds:
                pass
    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join(25)
    if any(t.is_alive() for t in threads):
        print("TREO"); sys.exit(3)
    bal = {n: bank.balance(n) for n in names}
    if bank.total() != 6000 or min(bal.values()) < 0:
        print("SAI", bank.total(), bal); sys.exit(4)
    print("OK")
""")

PARALLEL = PRELUDE + textwrap.dedent("""
    best = 9.0
    for _ in range(3):
        bank = Bank({n: 100 for n in "abcd"}, io_delay=0.1)
        t1 = threading.Thread(target=bank.transfer, args=("a", "b", 10), daemon=True)
        t2 = threading.Thread(target=bank.transfer, args=("c", "d", 10), daemon=True)
        start = time.time(); t1.start(); t2.start(); t1.join(5); t2.join(5)
        best = min(best, time.time() - start)
    # Mỗi chuyển khoản có 2 lần _audit (0,2 giây). Song song thì xong trong khoảng 0,2 giây; khóa chung thì 0,4.
    print("OK" if best < 0.32 else f"TUẦN TỰ {best:.2f}s"); sys.exit(0 if best < 0.32 else 5)
""")

SEMANTICS = PRELUDE + textwrap.dedent("""
    bank = Bank({"a": 50, "b": 0}, io_delay=0.001)
    done = []
    def self_transfer():
        bank.transfer("a", "a", 20)
        try:
            bank.transfer("a", "a", 999)
            done.append("thiếu InsufficientFunds khi tự chuyển quá số dư")
        except InsufficientFunds:
            pass
        done.append("xong")
    t = threading.Thread(target=self_transfer, daemon=True); t.start(); t.join(5)
    if t.is_alive():
        print("TREO khi tự chuyển cho chính mình"); sys.exit(3)
    errors = [d for d in done if d != "xong"]
    if bank.balance("a") != 50: errors.append(f"tự chuyển làm đổi số dư: {bank.balance('a')}")
    try:
        bank.transfer("a", "b", 51); errors.append("thiếu InsufficientFunds")
    except InsufficientFunds:
        if (bank.balance("a"), bank.balance("b")) != (50, 0): errors.append("số dư đổi dù không đủ tiền")
    for bad in ((("a", "b", 0), ValueError), (("a", "zz", 1), KeyError)):
        try:
            bank.transfer(*bad[0]); errors.append(f"thiếu {bad[1].__name__}")
        except bad[1]:
            pass
    calls = []
    orig = bank._audit
    bank._audit = lambda *e: (calls.append(e), orig(*e))
    bank.transfer("a", "b", 5)
    if not calls: errors.append("không còn gọi _audit")
    print("; ".join(errors) or "OK"); sys.exit(1 if errors else 0)
""")


def run(code, workdir, timeout):
    try:
        out = subprocess.run([sys.executable, "-c", code], cwd=str(workdir), capture_output=True, text=True,
                             timeout=timeout)
        return out.returncode, (out.stdout + out.stderr).strip()[-200:]
    except subprocess.TimeoutExpired:
        return 3, "TREO (hết giờ)"


def check(workdir, answer):
    workdir = Path(workdir)
    problems = []
    for name, code, timeout in (("ngữ nghĩa", SEMANTICS, 20), ("song song", PARALLEL, 30), ("tải nặng", STRESS, 40)):
        rc, out = run(code, workdir, timeout)
        if rc != 0:
            problems.append(f"{name}: {out}")
    return not problems, "; ".join(problems) or "đạt"
