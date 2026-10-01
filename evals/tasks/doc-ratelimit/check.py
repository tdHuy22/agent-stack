import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(workdir, answer):
    missing = [k for k in ("120", "X-RateLimit-Remaining", "429") if k.lower() not in answer.lower()]
    if re.search(r"\b60\s*request", answer) and "120" not in answer:
        return False, "dùng số cũ trong changelog"
    return not missing, "thiếu: " + ", ".join(missing) if missing else "đạt"
