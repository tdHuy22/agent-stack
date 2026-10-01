import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(workdir, answer):
    text = answer.lower()
    ok = "download" in text and re.search(r"path traversal|traversal|\.\./|duyệt thư mục", text)
    return bool(ok), "đạt" if ok else "không nêu path traversal ở download"
