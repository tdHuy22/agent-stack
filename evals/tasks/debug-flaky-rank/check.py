import os, subprocess, sys, textwrap
from pathlib import Path

# Chạy trong tiến trình con với nhiều PYTHONHASHSEED: lỗi phụ thuộc thứ tự set chỉ lộ ở vài hạt giống.
DRIVER = textwrap.dedent("""
    import sys
    sys.path.insert(0, ".")
    from rankings import build_table, render
    roster = ["Zeta", "alpha", "Beta", "Gamma", "delta", "Eps", "Omega", "Idle", "Idle2"]
    matches = [
        ("Zeta", 2, "alpha", 2), ("Beta", 3, "Gamma", 1), ("delta", 0, "Eps", 0), ("Omega", 1, "Zeta", 0),
        ("alpha", 1, "Beta", 0), ("Gamma", 2, "delta", 2), ("Eps", 0, "Omega", 1), ("Beta", 1, "Zeta", 1),
        ("Gamma", 0, "alpha", 1), ("Eps", 2, "delta", 1),
    ]
    rows = build_table(roster, matches)
    print(render(rows))
    print("|".join(f"{r.name}:{r.played}:{r.won}:{r.drawn}:{r.lost}:{r.gf}:{r.ga}:{r.gd}:{r.points}" for r in rows))
    for bad in (["A"], ):
        try:
            build_table(bad, [("A", 1, "B", 0)]); print("NO_VALUEERROR")
        except ValueError:
            print("VE")
    t = build_table(["Q", "q", "R"], [("Q", 1, "R", 1)])
    print([r.name for r in t])
""")

TIES = textwrap.dedent("""
    import sys
    sys.path.insert(0, ".")
    from rankings import build_table, render
    rows = build_table(["Tom", "Ann", "bob", "Cy", "Dee"], [("Tom", 1, "Ann", 1), ("bob", 1, "Cy", 1)])
    print(render(rows)); print(render([]) == "")
""")


def run(code, workdir, seed):
    env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONDONTWRITEBYTECODE="1")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(workdir), capture_output=True, text=True,
                         timeout=30, env=env)
    return out.returncode, out.stdout, out.stderr[-300:]


def check(workdir, answer):
    workdir = Path(workdir)
    outputs, problems = {}, []
    for seed in (0, 1, 2, 3, 4, 5, 6, 7):
        rc, out, err = run(DRIVER, workdir, seed)
        if rc != 0:
            return False, f"lỗi chạy (hạt {seed}): {err}"
        outputs[seed] = out
    if len(set(outputs.values())) > 1:
        problems.append("kết quả đổi theo PYTHONHASHSEED")
    got = outputs[0]
    expected = EXPECTED
    if got != expected:
        problems.append("kết quả sai so với đặc tả")
    rc, out, err = run(TIES, workdir, 0)
    if rc != 0 or out != TIES_EXPECTED:
        problems.append(f"hạng đồng hạng/rỗng sai: {(out or err)[:120]!r}")
    return not problems, "; ".join(problems) or "đạt"


# Đã tính tay theo đặc tả (xem bảng điểm ở DRIVER), không chép từ lời giải.
EXPECTED = (" 1. alpha         3   7\n 2. Omega         2   6\n 3. Beta          3   4\n 4. Eps           3   4\n"
            " 5. delta         3   2\n 5. Zeta          3   2\n 7. Gamma         3   1\n 8. Idle          0   0\n"
            " 8. Idle2         0   0\n"
            "alpha:3:2:1:0:4:2:2:7|Omega:2:2:0:0:2:0:2:6|Beta:3:1:1:1:4:3:1:4|Eps:3:1:1:1:2:2:0:4|"
            "delta:3:0:2:1:3:4:-1:2|Zeta:3:0:2:1:3:4:-1:2|Gamma:3:0:1:2:3:6:-3:1|Idle:0:0:0:0:0:0:0:0|"
            "Idle2:0:0:0:0:0:0:0:0\nVE\n['Q', 'R', 'q']\n")
TIES_EXPECTED = (" 1. Ann           1   1\n 1. bob           1   1\n 1. Cy            1   1\n 1. Tom           1   1\n"
                 " 5. Dee           0   0\nTrue\n")
