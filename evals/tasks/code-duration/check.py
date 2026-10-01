import hashlib, json, re, subprocess, sys
from pathlib import Path

def run(cmd, cwd, timeout=60):
    out = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return out.returncode, out.stdout + out.stderr

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

CASES_OK = {"1h30m": 5400, "45s": 45, "2d": 172800, "1d2h3m4s": 93784, "1h 30m": 5400, " 5m ": 300, "0s": 0}
CASES_BAD = ["", "   ", "10x", "1h1h", "30m1h", "-5m", "h", "1.5h", "5"]

def check(workdir, answer):
    sys.path.insert(0, str(workdir))
    for name in list(sys.modules):
        if name == "duration":
            del sys.modules[name]
    try:
        from duration import parse_duration
    except Exception as exc:
        return False, f"không import được: {exc}"
    wrong = []
    for text, expected in CASES_OK.items():
        try:
            got = parse_duration(text)
        except Exception as exc:
            got = repr(exc)
        if got != expected:
            wrong.append(f"{text!r} → {got} (cần {expected})")
    for text in CASES_BAD:
        try:
            parse_duration(text)
            wrong.append(f"{text!r} lẽ ra phải ném ValueError")
        except ValueError:
            pass
        except Exception as exc:
            wrong.append(f"{text!r} ném {type(exc).__name__} thay vì ValueError")
    sys.path.remove(str(workdir))
    return not wrong, "; ".join(wrong[:5]) or "đạt"
