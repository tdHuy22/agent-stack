import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(workdir, answer):
    text = answer.lower()
    token = "api_token" in text or "token" in text
    logged = "log" in text and ("password" in text or "mật khẩu" in text)
    missing = [n for n, v in (("token hardcode", token), ("ghi mật khẩu vào log", logged)) if not v]
    return not missing, "thiếu: " + ", ".join(missing) if missing else "đạt"
