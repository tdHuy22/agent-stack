import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(workdir, answer):
    text = answer.lower()
    if "get_user" not in text or "injection" not in text:
        return False, "không nêu SQL injection ở get_user"
    for line in text.splitlines():
        if "get_order" in line and re.search(r"injection|lỗ hổng|vulnerab|nguy hiểm", line) and not re.search(r"an toàn|safe|không có|tham số", line):
            return False, "báo nhầm get_order là lỗ hổng"
    return True, "đạt"
