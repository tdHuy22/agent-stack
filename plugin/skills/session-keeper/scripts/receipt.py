#!/usr/bin/env python3
"""Biên nhận kiểm tra: chạy một lệnh kiểm tra (test, lint, build) và ghi kết quả gắn với nội dung code
lúc chạy, để phiên sau và skill progress biết kết quả đó còn đúng cho code hiện tại hay đã cũ.

Kết quả đạt cũ không chứng minh cho code đã sửa sau đó. Biên nhận lưu dấu vân tay nội dung của cây làm
việc (file đang theo dõi và file mới), nên commit mà không đổi nội dung thì biên nhận vẫn còn khớp. Thêm một dấu cho
phần code (bỏ tài liệu theo done-gate), nên cập nhật §0, README sau bước kiểm cũng không làm cũ biên nhận.

Lệnh:
  receipt.py run [--project DIR] [--label TÊN] [--timeout GIÂY] -- <lệnh> [tham số...]
      Chạy lệnh (không qua shell), in output, ghi biên nhận. Mã thoát của receipt.py là mã thoát của lệnh.
  receipt.py show [--project DIR] [--json]
      In các lần kiểm tra đã ghi và cho biết từng kết quả còn khớp code hiện tại không.
  receipt.py forget [--project DIR] TÊN [TÊN...]
      Xoá biên nhận theo tên (tên như `show` in ra). Mã thoát 1 nếu có tên không tìm thấy.
  receipt.py fails-before [--project DIR] [--base REF] [--tests FILE...] [--link PATH...] [--label TÊN]
                          [--timeout GIÂY] -- <lệnh test> [tham số...]
      Bằng chứng test bắt được lỗi: chạy lệnh trên code trước bản sửa (commit REF, mặc định HEAD, cộng file test
      hiện tại) và sau bản sửa, trong thư mục tạm của hệ điều hành (fails_before.py). Mã 0: test bắt được lỗi;
      1: test đạt cả trên code cũ; 2: không kết luận được (sau bản sửa cũng trượt, hay đầu vào sai). File test mặc
      định là file đổi mà done-gate coi là test; `--link .venv` nối thư mục bị git bỏ qua mà lệnh cần.
  receipt.py lock [--project DIR] [--base REF] [--tests FILE...] [--link PATH...] [--level vua|cao]
                  [--label TÊN] [--timeout GIÂY] -- <lệnh test> [tham số...]
      Khóa test: chạy fails-before, mã 0 thì ghi sha256 và dấu từng dòng của mỗi file test vào `.agent/test-lock.json`
      của repo, kèm mức risk.py chấm (thấp: không khóa; --level chỉ nâng). Thêm dòng vào test khóa là siết (khóa lại
      được); sửa hay xóa là nới: hook nhắc (mức vừa) hay chặn (mức cao), done-gate báo đỏ.
  receipt.py locks [--project DIR]
      Liệt kê test đã khóa và file nào đã bị sửa.
  receipt.py unlock [--project DIR] --reason "<lời người dùng>" FILE...
      Bỏ khóa (nới), ghi bản ghi duyệt vào sổ. Hook chặn lệnh này trừ khi tin người dùng vừa gửi bảo mở khóa đúng file.
  receipt.py prune [--project DIR] [--dry-run]
      Xoá biên nhận trượt của lệnh test trỏ tới module hay file test không còn trong project (ví dụ
      `python3 -m unittest tests.test_cu` sau khi xoá tests/test_cu.py), vì chạy lại lệnh đó chỉ trượt mãi.
      Không chắc (discover, gói ngoài project, giá trị của option) thì giữ, để không che một test đang trượt thật.

Biên nhận nằm trong state/tests/ của agent-stack. Chỉ `lock`, `unlock` ghi vào project (`.agent/test-lock.json`,
commit cùng repo để mọi lần nới hiện ra trong diff).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))  # agentstack, testlock
import agentstack as A  # noqa: E402

TAIL_CHARS = 1500
MAX_CHECKS = 20


def summary_line(output: str) -> str:
    """Dòng tổng kết đáng tin nhất trong output (dòng cuối có chữ số hoặc từ khóa kết quả)."""
    keys = ("passed", "failed", "error", "ok", "fail", "ran ", "đạt", "lỗi", "tests", "warning")
    for line in reversed([ln.strip() for ln in output.splitlines() if ln.strip()]):
        if any(k in line.lower() for k in keys):
            return A.clip(line, 160)
    return ""


def record(root: Path, label: str, cmd: list, code: int, output: str, seconds: float,
           before, after, code_fingerprint=None, extra=None) -> dict:
    path = A.receipt_path(root)
    data = A.read_json(path, {}) or {}
    checks = data.get("checks") or {}
    rec = {"cmd": cmd, "ok": code == 0, "exit": code, "summary": summary_line(output),
           "tail": output[-TAIL_CHARS:], "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
           "seconds": round(seconds, 1), "fingerprint": after, "code_fingerprint": code_fingerprint,
           "fingerprint_before": before,
           "changed_tree": before is not None and after is not None and before != after, **(extra or {})}
    checks[label] = rec
    if len(checks) > MAX_CHECKS:  # giữ các lần kiểm tra mới nhất
        checks = dict(sorted(checks.items(), key=lambda kv: kv[1].get("ts", ""))[-MAX_CHECKS:])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        A.write_json_atomic(path, {"root": str(root), "checks": checks})
        rec["saved"] = True
    except OSError as exc:  # không ghi được biên nhận thì vẫn trả kết quả của lệnh
        rec["saved"] = False
        rec["save_error"] = str(exc)
    return rec


def risk_module():
    sys.path.insert(0, str(HERE.parents[2] / "done-gate" / "scripts"))
    import risk
    return risk


def fingerprints(root: Path):
    """(dấu vân tay cả cây, dấu vân tay phần code) của cây làm việc hiện tại. Phần code bỏ tài liệu (A.doc_filter), để
    cập nhật §0, README sau bước kiểm không làm cũ biên nhận (show, progress, hook Stop đọc cờ current)."""
    blobs, docs = A.tree_blobs(root), A.doc_filter(root)
    after = None if blobs is None else A.blobs_digest(blobs)
    return after, (None if blobs is None or docs is None else A.blobs_digest(blobs, docs))


def cmd_fails_before(root: Path, label: str, cmd: list, base: str, tests, links, timeout: float) -> int:
    return fails_before_run(root, label, cmd, base, tests, links, timeout)[0]


def fails_before_run(root: Path, label: str, cmd: list, base: str, tests, links, timeout: float):
    """(mã thoát, kết quả của fails_before hay None khi không chạy được)."""
    # Mọi lỗi đều thoát 2: traceback thoát 1, trùng nghĩa "test không bắt được lỗi".
    try:
        import fails_before as FB
    except Exception as exc:  # noqa: BLE001
        print(f"[receipt] không chạy được (lỗi bất ngờ): {exc!r}")
        return 2, None
    try:
        # Repo có clean filter riêng: tính dấu vân tay (git status, hash-object) sẽ chạy lệnh của repo (TM-57). Bỏ
        # dấu vân tay; hook Stop khi đó tính biên nhận chạy trong lượt.
        filtered = A.local_clean_filters(root)
        before = None if filtered else A.tree_fingerprint(root)
        risk = risk_module()
        result = FB.fails_before(root, cmd, base, tests, links, timeout, lambda p: risk.kind(p) == "test")
        after, code_fp = (None, None) if filtered else fingerprints(root)
    except FB.Problem as exc:
        print(f"[receipt] không chạy được: {exc}")
        return 2, None
    except Exception as exc:  # noqa: BLE001
        print(f"[receipt] không chạy được (lỗi bất ngờ): {exc!r}")
        return 2, None
    extra = {"kind": "fails-before", "verdict": result["verdict"], "base": result["base"], "tests": result["tests"],
             "before_exit": result["before_exit"], "after_exit": result["after_exit"]}
    rec = record(root, label, cmd, result["exit"], result["output"], result["seconds"], before, after, code_fp, extra)
    print(result["output"])
    note = " · thư mục làm việc đã đổi trong lúc chạy (không phải do lệnh này)" if rec["changed_tree"] else ""
    saved = "đã ghi biên nhận" if rec["saved"] else f"KHÔNG ghi được biên nhận ({rec['save_error']})"
    print(f"[receipt] {result['verdict']} · {', '.join(result['tests'][:3])} · {saved}{note}")
    return result["exit"], result


LEVEL_ORDER = {"thap": 0, "vua": 1, "cao": 2}


def testlock():
    import testlock as TL
    return TL


def git_top(root: Path):
    out = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def assessed_level(root: Path, base: str) -> str:
    """Mức rủi ro của thay đổi so với `base` theo risk.py; không chấm được thì "vua" (khóa còn hơn bỏ sót)."""
    try:
        risk = risk_module()
        return risk.assess(risk.collect(root, base))["level"]
    except Exception:  # noqa: BLE001
        return "vua"


def cmd_lock(root: Path, label: str, cmd: list, base: str, tests, links, timeout: float, level_arg) -> int:
    """Khóa test của thay đổi sau khi fails-before chứng minh chúng trượt trên code cũ (mã 0). Mức thấp không khóa;
    `--level` chỉ nâng được mức (siết), không hạ. File đã khóa mà bị sửa kiểu nới thì từ chối: phải `unlock` (người
    dùng duyệt) trước. Mã: 0 đã khóa hay mức thấp; 1, 2 như fails-before; 3 đụng file khóa bị nới."""
    TL = testlock()
    top = git_top(root)
    if top is None:
        print("[receipt] không khóa được: cần git repo")
        return 2
    level = assessed_level(root, base)
    if level_arg:
        if LEVEL_ORDER[level_arg] < LEVEL_ORDER[level]:
            print(f"[receipt] không hạ mức được: risk.py chấm {level}, --level {level_arg} thấp hơn (hạ mức là nới)")
            return 2
        level = level_arg
    if level == "thap":
        print("[receipt] mức rủi ro thấp: không khóa test (câu 3: mức thấp không khóa). Muốn khóa thì thêm --level vua.")
        return 0
    book = TL.load(top)
    if book.get("broken"):
        print(f"[receipt] không khóa: {TL.LOCK_REL} hỏng hay quá lớn, ghi đè sẽ mất các khóa cũ. Báo người dùng; trả sổ "
              "về bản đã commit (`git show HEAD:.agent/test-lock.json`) nếu nó bị sửa.")
        return 3
    loose = [rel for rel, entry in book["files"].items() if TL.status(top, rel, entry) in ("changed", "deleted")]
    if loose:
        print("[receipt] không khóa: file test đã khóa bị sửa hay xóa (nới): " + ", ".join(loose[:5])
              + ". Đề xuất cho người dùng duyệt rồi chạy `receipt.py unlock <file> --reason \"<lời người dùng>\"`, "
              "hoặc trả file về như cũ.")
        return 3
    code, result = fails_before_run(root, label, cmd, base, tests, links, timeout)
    if code != 0 or not result:
        print("[receipt] không khóa: fails-before chưa chứng minh test trượt trên code cũ")
        return code or 2
    locked = []
    for rel in result["tests"]:
        if not TL.safe_rel(rel):
            continue
        try:
            data = (top / rel).read_bytes()
        except OSError:
            continue
        old = book["files"].get(rel) or {}
        keep = old.get("level") if LEVEL_ORDER.get(old.get("level"), -1) > LEVEL_ORDER[level] else level
        book["files"][rel] = TL.entry_for(data, keep, cmd=cmd, base=result["base"], label=label)
        locked.append(f"{rel} ({keep})")
    try:
        TL.save(top, book)
    except OSError as exc:
        print(f"[receipt] KHÔNG ghi được sổ khóa ({exc})")
        return 2
    print(f"[receipt] đã khóa {len(locked)} file test vào {TL.LOCK_REL}: {', '.join(locked)}. Commit sổ cùng thay đổi.")
    return 0


def cmd_locks(root: Path) -> int:
    TL = testlock()
    top = git_top(root)
    book = TL.load(top) if top else TL.empty()
    if book.get("broken"):
        print(f"Sổ khóa {TL.LOCK_REL} hỏng hay quá lớn: không biết test nào đang khóa (done-gate báo đỏ).")
    if not book["files"]:
        print("Chưa có test nào bị khóa.")
        return 0
    names = {"same": "không đổi", "added": "chỉ thêm dòng (siết)", "changed": "bị sửa (nới, cần duyệt)",
             "deleted": "bị xóa (nới, cần duyệt)"}
    print(f"Test đã khóa ({TL.LOCK_REL}):")
    for rel, entry in sorted(book["files"].items()):
        print(f"- {rel}: mức {entry['level']}, khóa {ago(entry.get('ts'))}, {names[TL.status(top, rel, entry)]}")
    return 0


def cmd_unlock(root: Path, files: list, reason: str) -> int:
    """Bỏ khóa (nới): chỉ chạy khi người dùng đã duyệt; hook pretool_guard chặn lệnh này nếu tin người dùng vừa gửi
    không bảo mở khóa đúng file. Ghi bản ghi duyệt vào sổ để done-gate nêu lại trong báo cáo."""
    TL = testlock()
    top = git_top(root)
    if top is None:
        print("[receipt] cần git repo")
        return 2
    if not reason.strip():
        print("[receipt] thiếu --reason: chép lời duyệt của người dùng")
        return 2
    book = TL.load(top)
    if book.get("broken"):
        print(f"[receipt] {TL.LOCK_REL} hỏng hay quá lớn: không mở khóa (ghi lại sẽ mất các khóa khác)")
        return 2
    missing = []
    for f in files:
        try:
            rel = (root / f).resolve().relative_to(top.resolve()).as_posix()
        except ValueError:
            rel = None
        entry = book["files"].pop(rel, None) if rel else None
        if entry is None:
            missing.append(f)
            continue
        book["approvals"].append({"path": rel, "action": "unlock", "reason": reason.strip()[:500],
                                  "sha256": entry["sha256"], "level": entry["level"],
                                  "ts": datetime.now().astimezone().isoformat(timespec="seconds")})
        print(f"[receipt] đã mở khóa {rel} (mức {entry['level']})")
    if len(missing) < len(files):
        try:
            TL.save(top, book)
        except OSError as exc:
            print(f"[receipt] KHÔNG ghi được sổ khóa ({exc})")
            return 2
    for f in missing:
        print(f"[receipt] {f} không có trong sổ khóa")
    return 1 if missing else 0


def cmd_run(root: Path, label: str, cmd: list, timeout: float) -> int:
    before = A.tree_fingerprint(root)
    start = time.time()
    try:
        out = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=timeout)
        code, output = out.returncode, (out.stdout or "") + (out.stderr or "")
    except subprocess.TimeoutExpired as exc:
        code = 124
        output = ((exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        output += f"\n[receipt] dừng sau {timeout:.0f} giây"
    except OSError as exc:
        code, output = 127, f"[receipt] không chạy được lệnh: {exc}"
    seconds = time.time() - start
    after, code_fp = fingerprints(root)
    rec = record(root, label, cmd, code, output, seconds, before, after, code_fp)
    sys.stdout.write(output if output.endswith("\n") or not output else output + "\n")
    mark = "✓ đạt" if rec["ok"] else f"✗ trượt (mã {code})"
    note = " · lệnh đã làm thay đổi file trong project" if rec["changed_tree"] else ""
    where = "" if rec["fingerprint"] else " · không phải git repo nên không theo dõi được code có đổi sau đó không"
    saved = "đã ghi biên nhận" if rec["saved"] else f"KHÔNG ghi được biên nhận ({rec['save_error']})"
    print(f"[receipt] {mark} · {label} · {rec['seconds']} giây · {saved}{note}{where}")
    return code


MODULE_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")
PYTEST_VALUE_OPTS = ("--ignore", "--deselect", "--ignore-glob", "-k", "-m", "-p", "-c", "-o", "--rootdir",
                     "--junitxml", "--basetemp", "--confcutdir")
PYTEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")


def load_checks(root: Path) -> dict:
    """Các biên nhận đã ghi; bỏ qua phần hỏng (file không phải dict, mục không phải dict)."""
    data = A.read_json(A.receipt_path(root), {})
    checks = data.get("checks") if isinstance(data, dict) else None
    if not isinstance(checks, dict):
        return {}
    return {label: rec for label, rec in checks.items() if isinstance(label, str) and isinstance(rec, dict)}


def save_checks(root: Path, checks: dict):
    """Ghi lại biên nhận (xoá file khi không còn mục nào). Trả về lỗi dạng chữ, hoặc None khi ghi được."""
    path = A.receipt_path(root)
    try:
        if checks:
            path.parent.mkdir(parents=True, exist_ok=True)
            A.write_json_atomic(path, {"root": str(root), "checks": checks})
        elif path.exists():
            path.unlink()
    except OSError as exc:
        return str(exc)
    return None


def unittest_missing(root: Path, args: list) -> list:
    if "discover" in args:
        return []  # discover tự tìm test theo pattern: không biết chắc module nào
    missing, skip = [], False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg == "-k":
            skip = True  # giá trị của -k là mẫu tên test, không phải module
            continue
        if arg.startswith("-") or not MODULE_RE.match(arg):
            continue
        parts = arg.split(".")
        if not ((root / parts[0]).is_dir() or (root / f"{parts[0]}.py").is_file()):
            continue  # gốc không nằm trong project (gói đã cài, hay lớp test): không đoán
        # Còn khi có một tiền tố là file .py (phần sau là lớp, hàm test), hoặc cả tên là một gói.
        as_file = any((root / Path(*parts[:i])).with_suffix(".py").is_file() for i in range(1, len(parts) + 1))
        if not as_file and not (root / Path(*parts) / "__init__.py").is_file():
            missing.append(arg)
    return missing


def missing_targets(root: Path, cmd) -> list:
    """Module hay file test mà lệnh nhắc tới nhưng không còn trong project; rỗng khi không chắc. Chỉ xét
    `python -m unittest a.b.c` (module, lớp hay hàm test, gốc `a` phải nằm trong project; bỏ qua discover và giá
    trị của -k) và pytest với tham số là file test theo quy ước tên (`test_*.py`, `*_test.py`, kể cả `::test_y`)
    trong thư mục đang có. Lệnh khác trả về rỗng."""
    if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) for x in cmd):
        return []
    for i, arg in enumerate(cmd):
        if arg == "unittest" and i > 0 and cmd[i - 1] == "-m":
            return unittest_missing(root, cmd[i + 1:])
    pytest_at = next((i for i, arg in enumerate(cmd)
                      if (arg == "pytest" and i > 0 and cmd[i - 1] == "-m")
                      or (i == 0 and Path(arg).name in ("pytest", "py.test"))), None)
    if pytest_at is None:
        return []
    missing, skip = [], False
    for arg in cmd[pytest_at + 1:]:
        if skip:
            skip = False
            continue
        if arg in PYTEST_VALUE_OPTS:
            skip = True  # file bị loại khỏi lần chạy (--ignore x.py): mất cũng không làm lệnh trượt
            continue
        target = arg.split("::", 1)[0]
        if arg.startswith("-") or not PYTEST_FILE_RE.search(target):
            continue
        if (root / target).parent.is_dir() and not (root / target).exists():
            missing.append(arg)
    return missing


def cmd_forget(root: Path, labels: list) -> int:
    checks = load_checks(root)
    labels = list(dict.fromkeys(labels))
    gone = [label for label in labels if label in checks]
    unknown = [label for label in labels if label not in checks]
    for label in gone:
        del checks[label]
    error = save_checks(root, checks) if gone else None
    if error:
        print(f"Không ghi được biên nhận ({error}); chưa xoá gì.")
        return 1
    for label in gone:
        print(f"Đã xoá biên nhận: {label}")
    for label in unknown:
        print(f"Không có biên nhận tên {label!r}.")
    if unknown and checks:
        print("Các tên hiện có: " + "; ".join(sorted(checks)))
    return 1 if unknown else 0


def cmd_prune(root: Path, dry_run: bool) -> int:
    """Chỉ xoá biên nhận trượt; biên nhận đạt luôn giữ."""
    checks = load_checks(root)
    stale = {label: missing_targets(root, rec.get("cmd")) for label, rec in checks.items() if rec.get("ok") is False}
    stale = {label: miss for label, miss in stale.items() if miss}
    if not stale:
        print("Không có biên nhận nào trỏ tới test đã xoá.")
        return 0
    for label in stale:
        checks.pop(label)
    error = None if dry_run else save_checks(root, checks)
    if error:
        print(f"Không ghi được biên nhận ({error}); chưa xoá gì.")
        return 1
    verb = "Sẽ xoá" if dry_run else "Đã xoá"
    for label, miss in stale.items():
        print(f"{verb} biên nhận: {label} (không còn: {', '.join(miss)})")
    return 0


def ago(ts: str) -> str:
    try:
        delta = time.time() - datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return "?"
    if delta < 3600:
        return f"{int(delta // 60)} phút trước"
    if delta < 86400:
        return f"{int(delta // 3600)} giờ trước"
    return f"{int(delta // 86400)} ngày trước"


def freshness(rec: dict) -> str:
    """Kết quả còn đúng cho code hiện tại không, theo cờ current của A.receipt_status."""
    if rec.get("current") and rec.get("fresh") is False:
        return "còn khớp code hiện tại (sau đó chỉ tài liệu đổi)"
    return {True: "còn khớp code hiện tại", False: "code đã đổi sau lần chạy này, cần chạy lại",
            None: "không rõ code có đổi sau đó không"}[rec.get("current")]


def describe(label: str, rec: dict) -> str:
    mark = "✓ đạt" if rec.get("ok") else f"✗ trượt (mã {rec.get('exit')})"
    fresh = freshness(rec)
    summary = f" · {rec['summary']}" if rec.get("summary") else ""
    return f"- {label}: {mark}, {ago(rec.get('ts'))}, {fresh}{summary}"


def cmd_show(root: Path, as_json: bool) -> int:
    checks = A.receipt_status(root)
    if as_json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
        return 0
    if not checks:
        print(f"Chưa có biên nhận kiểm tra nào cho {root.name}. Ghi bằng: receipt.py run -- <lệnh kiểm tra>")
        return 0
    print(f"Kiểm tra đã ghi cho {root.name}:")
    for label, rec in sorted(checks.items(), key=lambda kv: kv[1].get("ts", ""), reverse=True):
        print(describe(label, rec))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Biên nhận kiểm tra gắn với nội dung code.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="chạy lệnh kiểm tra và ghi biên nhận")
    run.add_argument("--project", default=".")
    run.add_argument("--label", help="tên lần kiểm tra (mặc định: chính câu lệnh)")
    run.add_argument("--timeout", type=float, default=1800)
    run.add_argument("command", nargs=argparse.REMAINDER, help="-- <lệnh> [tham số...]")
    show = sub.add_parser("show", help="xem các biên nhận đã ghi")
    show.add_argument("--project", default=".")
    show.add_argument("--json", action="store_true")
    forget = sub.add_parser("forget", help="xoá biên nhận theo tên")
    forget.add_argument("--project", default=".")
    forget.add_argument("labels", nargs="+", metavar="TÊN")
    fb = sub.add_parser("fails-before", help="chứng minh test mới bắt được lỗi: trượt trước bản sửa, đạt sau")
    fb.add_argument("--project", default=".")
    fb.add_argument("--base", default="HEAD", help="commit ngay trước bản sửa (mặc định HEAD, khi chưa commit)")
    fb.add_argument("--tests", nargs="+", metavar="FILE", help="file test (mặc định: file test đổi so với --base)")
    fb.add_argument("--link", action="append", metavar="PATH",
                    help="nối thư mục bị git bỏ qua mà lệnh cần, ví dụ .venv (lặp lại được)")
    fb.add_argument("--label", help="tên biên nhận (mặc định: fails-before + câu lệnh)")
    fb.add_argument("--timeout", type=float, default=1800, help="giới hạn mỗi phía, giây")
    fb.add_argument("command", nargs=argparse.REMAINDER, help="-- <lệnh test> [tham số...]")
    lock = sub.add_parser("lock", help="khóa test sau khi fails-before chứng minh trượt trên code cũ")
    lock.add_argument("--project", default=".")
    lock.add_argument("--base", default="HEAD", help="commit ngay trước bản sửa (mặc định HEAD, khi chưa commit)")
    lock.add_argument("--tests", nargs="+", metavar="FILE", help="file test (mặc định: file test đổi so với --base)")
    lock.add_argument("--link", action="append", metavar="PATH", help="như fails-before")
    lock.add_argument("--level", choices=("vua", "cao"), help="nâng mức khóa (không hạ dưới mức risk.py chấm)")
    lock.add_argument("--label", help="tên biên nhận (mặc định: lock + câu lệnh)")
    lock.add_argument("--timeout", type=float, default=1800, help="giới hạn mỗi phía, giây")
    lock.add_argument("command", nargs=argparse.REMAINDER, help="-- <lệnh test> [tham số...]")
    locks = sub.add_parser("locks", help="xem test đã khóa và file nào đã bị sửa")
    locks.add_argument("--project", default=".")
    unlock = sub.add_parser("unlock", help="bỏ khóa test (nới): chỉ khi người dùng đã duyệt")
    unlock.add_argument("--project", default=".")
    unlock.add_argument("--reason", required=True, help="lời duyệt của người dùng")
    unlock.add_argument("files", nargs="+", metavar="FILE")
    prune = sub.add_parser("prune", help="xoá biên nhận trượt của test đã bị xoá khỏi project")
    prune.add_argument("--project", default=".")
    prune.add_argument("--dry-run", action="store_true", help="chỉ in, không xoá")
    args = ap.parse_args(argv)
    root = A.project_root(Path(args.project).expanduser().resolve())
    if args.cmd == "show":
        return cmd_show(root, args.json)
    if args.cmd == "forget":
        return cmd_forget(root, args.labels)
    if args.cmd == "prune":
        return cmd_prune(root, args.dry_run)
    if args.cmd == "locks":
        return cmd_locks(root)
    if args.cmd == "unlock":
        return cmd_unlock(root, args.files, args.reason)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        ap.error("thiếu lệnh kiểm tra, ví dụ: receipt.py run -- python3 -m pytest -q")
    if args.cmd == "fails-before":
        label = args.label or A.clip("fails-before: " + " ".join(command), 80)
        return cmd_fails_before(root, label, command, args.base, args.tests, args.link, args.timeout)
    if args.cmd == "lock":
        label = args.label or A.clip("lock: " + " ".join(command), 80)
        return cmd_lock(root, label, command, args.base, args.tests, args.link, args.timeout, args.level)
    return cmd_run(root, args.label or A.clip(" ".join(command), 80), command, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
