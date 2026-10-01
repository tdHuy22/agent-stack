import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

HIDDEN = """
import unittest
from users import change_email, create_user

class Hidden(unittest.TestCase):
    def test_message(self):
        with self.assertRaises(ValueError) as ctx:
            create_user(" X@Y ", "x")
        self.assertEqual(str(ctx.exception), "Email không hợp lệ: x@y")

    def test_change_keeps_fields(self):
        self.assertEqual(change_email({"email": "a@b.co", "name": "A"}, "B@C.io"),
                         {"email": "b@c.io", "name": "A"})
"""

def check(workdir, answer):
    workdir = Path(workdir)
    source = (workdir / "users.py").read_text(encoding="utf-8")
    if len(re.findall(r"re\.match\(EMAIL_RE", source)) > 1:
        return False, "phần kiểm tra email vẫn lặp lại"
    (workdir / "test_hidden.py").write_text(HIDDEN, encoding="utf-8")
    code, out = run([sys.executable, "-m", "unittest", "-q"], workdir)
    return code == 0, out[-400:]
