#!/usr/bin/env python3
"""Gộp nhánh mà subagent đã sửa trong worktree riêng (Agent với isolation "worktree") vào nhánh hiện tại.

Chỉ tự gộp khi chắc chắn: worktree thuộc chính repo này, test đạt trong worktree, gộp được bằng fast-forward, diff không
đụng file cấu hình nhạy cảm (quyền, hook, CI, luật cho agent), và file chưa commit ở cây làm việc chính không trùng
file nhánh đổi. Còn lại thì dừng, in lý do để phiên chính hỏi người dùng. Không bao giờ push.

  merge_back.py --worktree <đường dẫn hay tên nhánh> --test "<lệnh test>" [--commit "<thông điệp>"] [--keep] [--json]

--commit: worktree còn thay đổi chưa commit thì commit tất cả với thông điệp này trước (subagent quên commit).
--keep: gộp xong vẫn giữ worktree và nhánh (mặc định xoá cả hai).
--timeout: giây tối đa cho lệnh test (mặc định 1800); quá giờ thì giết cả nhóm tiến trình của nó.

Lưu ý: chạy script này là chạy toàn bộ mã của nhánh (test, conftest...) dưới quyền của bạn, ngoài vòng duyệt từng lệnh
của Claude Code. Chỉ dùng cho nhánh do subagent của chính phiên tạo.

Mã thoát: 0 đã gộp hoặc không có gì để gộp; 2 cần người dùng quyết; 1 test trượt hay lỗi.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import unicodedata
from pathlib import Path

# Thay đổi ở các đường dẫn này có thể nâng quyền hay đổi hành vi của agent và công cụ (quyền, hook, CI, luật và kế hoạch
# mà phiên sau nạp): không tự gộp. So sau NFKC và casefold (ổ đĩa macOS không phân biệt hoa thường và coi `ſ` là `s`,
# nên `.CLAUDE/` hay `.mcp.jſon` là file thật), ở mọi cấp thư mục, kể cả khi chính thư mục là một symlink được thêm vào.
SENSITIVE_DIRS = {".claude", ".github", ".githooks", ".husky", ".circleci", ".vscode", ".devcontainer", ".git",
                  ".agent", ".agents", ".opencode", ".cursor", ".gemini", ".windsurf", ".claude-plugin"}
SENSITIVE_NAMES = {"claude.md", "agents.md", "claude.local.md", "gemini.md", ".cursorrules", ".windsurfrules",
                   ".gitattributes", ".gitmodules", ".mcp.json", ".envrc", ".pre-commit-config.yaml", ".gitconfig",
                   ".gitlab-ci.yml", "opencode.json", "opencode.jsonc", "hooks.json",
                   "plan.md", "progress.md", "todo.md"}  # file kế hoạch: SessionStart nạp §0 vào mọi phiên
# Tên file giống secret: --commit không gom chúng vào lịch sử.
SECRET_NAME_RE = re.compile(r"(^|/)(\.env(\.[^/]*)?|[^/]*\.(pem|key|p12|pfx|keystore|jks)|id_(rsa|dsa|ecdsa|ed25519)[^/]*"
                            r"|[^/]*credential[^/]*|[^/]*secret[^/]*|\.netrc|\.npmrc|\.pypirc)$", re.IGNORECASE)
TEST_TIMEOUT = 1800


def git(cwd, *args, check=False):
    out = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.quotePath=false", "-C", str(cwd), *args],
                         capture_output=True, text=True, timeout=120)
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()[:300]}")
    return out


def worktrees(top: Path) -> list:
    """Các worktree của repo: [{path, branch, head}]; phần tử đầu là cây làm việc chính."""
    rows, cur = [], {}
    for line in git(top, "worktree", "list", "--porcelain", check=True).stdout.splitlines() + [""]:
        if not line.strip():
            if cur:
                rows.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = Path(line[9:]).resolve()
        elif line.startswith("branch "):
            cur["branch"] = line[7:].removeprefix("refs/heads/")
        elif line.startswith("HEAD "):
            cur["head"] = line[5:]
    return rows


def names(raw: str) -> list:
    """Danh sách tên từ output `-z` của git (tách theo NUL)."""
    return [x for x in raw.split("\0") if x]


def fold(name: str) -> str:
    return unicodedata.normalize("NFKC", name).casefold()


def sensitive(paths) -> list:
    hits = []
    for p in paths:
        parts = [fold(x) for x in p.split("/") if x]
        if any(x in SENSITIVE_DIRS for x in parts) or (parts and parts[-1] in SENSITIVE_NAMES):
            hits.append(p)
    return hits


def special_modes(top: Path, sha: str) -> list:
    """File nhánh thêm hay đổi thành symlink (120000) hoặc submodule (160000): không tự gộp."""
    hits = []
    parts = git(top, "diff", "-z", "--raw", "--no-renames", "--no-abbrev", "HEAD", sha).stdout.split("\0")
    for meta, path in zip(parts[0::2], parts[1::2]):  # -z: ":<mode cũ> <mode mới> ... <trạng thái>" rồi tên
        fields = meta.split()
        if len(fields) >= 2 and fields[1] in ("120000", "160000"):
            hits.append(path)
    return hits


def run_test(argv, cwd: Path, timeout: float = TEST_TIMEOUT):
    """Chạy lệnh test bằng argv (không shell) trong nhóm tiến trình riêng; quá giờ thì giết cả nhóm, kể cả tiến trình
    cháu. Trả (mã thoát hay None khi quá giờ, phần cuối output)."""
    proc = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            errors="replace", start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        out, _ = proc.communicate()
        code = None
    return code, "\n".join((out or "").strip().splitlines()[-15:])


def run(args) -> dict:
    top_out = git(args.repo, "rev-parse", "--show-toplevel")
    if top_out.returncode != 0:
        return {"status": "loi", "reason": f"{args.repo} không phải git repo"}
    top = Path(top_out.stdout.strip()).resolve()
    rows = worktrees(top)
    main = rows[0]
    if Path(main["path"]) != top:
        return {"status": "loi", "reason": "hãy chạy từ cây làm việc chính của repo, không từ một worktree phụ"}
    want = args.worktree
    target = None
    for row in rows[1:]:
        path_match = Path(want).expanduser().resolve() == row["path"] if ("/" in want or Path(want).exists()) else False
        if path_match or row.get("branch") == want:
            target = row
            break
    if target is None:
        return {"status": "loi", "reason": f"không tìm thấy worktree phụ `{want}` của repo này (git worktree list)"}
    wt, branch = target["path"], target.get("branch")
    if not branch:
        return {"status": "can-hoi", "reason": "worktree không ở trên nhánh nào (HEAD tách rời): không gộp tự động"}
    current = git(top, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if not current:
        return {"status": "can-hoi", "reason": "cây làm việc chính đang ở HEAD tách rời: không gộp tự động"}
    if current == branch:
        return {"status": "loi", "reason": "nhánh của worktree trùng nhánh hiện tại"}

    dirty_wt = git(wt, "status", "--porcelain").stdout.strip()
    if dirty_wt:
        if not args.commit:
            return {"status": "can-hoi", "reason": "worktree còn thay đổi chưa commit; commit trong worktree hoặc chạy "
                                                   "lại với --commit \"<thông điệp>\""}
        pending = names(git(wt, "ls-files", "-z", "--others", "--modified", "--exclude-standard").stdout)
        secrets = [f for f in pending if SECRET_NAME_RE.search(f)]
        if secrets:
            return {"status": "can-hoi", "branch": branch, "secret_like": secrets,
                    "reason": "worktree có file trông như secret chưa commit: không tự gom vào commit"}
        git(wt, "add", "-A", check=True)
        git(wt, "-c", "commit.gpgsign=false", "commit", "-q", "-m", args.commit, check=True)

    # Ghim đầu nhánh một lần: mọi bước kiểm, test và gộp dùng đúng commit này, để mã chạy lúc test không dời nhánh
    # sang commit chưa kiểm.
    sha = git(top, "rev-parse", "--verify", "-q", f"{branch}^{{commit}}").stdout.strip()
    if not sha:
        return {"status": "loi", "reason": f"không đọc được đầu nhánh `{branch}`"}
    if git(top, "merge-base", "--is-ancestor", "HEAD", sha).returncode != 0:
        return {"status": "can-hoi", "branch": branch,
                "reason": f"không gộp được bằng fast-forward: `{current}` đã có commit mà `{branch}` không có "
                          "(worktree tách từ nhánh khác, hay phiên chính đã commit tiếp)"}
    # --no-renames: đổi tên ra khỏi chỗ nhạy cảm cũng là xoá file ở đó, phải hiện cả hai đầu.
    # -z: tên có ", \\, tab hay xuống dòng không bị git bọc ngoặc kép (bọc thì lọt qua bước so tên).
    files = names(git(top, "diff", "-z", "--name-only", "--no-renames", "HEAD", sha).stdout)
    if not files:
        cleanup = [] if args.keep else remove(top, wt, branch)
        return {"status": "rong", "branch": branch, "files": [], "cleanup": cleanup,
                "reason": "nhánh không có thay đổi nào so với nhánh hiện tại"}
    risky = sensitive(files)
    if risky:
        return {"status": "can-hoi", "branch": branch, "files": files, "sensitive": risky,
                "reason": "diff đụng file nhạy cảm (quyền, hook, CI, luật hay kế hoạch cho agent): cần người dùng xem"}
    links = special_modes(top, sha)
    if links:
        return {"status": "can-hoi", "branch": branch, "files": files, "sensitive": links,
                "reason": "nhánh thêm symlink hay submodule: cần người dùng xem"}
    dirty_main = set()
    entries = git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        if len(entry) > 3:
            dirty_main.add(entry[3:])
            if entry[0] in "RC":  # đổi tên, chép: mục kế là tên cũ
                dirty_main.add(entries[i + 1] if i + 1 < len(entries) else "")
                i += 1
        i += 1
    overlap = sorted(dirty_main & set(files))
    if overlap:
        return {"status": "can-hoi", "branch": branch, "files": files, "overlap": overlap,
                "reason": "cây làm việc chính có file chưa commit trùng với file nhánh đổi"}

    try:
        argv = shlex.split(args.test)
    except ValueError as exc:
        return {"status": "loi", "reason": f"lệnh test không đọc được: {exc}"}
    if not argv:
        return {"status": "loi", "reason": "thiếu lệnh test"}
    try:
        code, tail = run_test(argv, wt, args.timeout)
    except OSError as exc:
        return {"status": "test-truot", "branch": branch, "files": files, "reason": f"không chạy được test: {exc}"}
    if code is None:
        return {"status": "test-truot", "branch": branch, "files": files, "test_tail": tail,
                "reason": f"test quá {args.timeout:.0f} giây, đã dừng cả nhóm tiến trình: không gộp"}
    if code != 0:
        return {"status": "test-truot", "branch": branch, "files": files, "test_exit": code,
                "test_tail": tail, "reason": "test trượt trong worktree: không gộp"}
    moved = (git(top, "rev-parse", "--verify", "-q", f"{branch}^{{commit}}").stdout.strip() != sha
             or git(wt, "rev-parse", "HEAD").stdout.strip() != sha)
    if moved:
        return {"status": "can-hoi", "branch": branch, "files": files, "test_tail": tail,
                "reason": "nhánh hay worktree đã đổi commit trong lúc chạy test (mã test tự commit?): không gộp"}

    merged = git(top, "merge", "--ff-only", "-q", sha)
    if merged.returncode != 0:
        return {"status": "can-hoi", "branch": branch, "files": files,
                "reason": f"git merge --ff-only không chạy được: {merged.stderr.strip()[:300]}"}
    cleanup = [] if args.keep else remove(top, wt, branch)
    return {"status": "da-gop", "branch": branch, "into": current, "files": files, "test_tail": tail,
            "cleanup": cleanup, "reason": "test đạt, đã gộp bằng fast-forward"}


def remove(top: Path, wt: Path, branch: str) -> list:
    """Xoá worktree rồi nhánh; trả các bước không làm được (để báo, không coi là lỗi)."""
    problems = []
    out = git(top, "worktree", "remove", str(wt))
    if out.returncode != 0:
        problems.append(f"giữ worktree {wt}: {out.stderr.strip()[:200]}")
        return problems
    out = git(top, "branch", "-d", branch)
    if out.returncode != 0:
        problems.append(f"giữ nhánh {branch}: {out.stderr.strip()[:200]}")
    return problems


LABELS = {"da-gop": "Đã gộp", "rong": "Không có gì để gộp", "can-hoi": "Cần bạn quyết", "test-truot": "Test trượt",
          "loi": "Lỗi"}
CODES = {"da-gop": 0, "rong": 0, "can-hoi": 2, "test-truot": 1, "loi": 1}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gộp nhánh worktree của subagent khi test đạt và fast-forward được.")
    ap.add_argument("--worktree", required=True, help="đường dẫn worktree hay tên nhánh của nó")
    ap.add_argument("--test", required=True, help="lệnh test chạy trong worktree (argv, không qua shell)")
    ap.add_argument("--repo", default=".", help="cây làm việc chính (mặc định thư mục hiện tại)")
    ap.add_argument("--commit", help="commit thay đổi còn lại trong worktree với thông điệp này trước khi gộp")
    ap.add_argument("--keep", action="store_true", help="gộp xong vẫn giữ worktree và nhánh")
    ap.add_argument("--timeout", type=float, default=TEST_TIMEOUT, help="giây tối đa cho lệnh test (mặc định 1800)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        result = run(args)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        result = {"status": "loi", "reason": str(exc)[:400]}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{LABELS[result['status']]}: {result['reason']}")
        if result.get("files"):
            print(f"File ({len(result['files'])}): " + ", ".join(result["files"][:30])
                  + (" …" if len(result["files"]) > 30 else ""))
        for key, label in (("sensitive", "File nhạy cảm"), ("overlap", "Trùng file chưa commit")):
            if result.get(key):
                print(f"{label}: " + ", ".join(result[key]))
        if result.get("test_tail"):
            print("Cuối output test:\n" + result["test_tail"])
        for line in result.get("cleanup") or []:
            print(f"Lưu ý: {line}")
    return CODES[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
