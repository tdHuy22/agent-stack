#!/usr/bin/env python3
"""Hook PreToolUse: chốt chặn tự động trước một số lệnh, để skill cần thiết chạy mà không cần người dùng nhắc.

- Cài skill, plugin, MCP chưa qua vet-skill và chưa được duyệt trong vetted.lock: từ chối, nhắc chạy vet-skill.
  Thêm marketplace lạ: hỏi người dùng.
- `git checkout <ref>` hay `git switch` khi cây có thay đổi chưa commit: hỏi người dùng (TM-3: skill bên thứ ba như
  differential-review checkout baseline trên cây đang sửa dở).
- Ghi báo cáo `*DIFFERENTIAL_REVIEW*.md` vào trong project thay vì thư mục tạm: từ chối (TM-4: danh sách lỗ hổng chưa
  vá bị commit lẫn).
- Sửa file mã nguồn khi router thấy lượt này làm chức năng đụng ranh giới tin cậy mà chưa có threat model: từ chối
  một lần, nhắc chạy threat-model trước khi code.
- Sửa file mã nguồn khi router thấy lượt này làm tính năng, sửa lỗi, refactor hay kiến trúc mà §0 của file kế hoạch
  chưa có tiêu chí xong: từ chối một lần, nhắc ghi tiêu chí (việc từ mức vừa mà tiêu chí do agent suy thì hỏi người
  dùng xác nhận). Hai nhắc cùng đến hạn thì gộp vào một lần từ chối.
- Tạo file `.md` mới không thuộc loại bắt buộc Markdown: từ chối một lần cho mỗi file trong lượt, nhắc viết HTML
  theo skill reader-page (luật chung "File cho người đọc viết bằng HTML"); ghi lại thì cho qua.
- Tạo tag git hay `gh release create` (sắp phát hành): nhắc bước 3 của quy trình bảo mật là audit cả repo (Semgrep
  qua static-analysis, rồi claude-security). Lần đầu thì từ chối để lời nhắc tới Claude, Claude hỏi người dùng; lệnh
  chỉ qua khi người dùng đã nhắn sau lần từ chối đó. Không theo dõi được phiên thì hỏi người dùng như cũ.
- Lệnh không đảo ngược được (cải tiến 6): `git push` (mọi dạng, trừ --dry-run), `git reset --hard`, `git clean -f`
  (trừ -n, và -X chỉ xóa file git bỏ qua), `rm -r` với đích ngoài chỗ ghi tạm, `git commit --amend` và `git rebase`
  khi viết lại commit đã có trên remote: qua cùng cổng với tag (chặn lần đầu, người dùng nhắn lại thì cho qua), khóa
  theo gốc repo và đúng lệnh. Chữ "git push" trong thông điệp commit, heredoc, echo không phải lệnh nên không bị hỏi.
- Lệnh xóa ổ đĩa (việc G, 19/11/2026): `diskutil erase*` (`eraseDisk`, `eraseVolume`), `secureErase`, `zeroDisk`,
  `randomDisk`, `partitionDisk`, `reformat`, `apfs deleteContainer`/`deleteVolume`/`eraseVolume`: chặn hẳn, lời đồng ý
  trong chat không mở (TM-148, TM-149). Tên lệnh và verb so không phân biệt hoa thường, sau khi bỏ `sudo`, mở `sh -c`,
  cả sau `/usr/bin/env`, `xargs`, `find -exec`, lệnh con, ống vào shell. Chỉ `diskutil` (bạn chốt 19/11/2026): `dd`,
  `newfs*`, `mkfs*`, ghi `>` vào `/dev/disk*` cần root, máy hỏi mật khẩu `sudo`, nên không chặn. Biết mà không sửa (hook
  chỉ nhằm chặn nhầm tay): `xargs sudo diskutil …`, tên lệnh trong biến, `python -c`, `osascript`, lệnh trong file
  script. Lớp hai: luật `permissions.deny` do bước `deny` của `tools/install.py` ghi.

Lệnh không khớp mẫu nào thì thoát ngay, không in gì. Mọi lỗi đều bỏ qua: hook không bao giờ được làm kẹt phiên.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

# `\` cuối dòng (số lẻ dấu `\`; `\\` là một dấu `\` thật): shell nối với dòng sau thành một lệnh.
CONTINUATION_RE = re.compile(r"(?<!\\)((?:\\\\)*)\\\n")
SHELL_C_RE = re.compile(r"^-[a-zA-Z]*c[a-zA-Z]*$")  # bash -c, -lc, -ec
HEREDOC_RE = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PREFIXES = {"sudo", "env", "command", "builtin", "exec", "time", "nohup", "nice", "timeout", "!"}
# Từ khóa shell đứng đầu một lệnh đơn (`if git push; then rm -rf x; fi`, `for d in a; do …; done`, `{ git push; }`).
KEYWORDS = {"if", "then", "elif", "else", "do", "while", "until", "{"}
# Cờ cần giá trị của các lệnh bọc (`sudo -u root rm -rf x`, `env -u X git push`, `timeout -s KILL 30 git push`).
WRAPPER_FLAGS_WITH_VALUE = {"sudo": {"-u", "-g", "-p", "-C", "-D", "-h", "-r", "-t", "-U", "-T", "--user", "--group",
                                     "--prompt", "--close-from", "--chdir", "--host", "--role", "--type", "--other-user",
                                     "--command-timeout"},
                            "env": {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"},
                            "nice": {"-n", "--adjustment"}, "timeout": {"-s", "--signal", "-k", "--kill-after"},
                            "time": {"-f", "-o", "--format", "--output"}, "exec": {"-a"}}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
SHELLS = {"sh", "bash", "zsh", "dash"}
FLAGS_WITH_VALUE = {"--scope", "-s", "--transport", "-t", "--env", "-e", "--header", "-H", "--sparse"}
# git tag: cờ chỉ xem, xóa hay kiểm tag (không tạo tag mới), và cờ cần giá trị (giá trị không phải tên tag).
TAG_READ_FLAGS = {"-l", "--list", "-d", "--delete", "-v", "--verify", "--contains", "--no-contains", "--points-at",
                  "--merged", "--no-merged", "--column", "--no-column", "--sort", "--format", "-h", "--help"}
TAG_FLAGS_WITH_VALUE = {"-m", "--message", "-F", "--file", "-u", "--local-user", "--cleanup", "--trailer"}
GH_RELEASE_FLAGS_WITH_VALUE = {"-n", "--notes", "-F", "--notes-file", "-t", "--title", "--target", "-R", "--repo",
                               "--discussion-category", "--notes-start-tag"}
REBASE_FLAGS_WITH_VALUE = {"--onto", "-s", "--strategy", "-X", "--strategy-option", "-x", "--exec", "--whitespace",
                           "--empty"}
REBASE_STATE_FLAGS = {"--continue", "--abort", "--skip", "--quit", "--edit-todo", "--show-current-patch"}
PUSH_REWRITE_FLAGS = {"-f", "--force", "--force-with-lease", "--force-if-includes", "--mirror", "--delete", "-d",
                      "--prune"}
REDIRECT_RE = re.compile(r"^\d*(>>?|<)")
# Chỗ tạm cho rm (bạn chọn 04/11/2026: "chỉ thư mục tạm thật"): bên dưới thư mục tạm của hệ điều hành (không phải chính
# nó), hay thư mục git bỏ qua mà có tên kiểu tạm, build, cache. Thư mục git bỏ qua khác (backups, state, samples) vẫn hỏi.
RM_SCRATCH_NAMES = {".tmp", "tmp", "build", "dist", "node_modules", "__pycache__", ".cache", ".venv", "venv",
                    ".pytest_cache", ".mypy_cache", ".ruff_cache"}
MKTEMP_RE = re.compile(r"(?:^|[\s;&|(])([A-Za-z_][A-Za-z0-9_]*)=[\"']?\$\(\s*mktemp\b([^)]*)\)")
GLOB_CHARS = "*?[{"
# Thư mục chạy không biết trước (`cd t*`, `--cwd $PWD/tests`): glob, biến hay lệnh con. Phần có biến, lệnh con thì giá trị
# có thể là bất cứ đâu (cả đường dẫn tuyệt đối).
DIR_UNKNOWN = GLOB_CHARS + "$`"
DIR_OPAQUE = "$`()"
REPORT_RE = re.compile(r"differential[_-]?review", re.I)
OS_TEMP = ("/tmp/", "/private/tmp/", "/private/var/folders/", "/var/folders/")
SOURCE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java", ".kt", ".php", ".rs", ".c",
              ".cc", ".cpp", ".h", ".hpp", ".cs", ".swift", ".scala", ".sh", ".lua", ".pl", ".sql"}
# File bắt buộc Markdown (luật chung, mục "File cho người đọc viết bằng HTML"): agent, công cụ hay nền tảng đọc nó.
# Tên file kế hoạch (PLAN_CANDIDATES) và LAST-TURN lấy từ agentstack, không chép lại ở đây.
MD_NAMES = {"claude.md", "claude.local.md", "agents.md", "gemini.md", "skill.md", "readme.md", "changelog.md",
            "contributing.md", "security.md", "code_of_conduct.md", "license.md", "support.md", "nhat-ky.md",
            "threat-model.md", "memory.md", "pull_request_template.md"}
# Lệnh xóa ổ đĩa: chặn hẳn (TM-148). Verb của diskutil so sau casefold.
DISKUTIL_WIPE = {"secureerase", "zerodisk", "randomdisk", "partitiondisk", "reformat"}
DISKUTIL_APFS = {"apfs", "ap"}
DISKUTIL_APFS_WIPE = {"deletecontainer", "deletevolume", "erasevolume"}
XARGS_VALUE_FLAGS = {"-I", "-J", "-L", "-n", "-P", "-R", "-S", "-s", "-E", "-d", "-a", "--max-args", "--max-procs",
                     "--max-lines", "--max-chars", "--delimiter", "--arg-file", "--eof", "--process-slot-var"}
DISK_SHELLS = SHELLS | {"ksh", "mksh", "csh", "tcsh", "fish"}
DISK_WRAPPERS = {"caffeinate", "arch"}  # chạy lệnh theo sau, cờ đứng trước
DISK_TEXT_RES = (
    re.compile(r"\bdiskutil\b[^\n;|&]*?\b(?:erase\w*|secureerase|zerodisk|randomdisk|partitiondisk|reformat|"
               r"deletecontainer|deletevolume)\b"),
)
MD_DIRS = {".claude", ".agent", ".agents", ".github", ".cursor", "skills", "agents", "commands", "memory", "plans",
           "references", "prompts"}


def decide(decision: str, reason: str) -> None:
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                                        "permissionDecisionReason": reason}}, ensure_ascii=False))


def lib():
    path = str(Path(__file__).resolve().parents[1] / "lib")
    if path not in sys.path:
        sys.path.insert(0, path)
    import agentstack
    return agentstack


def arch_lib():
    lib()
    import archgate
    return archgate


ARCH_FILE_REASON = ("agent-stack: `{rel}` là file luật kiến trúc của archctl, chỉ người dùng đổi (qua `archctl accept`, "
                    "`reject`, `baseline`). Muốn đổi luật thì chạy `archctl propose '<luật>' --reason \"...\"` (hay "
                    "`archctl block --on '<luật>' --reason \"...\"` khi bế tắc) rồi dừng phần việc đó, chờ người dùng.")
ARCH_CMD_REASON = ("agent-stack: `archctl {sub}` là lệnh của người dùng (giao thức archctl: agent chỉ đề xuất hay báo bế "
                   "tắc, người duyệt). Đừng chạy, kể cả qua đường khác. Dùng `archctl propose` hay `archctl block`, rồi "
                   "báo người dùng tự chạy `archctl {sub} …` trong terminal nếu họ đồng ý.")


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


def simple_commands(command: str, depth: int = 0, commenters: str = "#") -> list:
    """Tách chuỗi lệnh shell thành các lệnh đơn (danh sách argv): bỏ thân heredoc, tách ở ; && || | & ( ) và xuống
    dòng, nối dòng kết thúc bằng `\\`, bỏ gán biến và tiền tố như sudo, env; mở `bash -c "..."` (cả `-lc`, `-ec`) và
    `eval '...'` thêm một tầng. Chuỗi trích dẫn (thông điệp commit, echo) nằm trong argv của lệnh khác nên không bị hiểu
    nhầm là lệnh. Không phân tích được thì trả rỗng."""
    # Bỏ thân heredoc nhưng giữ phần còn lại của dòng mở (`cat <<'EOF' > f`, `<<EOF | tee f`, `<<EOF && git push`).
    text = CONTINUATION_RE.sub(r"\1 ", HEREDOC_RE.sub(lambda m: " " + m.group(3) + "\n", command))
    text = re.sub(r">\|", ">", text)  # `>|` (ghi đè dù noclobber) là chuyển hướng, không phải ống
    text = re.sub(r">&(?=[^\d\s&-])", ">", text)  # `>&file` ghi vào file, không phải chạy nền (`2>&1` giữ nguyên)
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = commenters
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    out, current = [], []
    for token in tokens + [";"]:
        if token and set(token) <= set(";&|()\n"):
            current = strip_prefixes(current)
            if current:
                flag = next((i for i, a in enumerate(current[1:], 1) if SHELL_C_RE.match(a)), None)
                if flag is not None and flag + 1 < len(current) and current[flag + 1] == "--":
                    flag += 1  # `bash -c -- '…'`: chuỗi lệnh đứng sau `--`
                if Path(current[0]).name in SHELLS and flag is not None and depth < 2:
                    out += simple_commands(current[flag + 1], depth + 1, commenters) if flag + 1 < len(current) else []
                elif current[0] == "eval" and depth < 2:
                    out += simple_commands(" ".join(current[1:]), depth + 1, commenters)
                else:
                    out.append(current)
            current = []
        else:
            current.append(token)
    return out


def strip_prefixes(argv: list) -> list:
    """Bỏ gán biến, từ khóa shell và lệnh bọc (kèm cờ của chúng; `timeout` bỏ cả thời lượng) ở đầu một lệnh đơn."""
    argv = list(argv)
    while argv and (ASSIGN_RE.match(argv[0]) or argv[0] in PREFIXES or argv[0] in KEYWORDS):
        word = argv.pop(0)
        values = WRAPPER_FLAGS_WITH_VALUE.get(word, set())
        while argv and argv[0].startswith("-") and argv[0] != "-" and (word in WRAPPER_FLAGS_WITH_VALUE
                                                                        or word == "command"):
            flag = argv.pop(0)
            if flag in values and argv:
                argv.pop(0)
        if word == "timeout" and argv:
            argv.pop(0)  # thời lượng
    return argv


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


def check_bash(command: str, cwd: str, session_id: str = ""):
    """(quyết định, lý do) hoặc None, xét mọi lệnh đơn trong chuỗi. Từ chối đứng trước cổng hỏi người dùng (nhắc audit,
    lệnh không đảo ngược), cổng đứng trước hỏi: lời nhắc không được che lệnh bị chặn đứng sau nó, vì qua cổng là cả
    chuỗi chạy."""
    results = []
    wipe = check_disk_command(command)  # chặn hẳn, đứng trước mọi cổng khác
    if wipe:
        return wipe
    if LOCK_NAME in command:
        found = lock_named_by_interpreter(command, cwd)
        if found:
            return found
    # Lọc trước trên chuỗi đã bỏ dấu nháy, gạch chéo như shell sẽ bỏ; casefold vì hệ thống file macOS không phân biệt
    # hoa thường.
    if "spec-appr" in re.sub(r"[\"'\\\\]", "", command).casefold() or "specbook" in command:
        try:
            found = spec_book_bash(command, cwd)
        except Exception:  # noqa: BLE001 (lỗi phần này không được tắt các chốt chặn khác)
            found = None
        if found:
            return found
    if ".arch" in command.casefold() or "archctl" in command.casefold():
        found = arch_named_by_interpreter(command, cwd) or arch_fed_to_shell(command, cwd)
        if found:
            return found
    if any(n in command for n in STACK_SNAP_NAMES) or ("stack.py" in command and "approve" in command):
        found = stack_named_by_interpreter(command)
        if found:
            return found
    if "find" in command:
        try:
            found = stack_find_check(command, cwd)
        except Exception:  # noqa: BLE001 (lỗi phần này không được tắt các chốt chặn khác)
            found = None
        if found:
            return found
    temp_vars = mktemp_vars(command)
    states = [(cwd, None, [])]
    for argv in simple_commands(command):
        if Path(argv[0]).name in ("cd", "pushd", "popd"):  # `cd <thư mục> && git tag v1`: các lệnh sau chạy ở thư mục mới
            states = next_dirs(argv, states)
            continue
        for here in dict.fromkeys(st[0] for st in states):
            result = check_argv(argv, here, temp_vars, session_id)
            try:
                unknown = unknown_dir_check(argv, here, session_id)  # chỉ hỏi: đứng sau mọi chặn và cổng ở trên
            except Exception:  # noqa: BLE001 (lỗi phần này không được tắt các chốt chặn khác)
                unknown = None
            results += [r for r in (result, unknown) if r and r not in results]
    denied = [r for r in results if r[0] == "deny"]
    if denied:
        return denied[0]
    if any(changes_remote(argv) for argv in simple_commands(command)):
        # `git remote add evil URL && git push evil`: đổi đích của push trong cùng chuỗi thì luôn hỏi
        results = [r[:3] + (None,) if r[0] == "confirm" else r for r in results]
    gated = [r for r in results if r[0] in ("audit", "confirm")]
    return (gate_user(gated, session_id) if gated else None) or next((r for r in results if r[0] == "ask"), None)


def next_dirs(argv: list, states: list) -> list:
    """Các trạng thái (thư mục chạy, OLDPWD, chồng pushd) có thể có sau `cd`, `pushd`, `popd`. Lệnh không đoán được
    (`cd -`, `popd` khi chồng rỗng, `cd t*`, `~user` không có) có thể thất bại và đứng nguyên, mà sau `;` lệnh tiếp vẫn
    chạy: giữ cả thư mục cũ để `popd; rm tests/x.py` vẫn bị chặn như trước. Tối đa 8 trạng thái."""
    out = {}
    for cwd, oldpwd, stack in states:
        new = change_dir(argv, cwd, oldpwd, stack)
        out.setdefault((new[0], new[1], tuple(new[2])), new)
        if "$OLDPWD" in new[0] or any(ch in a for a in argv[1:] for ch in GLOB_CHARS):
            out.setdefault((cwd, oldpwd, tuple(stack)), (cwd, oldpwd, stack))
    return list(out.values())[:8]


def change_dir(argv: list, cwd: str, oldpwd, stack: list) -> tuple:
    """(thư mục chạy, OLDPWD, chồng pushd) sau `cd`, `pushd`, `popd` trong chuỗi lệnh: bỏ chuyển hướng, cờ -L -P -e -@ và
    `--`. Không đoán được (`cd -`, `popd` khi chuỗi chưa đổi thư mục, `pushd +1`, nhiều tham số) thì thành `$OLDPWD` để
    `unknown_dir_check` xét. `cd` không tham số giữ thư mục cũ như trước."""
    prog = Path(argv[0]).name
    args = drop_redirects(argv[1:])
    while args and re.fullmatch(r"-[LPe@]+", args[0]):
        args = args[1:]
    args = args[1:] if args[:1] == ["--"] else args
    here = cwd or "."
    unknown = str(Path(here) / "$OLDPWD")
    if prog == "popd":
        return (stack[-1] if stack and not args else unknown), here, stack[:-1]
    if prog == "cd" and not args:
        return cwd, oldpwd, stack
    if len(args) != 1 or (args[0] != "-" and args[0][:1] in ("+", "-")):
        new = unknown
    elif args[0] == "-":
        new = oldpwd or unknown
    else:  # os.path.expanduser không ném lỗi với `~user` không có (Path.expanduser ném, làm hook sập, tắt mọi chốt chặn)
        target = os.path.expanduser(args[0])
        new = unknown if target.startswith("~") else str(Path(here) / target)
    return new, here, (stack + [here] if prog == "pushd" else stack)


def changes_remote(argv: list) -> bool:
    """Lệnh đổi remote hay chỗ git đẩy tới: `git remote add|set-url|rename`, `git config` đụng remote.*, url.*,
    pushurl, insteadOf."""
    argv = strip_prefixes(argv)
    if not argv or Path(argv[0]).name != "git":
        return False
    words = [a.lower() for a in argv[1:]]
    if "remote" in words:
        rest = words[words.index("remote") + 1:]
        return bool(rest) and rest[0] in ("add", "set-url", "rename")
    return "config" in words and any(re.match(r"(remote|url|branch)\.|.*(pushurl|insteadof)", w) for w in words)


def mktemp_vars(command: str) -> frozenset:
    """Tên biến được gán đúng một lần, bằng `$(mktemp …)` trong thư mục tạm mặc định (không -p, --tmpdir=<chỗ khác>):
    `rm -rf "$d"` sau đó là xóa chỗ tạm. Biến bị gán lần nữa trong chuỗi lệnh thì không tính."""
    names = {m.group(1) for m in MKTEMP_RE.finditer(command)
             if not re.search(r"(^|\s)(-[a-zA-Z]*p|--tmpdir)|(^|\s)[^-\s]*/", m.group(2))}  # chỗ khác, template có `/`

    def reassigned(n: str) -> bool:
        name = re.escape(n)
        other = (rf"\bfor\s+{name}\b|\bread\b[^;&|\n]*\b{name}\b|(?:^|[\s;&|(]){name}\+=|-v\s+{name}\b|"
                 rf"\b(?:declare|typeset|local|export|readonly)\s+(?:-\w+\s+)*{name}\b")
        return (len(re.findall(r"(?:^|[\s;&|(])" + name + r"=", command)) != 1
                or re.search(other, command) is not None)
    return frozenset(n for n in names if not reassigned(n))


def disk_prog(word: str) -> bool:
    name = Path(word).name.casefold()
    return name == "diskutil"


def disk_inner(argv: list) -> list:
    """Các argv mà `argv` chạy: chính nó, lệnh sau lệnh bọc viết bằng đường dẫn hay chữ hoa (`/usr/bin/env …`,
    `/usr/bin/sudo …`, `caffeinate …`), chuỗi của `sh -c` (mọi shell, so không phân biệt hoa thường), `su -c`,
    `env -S`, lệnh sau `xargs`, sau `find -exec`/`-execdir`/`-ok`."""
    out, todo = [], [argv]
    while todo:
        cur = todo.pop()
        if not cur or len(out) > 16:
            continue
        out.append(cur)
        name = Path(cur[0]).name.casefold()
        if any(c.isspace() for c in cur[0]):  # `sudo -s 'diskutil …'`: cả chuỗi là một lệnh shell
            todo += simple_commands(" ".join(cur))
        elif name in DISK_SHELLS or name == "su":
            flag = next((i for i, a in enumerate(cur[1:], 1) if SHELL_C_RE.match(a)), None)
            if flag is not None and flag + 1 < len(cur) and cur[flag + 1] == "--":
                flag += 1  # `bash -c -- '…'`
            if flag is not None and flag + 1 < len(cur):
                todo += simple_commands(cur[flag + 1])
        elif name == "env" and any(a in ("-S", "--split-string") or a.startswith("--split-string=") for a in cur):
            for i, a in enumerate(cur):
                if a in ("-S", "--split-string") and i + 1 < len(cur):
                    todo += simple_commands(cur[i + 1])
                elif a.startswith("--split-string="):
                    todo += simple_commands(a.split("=", 1)[1])
        elif name in DISK_WRAPPERS:
            rest = cur[1:]
            while rest and rest[0].startswith("-"):
                rest = rest[2:] if rest[0] in ("-t", "-w") and name == "caffeinate" else rest[1:]
            todo.append(rest)
        elif name in PREFIXES | {"doas"} and cur[0] != name:
            todo.append(strip_prefixes([name, *cur[1:]]))
        elif name == "doas":
            todo.append(strip_prefixes(["sudo", *cur[1:]]))
        elif name == "xargs":
            # Lệnh của xargs là từ đầu tiên không phải cờ hay giá trị của cờ (cờ của BSD và GNU gộp lại): xét mọi chỗ
            # có tên lệnh xóa ổ mà mọi từ trước nó là cờ hay giá trị của cờ cần giá trị (`xargs grep mkfs` không tính).
            for i in range(1, len(cur)):
                prefix_ok = all(w.startswith("-") or cur[j - 1] in XARGS_VALUE_FLAGS for j, w in enumerate(cur[1:i], 1))
                if prefix_ok and (disk_prog(cur[i]) or Path(cur[i]).name.casefold() in DISK_SHELLS):
                    todo.append(cur[i:])
        elif name == "find":
            for i, arg in enumerate(cur):
                if arg in ("-exec", "-execdir", "-ok", "-okdir"):
                    end = next((j for j in range(i + 1, len(cur)) if cur[j] in (";", "+")), len(cur))
                    todo.append(cur[i + 1:end])
    return out


def check_disk_command(command: str):
    """Chặn hẳn lệnh xóa ổ đĩa trong cả chuỗi lệnh (TM-148, review 19/11): tách bằng shlex cả khi giữ `#` giữa từ, mở
    lệnh con `$(…)` và backtick, chữ đưa vào shell qua ống (`echo '…' | sh`); không tách được thì quét chữ gốc."""
    parsed = simple_commands(command)
    if command.strip() and not parsed:
        name = disk_text_wipe(command)
        return disk_deny(name) if name else None
    # Lệnh con chỉ chạy ngoài nháy đơn và ngoài thân heredoc có nháy (`<<'EOF'`): bỏ hai phần đó trước khi tìm.
    live = HEREDOC_RE.sub(lambda m: " " + m.group(3) + "\n" if m.group(1) else m.group(0), command)
    live = re.sub(r"'[^']*'", "''", live)
    inner = [m.group(1) or m.group(2) for m in re.finditer(r"\$\(([^()]*)\)|`([^`]*)`", live)]
    inner = [text for text in inner if text]
    argvs = parsed + simple_commands(command, commenters="")
    for text in inner:
        argvs += simple_commands(text)
    for argv in argvs:
        found = check_disk_wipe(argv)
        if found:
            return found
    piped = any(a and Path(a[0]).name.casefold() in DISK_SHELLS and not any(SHELL_C_RE.match(x) for x in a[1:])
                and not positional(a[1:], set()) for a in parsed)
    if piped:
        name = disk_text_wipe(command)
        if name:
            return disk_deny(name)
    return None


def disk_text_wipe(command: str):
    """Khi không tách được lệnh (shlex lỗi, như `$'X\\'Y'`): quét chữ gốc tìm mẫu xóa ổ đĩa."""
    text = command.casefold()
    for rx in DISK_TEXT_RES:
        m = rx.search(text)
        if m:
            return m.group(0).strip()[:60]
    return None


def disk_wipe(argv: list):
    """Tên ngắn của lệnh xóa ổ đĩa trong `argv` (`diskutil eraseDisk`, `diskutil apfs deleteContainer`), kể cả qua
    lệnh bọc, shell, `xargs`, `find -exec`; hay None."""
    for inner in disk_inner(argv):
        found = disk_wipe_one(inner)
        if found:
            return found
    return None


def disk_wipe_one(argv: list):
    prog = Path(argv[0]).name.casefold()
    args = [a.casefold() for a in argv[1:]]
    if prog == "diskutil":
        verbs = [a for a in args if not a.startswith("-")]
        if verbs[:1] == ["quiet"]:
            verbs = verbs[1:]
        if verbs and (verbs[0].startswith("erase") or verbs[0] in DISKUTIL_WIPE):
            return f"diskutil {verbs[0]}"
        if verbs[:1] and verbs[0] in DISKUTIL_APFS and verbs[1:2] and verbs[1] in DISKUTIL_APFS_WIPE:
            return f"diskutil {verbs[0]} {verbs[1]}"
    return None


def check_disk_wipe(argv: list):
    name = disk_wipe(argv)
    return disk_deny(name) if name else None


def disk_deny(name: str):
    return "deny", (f"agent-stack: `{name}` là lệnh xóa ổ đĩa (dữ liệu mất hẳn), bị chặn hẳn: lời đồng ý trong chat "
                    "không mở được. Đừng chạy, kể cả qua đường khác. Nếu người dùng thật sự cần, họ tự chạy trong "
                    "terminal.")


def check_argv(argv: list, cwd: str, temp_vars=frozenset(), session_id: str = ""):
    wipe = check_disk_wipe(argv)
    if wipe:
        return wipe
    vet_hint = ("Chạy skill vet-skill cho nó trước; chỉ cài khi người dùng đã duyệt trong vetted.lock "
                "(cài bằng ./install.sh của agent-stack). Nếu người dùng muốn tự cài thì họ chạy lệnh này trong terminal.")
    prog, args = Path(argv[0]).name, argv[1:]
    try:
        locked = check_locked_bash(argv, cwd, session_id)
    except Exception as exc:  # noqa: BLE001 (lỗi ở phần sổ khóa không được tắt các chốt chặn khác)
        try:
            lib().log_event("hook-error", {"hook": "pretool_guard.testlock", "error": repr(exc)[:300]})
        except Exception:  # noqa: BLE001
            pass
        locked = None
    if locked:
        return locked
    try:
        arch = check_arch_argv(argv, cwd)
    except Exception as exc:  # noqa: BLE001 (lỗi phần archctl không được tắt các chốt chặn khác)
        try:
            lib().log_event("hook-error", {"hook": "pretool_guard.archctl", "error": repr(exc)[:300]})
        except Exception:  # noqa: BLE001
            pass
        arch = None
    if arch:
        return arch
    try:
        stack = check_stack_argv(argv, cwd, session_id)
    except Exception as exc:  # noqa: BLE001 (lỗi phần stack.json không được tắt các chốt chặn khác)
        try:
            lib().log_event("hook-error", {"hook": "pretool_guard.stack", "error": repr(exc)[:300]})
        except Exception:  # noqa: BLE001
            pass
        stack = None
    if stack:
        return stack
    words = positional(args)
    if prog == "claude" and words[:2] in (["plugin", "install"], ["plugin", "i"]) and len(words) > 2:
        plugin = words[2]
        if plugin.split("@")[0] in ("agent-stack", "agent-stack-vendor") or plugin in approved_plugins(lib()):
            return None
        return "deny", f"agent-stack: plugin `{plugin}` chưa qua vet-skill hoặc chưa được duyệt. {vet_hint}"
    if prog == "claude" and words[:3] == ["plugin", "marketplace", "add"] and len(words) > 3:
        source = words[3].rstrip("/")
        home = lib().home_dir()
        if home and Path(os.path.expanduser(source)).resolve() in (home.resolve(), (home / "vendor").resolve()):
            return None
        return "ask", (f"agent-stack: thêm marketplace `{source}` làm mọi plugin trong đó cài được, dù chưa qua "
                       "vet-skill. Người dùng xác nhận trước khi thêm.")
    if prog == "claude" and words[:1] == ["mcp"] and len(words) > 1 and words[1].startswith("add"):
        return "deny", f"agent-stack: thêm MCP server phải qua vet-skill trước. {vet_hint}"
    if prog == "npx" and "add" in words and any(w == "skills" or w.startswith("skills@") for w in words):
        return "deny", f"agent-stack: cài skill bên thứ ba phải qua vet-skill trước. {vet_hint}"
    gh_words = positional(args, GH_RELEASE_FLAGS_WITH_VALUE) if prog == "gh" else []
    if gh_words[:2] == ["release", "create"]:  # -R/--repo có thể đứng trước release
        names = gh_words[2:]
        return audit_reminder(f"tạo bản phát hành `{names[0]}`" if names else "tạo bản phát hành", Path(cwd or "."))
    if prog == "rm":
        return check_rm(args, cwd, temp_vars)
    if prog == "git":
        where = Path(cwd or ".")
        while args and args[0].startswith("-"):  # tùy chọn chung của git: -C <thư mục>, -c <khóa=giá trị>, --no-pager
            if args[0] in GIT_OPTS_WITH_VALUE and len(args) >= 2:
                if args[0] == "-C":
                    where = where / os.path.expanduser(args[1])  # `~user` không có: không ném lỗi
                args = args[2:]
            else:
                args = args[1:]
        if args[:1] in (["checkout"], ["switch"]):
            return check_checkout(args[0], args[1:], where)
        if args[:1] == ["tag"]:
            return check_tag(args[1:], where)
        if args[:1] in (["push"], ["reset"], ["clean"], ["commit"], ["rebase"]):
            return check_git_irreversible(args[0], drop_redirects(args[1:]), where)
    return None


def tag_names(args: list):
    """Tên tag mà `git tag <args>` sẽ tạo, hoặc [] nếu lệnh chỉ liệt kê, xóa, kiểm tag. Hiểu cờ ngắn gộp (-am "msg",
    -li), cờ có giá trị dính liền (-mmsg, --message=x) và bỏ chuyển hướng (2>/dev/null, > file)."""
    names, skip, rest = [], False, False
    for arg in args:
        if skip:
            skip = False
        elif rest:
            names.append(arg)
        elif arg == "--":
            rest = True
        elif re.match(r"^\d*(>>?|<)", arg):
            skip = re.fullmatch(r"\d*(>>?|<)", arg) is not None  # toán tử đứng riêng: bỏ cả đích theo sau
        elif arg.startswith("--"):
            if arg.split("=")[0] in TAG_READ_FLAGS:
                return []
            skip = arg in TAG_FLAGS_WITH_VALUE
        elif arg.startswith("-") and len(arg) > 1:
            for i, flag in enumerate(arg[1:]):
                if flag in "ldvn":
                    return []
                if flag in "mFu":  # cờ cần giá trị: phần còn lại là giá trị, hoặc đối số kế tiếp
                    skip = i == len(arg) - 2
                    break
        else:
            names.append(arg)
    return names


def check_tag(args: list, where: Path):
    """`git tag <tên> [commit]` (kể cả -a, -s, -f, -m): tạo tag, tức là sắp phát hành. Liệt kê, xóa, kiểm tag thì bỏ qua."""
    names = tag_names(args)
    return audit_reminder(f"tạo tag `{names[0]}`", where) if names else None


def audit_reminder(action: str, where: Path):
    """("audit", việc, khóa): khóa gồm gốc repo (hay chính thư mục, nếu không phải repo) và việc, để cổng nhớ riêng từng
    tag của từng repo, và thư mục con của cùng repo không bị nhắc lại."""
    top = (lib().git_out(where.expanduser(), "rev-parse", "--show-toplevel") or "").strip()
    return "audit", action, f"{top or where.expanduser().resolve()} {action}"


def gate_user(gated: list, session_id: str):
    """Cổng hỏi người dùng cho nhắc audit trước phát hành và lệnh không đảo ngược. Lần đầu thì từ chối, vì lý do kèm từ
    chối tới được Claude còn lý do kèm "ask" thì không, và auto mode có thể duyệt "ask" mà không ai đọc. Người dùng đã
    nhắn sau lần từ chối thì cho qua (None); một lần trả lời mở mọi khóa của lệnh (tag rồi push). Khóa của lệnh không đảo
    ngược dùng một lần, chỉ ở lượt ngay sau lần chặn (release_gate `once`). Không theo dõi được phiên (session_id lạ,
    không ghi được state) thì hỏi người dùng."""
    # Tin của người dùng mở lượt này đã bảo đúng việc (A.turn_consent) thì không hỏi lại; chỉ dùng lời đồng ý khi cả
    # chuỗi lệnh qua, kẻo nhắc audit còn chặn mà lời đồng ý đã mất.
    # Dùng một lần cho mỗi loại việc mỗi repo mỗi tin (khóa `use`), không theo chữ lệnh: "Push" không mở cho hai lệnh
    # push khác nhau.
    def use_key(r):
        return f"{r[2].split(' confirm ')[0]} {r[3][0]}"

    consented = [r for r in gated if r[0] == "confirm" and len(r) > 3 and r[3]
                 and lib().turn_consent(session_id, use_key(r), *r[3])]
    kinds = [use_key(r) for r in consented]
    if (consented and len(consented) == len(gated) and len(set(kinds)) == len(kinds)
            and all(lib().turn_consent(session_id, use_key(r), *r[3], use=True, gate_key=r[2]) for r in consented)):
        return None
    audits = [r for r in gated if r[0] == "audit"]
    confirms = [r for r in gated if r[0] == "confirm"]
    gate = lib().release_gate(session_id, [r[2] for r in gated], once=[r[2] for r in confirms])
    if gate == "pass":
        return None
    parts, questions = [], []
    if audits:
        action = ", ".join(dict.fromkeys(r[1] for r in audits))
        parts.append(f"sắp {action}, tức là sắp phát hành. Bước 3 của quy trình bảo mật là audit cả repo trước phát "
                     "hành: quét Semgrep (`/static-analysis:semgrep`), rồi `/claude-security` tìm phần Semgrep bỏ sót "
                     "(hai plugin thuộc bộ `bao-mat`; chưa bật thì `profile.py on bao-mat` rồi người dùng gõ "
                     "/reload-plugins).")
        questions.append("hỏi họ đã audit commit sắp phát hành chưa")
    if confirms:
        parts.append("lệnh không đảo ngược được: " + "; ".join(dict.fromkeys(r[1] for r in confirms)) + ".")
        questions.append("hỏi họ có muốn chạy đúng lệnh này không")
    text = " ".join(parts)
    if gate == "nudge":
        once = (" Lời đồng ý cho lệnh không đảo ngược chỉ dùng được một lần, ở lượt ngay sau câu trả lời; chạy lại sau đó "
                "thì hỏi lại." if confirms else "")
        return "deny", (f"agent-stack: {text} Dừng ở đây, đừng chạy lại lệnh trong lượt này: báo người dùng lời nhắc "
                        f"này và {' và '.join(questions)}. Người dùng trả lời đồng ý thì chạy lại đúng lệnh này, hook sẽ "
                        f"cho qua; họ không đồng ý thì đừng chạy; đổi lệnh thì hook hỏi lại.{once}")
    return "ask", f"agent-stack: {text} Người dùng xác nhận thì chạy tiếp; chưa chắc thì từ chối."


def gate_release(audits: list, session_id: str):
    """Cổng trước khi phát hành (giữ cho nơi gọi cũ): gate_user chỉ với nhắc audit."""
    return gate_user(audits, session_id)


def drop_redirects(args: list) -> list:
    """Bỏ chuyển hướng (2>/dev/null, > file, < in) và đích của toán tử đứng riêng khỏi argv."""
    out, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif REDIRECT_RE.match(arg):
            skip = re.fullmatch(r"\d*(>>?|<)&?", arg) is not None
        else:
            out.append(arg)
    return out


def short_flags(args: list) -> str:
    """Các chữ của cờ ngắn gộp (-fdx → "fdx"), không tính cờ dài."""
    return "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--") and len(a) > 1)


def confirm(command: str, why: str, where: Path, key_extra: str = "", consent=None):
    """("confirm", việc, khóa, consent): khóa gồm gốc repo (hay thư mục), đúng lệnh và `key_extra` (đích tuyệt đối của
    rm), để người dùng duyệt lệnh nào thì chỉ lệnh đó qua; đổi lệnh (thêm --force) hay đổi thư mục thì hỏi lại.
    `consent` = (việc trong A.CONSENT_VERBS, đích) để tin hiện tại của người dùng gọi đúng việc thì qua ngay."""
    top = (lib().git_out(where.expanduser(), "rev-parse", "--show-toplevel", timeout=1.5) or "").strip()
    shown = command if len(command) <= 160 else command[:159] + "…"
    key = f"{top or where.expanduser().resolve()} confirm {command} {key_extra}".rstrip()
    return "confirm", f"`{shown}` ({why})", key, consent


PUSH_FORCE_FLAGS = {"-f", "--force", "--force-with-lease", "--force-if-includes"}


def push_consent(args: list, rewrite: bool, where: Path | None = None):
    """Việc mà tin của người dùng phải gọi tên để `git push` qua không hỏi, hay None (luôn hỏi): chỉ push thường tới
    remote có tên (không URL, đường dẫn), refspec không có `:` (xóa hay đẩy sang tên khác), không --tags, --all,
    --mirror, --delete, --prune. Remote phải là remote đã có của repo. Ghi đè lịch sử (--force, +ref) thì tin phải nói
    cả "force"."""
    allowed = {"-u", "--set-upstream", "-q", "--quiet", "-v", "--verbose", "--no-verify", *PUSH_FORCE_FLAGS}
    flags = [a.split("=")[0] for a in args if a.startswith("-")]
    words = [a for a in args if not a.startswith("-")]
    if any(f not in allowed for f in flags) or len(words) > 2:
        return None
    if words and (not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", words[0])
                  or words[0] not in (lib().git_out(where or Path("."), "remote", timeout=1.5) or "").split()):
        return None  # URL, đường dẫn, user@host, remote chưa có
    if any(":" in w or not re.fullmatch(r"\+?[A-Za-z0-9_./-]+", w) for w in words[1:]):
        return None
    return ("push+force" if rewrite else "push", push_names(words, where))


def push_names(words: list, where: Path | None = None) -> tuple:
    """Tên mà tin của người dùng được nêu kèm "push" ("Push claude-remote", "push nhánh feature-x"): tên repo, remote,
    nhánh trong lệnh, hay nhánh hiện tại khi lệnh không ghi nhánh. Tên lạ (repo khác) vẫn làm tin không được tính."""
    where = where or Path(".")
    top = (lib().git_out(where, "rev-parse", "--show-toplevel", timeout=1.5) or "").strip()
    names = [top] if top else []
    names += [w.lstrip("+") for w in words]
    if len(words) < 2:
        names.append((lib().git_out(where, "rev-parse", "--abbrev-ref", "HEAD", timeout=1.5) or "").strip())
    return tuple(dict.fromkeys(n for n in names if n and n != "HEAD" and not re.search(r"[$`~*?\[]", n)))


def check_git_irreversible(verb: str, args: list, where: Path):
    """Lệnh git không đảo ngược được: push (trừ --dry-run), reset --hard, clean -f (trừ -n, và -X chỉ xóa file git bỏ
    qua), commit --amend và rebase khi viết lại commit đã có trên một nhánh remote."""
    if any(a in ("-h", "--help") for a in args):
        return None
    command = " ".join(["git", verb, *args])
    if verb == "push":
        if any(a in ("-n", "--dry-run") for a in args):
            return None
        rewrite = any(a.split("=")[0] in PUSH_REWRITE_FLAGS or (a.startswith("+") and len(a) > 1) for a in args)
        why = ("ghi đè hay xóa lịch sử trên remote; người khác có thể đã kéo bản cũ về" if rewrite
               else "đẩy commit lên remote; người khác thấy ngay, không rút lại êm được")
        return confirm(command, why, where, consent=push_consent(args, rewrite, where))
    if verb == "reset":
        if "--hard" not in args:
            return None
        return confirm(command, "bỏ mọi thay đổi chưa commit và dời nhánh; git không giữ bản nào của phần chưa commit",
                       where, consent=("reset", ()))
    if verb == "clean":
        flags = short_flags(args)
        if "n" in flags or "--dry-run" in args or not ("f" in flags or "--force" in args):
            return None
        if "X" in flags and "x" not in flags:
            return None  # -X chỉ xóa file git bỏ qua (build, cache): chỗ ghi tạm
        # -x xóa cả file git bỏ qua (.env, dữ liệu): luôn hỏi
        return confirm(command, "xóa hẳn file chưa track; git không có bản nào của chúng", where,
                       consent=None if "x" in flags else ("clean", ()))
    if verb == "commit":
        if "--amend" not in args or rewrites_pushed(where, ["-n", "1", "HEAD"]) is False:
            return None
        return confirm(command, "viết lại commit đã có trên remote; sau đó phải push --force", where,
                       consent=("amend", ()))
    if verb == "rebase":
        if any(a in REBASE_STATE_FLAGS for a in args):
            return None  # tiếp tục hay bỏ một lần rebase đã bắt đầu
        words = positional(args, REBASE_FLAGS_WITH_VALUE)
        if "--root" in args:
            revs = [words[0] if words else "HEAD"]
        else:
            revs = [f"{words[0] if words else '@{upstream}'}..{words[1] if len(words) > 1 else 'HEAD'}"]
        if rewrites_pushed(where, revs) is False:
            return None
        return confirm(command, "viết lại commit đã có trên remote; sau đó phải push --force", where,
                       consent=("rebase", ()))
    return None


def rewrites_pushed(where: Path, revs: list):
    """True khi tập commit `revs` (đối số của git rev-list) có commit đã nằm trên một nhánh remote, False khi không,
    None khi git không trả lời được (ref lạ, không phải repo, quá giờ): nơi gọi coi None như có, để hỏi cho chắc."""
    A = lib()
    # Hook có 5 giây (hooks.json): mỗi lệnh git tối đa 1,5 giây để cả hook không bị giết giữa chừng.
    total = A.git_out(where.expanduser(), "rev-list", "--count", *revs, timeout=1.5)
    local = A.git_out(where.expanduser(), "rev-list", "--count", *revs, "--not", "--remotes", timeout=1.5)
    try:
        return int(total) > int(local)
    except (TypeError, ValueError):
        return None


def check_rm(args: list, cwd: str, temp_vars=frozenset()):
    """`rm -r` (kể cả -rf, -fr, -R, --recursive; có -f hay không đều xóa hẳn cả cây) với đích ngoài chỗ ghi tạm."""
    targets, opts, rest = [], [], False
    for arg in drop_redirects(args):
        if rest or not arg.startswith("-") or arg == "-":
            targets.append(arg)
        elif arg == "--":
            rest = True
        else:
            opts.append(arg)
    flags = short_flags(opts)
    if not ("r" in flags or "R" in flags or "--recursive" in opts) or "--help" in opts:
        return None
    outside = [t for t in targets if not scratch_target(t, cwd, temp_vars)]
    if not outside:
        return None
    where = Path(cwd or ".").expanduser()
    shown = [str(full_target(t, where)) if not re.search(r"[$`~]", t) else t for t in outside[:3]]
    return confirm(" ".join(["rm", *args]), "xóa hẳn cả cây thư mục ngoài chỗ ghi tạm: " + ", ".join(shown),
                   where, key_extra=" ".join(sorted(shown)), consent=("rm", tuple(outside)))


def full_target(target: str, where: Path) -> Path:
    path = Path(os.path.expanduser(target))
    return Path(os.path.normpath(path if path.is_absolute() else where.resolve() / path))


def temp_roots() -> list:
    """Thư mục tạm của hệ điều hành (đã resolve): /tmp, $TMPDIR, thư mục tạm của Python."""
    import tempfile
    roots = {Path("/tmp").resolve(), Path(tempfile.gettempdir()).resolve()}
    if os.environ.get("TMPDIR"):
        roots.add(Path(os.environ["TMPDIR"]).resolve())
    return sorted(roots)


def scratch_target(target: str, cwd: str, temp_vars=frozenset()) -> bool:
    """Đích của rm nằm trong chỗ ghi tạm (rm_scratch). Đích là biến gán từ `$(mktemp …)` cùng chuỗi lệnh thì là chỗ tạm.
    Đích có lệnh con, biến khác, `~user`, hay `..` đứng sau ký tự glob, brace thì không tính là tạm. Glob chỉ xét thư
    mục đứng trước nó. Symlink: không có `/` cuối thì rm chỉ xóa chính link nên xét chỗ của link; có `/` thì xét đích."""
    # `$d` hay `$d/<đường dẫn cụ thể>`; có glob (`"$d"/*`) thì không: mktemp lỗi làm $d rỗng thì thành `/*`.
    var = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?(/[^$`*?\[{]*)?", target or "")
    if var and var.group(1) in temp_vars and ".." not in (var.group(2) or ""):
        return True
    if not target or "$(" in target or "`" in target:
        return False
    text = os.path.expandvars(os.path.expanduser(target))
    if "$" in text or text.startswith("~"):
        return False
    parts = Path(text).parts
    cut = next((i for i, part in enumerate(parts) if any(ch in part for ch in GLOB_CHARS)), len(parts))
    if any(".." in part for part in parts[cut:]):
        return False  # `.tmp/*/../..`, `.tmp/{x,../src}`: thoát ra ngoài sau glob
    base = Path(*parts[:cut]) if cut else Path(".")
    cwd_path = Path(cwd or ".").expanduser()
    full = base if base.is_absolute() else cwd_path / base
    if cut < len(parts):
        full = full.resolve() / "x"  # glob: xét một file bất kỳ ngay trong thư mục đó
    elif full.is_symlink() and not text.endswith("/"):
        full = full.parent.resolve() / full.name
    else:
        full = full.resolve()
    if full in (Path("/"), Path.home().resolve(), cwd_path.resolve()):
        return False
    return rm_scratch(full, glob=cut < len(parts))


def rm_scratch(path: Path, glob: bool = False) -> bool:
    """Chỗ tạm cho rm: bên dưới (không phải chính) thư mục tạm của hệ điều hành, hay đường dẫn git bỏ qua nằm trong thư
    mục có tên kiểu tạm, build, cache (RM_SCRATCH_NAMES, tính từ gốc repo). glob: `path` là một file trong thư mục bị
    glob, nên xét thư mục đó (`rm -rf /tmp/*` không phải chỗ tạm). Đường dẫn chưa có thì hỏi git cả dạng thư mục
    (`build/x`), vì mẫu `build/` trong .gitignore chỉ khớp thư mục."""
    anchor = path.parent if glob else path
    if any(root in anchor.parents for root in temp_roots()):
        return True
    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    A = lib()
    top = (A.git_out(parent, "rev-parse", "--show-toplevel", timeout=1.5) or "").strip()
    try:
        inside = anchor.relative_to(Path(top).resolve()).parts if top else ()
    except ValueError:
        inside = ()
    if not RM_SCRATCH_NAMES & set(inside):
        return False
    return any(A.git_out(parent, "check-ignore", "-q", str(p), timeout=1.5) is not None for p in (path, path / "x"))


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


def markdown_required(full: Path, root: str, A) -> bool:
    """File .md mà agent, công cụ hay nền tảng đọc như Markdown, nên không đổi sang HTML được. Thư mục đặc biệt
    (skills, agents…) chỉ tính tên gốc project và phần đường dẫn bên trong nó, để repo nằm dưới ~/work/agents/ không
    được miễn cả, còn phiên mở ngay trong ~/.claude vẫn được miễn."""
    name = full.name.lower()
    if name in MD_NAMES or REPORT_RE.search(full.name):
        return True
    if name in {Path(p).name.lower() for p in (*A.PLAN_CANDIDATES, A.LAST_TURN_REL)}:
        return True
    try:
        base = Path(root).resolve()
        parts = (base.name, *full.resolve().parent.relative_to(base).parts) if root else full.parent.parts
    except ValueError:  # ngoài project (file nhớ, plan mode trong ~/.claude): xét cả đường dẫn
        parts = full.parent.parts
    if any(part.lower() in MD_DIRS for part in parts):
        return True
    return any((d / "SKILL.md").exists() for d in (full.parent, full.parent.parent))  # tài liệu kèm skill


def check_new_markdown(full: Path, cwd: str, session_id: str):
    """Tạo file .md mới cho người đọc: nhắc viết HTML, một lần cho mỗi file trong lượt. Ghi lại thì cho qua, vì chỉ
    Claude biết file có bắt buộc Markdown hay không (project quy ước Markdown, người dùng xin .md)."""
    if full.suffix.lower() not in (".md", ".markdown") or not session_id or full.exists():
        return None
    A = lib()
    turn = A.load_turn(session_id)
    if not turn or markdown_required(full, turn.get("root") or cwd, A):
        return None
    nudged = turn.get("md_nudged") or []
    key = str(full.resolve())
    if key in nudged:
        return None
    turn["md_nudged"] = nudged + [key]
    A.save_turn(session_id, turn)
    return "deny", (f"agent-stack: file cho người đọc viết bằng HTML (luật chung, mục \"File cho người đọc viết bằng "
                    f"HTML\"). Viết `{full.with_suffix('.html').name}` theo skill reader-page thay cho `{full.name}`. "
                    "Nếu file này bắt buộc là Markdown (agent hay script đọc nó, nền tảng đòi Markdown, project quy "
                    "ước Markdown, người dùng xin .md) thì ghi lại đúng lệnh này: nhắc chỉ hiện một lần cho file này.")


LOCK_NAME = "test-lock.json"
# Lệnh có thể ghi sổ khóa khi nhắc tên nó (trình thông dịch, trình soạn): chặn. Lệnh khác chỉ chặn khi sổ là đích ghi.
LOCK_WRITERS = {"python", "python3", "node", "perl", "ruby", "sh", "bash", "zsh", "awk", "gawk", "ed", "ex", "vi",
                "vim", "nvim", "nano", "emacs", "dd", "sponge", "osascript", "uv", "uvx", "deno", "bun", "php"}
SED_LIKE = {"sed", "gsed", "perl"}
FILE_OPS = {"cp", "mv", "rm", "ln", "install", "tee", "sed", "gsed", "perl", "cat", "truncate", "unlink", "shred",
            "rsync", "git"}
RECEIPT_SAFE = {"run", "show", "forget", "fails-before", "prune", "lock", "locks"}  # tự ghi sổ đúng cách hay chỉ đọc
UNLOCK_CONSENTS = "unlock-consents.json"
SPEC_BOOK = "spec-approvals"  # state/spec-approvals.json: sổ duyệt spec (GĐ6, TM-128), chỉ hook ghi
SPEC_BOOK_REASON = ("agent-stack: `state/spec-approvals.json` là sổ duyệt spec. Chỉ hook ghi: prompt_submit khi chính "
                    "người dùng nhắn \"duyệt spec <mã>\", plan_exit khi người dùng duyệt kế hoạch có mục `## Spec`. "
                    "Agent ghi, sửa, dời hay xóa sổ là tự duyệt spec; cần duyệt thì dựng trang (`spec.py page`) và "
                    "đưa mã cho người dùng.")
RUNNER_RE = re.compile(r"^(python[\d.]*|uv|uvx|env|pipx|pyenv|poetry|pdm|hatch|rye)$")
# Cờ của receipt.py nhận giá trị: lệnh bên trong là phần còn lại sau chúng (argparse REMAINDER, có hay không `--`).
RECEIPT_VALUE_FLAGS = {"--project", "--label", "--timeout", "--base", "--link", "--tests", "--level", "--reason",
                       "--spec", "--allow", "--cwd", "--host"}
RECEIPT_MULTI_FLAGS = {"--tests", "--spec", "--allow"}  # nargs="+" của receipt.py: nuốt tới cờ kế tiếp
# Tên sổ duyệt sau khi shell bỏ dấu nháy, gạch chéo (`spec-approval"s".json` thành `spec-approvals.json`), hay còn glob.
SPEC_BOOK_TOKEN_RE = re.compile(r"spec-appr[^/\s]{0,8}\.json|spec-appr[^/\s]*[*?\[]", re.I)
SPEC_WRITE_API_RE = re.compile(r"\b(approve_code|approve_plan|approve_from_prompt|add_record|book_path)\b")


def testlock_lib():
    lib()  # đưa plugin/lib vào sys.path
    import testlock
    return testlock


def receipt_subcommand(argv: list):
    """Lệnh con khi argv chạy receipt.py, kể cả qua trình chạy (`uv run python3 -X utf8 …/receipt.py unlock …`);
    (None, []) khi không phải, hay khi receipt.py chỉ là tham số của lệnh thao tác file (`cp …/receipt.py x`)."""
    first = Path(argv[0]).name
    if first in FILE_OPS or not (first == "receipt.py" or RUNNER_RE.match(first)):
        return None, []
    at = next((i for i, a in enumerate(argv) if Path(a).name == "receipt.py"), None)
    if at is None:
        return None, []
    rest = argv[at + 1:]
    return (rest[0] if rest else ""), rest[1:]


def receipt_inner(rest: list) -> list:
    """Lệnh mà `receipt.py run|fails-before|lock` sẽ chạy: phần còn lại sau các cờ có giá trị, bỏ `--` đứng đầu."""
    i = 0
    while i < len(rest) and rest[i].startswith("-") and rest[i] != "--":
        flag, inline = rest[i].split("=", 1)[0], "=" in rest[i]
        i += 2 if flag in RECEIPT_VALUE_FLAGS and not inline else 1
        if flag in RECEIPT_MULTI_FLAGS and not inline:  # nargs="+": nuốt tới cờ kế tiếp (`--spec=x` chỉ một giá trị)
            while i < len(rest) and not rest[i].startswith("-"):
                i += 1
    inner = rest[i:]
    return inner[1:] if inner[:1] == ["--"] else inner


def receipt_run_dir(rest: list, where: Path) -> Path:
    """Thư mục receipt.py sẽ chạy lệnh bên trong: `--cwd` (tính từ thư mục hiện tại), không có thì gốc project của
    `--project` (mặc định thư mục hiện tại), như `run_place_arg` của receipt.py. Đường dẫn tương đối trong lệnh bên
    trong tính từ đây, không từ thư mục của hook."""
    values = {}
    i = 0
    while i < len(rest) and rest[i].startswith("-") and rest[i] != "--":
        flag, inline, value = rest[i].partition("=")
        if flag in ("--cwd", "--project"):
            values[flag] = value if inline else (rest[i + 1] if i + 1 < len(rest) else "")
        i += 2 if flag in RECEIPT_VALUE_FLAGS and not inline else 1
        if flag in RECEIPT_MULTI_FLAGS and not inline:
            while i < len(rest) and not rest[i].startswith("-"):
                i += 1
    base = Path(os.path.expanduser(str(where)))
    if values.get("--cwd"):
        return base / os.path.expanduser(values["--cwd"])
    project = values.get("--project") or "."
    if any(ch in project for ch in DIR_UNKNOWN):  # `--project $P`: không đoán gốc, để `unknown_dir_check` xét
        return base / os.path.expanduser(project)
    return lib().project_root(base / os.path.expanduser(project))


def target_path(where: Path, target: str):
    """Đường dẫn đầy đủ của đích; None khi không tính được (~ người dùng lạ, tên quá dài)."""
    try:
        return Path(os.path.expanduser(str(where))) / os.path.expanduser(target)
    except (RuntimeError, ValueError, OSError):
        return None


def is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except (OSError, ValueError):
        return False  # tên quá dài, không có quyền: không phải thư mục ta biết


def write_targets(argv: list, where: Path) -> list:
    """(đường dẫn đầy đủ, chữ trong lệnh) của các đích lệnh đơn có thể ghi đè, sửa hay xóa (đoán theo tên lệnh, không
    chắc thì bỏ qua): rm, mv, cp (đích cuối), sed/perl -i, truncate, tee, git [-C dir] rm|mv|checkout|restore, và đích
    của chuyển hướng `>`, `>>`."""
    out, args = [], argv[1:]
    for i, arg in enumerate(argv):
        m = re.fullmatch(r"\d*>>?\|?(.*)", arg) or (re.fullmatch(r"[^>]*?[^\d>]\d*>>?\|?([^>]*)", arg) if i else None)
        if m:
            target = m.group(1) or (argv[i + 1] if i + 1 < len(argv) else "")
            if target.startswith("&") and not re.fullmatch(r"&(\d+|-)", target):
                target = target[1:]  # `>&file`: ghi cả stdout lẫn stderr vào file
            if target and not target.startswith("&"):
                out.append((where, target))
    prog = Path(argv[0]).name
    words = [a for a in positional(drop_redirects(args), set()) if a != "--"]
    if prog in ("mv", "cp", "install", "ln", "rsync") and len(words) >= 2:
        dest = target_path(where, words[-1])
        if dest is not None and (is_dir(dest) or words[-1] in (".", "./") or words[-1].endswith("/")):
            # `cp x.py tests/`, `cp x.py .`: đích là tests/x.py, không phải cả thư mục (kể cả thư mục không biết trước)
            out += [(dest, Path(w).name) for w in words[:-1]]
        else:
            out.append((where, words[-1]))
        if prog == "mv":
            out += [(where, w) for w in words[:-1]]
    elif prog in ("rm", "truncate", "tee", "unlink", "shred"):
        out += [(where, w) for w in words]
    elif prog == "dd":
        out += [(where, a[3:]) for a in args if a.startswith("of=")]
    elif prog in SED_LIKE and any(a.startswith("-") and "i" in a.lstrip("-")[:3] for a in args):
        out += [(where, w) for w in words[1:]]  # bỏ biểu thức sed/perl
    elif prog == "git":
        rest, here = drop_redirects(args), where
        while rest and rest[0].startswith("-"):
            if rest[0] in GIT_OPTS_WITH_VALUE and len(rest) >= 2:
                if rest[0] == "-C":
                    here = Path(os.path.expanduser(rest[1])) if Path(rest[1]).is_absolute() else here / rest[1]
                rest = rest[2:]
            else:
                rest = rest[1:]
        sub = [a for a in positional(rest, set()) if a != "--"]
        staged_only = ("--staged" in rest or "-S" in rest) and "--worktree" not in rest and "-W" not in rest
        cached = sub[:1] == ["rm"] and "--cached" in rest
        if sub[:1] in (["rm"], ["mv"]) and not cached:
            out += [(here, w) for w in sub[1:]]
        elif sub[:1] == ["checkout"]:
            # Trả file về bản trong index (`git checkout -- f`, `git checkout f`) là bỏ thay đổi dở, không phải nới; chỉ
            # lấy file từ một commit khác (`git checkout HEAD~1 -- f`) mới ghi bản lạ.
            before = positional(rest[1:rest.index("--")], set()) if "--" in rest else None
            paths = sub[1:]
            if before is None and paths and target_path(here, paths[0]) is not None and \
                    os.path.lexists(str(target_path(here, paths[0]))):
                before = []
            if before is None:
                before, paths = paths[:1], paths[1:]
            if before:
                out += [(here, w) for w in paths]
        elif sub[:1] == ["restore"] and not staged_only and any(a.startswith(("--source", "-s")) for a in rest):
            out += [(here, w) for w in sub[1:]]
    return [(full, text) for full, text in ((target_path(w, t), t) for w, t in out) if full is not None]


def locked_hit(full: Path, how: str, session_id: str, change: str = "changed"):
    """Quyết định khi một thao tác đụng file test đã khóa (câu 3): chỉ thêm (siết) thì qua; nới ở mức cao thì chặn, mức
    vừa thì nhắc một lần mỗi lượt cho mỗi file."""
    TL = testlock_lib()
    found = TL.lookup(full)
    if not found or change in ("same", "added"):
        return None
    top, rel, entry = found
    fix = (f"Sửa code cho test đạt, không sửa test. Nếu test sai thật thì dừng và đề xuất cho người dùng (đây là "
           f"nới); họ duyệt bằng một tin nêu đúng file (như \"mở khóa {rel}\") thì chạy `receipt.py unlock {rel} "
           f"--reason \"<lời họ>\"` rồi mới sửa. Thêm hàm test mới bằng Edit hay Write (siết) thì không bị chặn; lệnh "
           f"shell ghi vào test khóa luôn tính là nới.")
    if entry.get("level") == "cao":
        return "deny", f"agent-stack: `{rel}` là test đã khóa ở mức rủi ro cao; {how} là nới, bị chặn. {fix}"
    A = lib()
    turn = A.load_turn(session_id) if session_id else None
    msg = (f"agent-stack: `{rel}` là test đã khóa (mức vừa); {how} là nới và done-gate sẽ đánh dấu đỏ. {fix} Nhắc "
           "này chỉ hiện một lần mỗi lượt cho file này.")
    if not turn:
        return "ask", msg
    key = f"{top}:{rel}"
    nudged = turn.get("lock_nudged") if isinstance(turn.get("lock_nudged"), list) else []
    if key in nudged:
        return None
    turn["lock_nudged"] = nudged + [key]
    A.save_turn(session_id, turn)
    return "deny", msg


def is_spec_book(full: Path) -> bool:
    """`full` là sổ duyệt spec, kể cả qua symlink mang tên khác hay viết hoa khác (hệ thống file macOS không phân biệt
    hoa thường, TM-128)."""
    try:
        book = lib().state_dir().resolve() / (SPEC_BOOK + ".json")
        target = full.resolve()
        if target == book or (target.exists() and book.exists() and os.path.samefile(target, book)):
            return True
        return target.name.casefold() == book.name and str(target.parent).casefold() == str(book.parent).casefold()
    except (OSError, RuntimeError, ValueError):
        return full.name.casefold() == SPEC_BOOK + ".json"


def spec_book_bash(command: str, cwd: str):
    """Chặn (S5, TM-128): ghi vào sổ duyệt spec qua chuyển hướng hay lệnh thao tác file; trình thông dịch, trình soạn
    nêu tên sổ (kể cả tên che bằng dấu nháy, gạch chéo, glob); trình thông dịch gọi hàm ghi của specbook. Lệnh chỉ nhắc
    tên (git commit -m, git grep, awk tìm chữ, pytest -k) hay chỉ đọc (cat, jq) thì cho qua."""
    where = Path(cwd or ".")
    writers = (FILE_OPS - {"cat", "git"}) | LOCK_WRITERS

    def interp(name: str) -> bool:
        return bool(RUNNER_RE.match(name) or name in LOCK_WRITERS)

    for argv in simple_commands(command):
        if not argv or Path(argv[0]).name == "git":
            continue  # git không ghi được sổ ngoài repo; `git show … > sổ` vẫn bị bắt ở đích chuyển hướng bên dưới
        name = Path(argv[0]).name
        if (name in writers or interp(name)) and any(SPEC_BOOK_TOKEN_RE.search(a) for a in argv[1:]):
            return "deny", SPEC_BOOK_REASON
        if interp(name) and any("specbook" in a for a in argv[1:]) and any(SPEC_WRITE_API_RE.search(a)
                                                                          for a in argv[1:]):
            return "deny", SPEC_BOOK_REASON
    for argv in simple_commands(command):
        if argv and any(SPEC_BOOK_TOKEN_RE.search(text) or SPEC_BOOK in text for _, text in write_targets(argv, where)):
            return "deny", SPEC_BOOK_REASON
    for m in HEREDOC_RE.finditer(command):  # thân heredoc đưa vào trình thông dịch
        head = command[command.rfind("\n", 0, m.start()) + 1:m.start()]
        body = m.group(0)
        risky = SPEC_BOOK_TOKEN_RE.search(body) or ("specbook" in body and SPEC_WRITE_API_RE.search(body))
        if risky and any(a and interp(Path(a[0]).name) for a in simple_commands(head)):
            return "deny", SPEC_BOOK_REASON
    return None


def lock_named_by_interpreter(command: str, cwd: str):
    """Trình thông dịch hay trình soạn (python -c, node -e, heredoc vào python…) mà cả chuỗi lệnh nhắc tên sổ khóa,
    khi repo có sổ: chặn (TM-103). Lệnh khác nhắc tên sổ (cat, git add) xét ở check_locked_bash."""
    try:
        TL = testlock_lib()
        top = TL.find_top(Path(cwd or "."))
        if top is None or not (top / TL.LOCK_REL).is_file():
            return None
        def interp(argv) -> bool:
            name = Path(argv[0]).name if argv else ""
            return bool(RUNNER_RE.match(name) or name in LOCK_WRITERS) and receipt_subcommand(argv)[0] is None

        named = any(interp(a) and any(LOCK_NAME in x for x in a[1:]) for a in simple_commands(command))
        for m in HEREDOC_RE.finditer(command):  # thân heredoc đưa vào trình thông dịch (`python3 - <<'EOF'`)
            head = command[command.rfind("\n", 0, m.start()) + 1:m.start()]
            if LOCK_NAME in m.group(0) and any(interp(a) for a in simple_commands(head)):
                named = True
        if not named:
            return None
    except Exception:  # noqa: BLE001
        return None
    return "deny", ("agent-stack: lệnh này chạy trình thông dịch hay trình soạn và nhắc tới `.agent/test-lock.json` (sổ "
                    "khóa test). Chỉ sửa sổ bằng `receipt.py lock` hay `receipt.py unlock` (cần người dùng duyệt).")


def check_unlock(rest: list, where: Path, session_id: str):
    """`receipt.py unlock`: chỉ qua khi tin người dùng mở lượt này bảo mở khóa đúng các file (TM-104), một lần mỗi tin;
    không có đường "người dùng đã nhắn gì đó sau lần chặn" như git push, vì người cần kiểm chính là agent. Qua thì ghi
    biên nhận đồng ý vào state/ (ngoài repo) để done-gate phân biệt bản ghi duyệt thật với bản agent tự khai."""
    project = where
    for i, arg in enumerate(rest[:-1]):
        if arg == "--project":
            project = target_path(where, rest[i + 1]) or where
    files = positional(rest, {"--reason", "--project"})
    if not files:
        return None
    A, TL = lib(), testlock_lib()
    top = TL.find_top(project)
    rels = []
    for f in files:
        full = target_path(project, f)
        try:
            rels.append(full.resolve().relative_to(top).as_posix() if full is not None and top else f)
        except (OSError, ValueError, RuntimeError):
            rels.append(f)
    book = TL.load(top) if top else TL.empty()
    names = [Path(r).name for r in book["files"]]
    text = str((A.load_turn(session_id) or {}).get("consent_text") or "") if session_id else ""
    vague = [r for r in rels if names.count(Path(r).name) > 1 and r not in text]
    key = f"{top or project} unlock {' '.join(sorted(rels))}"
    if session_id and not vague and A.turn_consent(session_id, key, "unlock", tuple(rels), use=True):
        try:
            turn = A.load_turn(session_id) or {}
            path = A.state_dir() / UNLOCK_CONSENTS
            seen = A.read_json(path, [])
            seen = seen if isinstance(seen, list) else []
            for rel in rels:
                sha = (book["files"].get(rel) or {}).get("sha256", "")
                seen.append({"top": str(top), "path": rel, "sha256": sha, "ts": time.time(),
                             "text": str(turn.get("consent_text") or "")[:300]})
            path.parent.mkdir(parents=True, exist_ok=True)
            A.write_json_atomic(path, seen[-200:])
        except (OSError, ValueError, RuntimeError):
            pass  # thiếu biên nhận thì done-gate báo đỏ: đóng chứ không mở
        return None
    shown = ", ".join(files)
    return "deny", (f"agent-stack: mở khóa {shown} là nới test đã khóa, chỉ chạy khi tin người dùng vừa gửi bảo mở khóa "
                    f"đúng file đó (ví dụ \"mở khóa {files[0]}\"). Dừng ở đây, đừng chạy lại trong lượt này: đề xuất "
                    "cho người dùng vì sao test cần đổi; họ trả lời như vậy thì chạy lại đúng lệnh này.")


# Bản chụp cấu hình project đã duyệt (.agent/stack.json, GĐ4) nằm trong state/stack-approved/ (TM-119): chỉ
# `stack.py approve` (qua lời duyệt của người dùng) hay hook (khi file chỉ siết) được ghi. Tên dưới đây trong lệnh trình
# thông dịch thì chặn (dò theo tên, như sổ khóa test).
STACK_SNAP_NAMES = ("stack-approved", "save_snapshot", "APPROVED_DIR", "snapshot_path")
STACK_SNAP_REASON = ("agent-stack: `state/stack-approved/` là bản chụp cấu hình project người dùng đã duyệt; chỉ đổi qua "
                     "`stack.py approve <mã mục>` sau khi người dùng duyệt đúng mục đó. Ghi, xóa hay dời nó (kể cả dời "
                     "cả thư mục state/) là tự duyệt việc nới.")
STACK_HIDDEN_REASON = ("agent-stack: `stack.py approve` chỉ chạy trực tiếp (`python3 …/stack.py approve <mã mục>`) để hook "
                       "kiểm lời duyệt của người dùng; chạy qua xargs, find -exec, heredoc, chuỗi đưa vào shell hay "
                       "`python -c` thì không kiểm được nên bị chặn.")
STACK_REMOVERS = {"rm", "rmdir", "unlink", "shred", "trash"}
STACK_VALUE_FLAGS = {"--project", "--item", "--remove"}
FIND_LEAD_FLAGS = {"-H", "-L", "-P"}
FIND_LEAD_VALUE_FLAGS = {"-D", "-O"}


def removed_paths(argv: list, where: Path) -> list:
    """Đường dẫn bị xóa hay dời đi (không tính đích): mọi tham số của rm, rmdir…; nguồn của mv; điểm bắt đầu của find
    khi find có -delete hay -exec, -ok (bỏ qua -H, -L, -P, -D x, -O x đứng đầu). find chỉ đọc thì không tính."""
    prog = Path(argv[0]).name
    if prog in STACK_REMOVERS:
        names = [a for a in argv[1:] if not a.startswith("-")]
    elif prog == "mv":
        names = positional(argv[1:], {"-t", "--target-directory", "-S", "--suffix"})
        target_flag = any(a in ("-t", "--target-directory") or a.startswith("--target-directory=")
                          or (a.startswith("-t") and len(a) > 2) for a in argv[1:])
        names = names if target_flag else names[:-1]  # `mv -t dir a b`: mọi tham số vị trí là nguồn
    elif prog == "find" and find_destructive(argv):
        names = find_starts(argv)
    else:
        return []
    return [p for p in (target_path(where, n) for n in names) if p is not None]


FIND_READ_ONLY = {"cat", "wc", "ls", "stat", "grep", "head", "tail", "echo", "file", "du", "printf", "md5", "shasum",
                  "sha256sum", "realpath", "readlink", "basename", "dirname", "test", "["}


def find_starts(argv: list) -> list:
    """Điểm bắt đầu của find (bỏ qua -H, -L, -P, -D x, -O x, -Dx, -O3 đứng đầu); không có thì `.`."""
    i = 1
    while i < len(argv) and (argv[i] in FIND_LEAD_FLAGS or argv[i] in FIND_LEAD_VALUE_FLAGS
                             or re.fullmatch(r"-O\d+|-D\S+", argv[i])):
        i += 2 if argv[i] in FIND_LEAD_VALUE_FLAGS else 1
    names = []
    while i < len(argv) and not argv[i].startswith(("-", "(", "!", ")")):
        names.append(argv[i])
        i += 1
    return names or ["."]


def find_destructive(argv: list) -> bool:
    """find có -delete, hay -exec, -ok chạy lệnh không thuộc nhóm chỉ đọc (wc, ls, stat, grep…)."""
    if "-delete" in argv:
        return True
    return any(sub and Path(sub[0]).name not in FIND_READ_ONLY for sub in launched_commands(argv))


def find_argvs(command: str) -> list:
    """argv của từng lệnh find trong chuỗi, tách bằng shlex trên chuỗi gốc: dấu ngoặc `\\(`, `'('` của find không
    làm vỡ lệnh như ở simple_commands. Hết lệnh ở |, ||, &&, & hay ; nằm ngoài -exec."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    out, current, in_exec = [], None, False
    for tok in tokens:
        if current is None:
            if Path(tok).name == "find":
                current, in_exec = [tok], False
            continue
        if in_exec and tok in (";", "+"):
            current.append(tok)
            in_exec = False
            continue
        if not in_exec and (tok in ("|", "||", "&&", "&") or tok.endswith(";")):
            if tok.endswith(";") and tok != ";":
                current.append(tok[:-1])
            out.append(current)
            current = None
            continue
        current.append(tok)
        if tok in FIND_ACTIONS:
            in_exec = True
    if current:
        out.append(current)
    return out


def stack_find_check(command: str, cwd: str):
    """Lượt riêng cho find (TM-119): xóa hay dời bản chụp đã duyệt, hay chạy stack.py hộ, kể cả khi lệnh có dấu ngoặc,
    hay khi điểm bắt đầu là thư mục cha của state/ mà lệnh nhắc tới stack-approved hay state."""
    where = Path(cwd or ".")
    for argv in find_argvs(command):
        if stack_hidden(argv):
            return "deny", STACK_HIDDEN_REASON
        if not find_destructive(argv):
            continue
        for full in removed_paths(argv, where):
            if in_stack_snapshots(full, ancestors=True):
                return "deny", STACK_SNAP_REASON
            try:
                above = full.resolve() in lib().state_dir().resolve().parents
            except (OSError, RuntimeError, ValueError):
                above = False
            if above and any("stack-approved" in a or re.search(r"(^|/)state(/|$)", a) for a in argv[1:]):
                return "deny", STACK_SNAP_REASON
    return None


def in_stack_snapshots(full: Path, ancestors: bool = False) -> bool:
    """`full` nằm trong state/stack-approved/; `ancestors`: hay là chính thư mục state/ (`rm -r state`, `mv state x`).
    Thư mục cao hơn (repo, home) để cổng lệnh không đảo ngược (`rm -r` ngoài thư mục tạm) hỏi người dùng."""
    try:
        state = lib().state_dir().resolve()
        snap = (state / "stack-approved").resolve()
        target = full.resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return target == snap or snap in target.parents or (ancestors and target == state)


def stack_subcommand(argv: list):
    """("approve", phần sau stack.py) khi argv chạy thẳng stack.py của skill project-setup (hay qua trình chạy như
    python3, uv run) với lệnh con approve ở bất kỳ vị trí nào (cờ đặt trước vẫn tính); lệnh con khác thì (tên, phần
    sau); (None, []) khi stack.py không phải lệnh được chạy."""
    first = Path(argv[0]).name
    if first in FILE_OPS or not (first == "stack.py" or RUNNER_RE.match(first)):
        return None, []
    at = next((i for i, a in enumerate(argv) if Path(a).name == "stack.py"), None)
    if at is None:  # `python3 -m stack …` (chạy từ thư mục scripts, hay qua PYTHONPATH)
        at = next((i + 1 for i, a in enumerate(argv[:-1]) if a == "-m" and STACK_MODULE_RE.match(argv[i + 1])), None)
    if at is None:  # `python3 -mstack …`
        at = next((i for i, a in enumerate(argv) if a.startswith("-m") and STACK_MODULE_RE.match(a[2:])), None)
    if at is None:
        return None, []
    rest = argv[at + 1:]
    words = positional(rest, STACK_VALUE_FLAGS)
    if "approve" in words:
        return "approve", rest
    return (words[0] if words else ""), rest


STACK_MODULE_RE = re.compile(r"^(?:[\w.]+\.)?stack$")
STACK_IMPORT_RE = re.compile(r"\b(?:import|from)\s+(?:[\w.]+\.)?stack\b|__import__|importlib|import_module|runpy|"
                             r"stack\.py")
STACK_FAN_OUT = {"xargs", "parallel", "find"}  # lệnh con lấy tham số từ stdin hay từ file tìm được: không kiểm được
STACK_PREFIXES = {"env", "nohup", "timeout", "sudo", "nice", "time", "watch", "exec", "command", "builtin",
                  "caffeinate", "script", "stdbuf", "ionice"}
XARGS_VALUE_FLAGS = {"-I", "-i", "-n", "-P", "-L", "-l", "-s", "-d", "-E", "-e", "-a", "-j", "--jobs"}
FIND_ACTIONS = {"-exec", "-execdir", "-ok", "-okdir"}


def launched_commands(argv: list) -> list:
    """Các lệnh con mà argv sẽ chạy hộ: sau `-exec` của find, lệnh của xargs, parallel, và lệnh sau các tiền tố như
    env, timeout, nohup. Rỗng khi argv không chạy hộ gì."""
    prog = Path(argv[0]).name
    out = []
    if prog == "find":
        for i, a in enumerate(argv):
            if a in FIND_ACTIONS:
                end = next((j for j in range(i + 1, len(argv)) if argv[j] in (";", "+", "\\;")), len(argv))
                out.append(argv[i + 1:end])
    elif prog in ("xargs", "parallel"):
        i = 1
        while i < len(argv) and argv[i].startswith("-"):
            i += 2 if argv[i] in XARGS_VALUE_FLAGS else 1
        out.append(argv[i:])
    elif prog in STACK_PREFIXES:
        i = 1
        while i < len(argv) and (argv[i].startswith("-") or "=" in argv[i] or re.fullmatch(r"[\d.]+[smhd]?", argv[i])):
            i += 1
        out.append(argv[i:])
    return [x for x in out if x]


def stack_hidden(argv: list) -> bool:
    """stack.py chạy hộ mà hook không kiểm được lời duyệt: qua xargs, parallel, find -exec (bất kể lệnh con, vì tham số
    đến từ stdin hay từ file tìm được); `approve` sau tiền tố env, timeout…; hay trong mã chạy như code (`sh -c "…"`,
    `python -c "…"` có stack.py, import stack, runpy). Đọc file (`grep approve …/stack.py`, `find … -name stack.py
    -exec grep …`) thì không tính."""
    prog = Path(argv[0]).name
    if stack_subcommand(argv)[0] is not None:
        return False
    names_stack = any("stack.py" in a or STACK_MODULE_RE.match(a) for a in argv[1:])
    for sub in launched_commands(argv):
        kind = stack_subcommand(sub)[0]
        if kind is not None and (prog in STACK_FAN_OUT or kind == "approve"):
            return True
        # `find … -name stack.py -exec python3 {} approve …`, `… | xargs -I{} python3 {} approve`: stack.py do find
        # hay stdin đưa vào chỗ {}, không có tên trong lệnh con
        runs_code = sub and (RUNNER_RE.match(Path(sub[0]).name) or Path(sub[0]).name in STACK_SHELLS)
        if prog in STACK_FAN_OUT and names_stack and runs_code and (
                any(x in ("{}", "%") for x in sub) or any("approve" in x for x in sub)):
            return True
        if sub and stack_hidden(sub):
            return True
    if not any("approve" in a for a in argv):
        return False
    as_code = prog in STACK_SHELLS or (bool(RUNNER_RE.match(prog) or prog in LOCK_WRITERS)
                                       and any(a in ("-c", "-e", "--eval") for a in argv[1:]))
    return as_code and any(STACK_IMPORT_RE.search(a) and Path(a).name != "stack.py" for a in argv[1:])


STACK_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "eval", "source", "."}


def stack_piped_to_shell(command: str) -> bool:
    """Chuỗi lệnh có `stack.py` và approve mà có một lệnh shell trần (không `-c`, không tham số: đọc lệnh từ stdin, như
    `echo '… stack.py approve all' | sh`). Chữ nằm trong dấu nháy của commit message không tạo ra lệnh shell nào."""
    if "stack.py" not in command or "approve" not in command:
        return False
    for a in simple_commands(command):
        if not a:
            continue
        if Path(a[0]).name in SHELLS and not any(SHELL_C_RE.match(x) for x in a[1:]) and not positional(a[1:], set()):
            return True
        # xargs, parallel đưa chữ từ stdin vào shell hay trình thông dịch (`… | xargs -I{} sh -c {}`)
        if Path(a[0]).name in ("xargs", "parallel") and any(
                sub and (Path(sub[0]).name in STACK_SHELLS or RUNNER_RE.match(Path(sub[0]).name))
                for sub in launched_commands(a)):
            return True
    return False


def check_stack_argv(argv: list, cwd: str, session_id: str):
    """`stack.py approve <mã mục>…` chỉ qua khi tin người dùng mở lượt này bảo duyệt đúng các mục đó (TM-119), một lần
    mỗi tin; lệnh ghi, xóa, dời `state/stack-approved/` (hay thư mục chứa nó) thì chặn."""
    where = Path(cwd or ".")
    prog = Path(argv[0]).name
    for full, _ in write_targets(argv, where):
        if in_stack_snapshots(full, ancestors=prog in STACK_REMOVERS):
            return "deny", STACK_SNAP_REASON
    for full in removed_paths(argv, where):  # `rm -rf state`, `mv state x`, `find -L state -delete`
        if in_stack_snapshots(full, ancestors=True):
            return "deny", STACK_SNAP_REASON
    if stack_hidden(argv):
        return "deny", STACK_HIDDEN_REASON
    sub, rest = stack_subcommand(argv)
    if sub != "approve":
        return None
    words = positional(rest, STACK_VALUE_FLAGS)
    words.remove("approve")
    items = words
    if not items:
        return None
    A = lib()
    project = where
    for i, arg in enumerate(rest[:-1]):
        if arg == "--project":
            project = target_path(where, rest[i + 1]) or where
    key = f"{project} stack-approve {' '.join(sorted(items))}"
    if session_id and A.turn_consent(session_id, key, "approve", tuple(items), use=True):
        return None
    example = f"duyệt hết {items[0][4:]}" if items[0].startswith("all:") else f"duyệt {items[0]}"
    return "deny", (f"agent-stack: `stack.py approve {' '.join(items)}` là nới cấu hình project (.agent/stack.json), chỉ chạy "
                    f"khi tin người dùng vừa gửi bảo duyệt đúng mục đó (ví dụ \"{example}\"). Dừng ở đây, "
                    "đừng chạy lại trong lượt này: đưa người dùng mục đó kèm lý do và bằng chứng (`stack.py check`); họ "
                    "trả lời như vậy thì chạy lại đúng lệnh này.")


def stack_named_by_interpreter(command: str):
    """Trình thông dịch hay trình soạn mà chuỗi lệnh nhắc tới bản chụp đã duyệt (python -c, heredoc…): chặn."""
    try:
        def interp(argv) -> bool:
            name = Path(argv[0]).name if argv else ""
            return bool(RUNNER_RE.match(name) or name in LOCK_WRITERS) and stack_subcommand(argv)[0] is None

        named = any(interp(a) and any(n in x for x in a[1:] for n in STACK_SNAP_NAMES) for a in simple_commands(command))
        for m in HEREDOC_RE.finditer(command):
            head = command[command.rfind("\n", 0, m.start()) + 1:m.start()]
            if any(n in m.group(0) for n in STACK_SNAP_NAMES) and any(interp(a) for a in simple_commands(head)):
                named = True
            if ("stack.py" in m.group(0) or STACK_IMPORT_RE.search(m.group(0))) and "approve" in m.group(0) and any(  # heredoc đưa `stack.py approve` vào shell
                    Path(a[0]).name in STACK_SHELLS or interp(a) for a in simple_commands(head) if a):
                return "deny", STACK_HIDDEN_REASON
        if stack_piped_to_shell(command):
            return "deny", STACK_HIDDEN_REASON
    except Exception:  # noqa: BLE001
        return None
    return ("deny", STACK_SNAP_REASON) if named else None


def check_locked_bash(argv: list, cwd: str, session_id: str = ""):
    """Lệnh đơn đụng sổ khóa hay test đã khóa (TM-102..104). `receipt.py unlock` qua cổng đồng ý của người dùng."""
    sub, rest = receipt_subcommand(argv)
    where, pending = Path(cwd or "."), None
    if sub == "unlock":
        return check_unlock(rest, where, session_id)
    if sub in ("run", "fails-before", "lock"):  # `receipt.py run [--] rm tests/x.py`: xét lệnh bên trong
        inner = receipt_inner(rest)
        found = check_bash(shlex.join(inner), str(receipt_run_dir(rest, where)), session_id) if inner else None
        if found and found[0] == "deny":
            return found
        pending = found if found and found[0] == "ask" else None  # `receipt.py run … -- x > sổ`: phần ngoài vẫn xét
    TL = testlock_lib()
    prog = Path(argv[0]).name
    targets = write_targets(argv, where)
    for arg in argv[1:]:
        if LOCK_NAME not in arg:
            continue
        full = target_path(where, arg.lstrip(">"))
        if full is not None and TL.is_lock_file(full) and (
                prog in LOCK_WRITERS or any(TL.is_lock_file(t) for t, _ in targets)):
            return "deny", ("agent-stack: `.agent/test-lock.json` là sổ khóa test, chỉ sửa bằng `receipt.py lock` "
                            "hay `receipt.py unlock` (cần người dùng duyệt). Sửa tay sổ là nới mà không ai duyệt.")
    for full, text in targets:
        try:
            if any(ch in text for ch in GLOB_CHARS):  # `rm tests/*.py`: shell mở rộng trước khi chạy
                paths = expand_glob(full)
            else:
                paths = locked_inside(TL, full) if full.is_dir() else [full]
            if any(TL.is_lock_file(p) for p in paths):
                return "deny", ("agent-stack: lệnh này xóa hay ghi đè `.agent/test-lock.json` (sổ khóa test). Chỉ sửa "
                                "sổ bằng `receipt.py lock` hay `receipt.py unlock` (cần người dùng duyệt).")
            for path in paths:
                hit = locked_hit(path, f"lệnh shell `{prog}`", session_id)
                if hit:
                    return hit
        except (OSError, RuntimeError, ValueError):
            continue
    return pending


def check_arch_argv(argv: list, cwd: str):
    """Lệnh đơn chạy lệnh archctl chỉ người được chạy (cả qua xargs, find -exec, đường dẫn tuyệt đối), hay ghi, xóa,
    đổi tên file luật trong `.arch/` (TM-115). `propose`, `block`, `check`, `verify` vẫn qua."""
    G = arch_lib()
    where = Path(cwd or ".")
    for i, word in enumerate(argv):
        if G.is_archctl(word):
            rest = strip_prefixes(argv[i:])
            sub = G.human_command(rest)
            if sub:
                return "deny", ARCH_CMD_REASON.format(sub=sub)
            if G.nested_init(rest, where):
                return "deny", ("agent-stack: `archctl init` ở đây tạo một bộ luật mới lồng trong project đã có "
                                "`.arch/system.arch`; hook sẽ kiểm theo bộ luật rỗng gần hơn. Đổi luật thì `archctl "
                                "propose`; muốn tách bộ luật thì báo người dùng tự chạy.")
            if i and Path(argv[0]).name == "xargs" and not positional(rest[1:], G.VALUE_FLAGS):
                return "deny", ("agent-stack: `xargs archctl` lấy lệnh con từ stdin nên không biết sẽ chạy gì "
                                "(có thể là accept, baseline). Gọi archctl với lệnh con viết rõ.")
    targets = write_targets(argv, where)
    targets += [(t, text) for text in G.out_targets(strip_prefixes(argv)) for t in [target_path(where, text)] if t]
    for full, text in targets:
        paths = [full]
        if any(ch in text for ch in GLOB_CHARS):  # `sed -i … .arch/*.arch`: shell mở rộng trước khi chạy
            import glob
            paths += [Path(p) for p in glob.glob(str(full))[:500]]
        for path in paths:
            if G.is_protected(path, where):
                return "deny", ARCH_FILE_REASON.format(rel=arch_rel(path, text))
    return None


def arch_rel(full: Path, text: str) -> str:
    """Tên gọn của file luật cho lời báo: `.arch/<tên>`."""
    if full.name.casefold() == ".arch":
        return ".arch/ (cả thư mục luật)"
    return f".arch/{full.name}" if full.parent.name.casefold() == ".arch" else (text or str(full))


def arch_named_by_interpreter(command: str, cwd: str):
    """Trình thông dịch hay trình soạn (python -c, node -e, heredoc vào python…) mà chuỗi lệnh nhắc tên một file luật
    `.arch/<tên>`, khi project có `.arch/system.arch`: chặn (TM-115). Đọc luật thì dùng Read hay `cat`."""
    try:
        G = arch_lib()
        if G.find_root(Path(cwd or ".")) is None:
            return None
        names = [f"{G.ARCH_DIR}/{n}" for n in G.PROTECTED]

        def interp(argv) -> bool:
            name = Path(argv[0]).name if argv else ""
            return bool(RUNNER_RE.match(name) or name in LOCK_WRITERS) and receipt_subcommand(argv)[0] is None

        hit = next((n for a in simple_commands(command) if interp(a) for x in a[1:] for n in names
                    if n in x.casefold()), None)
        for m in HEREDOC_RE.finditer(command):
            head = command[command.rfind("\n", 0, m.start()) + 1:m.start()]
            found = next((n for n in names if n in m.group(0).casefold()), None)
            if found and any(interp(a) for a in simple_commands(head)):
                hit = hit or found
        if not hit:
            return None
    except Exception:  # noqa: BLE001
        return None
    return "deny", ARCH_FILE_REASON.format(rel=hit)


HUMAN_ARCHCTL_RE = re.compile(r"\barchctl\b[^\n;&|]*?\b(accept|reject|baseline|serve)\b", re.I)


def arch_fed_to_shell(command: str, cwd: str):
    """Lệnh archctl chỉ người được chạy nằm trong chữ đưa vào shell qua stdin: thân heredoc của `bash <<EOF`, hay
    `echo "…" | sh` (simple_commands không mở các dạng này như `bash -c`)."""
    try:
        for m in HEREDOC_RE.finditer(command):
            head = command[command.rfind("\n", 0, m.start()) + 1:m.start()]
            if any(Path(a[0]).name in SHELLS for a in simple_commands(head) if a):
                body = m.group(0).split("\n", 1)[1] if "\n" in m.group(0) else ""
                for argv in simple_commands(body):
                    found = check_arch_argv(argv, cwd)
                    if found:
                        return found
        bare_shell = any(Path(a[0]).name in SHELLS and not any(SHELL_C_RE.match(x) for x in a[1:])
                         and not positional(a[1:], set()) for a in simple_commands(command) if a)
        m = HUMAN_ARCHCTL_RE.search(command) if bare_shell else None
        if m:
            return "deny", ARCH_CMD_REASON.format(sub=m.group(1).lower())
    except Exception:  # noqa: BLE001
        return None
    return None


def brace_expand(pattern: str) -> list:
    """Mở một tầng ngoặc nhọn của shell: tests/test_{a,b}.py → hai mẫu."""
    m = re.search(r"\{([^{}]*,[^{}]*)\}", pattern)
    if not m:
        return [pattern]
    return [x for part in m.group(1).split(",")[:50] for x in brace_expand(pattern[:m.start()] + part + pattern[m.end():])]


def expand_glob(full: Path) -> list:
    """File khóa (và chính sổ khóa) khớp mẫu glob: so mẫu với các mục trong sổ, không quét đĩa (TM-106)."""
    import fnmatch
    TL = testlock_lib()
    prefix = str(full).split("*")[0].split("?")[0].split("[")[0].split("{")[0]
    top = TL.find_top(Path(prefix) if prefix.endswith("/") else Path(prefix).parent)
    if top is None or not (top / TL.LOCK_REL).is_file():
        return []
    candidates = [top / rel for rel in TL.load(top)["files"]] + [top / TL.LOCK_REL]
    pats = brace_expand(str(full))
    return [c for c in candidates if any(fnmatch.fnmatchcase(str(c), p) or fnmatch.fnmatchcase(str(c.resolve()), p)
                                         for p in pats)]


def locked_inside(TL, folder: Path) -> list:
    """File đã khóa nằm trong thư mục `folder` (`rm -r tests/`, `git checkout -- tests`)."""
    try:
        top = TL.find_top(folder)
        rel = folder.resolve().relative_to(top).as_posix() if top else None
    except (OSError, ValueError):
        return []
    if top is None or not (top / TL.LOCK_REL).is_file():
        return []  # project không có sổ khóa: hành vi như cũ
    prefix = "" if rel in (".", "") else rel + "/"
    return [top / p for p in [*TL.load(top)["files"], TL.LOCK_REL] if p.startswith(prefix)]


def unknown_dir_pattern(full: str):
    """(thư mục biết chắc phía trước, mẫu glob) cho đích `full` có glob, biến hay lệnh con trong đường dẫn. Glob giữ
    nguyên; từ biến, lệnh con hay `..` sau chỗ không biết trở về trước thành `*`, vì giá trị có thể là đường dẫn tuyệt
    đối. None khi đường dẫn biết rõ."""
    parts = full.split("/")
    first = next((i for i, p in enumerate(parts) if any(ch in p for ch in DIR_UNKNOWN)), None)
    if first is None:
        return None
    cut = max((i for i, p in enumerate(parts) if any(ch in p for ch in DIR_OPAQUE) or (p == ".." and i > first)),
              default=None)
    anchor = Path("/".join(parts[:first]) or "/").resolve()  # `/var` → `/private/var`, như gốc repo trong sổ
    head, rest = (str(anchor).rstrip("/"), parts[first:]) if cut is None else ("*", parts[cut + 1:])
    return anchor, "/".join([head] + [p for p in rest if p not in ("", ".")])


def unknown_dir_check(argv: list, cwd: str, session_id: str = ""):
    """Thư mục chạy không biết trước (`cd t*`, `--cwd $PWD/tests`, `--project $P`): đích tương đối của lệnh ghi, xóa
    khớp test đã khóa hay sổ khóa khi coi phần không biết là bất kỳ thì hỏi người dùng, thay vì cho qua vì đường dẫn
    chữ không trùng mục nào. So mẫu với các mục sổ của project chứa phần biết chắc, không quét đĩa (TM-106). Đích có
    biến (`rm "$f"`) hay tuyệt đối thì không xét ở đây (TM-146)."""
    where = os.path.expanduser(cwd or ".")
    where = os.path.join(os.getcwd(), where) if not os.path.isabs(where) else where  # không gộp `..`: `cd "$X/.."`
    if not any(ch in where for ch in DIR_UNKNOWN):
        return None
    import fnmatch
    TL = testlock_lib()
    for full, text in write_targets(argv, Path(where)):
        found = None if any(ch in text for ch in DIR_OPAQUE) or text.startswith(("/", "~")) else \
            unknown_dir_pattern(str(full))
        if found is None:
            continue
        anchor, pattern = found
        top = TL.find_top(anchor)
        if top is None or not (top / TL.LOCK_REL).is_file():
            continue
        pats = [q for p in brace_expand(pattern) for q in (p, p.rstrip("/") + "/*")]  # đích có thể là thư mục
        for cand in [top / rel for rel in TL.load(top)["files"]] + [top / TL.LOCK_REL]:
            if not any(fnmatch.fnmatchcase(str(cand), p) for p in pats):
                continue
            rel = cand.relative_to(top).as_posix()
            why = ("agent-stack: hook không biết thư mục chạy lệnh này (`cd`, `pushd`, `--cwd` hay `--project` có "
                   f"glob, biến hay lệnh con), mà đích `{text}` có thể là `{rel}`")
            fix = ("Viết thẳng đường dẫn thư mục (không glob, không biến) để hook kiểm được. Người dùng chỉ đồng ý khi "
                   "chắc lệnh không đụng file đó.")
            if TL.is_lock_file(cand):
                return "ask", f"{why}, sổ khóa test (chỉ sửa bằng `receipt.py lock` hay `unlock`). {fix}"
            if TL.lookup(cand):  # không gọi locked_hit: nó ghi lời nhắc mức vừa của lượt mà câu hỏi không tới Claude
                return "ask", f"{why}, test đã khóa; xóa hay ghi đè test khóa là nới. {fix}"
    return None


def check_locked_write(tool: str, tool_input: dict, full: Path, session_id: str):
    """Write/Edit/MultiEdit/NotebookEdit vào sổ khóa (chặn) hay vào test đã khóa: so nội dung mới với bản khóa."""
    TL = testlock_lib()
    if TL.is_lock_file(full):
        return "deny", ("agent-stack: `.agent/test-lock.json` là sổ khóa test, chỉ sửa bằng `receipt.py lock` hay "
                        "`receipt.py unlock` (cần người dùng duyệt).")
    found = TL.lookup(full)
    if not found:
        return None
    new = new_content(tool, tool_input, full)
    change = "changed" if new is None else TL.compare(found[2], new)
    how = {"Write": "ghi đè file", "NotebookEdit": "sửa notebook"}.get(tool, "sửa dòng có sẵn")
    return locked_hit(full, how, session_id, change)


def new_content(tool: str, tool_input: dict, full: Path):
    """Nội dung file sau thao tác; None khi không tính được (coi là nới)."""
    if tool == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None
    try:
        if full.stat().st_size > 1_000_000:
            return None
        text = full.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    edits = tool_input.get("edits") if tool == "MultiEdit" else [tool_input] if tool == "Edit" else None
    if not isinstance(edits, list):
        return None
    for e in edits:
        old, rep = (e.get("old_string"), e.get("new_string")) if isinstance(e, dict) else (None, None)
        if not isinstance(old, str) or not isinstance(rep, str) or old not in text:
            return None
        text = text.replace(old, rep) if e.get("replace_all") else text.replace(old, rep, 1)
    return text


def check_write(tool_input: dict, cwd: str, session_id: str, tool: str = "Write"):
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path:
        return None
    full = Path(path) if Path(path).is_absolute() else Path(cwd or ".") / path
    try:
        if arch_lib().is_protected(full, cwd or "."):
            return "deny", ARCH_FILE_REASON.format(rel=arch_rel(full, path))
    except Exception:  # noqa: BLE001
        pass
    if in_stack_snapshots(full):
        return "deny", STACK_SNAP_REASON
    if is_spec_book(full):
        return "deny", SPEC_BOOK_REASON
    locked = check_locked_write(tool, tool_input, full, session_id)
    if locked:
        return locked
    if REPORT_RE.search(full.name) and full.suffix.lower() == ".md" and not safe_scratch(full):
        return "deny", ("agent-stack: báo cáo differential-review là danh sách lỗ hổng chưa vá; đừng ghi vào trong "
                        "project (dễ bị commit lẫn). Ghi vào `.tmp/` của project (nếu đã bị git bỏ qua) hoặc thư mục "
                        "tạm của hệ điều hành.")
    if tool == "Write":
        nudge = check_new_markdown(full, cwd, session_id)
        if nudge:
            return nudge
    if full.suffix.lower() not in SOURCE_EXT or not session_id:
        return None
    A = lib()
    turn = A.load_turn(session_id)
    if not turn or not (turn.get("threat_model") or turn.get("criteria")):
        return None
    root = Path(turn.get("root") or "")
    try:
        full.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    if re.search(r"(^|/)(tests?|spec|__tests__)/", str(full)) or re.match(r"test_|.*_test\.", full.name):
        return None
    if in_nested_repo(full, root):
        return None  # subagent làm trong worktree: phiên chính lo threat model và §0 (luật không sửa file kế hoạch)
    reasons = []
    if turn.get("threat_model") and not turn.get("threat_model_nudged") and not threat_model_written(root, turn):
        turn["threat_model_nudged"] = True
        own = (root / ".claude" / "skills" / "threat-model" / "SKILL.md").exists()
        skill = "skill threat-model của project này" if own else "skill agent-stack:threat-model"
        reasons.append(f"lượt này làm chức năng đụng ranh giới tin cậy mà chưa có threat model. Trước khi code, chạy "
                       f"{skill} (ghi `.agent/threat-model.md`), rồi viết code kèm các chốt chặn")
    plan = None if turn.get("criteria_nudged") else plan_without_criteria(A, root)
    if turn.get("criteria") and plan:
        turn["criteria_nudged"] = True
        reasons.append(
            f"lượt này làm tính năng, sửa lỗi hay refactor mà §0 của `{plan}` chưa có tiêu chí xong. Trước khi code, "
            "ghi 2–4 tiêu chí vào §0 dạng `- **Tiêu chí xong** (việc, ngày, nguồn): 1) … 2) …`, mỗi tiêu chí là một "
            "lệnh phải đạt hay một cặp đầu vào và đầu ra mong đợi, lấy nguyên lời người dùng khi có (nguồn: lời "
            "bạn). Việc từ mức vừa (đụng hook hay code chạy tự động, nhiều file, ranh giới tin cậy, hành vi người "
            "dùng thấy) mà tiêu chí do agent tự suy thì hỏi người dùng xác nhận rồi mới code (nguồn: bạn xác nhận); "
            "chốt việc sẽ so kết quả với chính các tiêu chí này")
    if not reasons:
        return None
    A.save_turn(session_id, turn)
    return "deny", ("agent-stack: " + ". Ngoài ra, ".join(reasons) + ". Nếu nhắc không hợp (việc thật ra nhỏ, hay "
                    "không đụng ranh giới tin cậy) thì cứ ghi lại file này: mỗi nhắc chỉ hiện một lần mỗi lượt.")


def in_nested_repo(full: Path, root: Path) -> bool:
    """File nằm trong worktree hay repo lồng bên trong project (có `.git` ở thư mục giữa file và gốc project)."""
    try:
        top = root.resolve()
        for folder in full.resolve().parents:
            if folder == top or top not in folder.parents:
                return False
            if (folder / ".git").exists():
                return True
    except OSError:
        return False
    return False


def threat_model_written(root: Path, turn: dict) -> bool:
    try:
        return (root / ".agent" / "threat-model.md").stat().st_mtime >= turn["ts"]
    except OSError:
        return False


def plan_without_criteria(A, root: Path):
    """Đường dẫn file kế hoạch (tính từ project) khi §0 của nó chưa có tiêu chí xong; None khi đã có, hay project
    không có file kế hoạch có §0 (khi đó chốt việc tự viết tiêu chí và báo là viết ở cuối việc)."""
    found = A.read_plan(root)
    if not found or not found[2]["heading"] or A.has_value(found[2]["fields"].get("criteria")):
        return None
    try:
        return found[0].relative_to(root).as_posix()
    except ValueError:
        return found[0].name

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
        result = check_bash(str(tool_input.get("command") or ""), cwd, data.get("session_id") or "")
    elif tool == "Monitor":  # Monitor chạy lệnh shell: chỉ xét lệnh xóa ổ đĩa (review 19/11)
        result = check_disk_command(str(tool_input.get("command") or ""))
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        result = check_write(tool_input, cwd, data.get("session_id") or "", tool)
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
