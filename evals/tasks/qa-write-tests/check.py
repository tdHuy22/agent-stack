import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

import shutil, tempfile

MUTANTS = {
    "không chữ thường": "text = text.lower()", 
    "không gộp gạch": 'text = re.sub(r"[^a-z0-9]+", "-", text)',
    "không bỏ gạch hai đầu": 'return text.strip("-")',
}
REPLACE = {
    "không chữ thường": "text = text",
    "không gộp gạch": 'text = re.sub(r"[^a-z0-9]", "-", text)',
    "không bỏ gạch hai đầu": "return text",
}

def check(workdir, answer):
    workdir = Path(workdir)
    if not (workdir / "test_text.py").exists():
        return False, "chưa có test_text.py"
    original = (workdir / "text.py").read_text(encoding="utf-8")
    if "re.sub" not in original or "strip" not in original:
        return False, "text.py đã bị sửa"
    code, out = run([sys.executable, "-m", "unittest", "-q"], workdir)
    if code != 0:
        return False, "test không đạt với code gốc: " + out[-200:]
    killed = []
    for name, needle in MUTANTS.items():
        tmp = Path(tempfile.mkdtemp(dir=str(workdir.parent)))
        try:
            shutil.copy(workdir / "test_text.py", tmp / "test_text.py")
            (tmp / "text.py").write_text(original.replace(needle, REPLACE[name]), encoding="utf-8")
            code, _ = run([sys.executable, "-m", "unittest", "-q"], tmp)
            if code != 0:
                killed.append(name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return len(killed) >= 2, f"bắt được {len(killed)}/3 lỗi cấy: {', '.join(killed) or 'không'}"
