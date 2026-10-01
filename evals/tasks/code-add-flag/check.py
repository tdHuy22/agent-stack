import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(workdir, answer):
    workdir = Path(workdir)
    code, out = run([sys.executable, "wc.py", "--json", "sample.txt"], workdir)
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return False, f"không phải JSON: {out[-200:]}"
    if data != {"lines": 4, "words": 6}:
        return False, f"sai giá trị: {data}"
    code, out = run([sys.executable, "wc.py", "sample.txt"], workdir)
    if out.strip() != "4 dòng, 6 từ":
        return False, f"đầu ra cũ bị đổi: {out.strip()!r}"
    return True, "đạt"
