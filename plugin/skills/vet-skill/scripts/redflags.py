"""Luật dò dấu hiệu nguy hiểm trong skill/plugin của bên thứ ba.

Mỗi luật có phạm vi áp dụng:
  code  - script, file thực thi, cấu hình hook/MCP (chạy thật trên máy)
  md    - file chỉ dẫn cho model (SKILL.md, agents/*.md, commands/*.md...)
  any   - mọi file văn bản

Một mẫu xuất hiện trong tài liệu (md) có thể chỉ là ví dụ minh họa, ví dụ skill
bảo mật mô tả kiểu tấn công. Vì vậy vet.py chấm nặng hơn khi mẫu nằm trong code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SEVERITIES = ("critical", "high", "medium", "low", "info")


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    scope: str
    pattern: re.Pattern
    why: str


def _r(rule_id, severity, scope, regex, why, flags=re.IGNORECASE):
    return Rule(rule_id, severity, scope, re.compile(regex, flags), why)


RULES = [
    # Tải và chạy mã từ xa
    _r("rce-pipe", "critical", "any",
       r"\b(curl|wget)\b[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z|da)?sh\b|\b(ba|z)?sh\s+<\(\s*(curl|wget)|\biex\b[^\n]{0,80}\b(irm|iwr|invoke-webrequest|downloadstring)",
       "Tải script từ mạng rồi chạy thẳng bằng shell."),
    _r("download-exec", "high", "code",
       r"\b(curl|wget)\b[^\n]*(\s-o\s|\s-O\b|>\s*\S+)[^\n]*(&&|;)\s*(chmod\s+\+x|\./|(ba|z)?sh\s|open\s)",
       "Tải file về rồi cấp quyền chạy hoặc chạy ngay."),
    _r("decode-exec", "critical", "any",
       r"base64\s+(-d|--decode|-D)\b[^\n]*\|\s*(sudo\s+)?(ba|z)?sh\b|\b(exec|eval)\s*\([^\n]{0,80}(b64decode|base64|atob|Buffer\.from|fromCharCode|codecs\.decode)",
       "Giải mã nội dung bị che giấu rồi thực thi."),
    _r("reverse-shell", "critical", "any",
       r"/dev/tcp/|\bnc\s+(-[a-z]*e|-c)\b|\bncat\b[^\n]*\s-e\b|\bsocat\b[^\n]*\b(exec|system)\s*:|\bbash\s+-i\s*>&",
       "Mở reverse shell, cho máy khác điều khiển máy này."),
    # Đánh cắp thông tin xác thực
    _r("credential-access", "high", "any",
       r"~/\.ssh\b|\.ssh/id_|\bid_(rsa|ed25519|ecdsa)\b|\.aws/credentials|\.netrc\b|\.config/gh/hosts\.yml|\.claude/\.credentials|security\s+(find|dump)-(generic|internet)-password|\bdump-keychain\b|Login Data\b|Cookies\.binarycookies|keychain-db|\.gnupg/",
       "Đọc khóa SSH, token, keychain hoặc dữ liệu đăng nhập trình duyệt."),
    _r("exfil-endpoint", "high", "any",
       r"webhook\.site|requestbin|pipedream\.net|ngrok(-free)?\.(io|app|dev)|discord(app)?\.com/api/webhooks|api\.telegram\.org/bot|pastebin\.com|transfer\.sh|\b0x0\.st\b|interact\.sh|burpcollaborator|\boast\.(fun|pro|me|live|site)\b",
       "Gửi dữ liệu tới dịch vụ hứng dữ liệu (webhook, paste, tunnel)."),
    _r("post-local-file", "high", "code",
       r"\bcurl\b[^\n]*(\s-d|--data(-binary|-raw)?|\s-F|--form|--upload-file|\s-T)\s+['\"]?@",
       "Gửi nội dung file cục bộ lên mạng."),
    _r("raw-ip-url", "medium", "any",
       r"https?://(?!127\.0\.0\.1|0\.0\.0\.0|localhost)\d{1,3}(\.\d{1,3}){3}",
       "URL trỏ thẳng vào địa chỉ IP thay vì tên miền."),
    # Kỹ thuật thường gặp trong mã độc macOS (AMOS)
    _r("gatekeeper-bypass", "critical", "any",
       r"\bxattr\s+(-[a-z]*[dcr][a-z]*\s+)+[^\n]*com\.apple\.quarantine|\bspctl\s+--master-disable",
       "Gỡ cờ quarantine hoặc tắt Gatekeeper của macOS."),
    _r("osascript-password", "critical", "any",
       r"\bosascript\b[^\n]*(hidden answer|password|mật khẩu)",
       "Hiện hộp thoại giả để hỏi mật khẩu (kỹ thuật của mã độc AMOS)."),
    _r("persistence", "high", "code",
       r"Library/Launch(Agents|Daemons)|\blaunchctl\s+(load|bootstrap|submit)|\bcrontab\s+-|>>\s*['\"]?(~|\$HOME)?/?\.(zshrc|bashrc|bash_profile|zprofile|profile)\b",
       "Cài cơ chế tự chạy lại (LaunchAgent, cron, file khởi động shell)."),
    _r("destructive", "high", "code",
       r"\brm\s+-[a-z]*r[a-z]*f?[a-z]*\s+(/(\s|$|\*)|~(/?\s|/?$)|\$HOME\b)|\bmkfs\.|\bdd\s+if=[^\n]*of=/dev/",
       "Lệnh xóa hoặc ghi đè diện rộng."),
    # Vượt quyền của chính agent
    _r("permission-bypass", "high", "any",
       r"--dangerously-skip-permissions|\bbypassPermissions\b|--yolo\b|\"defaultMode\"\s*:\s*\"bypassPermissions\"",
       "Tắt cơ chế xin quyền của agent."),
    _r("sudo", "medium", "code", r"(^|[;&|\s])sudo\s+", "Chạy lệnh với quyền root."),
    _r("long-base64", "medium", "any", r"[A-Za-z0-9+/]{300,}={0,2}",
       "Chuỗi base64 dài, có thể là mã bị che giấu.", flags=0),
    _r("remote-package", "medium", "any",
       r"\bpip3?\s+install\s+[^\n]*(git\+|https?://)|\bnpx\s+(-y|--yes)\s+\S+",
       "Cài gói từ URL hoặc tự cài gói npm khi chạy, không ghim phiên bản."),
    _r("npm-lifecycle", "medium", "code", r"\"(pre|post)install\"\s*:",
       "Script tự chạy khi cài gói npm."),
    # Nhắm vào model (chỉ trong file chỉ dẫn)
    _r("prompt-injection", "high", "md",
       r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|messages)|disregard\s+(all\s+)?(the\s+)?(previous|prior|above)|(do\s+not|don'?t)\s+(tell|inform|notify|ask)\s+the\s+user|without\s+(telling|asking|informing|notifying)\s+the\s+user|bỏ\s+qua\s+(mọi|tất\s+cả|các)?\s*(hướng\s+dẫn|chỉ\s+dẫn)|(đừng|không\s+được)\s+(nói|báo)\s+(cho\s+)?người\s+dùng",
       "Câu chữ nhằm vô hiệu hóa chỉ dẫn hoặc giấu hành động khỏi người dùng."),
    _r("trigger-hijack", "low", "md",
       r"^description:[^\n]*\b(always use|use (this )?(for|on) (every|all|any)|use always|luôn (luôn )?dùng)\b",
       "Mô tả quá rộng để skill tự kích hoạt trong mọi tình huống."),
]

# Ký tự vô hình hoặc đảo chiều: dùng để giấu chỉ dẫn khỏi mắt người đọc.
HIDDEN_CHARS = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")

# Lệnh phổ biến mà một thư mục bin/ trên PATH có thể giả mạo.
SHADOWED_COMMANDS = {"git", "ls", "cat", "python", "python3", "node", "npm", "npx", "curl", "ssh", "sudo",
                     "bash", "sh", "zsh", "claude", "opencode", "gh", "pip", "pip3", "uv", "brew", "open", "rm"}


def scan_text(text: str, kind: str):
    """Trả về danh sách (rule, line_no, excerpt) cho một file. kind: code | md | other."""
    hits = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if len(line) > 5000:
            line = line[:5000]
        for rule in RULES:
            if rule.scope == "code" and kind != "code":
                continue
            if rule.scope == "md" and kind != "md":
                continue
            if rule.pattern.search(line):
                hits.append((rule, line_no, line.strip()[:160]))
    return hits


FENCE_ESCAPE = re.compile(chr(0x200B) + "(?=`)")
COMMENT_LINE = re.compile(r"^\s*(#|//|--|;|\*|/\*|<!--|rem\s)", re.IGNORECASE)
# allowed-tools tự duyệt sẵn lệnh tải-rồi-chạy hoặc lệnh tới host bất kỳ
RISKY_ALLOWED = re.compile(r"Bash\([^)]*(\|\s*(sudo\s+)?(ba|z)?sh\b|https?://\*|curl\s+\*|wget\s+\*)[^)]*\)",
                           re.IGNORECASE)


def is_comment(line: str) -> bool:
    return bool(COMMENT_LINE.match(line))


def hidden_chars(text: str, ignore_leading_bom: bool = True):
    """Trả về danh sách (line_no, codepoints, benign) có ký tự vô hình.

    benign = True khi chỉ là U+200B đứng ngay trước dấu backtick: mẹo thường dùng để
    hiển thị code fence lồng nhau trong ví dụ Markdown.
    """
    found = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if line_no == 1 and ignore_leading_bom and line.startswith(chr(0xFEFF)):
            line = line[1:]
        chars = HIDDEN_CHARS.findall(line)
        if chars:
            benign = not HIDDEN_CHARS.findall(FENCE_ESCAPE.sub("", line))
            found.append((line_no, sorted({f"U+{ord(c):04X}" for c in chars}), benign))
    return found
