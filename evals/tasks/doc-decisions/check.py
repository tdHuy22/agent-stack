import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

EXPECTED = {("đỗ minh an", "2026-10-15"), ("vũ thu hà", "2026-10-05"), ("ngô thanh bình", "2026-10-31")}

def check(workdir, answer):
    path = Path(workdir) / "decisions.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"không đọc được decisions.json: {exc}"
    got = {(str(i.get("owner", "")).strip().lower(), str(i.get("due", "")).strip()) for i in items if isinstance(i, dict)}
    if got != EXPECTED:
        return False, f"lệch: thừa {got - EXPECTED}, thiếu {EXPECTED - got}"
    return True, "đạt"
