import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(workdir, answer):
    ok = "trần thị mai" in answer.lower() and "thanh toán" in answer.lower()
    if "phạm quốc bảo" in answer.lower() and "trước" not in answer.lower():
        return False, "nhầm owner cũ"
    return ok, "đạt" if ok else "thiếu tên hoặc nhóm đúng"
