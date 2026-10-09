#!/usr/bin/env python3
"""Hook PreToolUse: chốt chặn tự động trước một số lệnh, để skill cần thiết chạy mà không cần người dùng nhắc.

- Cài skill, plugin, MCP chưa qua vet-skill và chưa được duyệt trong vetted.lock: từ chối, nhắc chạy vet-skill.
  Thêm marketplace lạ: hỏi người dùng.
- `git checkout <ref>` hay `git switch` khi cây có thay đổi chưa commit: hỏi người dùng (TM-3: skill bên thứ ba như
  differential-review checkout baseline trên cây đang sửa dở).
- Ghi báo cáo `*DIFFERENTIAL_REVIEW*.md` vào trong project thay vì thư mục tạm: từ chối (TM-4: danh sách lỗ hổng chưa
  vá bị commit lẫn).
- Sửa file mã nguồn khi router thấy lượt này làm chức năng đụng ranh giới tin cậy mà chưa có threat model: từ chối
  một lần, nhắc chạy mo-hinh-de-doa trước khi code.

Lệnh không khớp mẫu nào thì thoát ngay, không in gì. Mọi lỗi đều bỏ qua: hook không bao giờ được làm kẹt phiên.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

HEREDOC_RE = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PREFIXES = {"sudo", "env", "command", "exec", "time", "nohup", "nice", "!"}
SHELLS = {"sh", "bash", "zsh", "dash"}
FLAGS_WITH_VALUE = {"--scope", "-s", "--transport", "-t", "--env", "-e", "--header", "-H", "--sparse"}
REPORT_RE = re.compile(r"differential[_-]?review", re.I)
OS_TEMP = ("/tmp/", "/private/tmp/", "/private/var/folders/", "/var/folders/")
SOURCE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java", ".kt", ".php", ".rs", ".c",
              ".cc", ".cpp", ".h", ".hpp", ".cs", ".swift", ".scala", ".sh", ".lua", ".pl", ".sql"}


def decide(decision: str, reason: str) -> None:
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                                        "permissionDecisionReason": reason}}, ensure_ascii=False))


def lib():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
    import agentstack
    return agentstack


def approved_plugins(A) -> set:
    """Id "tên@marketplace" của plugin trong catalog.json đã được duyệt trong vetted.lock."""
    home = A.home_dir()
    if not home:
        return set()
    lock = (A.read_json(home / "vetted.lock", {}) or {}).get("entries", {})
    out = set()
    for item in (A.read_json(home / "catalog.json", {}) or {}).get("items", []):
        inst = item.get("install") or {}
        review = ((lock.get(item.get("key")) or {}).get("human_review") or {}).get("status")
        if review == "approved" and inst.get("plugin") and inst.get("marketplace"):
            out.add(f"{inst['plugin']}@{inst['marketplace']}")
    return out


def simple_commands(command: str, depth: int = 0) -> list:
    """Tách chuỗi lệnh shell thành các lệnh đơn (danh sách argv): bỏ thân heredoc, tách ở ; && || | & ( ) và xuống
    dòng, bỏ gán biến và tiền tố như sudo, env; mở `bash -c "..."` thêm một tầng. Chuỗi trích dẫn (thông điệp commit,
    echo) nằm trong argv của lệnh khác nên không bị hiểu nhầm là lệnh. Không phân tích được thì trả rỗng."""
    text = HEREDOC_RE.sub("\n", command)
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    out, current = [], []
    for token in tokens + [";"]:
        if token and set(token) <= set(";&|()\n"):
            while current and (ASSIGN_RE.match(current[0]) or current[0] in PREFIXES):
                current.pop(0)
            if current:
                if Path(current[0]).name in SHELLS and "-c" in current and depth < 2:
                    i = current.index("-c")
                    out += simple_commands(current[i + 1], depth + 1) if i + 1 < len(current) else []
                else:
                    out.append(current)
            current = []
        else:
            current.append(token)
    return out


def positional(args: list, with_value=FLAGS_WITH_VALUE) -> list:
    """Đối số không phải cờ, bỏ cả giá trị của cờ cần giá trị (--scope project)."""
    out, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif arg.startswith("-"):
            skip = arg in with_value
        else:
            out.append(arg)
    return out


def check_bash(command: str, cwd: str):
    """(quyết định, lý do) hoặc None, xét từng lệnh đơn trong chuỗi."""
    for argv in simple_commands(command):
        result = check_argv(argv, cwd)
        if result:
            return result
    return None


def check_argv(argv: list, cwd: str):
    vet_hint = ("Chạy skill vet-skill cho nó trước; chỉ cài khi người dùng đã duyệt trong vetted.lock "
                "(cài bằng ./install.sh của agent-stack). Nếu người dùng muốn tự cài thì họ chạy lệnh này trong terminal.")
    prog, args = Path(argv[0]).name, argv[1:]
    words = positional(args)
    if prog == "claude" and words[:2] in (["plugin", "install"], ["plugin", "i"]) and len(words) > 2:
        plugin = words[2]
        if plugin.split("@")[0] in ("agent-stack", "agent-stack-vendor") or plugin in approved_plugins(lib()):
            return None
        return "deny", f"agent-stack: plugin `{plugin}` chưa qua vet-skill hoặc chưa được duyệt. {vet_hint}"
    if prog == "claude" and words[:3] == ["plugin", "marketplace", "add"] and len(words) > 3:
        source = words[3].rstrip("/")
        home = lib().home_dir()
        if home and Path(source).expanduser().resolve() in (home.resolve(), (home / "vendor").resolve()):
            return None
        return "ask", (f"agent-stack: thêm marketplace `{source}` làm mọi plugin trong đó cài được, dù chưa qua "
                       "vet-skill. Người dùng xác nhận trước khi thêm.")
    if prog == "claude" and words[:1] == ["mcp"] and len(words) > 1 and words[1].startswith("add"):
        return "deny", f"agent-stack: thêm MCP server phải qua vet-skill trước. {vet_hint}"
    if prog == "npx" and "add" in words and any(w == "skills" or w.startswith("skills@") for w in words):
        return "deny", f"agent-stack: cài skill bên thứ ba phải qua vet-skill trước. {vet_hint}"
    if prog == "git":
        where = Path(cwd or ".")
        while args and args[0].startswith("-"):  # tùy chọn chung của git: -C <thư mục>, -c <khóa=giá trị>, --no-pager
            if args[0] in ("-C", "-c") and len(args) >= 2:
                if args[0] == "-C":
                    where = where / Path(args[1]).expanduser()
                args = args[2:]
            else:
                args = args[1:]
        if args[:1] in (["checkout"], ["switch"]):
            return check_checkout(args[0], args[1:], where)
    return None


def check_checkout(verb: str, args: list, where: Path):
    if any(a in ("-b", "-B", "-c", "-C", "--orphan", "-h", "--help") for a in args):
        return None  # tạo nhánh mới từ chỗ đang đứng: cây giữ nguyên
    targets = [a for a in args if not a.startswith("-")]
    if not targets:
        return None
    dirty = (lib().git_out(where, "status", "--porcelain", "--untracked-files=no") or "").strip()
    if not dirty:
        return None
    count = len(dirty.splitlines())
    if "--" in args or any(t == "." or (where / t).exists() for t in targets):
        return "ask", (f"agent-stack: `git {verb} {' '.join(args)}` ghi đè file bằng bản ở commit, làm mất thay đổi "
                       f"chưa commit (đang có {count} file đổi). Người dùng xác nhận nếu vẫn muốn chạy.")
    return "ask", (f"agent-stack: `git {verb}` sẽ đổi HEAD trong khi {count} file đang có thay đổi chưa commit; thay "
                   "đổi đó sẽ đi theo sang commit khác. Để xem file ở commit khác, dùng `git show <ref>:<file>`. "
                   "Người dùng xác nhận nếu vẫn muốn chạy.")


def safe_scratch(path: Path) -> bool:
    """Chỗ ghi tạm không lọt vào git: thư mục tạm của hệ điều hành, hay thư mục mà git của project bỏ qua."""
    text = str(path.resolve())
    tmp = os.environ.get("TMPDIR", "")
    if any(text.startswith(t) for t in OS_TEMP) or (tmp and text.startswith(str(Path(tmp).resolve()) + "/")):
        return True
    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return lib().git_out(parent, "check-ignore", "-q", str(path)) is not None


def check_write(tool_input: dict, cwd: str, session_id: str):
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path:
        return None
    full = Path(path) if Path(path).is_absolute() else Path(cwd or ".") / path
    if REPORT_RE.search(full.name) and full.suffix.lower() == ".md" and not safe_scratch(full):
        return "deny", ("agent-stack: báo cáo differential-review là danh sách lỗ hổng chưa vá; đừng ghi vào trong "
                        "project (dễ bị commit lẫn). Ghi vào `.tmp/` của project (nếu đã bị git bỏ qua) hoặc thư mục "
                        "tạm của hệ điều hành.")
    if full.suffix.lower() not in SOURCE_EXT or not session_id:
        return None
    A = lib()
    turn = A.load_turn(session_id)
    if not turn or not turn.get("threat_model") or turn.get("threat_model_nudged"):
        return None
    root = Path(turn.get("root") or "")
    try:
        full.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    if re.search(r"(^|/)(tests?|spec|__tests__)/", str(full)) or re.match(r"test_|.*_test\.", full.name):
        return None
    model = root / ".agent" / "threat-model.md"
    try:
        if model.stat().st_mtime >= turn["ts"]:
            return None
    except OSError:
        pass
    turn["threat_model_nudged"] = True
    A.save_turn(session_id, turn)
    own = (root / ".claude" / "skills" / "threat-model" / "SKILL.md").exists()
    skill = "skill threat-model của project này" if own else "skill mo-hinh-de-doa"
    return "deny", (f"agent-stack: lượt này làm chức năng đụng ranh giới tin cậy mà chưa có threat model. Trước khi "
                    f"code, chạy {skill} (ghi `.agent/threat-model.md`), rồi viết code kèm các chốt chặn. Nếu chức "
                    "năng thật ra không đụng ranh giới tin cậy thì cứ ghi lại file này: nhắc này chỉ hiện một lần.")


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    tool, tool_input = data.get("tool_name"), data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return
    cwd = data.get("cwd") or ""
    if tool == "Bash":
        result = check_bash(str(tool_input.get("command") or ""), cwd)
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        result = check_write(tool_input, cwd, data.get("session_id") or "")
    else:
        result = None
    if result:
        decide(*result)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 (hook không được làm kẹt phiên)
        try:
            lib().log_event("hook-error", {"hook": "pretool_guard", "error": repr(exc)[:300]})
        except Exception:  # noqa: BLE001
            pass
    sys.exit(0)
