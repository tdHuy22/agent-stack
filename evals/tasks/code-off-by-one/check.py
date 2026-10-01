import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

ORIGINAL_TEST = "4c89c915aa9a62133833296c8777a6b5aea0f5632c7fb7ab3ba4e9ca71a69eae"

def check(workdir, answer):
    workdir = Path(workdir)
    if sha(workdir / "test_pager.py") != ORIGINAL_TEST:
        return False, "file test đã bị sửa"
    code, out = run([sys.executable, "-m", "unittest", "-q"], workdir)
    return code == 0, out[-400:]
