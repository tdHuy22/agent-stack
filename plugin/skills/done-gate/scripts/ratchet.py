"""Bánh cóc của done-gate (GĐ2, 13/11/2026): phân loại thay đổi là siết hay nới bằng diff và sổ khóa, không theo lời
agent tự nhận. Siết (agent tự làm): thêm test, thêm hàm test hay thêm assert ở cuối hàm của test đã khóa (testlock.compare),
khóa thêm, nâng ngưỡng. Nới (người dùng
duyệt): sửa hay xóa test đã khóa, mở khóa không có bản ghi duyệt, sửa tay sổ khóa, hạ ngưỡng, sửa hay xóa dòng spec có
sẵn, nới assert hay thêm skip. Spec và code đổi trong cùng một thay đổi thì đỏ.

So file trên đĩa với sổ khóa (không phụ thuộc hook, TM-102) và sổ hiện tại với sổ ở base (TM-103).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import testlock as TL  # noqa: E402

SPEC_RE = re.compile(r"(^|/)\.agent/specs?/|(^|/)specs?/[^/]+\.(md|html|feature|ya?ml)$|(^|/)spec[^/]*\.(md|html)$|"
                     r"(^|/)[^/]+\.spec\.(md|html)$|(^|/)\.arch/")
CONFIG_RE = re.compile(r"(^|/)(pyproject\.toml|setup\.cfg|tox\.ini|pytest\.ini|\.coveragerc|ruff\.toml|biome\.json|"
                       r"package\.json|(jest|vitest|karma)\.config\.\w+|\.github/workflows/[^/]+\.ya?ml|Makefile|"
                       r"codecov\.ya?ml|\.pre-commit-config\.ya?ml)$")
# Ngưỡng: khóa = số (TOML, INI, JSON, Python, YAML) hay cờ dòng lệnh --x=số. Tên khóa phải có một từ ngưỡng đứng riêng
# (tách ở _ . - và chữ hoa): MAX_TOTAL_CHARS, fail_under, coverageThreshold; không phải admin_count, terminal_width.
THRESHOLD_RE = re.compile(r"([A-Za-z_][\w.-]*)[\"']?\s*[:=]\s*[\"']?(\d+(?:\.\d+)?)\b")
THRESHOLD_WORDS = {"threshold", "thresholds", "min", "max", "minimum", "maximum", "limit", "budget", "coverage", "under"}
UPPER_WORDS = {"max", "maximum", "limit", "budget"}  # tăng các ngưỡng này là nới; còn lại giảm là nới
COMMENT_RE = re.compile(r"^\s*(#|//|;|--(?!\w))")


def key_words(key: str) -> set:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    return {w.lower() for w in re.split(r"[\s_.-]+", spaced) if w}


def git_text(root: Path, *args: str):
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def thresholds(text: str) -> dict:
    found = {}
    for line in (text or "").splitlines():
        if COMMENT_RE.match(line):
            continue
        for key, value in THRESHOLD_RE.findall(line):
            if key_words(key) & THRESHOLD_WORDS:
                found.setdefault(key.lower(), float(value))
    return found


def threshold_moves(changes: list, kind) -> tuple:
    """(nới, siết): ngưỡng số đổi hay bị bỏ trong file test hay file cấu hình kiểm, xét theo chiều của tên khóa."""
    loose, tight = [], []
    for c in changes:
        if kind(c["path"]) != "test" and not CONFIG_RE.search(c["path"]):
            continue
        old, new = thresholds(c.get("removed") or ""), thresholds(c.get("text") or "")
        for key in sorted(old):
            a = old[key]
            if key not in new:
                loose.append(f"bỏ ngưỡng {key} = {a:g} ({c['path']})")
                continue
            b = new[key]
            if a == b:
                continue
            looser = b > a if key_words(key) & UPPER_WORDS else b < a
            shown = f"{key}: {a:g} → {b:g} ({c['path']})"
            (loose if looser else tight).append(("hạ ngưỡng " if looser else "nâng ngưỡng ") + shown)
    return loose, tight


def consent_receipts(top: Path) -> dict:
    """{(đường dẫn, sha256 của bản đã khóa): số lần} mà hook pretool_guard đã cho `receipt.py unlock` qua nhờ lời người
    dùng, theo biên nhận trong state/ của agent-stack (ngoài repo, TM-104)."""
    out = {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
        import agentstack as A
        seen = A.read_json(A.state_dir() / "unlock-consents.json", [])
        here = str(Path(top).resolve())
        for r in seen if isinstance(seen, list) else []:
            if isinstance(r, dict) and str(Path(str(r.get("top"))).resolve()) == here:
                key = (r.get("path"), r.get("sha256"))
                out[key] = out.get(key, 0) + 1
    except Exception:  # noqa: BLE001
        return {}
    return out


def entry_matches_file(top: Path, rel: str, entry: dict) -> bool:
    """Mục sổ đúng là bản `receipt.py lock` sẽ ghi cho file hiện tại (sha, dấu dòng, cấu trúc), không yếu hơn."""
    try:
        data = (Path(top) / rel).read_bytes()
    except OSError:
        return False
    fresh = TL.entry_for(data, entry.get("level", "vua"))
    return (entry.get("sha256") == fresh["sha256"] and entry.get("lines") == fresh["lines"]
            and (entry.get("py") or {}).get("items") == (fresh.get("py") or {}).get("items"))


def base_book(top: Path, base: str | None) -> dict:
    text = git_text(top, "show", f"{base or 'HEAD'}:{TL.LOCK_REL}")
    return TL.parse(text) if text else TL.empty()


def classify(root, changes: list, base: str | None = None, kind=None, weakening=None) -> dict:
    """{"loosen", "approved", "tighten", "red", "verdict"}; verdict: "do" (có nới chưa duyệt hay spec + code cùng đổi),
    "vang" (chỉ nới đã duyệt), "xanh" (chỉ siết), "" (không có gì để nói)."""
    root = Path(root)
    top_text = git_text(root, "rev-parse", "--show-toplevel")
    top = Path(top_text.strip()) if top_text and top_text.strip() else root
    kind = kind or (lambda p: "test" if re.search(r"(^|/)tests?/|test_|_test\.", p) else "code")
    loosen, approved, tighten, red = [], [], [], []
    now, before = TL.load(top), base_book(top, base)
    if now.get("broken"):
        loosen.append(f"sổ khóa {TL.LOCK_REL} hỏng hay quá lớn: không biết test nào đang khóa (sổ bị sửa tay?)")
    receipts = consent_receipts(top)
    old_approvals = {(a.get("path"), a.get("sha256"), a.get("ts")) for a in before["approvals"]}
    approvals = {}
    for a in now["approvals"]:
        key = (a.get("path"), a.get("sha256"))
        if (a.get("path"), a.get("sha256"), a.get("ts")) in old_approvals:
            approvals[key] = a
        elif receipts.get(key, 0) > 0:
            receipts[key] -= 1  # một lời đồng ý chỉ cho một lần mở khóa đúng bản đã khóa
            approvals[key] = a
        else:
            loosen.append(f"bản ghi duyệt mở khóa {a.get('path')} không có biên nhận đồng ý của hook (tự ghi vào sổ?)")

    for rel, old in before["files"].items():
        cur = now["files"].get(rel)
        if cur is None:
            ok = approvals.get((rel, old.get("sha256")))
            if ok:
                approved.append(f"mở khóa {rel} (mức {old['level']}), lời duyệt ghi: {ok.get('reason', '')[:120]}")
            else:
                loosen.append(f"mở khóa {rel} mà sổ không có bản ghi duyệt (sổ bị sửa tay?)")
        elif {k: v for k, v in cur.items() if k != "ts"} != {k: v for k, v in old.items() if k != "ts"}:
            # Mục khóa đổi (sha, dòng, cấu trúc, mức): so file hiện tại với bản ở base, không với sổ vừa sửa.
            ok = approvals.get((rel, old.get("sha256")))
            if TL.LEVELS.index(cur["level"]) < TL.LEVELS.index(old["level"]):
                loosen.append(f"hạ mức khóa {rel}: {old['level']} → {cur['level']}")
            if ok:
                approved.append(f"sửa rồi khóa lại {rel} sau khi mở khóa, lời duyệt ghi: {ok.get('reason', '')[:120]}")
            elif not entry_matches_file(top, rel, cur):
                loosen.append(f"mục sổ của {rel} không khớp file hiện tại (sổ bị sửa tay cho yếu đi?)")
            elif TL.status(top, rel, old) in ("added", "same"):
                tighten.append(f"khóa lại {rel} sau khi thêm test")
            else:
                loosen.append(f"sửa test đã khóa {rel} rồi ghi lại sổ (dòng cũ bị sửa hay xóa)")
    for rel, entry in now["files"].items():
        if rel not in before["files"]:
            tighten.append(f"khóa thêm {rel} (mức {entry['level']})")
        state = TL.status(top, rel, entry)
        if state == "changed":
            loosen.append(f"sửa test đã khóa {rel} (mức {entry['level']}): dòng cũ bị sửa hay xóa")
        elif state == "deleted":
            loosen.append(f"xóa test đã khóa {rel} (mức {entry['level']})")
        elif state == "added":
            tighten.append(f"thêm test vào test đã khóa {rel} (chưa khóa lại)")

    locked = set(now["files"]) | set(before["files"])
    for c in changes:
        path = c["path"]
        if kind(path) == "test" and path not in locked and (c.get("added") or 0) > 0 and not c.get("removed"):
            tighten.append(f"thêm test {path}")
    if weakening:
        weakening(changes, lambda _pts, reason, paths: loosen.append(
            f"{reason}" + (f": {', '.join(paths[:3])}" if paths else "")))

    loose, tight = threshold_moves(changes, kind)
    loosen += loose
    tighten += tight

    specs = [c for c in changes if SPEC_RE.search(c["path"].lower())]
    for c in specs:
        if (c.get("removed") or "").strip():
            loosen.append(f"đổi spec {c['path']}: dòng có sẵn bị sửa hay xóa")
    code = [c["path"] for c in changes if kind(c["path"]) == "code" and not SPEC_RE.search(c["path"].lower())
            and c["path"] != TL.LOCK_REL]
    if specs and code:
        red.append(f"spec và code đổi trong cùng một thay đổi: {', '.join(c['path'] for c in specs[:3])} cùng "
                   f"{', '.join(code[:3])}" + (f" và {len(code) - 3} file khác" if len(code) > 3 else ""))

    verdict = "do" if loosen or red else "vang" if approved else "xanh" if tighten else ""
    return {"loosen": loosen, "approved": approved, "tighten": tighten, "red": red, "verdict": verdict}


def render(r: dict) -> list:
    if not r or not r.get("verdict"):
        return []
    head = {"do": "🔴 có nới chưa được duyệt: đưa vào \"Cần bạn quyết\", đề xuất cho người dùng, không tự quyết",
            "vang": "🟡 chỉ có nới đã được người dùng duyệt: nêu lại trong báo cáo",
            "xanh": "🟢 chỉ siết"}[r["verdict"]]
    lines = [f"Bánh cóc: {head}"]
    lines += [f"- 🔴 nới: {x}" for x in r["loosen"]]
    lines += [f"- 🔴 {x}" for x in r["red"]]
    lines += [f"- 🟡 nới đã duyệt: {x}" for x in r["approved"]]
    lines += [f"- 🟢 siết: {x}" for x in r["tighten"][:8]]
    if len(r["tighten"]) > 8:
        lines.append(f"- 🟢 và {len(r['tighten']) - 8} chỗ siết khác")
    return lines
