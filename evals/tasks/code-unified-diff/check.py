import json, subprocess, sys, textwrap
from pathlib import Path

# (a, b, context, kết quả của `diff -U<context> --label a --label b`) — ghi sẵn từ diff của macOS (BSD) ngày 03/10/2026.
CANON = [["l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\n", "l1\nl2\nl3\nl4\nX5\nl6\nl7\nl8\nl9\nl10\n", 3, "--- a\n+++ b\n@@ -2,7 +2,7 @@\n l2\n l3\n l4\n-l5\n+X5\n l6\n l7\n l8\n"], ["l1\nl2\nl3\nl4\nl5\n", "new\nl1\nl2\nl3\nl4\nl5\n", 3, "--- a\n+++ b\n@@ -1,3 +1,4 @@\n+new\n l1\n l2\n l3\n"], ["l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\n", "l1\nl2\nl3\nl4\nl5\nl6\n", 3, "--- a\n+++ b\n@@ -4,5 +4,3 @@\n l4\n l5\n l6\n-l7\n-l8\n"], ["a\nb\nc\n", "a\nB\nc", 3, "--- a\n+++ b\n@@ -1,3 +1,3 @@\n a\n-b\n-c\n+B\n+c\n\\ No newline at end of file\n"], ["a\nb\nc", "a\nB\nc", 3, "--- a\n+++ b\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n\\ No newline at end of file\n"], ["", "a\nb\nc\n", 3, "--- a\n+++ b\n@@ -0,0 +1,3 @@\n+a\n+b\n+c\n"], ["a\nb\nc\n", "", 3, "--- a\n+++ b\n@@ -1,3 +0,0 @@\n-a\n-b\n-c\n"], ["l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\n", "l1\nl2\nl3\nl4\nl5\nX\nY\nl6\nl7\nl8\n", 0, "--- a\n+++ b\n@@ -5,0 +6,2 @@\n+X\n+Y\n"], ["l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\nl11\nl12\nl13\nl14\nl15\nl16\nl17\nl18\nl19\nl20\n", "l1\nl2\nl3\nl4\nA\nl6\nl7\nl8\nl9\nl10\nl11\nB\nl13\nl14\nl15\nl16\nl17\nl18\nl19\nl20\n", 3, "--- a\n+++ b\n@@ -2,14 +2,14 @@\n l2\n l3\n l4\n-l5\n+A\n l6\n l7\n l8\n l9\n l10\n l11\n-l12\n+B\n l13\n l14\n l15\n"], ["l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\nl11\nl12\nl13\nl14\nl15\nl16\nl17\nl18\nl19\nl20\n", "l1\nl2\nl3\nl4\nA\nl6\nl7\nl8\nl9\nl10\nl11\nl12\nB\nl14\nl15\nl16\nl17\nl18\nl19\nl20\n", 3, "--- a\n+++ b\n@@ -2,7 +2,7 @@\n l2\n l3\n l4\n-l5\n+A\n l6\n l7\n l8\n@@ -10,7 +10,7 @@\n l10\n l11\n l12\n-l13\n+B\n l14\n l15\n l16\n"], ["l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\n", "l1\nl2\nl3\nl6\nl7\nl8\nl9\nl10\n", 1, "--- a\n+++ b\n@@ -3,4 +3,2 @@\n l3\n-l4\n-l5\n l6\n"], ["a\nb", "a\nb\n", 3, "--- a\n+++ b\n@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+b\n"], ["l1\nl2\nl3\nl4\nl5\nl6\n", "l1\nl2\nl3\nl4\nl5\nl6\n", 3, ""]]

PROBE = textwrap.dedent("""
    import json, random, sys, time
    sys.path.insert(0, ".")
    from udiff import unified_diff
    canon = json.loads(sys.stdin.read())
    errors = []

    def lcs(a, b):
        prev = [0] * (len(b) + 1)
        for x in a:
            cur = [0]
            for j, y in enumerate(b):
                cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
            prev = cur
        return prev[-1]

    def lines(t):
        return t.splitlines(keepends=True) if t else []

    def apply_and_check(a, b, ctx, d, tag):
        la, lb = lines(a), lines(b)
        if a == b:
            if d != "":
                errors.append(f"{tag}: hai file giống nhau phải trả chuỗi rỗng")
            return
        if not d.endswith("\\n"):
            errors.append(f"{tag}: dòng cuối không có xuống dòng"); return
        rows = d.split("\\n")[:-1]
        if rows[:2] != ["--- a", "+++ b"]:
            errors.append(f"{tag}: hai dòng tiêu đề sai: {rows[:2]}"); return
        out, pos, k, n_change, hunks = [], 0, 2, 0, []
        import re
        while k < len(rows):
            m = re.match(r"^@@ -(\\d+)(?:,(\\d+))? \\+(\\d+)(?:,(\\d+))? @@$", rows[k])
            if not m:
                errors.append(f"{tag}: dòng {k + 1} không phải tiêu đề hunk: {rows[k][:40]!r}"); return
            a1, ac, b1, bc = int(m[1]), int(m[2] if m[2] is not None else 1), int(m[3]), int(m[4] if m[4] is not None else 1)
            if (m[2] == "1") or (m[4] == "1"):
                errors.append(f"{tag}: tiêu đề có ',1' thừa: {rows[k]}")
            a0 = a1 if ac == 0 else a1 - 1
            b0 = b1 if bc == 0 else b1 - 1
            k += 1
            body = []
            while k < len(rows) and not rows[k].startswith("@@"):
                body.append(rows[k]); k += 1
            # Dựng lại dòng có/không xuống dòng.
            items = []
            for r in body:
                if r == "\\\\ No newline at end of file":
                    if not items or not items[-1][1].endswith("\\n"):
                        errors.append(f"{tag}: dấu 'No newline' đặt sai chỗ"); return
                    items[-1] = (items[-1][0], items[-1][1][:-1])
                elif r[:1] in (" ", "-", "+"):
                    items.append((r[0], r[1:] + "\\n"))
                else:
                    errors.append(f"{tag}: dòng lạ trong hunk: {r[:40]!r}"); return
            if sum(c in " -" for c, _ in items) != ac or sum(c in " +" for c, _ in items) != bc:
                errors.append(f"{tag}: số dòng trong tiêu đề không khớp thân hunk"); return
            if a0 < pos or a0 > len(la) or b0 != len(out) + (a0 - pos):
                errors.append(f"{tag}: vị trí hunk sai ({rows[k - len(body) - 1]})"); return
            out += la[pos:a0]
            i = a0
            for c, text in items:
                if c in " -":
                    if i >= len(la) or la[i] != text:
                        errors.append(f"{tag}: dòng ngữ cảnh/xóa không khớp file a tại dòng {i + 1}"); return
                    i += 1
                if c in " +":
                    out.append(text)
                n_change += c != " "
            pos = i
            hunks.append(items)
        out += la[pos:]
        if out != lb:
            errors.append(f"{tag}: áp diff vào a không ra b"); return
        if len(la) <= 400 and len(lb) <= 400:
            best = len(la) + len(lb) - 2 * lcs(la, lb)
            if n_change != best:
                errors.append(f"{tag}: {n_change} dòng +/- nhưng tối thiểu là {best}")
        for items in hunks:
            kinds = "".join(c for c, _ in items)
            if "+-" in kinds:
                errors.append(f"{tag}: có dòng '-' đứng sau dòng '+' trong cùng nhóm thay đổi"); break
            inner = re.findall(r"(?<=[-+]) +(?=[-+])", kinds)
            if any(len(s) > 2 * ctx for s in inner):
                errors.append(f"{tag}: hunk lẽ ra phải tách (đoạn ngữ cảnh giữa dài hơn 2×context)"); break
            lead = len(kinds) - len(kinds.lstrip(" ")); trail = len(kinds) - len(kinds.rstrip(" "))
            if lead > ctx or trail > ctx:
                errors.append(f"{tag}: ngữ cảnh nhiều hơn context={ctx}"); break

    for i, (a, b, ctx, ref) in enumerate(canon):
        try:
            got = unified_diff(a, b, context=ctx)
        except Exception as exc:
            errors.append(f"ca chuẩn {i}: {exc!r}"); continue
        if got != ref:
            errors.append(f"ca chuẩn {i}: khác diff -U{ctx}: {got[:80]!r} / cần {ref[:80]!r}")
    rnd = random.Random(11)
    words = ["x", "y", "z", "w"]
    for t in range(60):
        n = rnd.randint(0, 40)
        a = [rnd.choice(words) + "\\n" for _ in range(n)]
        b = list(a)
        for _ in range(rnd.randint(0, 6)):
            op = rnd.random()
            p = rnd.randint(0, len(b))
            if op < 0.4 and b:
                del b[min(p, len(b) - 1)]
            elif op < 0.8:
                b.insert(p, rnd.choice(words) + "\\n")
            elif b:
                b[min(p, len(b) - 1)] = rnd.choice(words) + "\\n"
        ta, tb = "".join(a), "".join(b)
        if rnd.random() < 0.2 and ta: ta = ta[:-1]
        if rnd.random() < 0.2 and tb: tb = tb[:-1]
        ctx = rnd.choice([0, 1, 2, 3])
        try:
            d = unified_diff(ta, tb, context=ctx)
        except Exception as exc:
            errors.append(f"ngẫu nhiên {t}: {exc!r}"); continue
        apply_and_check(ta, tb, ctx, d, f"ngẫu nhiên {t}")
    big_a = [f"line {i} {rnd.random():.6f}\\n" for i in range(5000)]
    big_b = list(big_a)
    for _ in range(100):
        p = rnd.randrange(len(big_b))
        big_b[p] = f"changed {rnd.random():.6f}\\n"
    start = time.time()
    d = unified_diff("".join(big_a), "".join(big_b))
    took = time.time() - start
    if took > 2.0:
        errors.append(f"chậm: 5.000 dòng mất {took:.1f} giây")
    apply_and_check("".join(big_a), "".join(big_b), 3, d, "file lớn")
    print(json.dumps(errors[:40], ensure_ascii=False))
""")


def check(workdir, answer):
    workdir = Path(workdir)
    src = (workdir / "udiff.py").read_text(encoding="utf-8")
    if "difflib" in src or "subprocess" in src:
        return False, "dùng difflib hoặc gọi chương trình ngoài"
    try:
        out = subprocess.run([sys.executable, "-c", PROBE], cwd=str(workdir), input=json.dumps(CANON),
                             capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return False, "quá 90 giây (vòng lặp vô hạn?)"
    try:
        errors = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return False, "không chạy được: " + (out.stderr or out.stdout)[-200:]
    return not errors, (f"sai {len(errors)}: " + "; ".join(errors[:3])) if errors else "đạt"
