#!/usr/bin/env python3
"""Kích hoạt agent-stack ở mức toàn cục cho Claude Code.

MẶC ĐỊNH CHỈ IN KẾ HOẠCH, không sửa gì. Thêm --apply để thực hiện. Mỗi lần --apply đều
sao lưu cấu hình trước, và ghi nhật ký vào state/install-logs/ để --rollback hoàn tác.

Các bước (chạy theo thứ tự; --only để chọn một phần):
  rules       ~/.claude/CLAUDE.md -> global/CLAUDE.global.md
  plugin      marketplace cục bộ agent-stack-local + plugin agent-stack (scope user)
  statusline  statusLine trong ~/.claude/settings.json (chỉ khi chưa có)
  autocontinue  autoContinueAtUsageLimit = true trong ~/.claude/settings.json (chỉ khi chưa đặt): phiên trong
              terminal tự chờ rồi làm tiếp khi chạm giới hạn 5 giờ
  catalog     cài các mục đã duyệt trong vetted.lock (scope user); mục scope project chỉ in lệnh. MCP từ xa
              (kind mcp-remote): `claude mcp add -s user --transport http`, chỉ khi URL khớp bản đã duyệt và định
              nghĩa tool lấy lại ngay trước khi cài còn khớp hash đã duyệt
  tools       công cụ dòng lệnh mà mục đã duyệt cần (khóa "brew" trong catalog.json), cài bằng Homebrew

Mã thoát: 0 = cài đủ; 1 = có bước lỗi; 2 = không lỗi nhưng có mục bị bỏ qua (cài chưa đủ).
Cài một phần không phải là thành công: phần tổng kết cuối luôn liệt kê mục bị bỏ qua và mục lỗi.

Ghi lại và gỡ sạch: mỗi lần --apply ghi INSTALLED.md (bảng từng thay đổi, nơi sao lưu, lệnh gỡ riêng
từng mục) cùng nhật ký máy đọc trong state/install-logs/. --rollback --apply chạy ngược từng bước,
khôi phục bản sao lưu, xóa thư mục do lần cài tạo ra (kể cả vendor/), dọn enabledPlugins trong
settings.json, rồi so với bản chụp trước khi cài và báo những gì còn khác.

Ví dụ:
  python3 tools/install.py                 # xem trước
  python3 tools/install.py --apply         # thực hiện
  python3 tools/install.py --rollback      # hoàn tác lần --apply gần nhất
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

HOME_STACK = Path(os.environ.get("AGENT_STACK_HOME") or Path(__file__).resolve().parents[1]).resolve()
STEPS = ("rules", "plugin", "statusline", "autocontinue", "catalog", "tools")
MARKETPLACE = "agent-stack-local"
VENDOR_MARKETPLACE = "agent-stack-vendor-local"
VENDOR_PLUGIN = "agent-stack-vendor"
SKIP_IN_VENDOR = {".git", ".vet-complete", ".claude-plugin", ".cursor-plugin", ".codex-plugin"}
SKIP_IN_VENDOR_PLUGIN = {".git", ".vet-complete"}  # plugin cần giữ .claude-plugin/plugin.json
DIGEST_IGNORED = {".in_use", ".orphaned_at", ".git", ".vet-complete"}
PATCH_DIR = "patches"  # bản vá cục bộ đã duyệt cho đồ bên thứ ba (mục local_patches của vetted.lock)
# Mã của vet-skill nằm cạnh file này (không theo AGENT_STACK_HOME, vốn chỉ trỏ dữ liệu: lock, catalog, cache).
VET_SCRIPTS = Path(__file__).resolve().parents[1] / "plugin" / "skills" / "vet-skill" / "scripts"
MCP_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def read_json_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def vetted_checkout_problem(cache: Path, sha: str, subpath: str = ""):
    """Lý do không được chép bản trong .vet-cache, hoặc None. Bản chép phải là checkout git ở đúng commit đã duyệt và
    không bị sửa sau khi vet (ngoài dấu .vet-complete do vet.py ghi): kiểm lệch so với chính .vet-cache nên không bắt
    được việc cache bị sửa, phải chặn ở đây."""
    def git(*args):
        return subprocess.run(["git", "--no-optional-locks", "-C", str(cache), *args], capture_output=True, text=True,
                              timeout=30)
    try:
        head = git("rev-parse", "HEAD")
        status = git("status", "--porcelain", "--untracked-files=all", "--ignored")
        # Sparse checkout của vet.py gắn cờ skip-worktree cho file ngoài thư mục con, nên chỉ xét trong thư mục con.
        flags = git("ls-files", "-v", "--", subpath or ".")
    except (OSError, subprocess.SubprocessError) as exc:
        return f"không kiểm được {cache.name} bằng git ({exc})"
    if head.returncode != 0 or status.returncode != 0 or flags.returncode != 0:
        return f"{cache.name} không phải checkout git"
    if not sha or head.stdout.strip() != sha:
        return f"{cache.name} đang ở {head.stdout.strip()[:12]}, không phải commit đã duyệt {sha[:12]}"
    dirty = [line for line in status.stdout.splitlines() if line.strip() and line[3:] != ".vet-complete"]
    if dirty:
        return f"{cache.name} có {len(dirty)} file đổi sau khi vet ({', '.join(x[3:] for x in dirty[:3])})"
    # Cờ chữ thường (assume-unchanged) hay S (skip-worktree) làm git status không thấy file bị sửa.
    hidden = [line[2:] for line in flags.stdout.splitlines() if line[:1].islower() or line[:1] == "S"]
    if hidden:
        return f"{cache.name} có {len(hidden)} file bị ẩn khỏi git status ({', '.join(hidden[:3])})"
    return None


def export_vetted(cache: Path, sha: str, subpath: str, dest: Path, skip) -> None:
    """Chép vào dest đúng các file git ghi nhận ở commit sha (git archive), nên file bị ignore, bị ẩn hay bị sửa trong
    .vet-cache sau khi vet không lọt vào. Giải nén bằng bộ lọc "data" của tarfile: chặn đường dẫn tuyệt đối, "..",
    và link trỏ ra ngoài."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "vetted.tar"
        with archive.open("wb") as fh:
            subprocess.run(["git", "--no-optional-locks", "-C", str(cache), "archive", "--format=tar", sha, "--",
                            subpath or "."], stdout=fh, stderr=subprocess.PIPE, check=True, timeout=300)
        out = Path(tmp) / "tree"
        with tarfile.open(archive) as tar:
            tar.extractall(out, filter="data")
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(out / subpath if subpath else out, dest, symlinks=True,
                        ignore=lambda d, names: [n for n in names if n in skip])


def tree_digests(root: Path) -> dict:
    """Đường dẫn tương đối → sha256 của mọi file, bỏ dấu vết của Claude Code và git (như kiểm lệch của vet-skill)."""
    out = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and not any(part in DIGEST_IGNORED for part in rel.parts):
            out[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def patches_format_problem(patches) -> str | None:
    """Lý do mục local_patches của vetted.lock sai dạng, hoặc None."""
    def digest(value):
        return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    if not isinstance(patches, list):
        return "local_patches không phải danh sách"
    for patch in patches:
        if not (isinstance(patch, dict) and isinstance(patch.get("path"), str) and digest(patch.get("sha256"))
                and isinstance(patch.get("files"), dict) and patch["files"]
                and all(isinstance(k, str) and k and (v is None or digest(v)) for k, v in patch["files"].items())):
            return "local_patches có bản vá thiếu hay sai path, sha256, files"
    return None


def read_patch(stack: Path, patch: dict):
    """(bytes của file vá, None), hoặc (None, lý do không được áp). File vá phải nằm trong patches/ của agent-stack và
    khớp sha256 bạn đã duyệt. Đọc một lần rồi dùng đúng bytes đó để áp, không đọc lại theo đường dẫn."""
    rel = str(patch.get("path") or "")
    path = (stack / rel).resolve()
    if not rel or (stack / PATCH_DIR).resolve() not in path.parents or not path.is_file():
        return None, f"bản vá {rel or '?'} không phải file trong {PATCH_DIR}/"
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != patch.get("sha256"):
        return None, f"bản vá {rel} khác bản đã duyệt (sha256)"
    return data, None


def patch_file_problem(stack: Path, patch: dict):
    return read_patch(stack, patch)[1]


def patch_shape_problem(data: bytes, cwd: Path, env: dict):
    """Lý do bản vá có thay đổi mà phép so sha256 nội dung không thấy được, hoặc None. Chỉ cho sửa nội dung file văn bản,
    tạo file thường (100644) và xóa file; chặn symlink, đổi quyền, đổi tên, chép, file nhị phân, và đường dẫn có phần
    bị bỏ qua khi băm (DIGEST_IGNORED)."""
    out = subprocess.run(["git", "apply", "--numstat", "--summary", "-"], input=data, cwd=cwd, env=env,
                         capture_output=True, timeout=60)
    if out.returncode != 0:
        return (out.stderr or out.stdout).decode("utf-8", "replace").strip()[:200]
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        cols = line.split("\t")
        if len(cols) == 3:  # numstat: thêm, bớt, đường dẫn; file nhị phân ghi "-"
            if "-" in cols[:2]:
                return f"đụng file nhị phân {cols[2]}"
            if any(part in DIGEST_IGNORED for part in Path(cols[2]).parts):
                return f"đụng đường dẫn không được băm {cols[2]}"
            continue
        line = line.strip()
        if line and not line.startswith(("create mode 100644 ", "delete mode 100644 ", "delete mode 100755 ")):
            return f"có thay đổi không cho phép ({line[:80]})"
    return None


def apply_patches(stack: Path, dest: Path, patches: list):
    """Áp các bản vá đã duyệt vào bản vừa xuất ở dest; trả về lý do lỗi, hoặc None. Tập file bị đổi và sha256 sau khi vá
    phải đúng bằng mục files của bản vá trong lock (đường dẫn → sha256, null là file bị xóa)."""
    # Chặn dò repo ở dest.parent để git apply chạy như patch thường, không đọc cấu hình hay .gitattributes của repo
    # agent-stack bao ngoài. Trong hay ngoài repo, git apply đều từ chối đường dẫn tuyệt đối, ".." và ghi qua symlink
    # (đã thử 10/10/2026); tập file bị đổi còn được so với lock ở dưới.
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    env["GIT_CEILING_DIRECTORIES"] = str(dest.parent.resolve())
    for patch in patches:
        data, problem = read_patch(stack, patch)
        if problem:
            return problem
        shape = patch_shape_problem(data, dest, env)
        if shape:
            return f"không áp bản vá {patch['path']}: {shape}"
        before = tree_digests(dest)
        out = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], input=data, cwd=dest, env=env,
                             capture_output=True, timeout=60)
        if out.returncode != 0:
            err = (out.stderr or out.stdout).decode("utf-8", "replace").strip()[:200]
            return f"không áp được bản vá {patch['path']}: {err}"
        after = tree_digests(dest)
        changed = {k: after.get(k) for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
        if changed != (patch.get("files") or {}):
            return f"bản vá {patch['path']} đổi file khác với bản đã duyệt"
    return None


class Installer:
    def __init__(self, apply: bool, replace_existing: bool, restore_workflow_warning: bool):
        self.apply = apply
        self.replace_existing = replace_existing
        self.restore_workflow_warning = restore_workflow_warning
        self.home = Path.home()
        self.claude_dir = self.home / ".claude"
        self.claude_bin = os.environ.get("AGENT_STACK_CLAUDE_BIN", "claude")
        base, n = time.strftime("%Y%m%d-%H%M%S"), 1
        stamp = base
        # hai lần chạy trong cùng một giây không được dùng chung thư mục sao lưu (bản chụp sẽ bị ghi đè)
        while (HOME_STACK / "backups" / f"install-{stamp}").exists() or \
                list((HOME_STACK / "state" / "install-logs").glob(f"{stamp}.*json")):
            n += 1
            stamp = f"{base}-{n}"
        self.backup_dir = HOME_STACK / "backups" / f"install-{stamp}"
        self.log_path = HOME_STACK / "state" / "install-logs" / f"{stamp}.json"
        self.actions = []
        self.lines = []
        self.skipped = []
        self.failures = []
        self.stamp = stamp
        self.pristine = {}

    # ------------------------------------------------------------ tiện ích

    def say(self, text: str) -> None:
        self.lines.append(text)
        print(text)

    def record(self, **action) -> None:
        self.actions.append(action)

    def ensure_dir(self, path: Path) -> None:
        """Tạo thư mục (cả các cấp cha) và ghi lại từng thư mục mới, để lần gỡ xóa đúng những thư mục đó."""
        missing = []
        for candidate in [path, *path.parents]:
            if candidate.exists():
                break
            missing.append(candidate)
        for directory in reversed(missing):
            directory.mkdir()
            self.record(type="mkdir", path=str(directory))

    def snapshot_pristine(self) -> None:
        """Chụp các file cấu hình mà plugin CLI có thể sửa, trước khi cài, để lần gỡ so lại."""
        targets = {"settings.json": self.claude_dir / "settings.json",
                   "known_marketplaces.json": self.claude_dir / "plugins" / "known_marketplaces.json",
                   "installed_plugins.json": self.claude_dir / "plugins" / "installed_plugins.json"}
        folder = self.backup_dir / "pristine"
        for name, path in targets.items():
            if path.exists():
                folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, folder / name)
                self.pristine[name] = str(folder / name)
            else:
                self.pristine[name] = None
        self.pristine["plugins_listing"] = plugins_listing()

    def backup_target(self, path: Path, suffix: str = "") -> Path:
        """Đường dẫn bản sao lưu chưa dùng. Cùng một file được sao lưu nhiều lần trong một lần cài
        (ví dụ settings.json ở hai bước) thì mỗi bản một tên, để hoàn tác về đúng bản gốc."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        base = str(path.relative_to(self.home)).replace("/", "__")
        n = 1
        while True:
            target = self.backup_dir / (base + (f".{n}" if n > 1 else "") + suffix)
            if not (target.exists() or target.is_symlink()):
                return target
            n += 1

    def backup(self, path: Path):
        """Sao lưu một file (hoặc symlink) trước khi thay; trả về đường dẫn bản sao lưu."""
        if not (path.exists() or path.is_symlink()):
            return None
        if path.is_dir() and not path.is_symlink():
            dest = self.backup_target(path, ".dir")
            shutil.move(str(path), str(dest))
            return str(dest)
        if path.is_symlink():
            dest = self.backup_target(path, ".symlink")
            dest.write_text(os.readlink(path))
            return str(dest)
        dest = self.backup_target(path)
        shutil.copy2(path, dest)
        return str(dest)

    def backup_inside_stack(self, path: Path) -> str:
        """Sao lưu một file nằm trong agent-stack (không nằm dưới HOME như các file khác)."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        dest = self.backup_dir / ("stack__" + str(path.relative_to(HOME_STACK)).replace("/", "__"))
        shutil.copy2(path, dest)
        return str(dest)

    def link(self, src: Path, dest: Path) -> None:
        if dest.is_symlink() and Path(os.readlink(dest)) == src:
            self.say(f"  = đã có: {dest} -> {src}")
            return
        if (dest.exists() or dest.is_symlink()) and not self.replace_existing:
            self.say(f"  ! bỏ qua: {dest} đã tồn tại và không phải của agent-stack (thêm --replace-existing để thay, có sao lưu)")
            self.skipped.append(f"{dest}: đã có file không phải của agent-stack")
            return
        new_dir = "" if dest.parent.exists() else f" (tạo thư mục {dest.parent})"
        self.say(f"  + symlink: {dest} -> {src}{new_dir}")
        if not self.apply:
            return
        previous = self.backup(dest)  # thư mục thật thì được chuyển hẳn vào bản sao lưu
        self.ensure_dir(dest.parent)
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        dest.symlink_to(src)
        self.record(type="symlink", path=str(dest), src=str(src), backup=previous)

    def run(self, args: list, undo: list = None, ok_if: str = "") -> None:
        self.say(f"  $ {' '.join(args)}")
        if not self.apply:
            return
        try:
            out = subprocess.run(args, capture_output=True, text=True)
        except OSError as exc:
            self.say(f"    lỗi: {exc}")
            self.failures.append(f"{' '.join(args[:4])}: {exc}")
            return
        text = (out.stdout + out.stderr).strip()
        unchanged = bool(ok_if) and ok_if in text.lower()
        if out.returncode != 0 and not unchanged:
            self.say(f"    lỗi ({out.returncode}): {text[:300]}")
            self.failures.append(f"{' '.join(args[:4])}: mã {out.returncode}: {text[:160]}")
            return
        if unchanged:
            self.say("    = đã có, không đổi")  # không ghi vào nhật ký: lần gỡ không được gỡ thứ lần này không cài
            return
        self.record(type="cmd", cmd=args, undo=undo)

    def edit_settings(self, mutate) -> None:
        path = self.claude_dir / "settings.json"
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                self.say(f"  ! không đọc được {path}: {exc}. Không sửa file này.")
                self.failures.append(f"{path}: JSON không hợp lệ")
                return
        before = json.loads(json.dumps(data))
        mutate(data)
        if json.dumps(data, sort_keys=True) == json.dumps(before, sort_keys=True):
            return
        if not self.apply:
            return
        keys = sorted(k for k in set(before) | set(data) if before.get(k) != data.get(k))
        previous = self.backup(path)
        self.ensure_dir(path.parent)
        tmp = path.with_suffix(".agent-stack.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        self.record(type="file", path=str(path), backup=previous, keys=keys)

    # ------------------------------------------------------------ các bước

    def step_rules(self) -> None:
        self.say("[rules] luật chung cho Claude Code")
        self.link(HOME_STACK / "global" / "CLAUDE.global.md", self.claude_dir / "CLAUDE.md")

    def step_plugin(self) -> None:
        self.say("[plugin] marketplace cục bộ và plugin agent-stack")
        # Claude Code chép plugin vào cache khi cài; file trỏ này đi theo bản chép để hook tìm về repo
        # (state/, vetted.lock, catalog.json). Không đưa vào git.
        pointer = HOME_STACK / "plugin" / ".agent-stack-home"
        if not (pointer.exists() and pointer.read_text(encoding="utf-8").strip() == str(HOME_STACK)):
            self.say(f"  + {short(str(pointer))} = {short(str(HOME_STACK))}")
            if self.apply:
                existed = pointer.exists()
                previous = self.backup_inside_stack(pointer) if existed else None
                pointer.write_text(str(HOME_STACK) + "\n", encoding="utf-8")
                self.record(type="file", path=str(pointer), backup=previous, keys=["đường dẫn repo"])
        self.run([self.claude_bin, "plugin", "marketplace", "add", str(HOME_STACK)],
                 undo=[self.claude_bin, "plugin", "marketplace", "remove", MARKETPLACE], ok_if="already")
        self.run([self.claude_bin, "plugin", "install", f"agent-stack@{MARKETPLACE}", "--scope", "user"],
                 undo=[self.claude_bin, "plugin", "uninstall", f"agent-stack@{MARKETPLACE}", "--scope", "user"],
                 ok_if="already")
        # đã cài từ trước thì install không chép lại: cập nhật để bản chép khớp với code trong repo
        self.run([self.claude_bin, "plugin", "update", f"agent-stack@{MARKETPLACE}", "--scope", "user"],
                 ok_if="latest")

    def step_statusline(self) -> None:
        self.say("[statusline] model · effort · ctx · 5h · 7d")
        command = f"python3 {HOME_STACK / 'statusline' / 'statusline.py'}"

        def mutate(data):
            if "statusLine" in data:
                self.say(f"  = đã có statusLine, giữ nguyên: {json.dumps(data['statusLine'])[:120]}")
            else:
                self.say(f"  + statusLine = {command}")
                data["statusLine"] = {"type": "command", "command": command}
            if self.restore_workflow_warning and data.get("skipWorkflowUsageWarning"):
                self.say("  + bỏ skipWorkflowUsageWarning (bật lại cảnh báo usage của workflow)")
                data.pop("skipWorkflowUsageWarning")
        self.edit_settings(mutate)

    def step_autocontinue(self) -> None:
        self.say("[autocontinue] tự chờ rồi làm tiếp khi chạm giới hạn 5 giờ (autoContinueAtUsageLimit)")

        def mutate(data):
            if "autoContinueAtUsageLimit" in data:
                self.say(f"  = đã đặt autoContinueAtUsageLimit = {json.dumps(data['autoContinueAtUsageLimit'])}, giữ nguyên")
            else:
                self.say("  + autoContinueAtUsageLimit = true")
                data["autoContinueAtUsageLimit"] = True
        self.edit_settings(mutate)

    def approved(self) -> dict:
        lock = json.loads((HOME_STACK / "vetted.lock").read_text(encoding="utf-8"))["entries"]
        return {k: v for k, v in lock.items() if (v.get("human_review") or {}).get("status") == "approved"}

    def step_catalog(self) -> None:
        self.say("[catalog] các mục đã duyệt trong vetted.lock")
        catalog = json.loads((HOME_STACK / "catalog.json").read_text(encoding="utf-8"))
        approved = self.approved()
        added_marketplaces = set()
        vendored = []
        for item in catalog["items"]:
            key, inst = item["key"], item["install"]
            entry = approved.get(key)
            if not entry:
                self.say(f"  · chờ duyệt: {key}")
                continue
            if entry["verdict"] == "FAIL":
                self.say(f"  ! bỏ qua (FAIL): {key}")
                continue
            if item["kind"] == "mcp-remote":
                self.install_mcp(item, entry)
                continue
            if item["kind"] in ("vendor-skill", "vendor-plugin"):
                vendored.append((item, entry))
                continue
            plugin_id = f"{inst['plugin']}@{inst['marketplace']}"
            if item["scope"] != "user":
                prefix = f"claude plugin marketplace add {inst['marketplace_repo']} && " if inst.get("marketplace_repo") else ""
                self.say(f"  · {item['scope']}: tự cài khi cần, trong project: {prefix}claude plugin install {plugin_id} --scope project")
                continue
            if inst.get("marketplace_repo") and inst["marketplace"] not in added_marketplaces:
                self.run([self.claude_bin, "plugin", "marketplace", "add", inst["marketplace_repo"]],
                         undo=[self.claude_bin, "plugin", "marketplace", "remove", inst["marketplace"]], ok_if="already")
                added_marketplaces.add(inst["marketplace"])
            self.run([self.claude_bin, "plugin", "install", plugin_id, "--scope", "user"],
                     undo=[self.claude_bin, "plugin", "uninstall", plugin_id, "--scope", "user"], ok_if="already")
        if vendored:
            self.vendor(vendored)

    def install_mcp(self, item: dict, entry: dict) -> None:
        """MCP từ xa: chỉ cài đúng URL đã duyệt, không đè server cùng tên, và chỉ khi định nghĩa tool lấy lại
        ngay lúc cài còn khớp hash đã duyệt (server có thể đổi tool sau khi bạn duyệt)."""
        if str(VET_SCRIPTS) not in sys.path:
            sys.path.insert(0, str(VET_SCRIPTS))
        import mcp_remote
        inst = item.get("install") if isinstance(item.get("install"), dict) else {}
        name, url = str(inst.get("name", "")), str(inst.get("url", ""))
        if not MCP_NAME_RE.match(name) or not mcp_remote.URL_RE.match(url):
            self.say(f"  ! bỏ qua {item['key']}: tên hay URL của MCP sai dạng trong catalog.json")
            self.failures.append(f"{item['key']}: tên hay URL MCP sai dạng")
            return
        if entry.get("kind") != "mcp-remote" or entry.get("source") != "mcp:" + url:
            self.say(f"  ! bỏ qua {item['key']}: URL trong catalog.json khác URL đã duyệt trong vetted.lock")
            self.failures.append(f"{item['key']}: URL MCP khác bản đã duyệt")
            return
        if item["scope"] == "skill":
            self.say(f"  · skill: MCP {name} không cài vào Claude Code, gọi qua skill goi-mcp khi việc cần")
            return
        if item["scope"] != "user":
            self.say(f"  · {item['scope']}: tự cài khi cần, trong project: claude mcp add -s project --transport http {name} {url}")
            return
        have = mcp_remote.user_servers(mcp_remote.claude_json_path(self.home)).get(name)
        if have is not None:
            if isinstance(have, dict) and have.get("url") == url:
                self.say(f"  = đã có MCP {name}: {url}")
            else:
                self.say(f"  ! bỏ qua MCP {name}: ~/.claude.json đã có server cùng tên trỏ chỗ khác, không ghi đè")
                self.skipped.append(f"MCP {name}: trùng tên với server sẵn có")
            return
        if not self.apply:
            self.say(f"  · trước khi cài sẽ lấy lại định nghĩa tool của {url}, chỉ cài khi khớp hash đã duyệt "
                     f"{entry.get('sha', '')[:12]}")
        else:
            try:
                live = mcp_remote.digests(mcp_remote.fetch_snapshot(url))
            except Exception as exc:  # noqa: BLE001 - không kiểm được thì không cài, và không làm sập lần cài
                self.say(f"  ! không cài MCP {name}: không lấy được định nghĩa tool để so "
                         f"({mcp_remote.clean(str(exc) or type(exc).__name__, 160)})")
                self.failures.append(f"{item['key']}: không kiểm được định nghĩa tool")
                return
            if live["sha"] != entry.get("sha"):
                change = mcp_remote.diff(entry, live)
                detail = "; ".join(f"{label} {', '.join(mcp_remote.clean(x, 40) for x in change[k])}"
                                   for k, label in (("changed", "đổi"), ("added", "thêm"), ("removed", "mất")) if change[k])
                self.say(f"  ! không cài MCP {name}: định nghĩa tool khác bản đã duyệt ({detail or 'hash khác'}); "
                         f"chạy lại vet.py scan {url}, đọc báo cáo rồi duyệt lại")
                self.failures.append(f"{item['key']}: định nghĩa tool đổi sau khi duyệt")
                return
            self.say(f"  ✓ định nghĩa tool của {name} khớp bản đã duyệt {entry['sha'][:12]}")
        self.run([self.claude_bin, "mcp", "add", "-s", "user", "--transport", "http", name, url],
                 undo=[self.claude_bin, "mcp", "remove", "-s", "user", name])

    def vendor(self, vendored: list) -> None:
        """Chép đúng commit đã kiểm vào vendor/: skill chỉ-có-chỉ-dẫn vào vendor/skills (gộp thành plugin
        agent-stack-vendor), plugin bên thứ ba nguyên thư mục vào vendor/plugins/<tên>. vendor/ là marketplace riêng,
        nên bản cài luôn là bản đã kiểm (không theo HEAD của repo gốc), và gỡ thì xóa được cả thư mục mà không đụng
        file nào trong git. Plugin scope project chỉ được chép sẵn; người dùng tự cài trong project cần dùng."""
        vendor_root = HOME_STACK / "vendor"
        record, skills, plugins, exports, patch_lists = {}, [], [], {}, {}
        for item, entry in vendored:
            is_plugin = item["kind"] == "vendor-plugin"
            name = item["install"]["plugin" if is_plugin else "name"]
            cache = HOME_STACK / ".vet-cache" / Path(entry["report"]).stem
            src = cache / entry["subpath"] if entry.get("subpath") else cache
            if not is_plugin and item["scope"] != "user":
                self.say(f"  · {item['scope']}: {name} không chép mặc định; khi cần, đổi scope trong catalog.json thành user rồi chạy lại")
                continue
            if not (src / (".claude-plugin/plugin.json" if is_plugin else "SKILL.md")).exists():
                self.say(f"  ! thiếu bản đã kiểm trong cache cho {name}: chạy lại vet.py scan {item['key']}")
                self.failures.append(f"{item['key']}: đã duyệt nhưng thiếu bản đã kiểm trong .vet-cache")
                continue
            problem = vetted_checkout_problem(cache, entry.get("sha", ""), entry.get("subpath") or "")
            if problem:
                self.say(f"  ! không chép {name}: {problem}; xóa thư mục đó rồi chạy lại vet.py scan {item['key']}")
                self.failures.append(f"{item['key']}: {problem}")
                continue
            patches = entry.get("local_patches") or []
            problem = patches_format_problem(patches) or next(
                (x for x in (patch_file_problem(HOME_STACK, p) for p in patches) if x), None)
            if problem:
                self.say(f"  ! không chép {name}: {problem}")
                self.failures.append(f"{item['key']}: {problem}")
                continue
            dest = f"plugins/{name}" if is_plugin else f"skills/{name}"
            patched = "".join(f" + vá {p['path']} (sha256 {p['sha256'][:12]}, đổi {', '.join(sorted(p['files']))})"
                              for p in patches)
            self.say(f"  + vendor: {name} @ {entry['sha'][:12]}{patched} -> vendor/{dest}")
            record[name] = {"key": item["key"], "sha": entry["sha"], "kind": item["kind"]}
            if patches:
                record[name]["patches"] = [p["path"] for p in patches]
            exports[name] = (cache, entry["sha"], entry.get("subpath") or "")
            patch_lists[name] = patches
            (plugins if is_plugin else skills).append((name, src, item["scope"]))
        if not record:
            return
        if self.apply:
            existed = vendor_root.exists()
            if existed and not (vendor_root / "VENDORED.json").exists():
                self.say(f"  ! {vendor_root} đã có và không phải do agent-stack tạo; không ghi đè")
                self.failures.append(f"{vendor_root}: thư mục lạ")
                return
            if not existed:
                vendor_root.mkdir()
                # Đánh dấu ngay là của agent-stack: mọi mục đều hỏng thì lần chạy sau không coi đây là thư mục lạ.
                (vendor_root / "VENDORED.json").write_text("{}\n")
                self.record(type="vendor-dir", path=str(vendor_root))
            for group, items, skip in (("skills", skills, SKIP_IN_VENDOR), ("plugins", plugins, SKIP_IN_VENDOR_PLUGIN)):
                for name, src, _ in items:
                    meta_src = exports[name]
                    try:
                        export_vetted(*meta_src, vendor_root / group / name, skip)
                        problem = apply_patches(HOME_STACK, vendor_root / group / name, patch_lists[name])
                    except (OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
                        shutil.rmtree(vendor_root / group / name, ignore_errors=True)
                        self.say(f"  ! không chép được {name} từ commit đã duyệt: {exc}")
                        self.failures.append(f"{record.pop(name)['key']}: không xuất được bản đã duyệt ({exc})")
                        continue
                    if problem:
                        # Bản chưa vá hay vá sai không được nằm lại trong vendor/, kẻo lần sau bị cài nhầm.
                        shutil.rmtree(vendor_root / group / name, ignore_errors=True)
                        self.say(f"  ! không chép {name}: {problem}")
                        self.failures.append(f"{record.pop(name)['key']}: {problem}")
            skills = [x for x in skills if x[0] in record]
            plugins = [x for x in plugins if x[0] in record]
            if not record:
                return
            meta = vendor_root / ".claude-plugin"
            meta.mkdir(exist_ok=True)
            listed = []
            if skills:
                (meta / "plugin.json").write_text(json.dumps({
                    "name": VENDOR_PLUGIN, "version": time.strftime("%Y.%m.%d"),
                    "description": "Skill của bên thứ ba, chép đúng commit đã kiểm duyệt bằng vet-skill.",
                    "author": {"name": "tdHuy22"}}, ensure_ascii=False, indent=2) + "\n")
                listed.append({"name": VENDOR_PLUGIN, "source": "./",
                               "description": "Skill của bên thứ ba đã kiểm duyệt, ghim commit."})
            listed += [{"name": name, "source": f"./plugins/{name}",
                        "description": f"Plugin bên thứ ba, ghim commit đã kiểm {record[name]['sha'][:12]}."}
                       for name, _, _ in plugins]
            (meta / "marketplace.json").write_text(json.dumps({
                "name": VENDOR_MARKETPLACE, "owner": {"name": "tdHuy22"},
                "description": "Marketplace cục bộ cho skill và plugin bên thứ ba đã kiểm duyệt (do install.py tạo).",
                "plugins": listed}, ensure_ascii=False, indent=2) + "\n")
            (vendor_root / "VENDORED.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        self.run([self.claude_bin, "plugin", "marketplace", "add", str(vendor_root)],
                 undo=[self.claude_bin, "plugin", "marketplace", "remove", VENDOR_MARKETPLACE], ok_if="already")
        installs = ([VENDOR_PLUGIN] if skills else []) + [name for name, _, scope in plugins if scope == "user"]
        for name in installs:
            pid = f"{name}@{VENDOR_MARKETPLACE}"
            self.run([self.claude_bin, "plugin", "install", pid, "--scope", "user"],
                     undo=[self.claude_bin, "plugin", "uninstall", pid, "--scope", "user"], ok_if="already")
            # Xem trước thì chưa có bản đã vá để so, nên plugin có bản vá chỉ được so khi chạy thật.
            if name != VENDOR_PLUGIN and (self.apply or not patch_lists.get(name)) and self.stale_install(
                    pid, vendor_root / "plugins" / name if self.apply else next(src for n, src, _ in plugins if n == name)):
                # `claude plugin update` báo "đã là bản mới nhất" khi version không đổi (đã thử 09/10/2026), nên sau
                # khi vet lại ở commit mới phải gỡ rồi cài lại để bản trong cache khớp bản đã duyệt.
                self.say(f"  ~ {pid}: bản đã cài khác bản đã duyệt, cài lại")
                self.run([self.claude_bin, "plugin", "uninstall", pid, "--scope", "user"],
                         undo=[self.claude_bin, "plugin", "install", pid, "--scope", "user"])
                self.run([self.claude_bin, "plugin", "install", pid, "--scope", "user"],
                         undo=[self.claude_bin, "plugin", "uninstall", pid, "--scope", "user"])
        for name, _, scope in plugins:
            if scope != "user":
                self.say(f"  · {scope}: {name} đã ghim trong vendor/; trong project cần dùng: "
                         f"claude plugin install {name}@{VENDOR_MARKETPLACE} --scope project")

    def stale_install(self, pid: str, expected: Path) -> bool:
        """Bản cài của pid (installPath trong installed_plugins.json) khác nội dung expected. Không đọc được thì False."""
        entries = (read_json_file(self.claude_dir / "plugins" / "installed_plugins.json").get("plugins") or {}).get(pid) or []
        paths = [Path(e["installPath"]) for e in entries if isinstance(e, dict) and e.get("installPath")]
        return any(path.is_dir() and expected.is_dir() and tree_digests(path) != tree_digests(expected) for path in paths)

    def step_tools(self) -> None:
        """Công cụ dòng lệnh cho các mục đã duyệt (khóa "brew" của mục trong catalog.json), kể cả mục scope project:
        plugin cài theo project vẫn cần công cụ trên máy. Đã có trên PATH thì bỏ qua."""
        self.say("[tools] công cụ dòng lệnh cho các mục đã duyệt")
        catalog = json.loads((HOME_STACK / "catalog.json").read_text(encoding="utf-8"))
        approved = self.approved()
        wanted = {}
        for item in catalog["items"]:
            entry = approved.get(item["key"])
            if entry and entry.get("verdict") != "FAIL":
                for name in item.get("brew") or []:
                    wanted.setdefault(name, item["key"])
        if not wanted:
            self.say("  = không mục nào cần công cụ ngoài")
            return
        brew = os.environ.get("AGENT_STACK_BREW_BIN") or shutil.which("brew")
        for name, key in wanted.items():
            if shutil.which(name):
                self.say(f"  = {name} đã có ({shutil.which(name)})")
                continue
            if not brew:
                self.say(f"  ! không có Homebrew nên không cài được {name} (cho {key})")
                self.skipped.append(f"{name}: cần Homebrew")
                continue
            self.run([brew, "install", name], undo=[brew, "uninstall", name])

    # ------------------------------------------------------------ chạy

    def run_steps(self, steps) -> int:
        mode = "THỰC HIỆN" if self.apply else "XEM TRƯỚC (chưa sửa gì; thêm --apply để thực hiện)"
        self.say(f"agent-stack install · {mode}")
        if self.apply:
            self.snapshot_pristine()
        for step in steps:
            getattr(self, f"step_{step}")()
        code = self.summary()
        if self.apply and not self.actions and self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)  # không thay đổi gì: không để lại bản chụp thừa
        if self.apply and self.actions:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text(json.dumps({"created": time.time(), "backup_dir": str(self.backup_dir),
                                                 "pristine": self.pristine,
                                                 "steps": list(steps), "actions": self.actions,
                                                 "skipped": self.skipped, "failures": self.failures},
                                                ensure_ascii=False, indent=2) + "\n")
            manifest = write_manifest()
            self.say(f"Đã ghi lại: {manifest} (dễ đọc) và {self.log_path} (máy đọc).")
            self.say("Gỡ toàn bộ: ./install.sh --rollback --apply (xem trước: ./install.sh --rollback)")
        return code

    def summary(self) -> int:
        """In tổng kết. Cài một phần không được trông như thành công."""
        planned = sum(1 for line in self.lines if line.startswith(("  + ", "  $ ")))
        done = f"{len(self.actions)} thay đổi đã làm" if self.apply else f"{planned} thay đổi sẽ làm"
        self.say(f"Tổng kết: {done}, {len(self.skipped)} mục bị bỏ qua, {len(self.failures)} lỗi.")
        for item in self.skipped:
            self.say(f"  - bỏ qua: {item}")
        for item in self.failures:
            self.say(f"  - lỗi: {item}")
        if self.failures:
            self.say("⚠️ Có lỗi: phần cài chưa hoàn tất. Sửa lỗi rồi chạy lại; các bước đã xong sẽ không bị làm lại.")
            return 1
        if self.skipped:
            self.say("⚠️ Cài chưa đủ: các mục bị bỏ qua ở trên chưa được kích hoạt.")
            return 2
        return 0


# ------------------------------------------------------------ ghi lại và gỡ

def short(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def describe_action(action: dict) -> tuple:
    """(loại, ở đâu, chi tiết, cách gỡ riêng mục này) cho một dòng trong INSTALLED.md."""
    kind = action["type"]
    if kind == "symlink":
        undo = f"`rm {short(action['path'])}`" + (f", rồi khôi phục `{short(action['backup'])}`" if action.get("backup") else "")
        return "symlink", short(action["path"]), f"→ `{short(action['src'])}`", undo
    if kind == "file":
        keys = ", ".join(f"`{k}`" for k in action.get("keys") or []) or "?"
        undo = (f"chép lại từ `{short(action['backup'])}`" if action.get("backup")
                else f"`rm {short(action['path'])}` (trước khi cài chưa có file này)")
        return "sửa file", short(action["path"]), f"khóa {keys}", undo
    if kind == "mkdir":
        return "thư mục mới", short(action["path"]), "", f"`rmdir {short(action['path'])}` (khi đã trống)"
    if kind == "vendor-dir":
        return "thư mục mới", short(action["path"]), "skill và plugin bên thứ ba, ghim commit (xem `VENDORED.json`)", \
            f"`rm -rf {short(action['path'])}`"
    if kind == "cmd":
        undo = f"`{cmd_text(action['undo'])}`" if action.get("undo") else "—"
        label = "lệnh claude" if is_claude(action["cmd"]) else "lệnh " + Path(action["cmd"][0]).name
        return label, f"`{cmd_text(action['cmd'])}`", "", undo
    return kind, short(action.get("path", "")), "", "—"


def is_claude(cmd: list) -> bool:
    return Path(cmd[0]).name in ("claude", Path(os.environ.get("AGENT_STACK_CLAUDE_BIN", "claude")).name)


def cmd_text(cmd: list) -> str:
    """Lệnh để in ra: `claude ...` cho CLI của Claude (kể cả bản giả trong test), tên chương trình cho lệnh khác."""
    return ("claude" if is_claude(cmd) else Path(cmd[0]).name) + " " + " ".join(cmd[1:])


def git_head() -> str:
    try:
        out = subprocess.run(["git", "--no-optional-locks", "-C", str(HOME_STACK), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "?"
    except (OSError, subprocess.TimeoutExpired):
        return "?"


LOG_DIR = HOME_STACK / "state" / "install-logs"


def load_log(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("created", path.stat().st_mtime)
    return data


def active_logs() -> list:
    """Các lần cài còn hiệu lực (chưa gỡ), cũ nhất trước. Sắp theo thời điểm ghi trong nhật ký,
    không theo tên file, vì `…-2.json` đứng trước `….json` khi so tên."""
    logs = [p for p in LOG_DIR.glob("*.json") if not p.name.endswith(".rolled-back.json") and p.name != "last-rollback.json"]
    return sorted(logs, key=lambda p: (load_log(p)["created"], p.name))


def when(ts: float) -> str:
    return time.strftime("%H:%M %d/%m/%Y", time.localtime(ts))


def write_manifest() -> Path:
    """INSTALLED.md: bản ghi dễ đọc của mọi lần cài còn hiệu lực, cách gỡ từng mục và gỡ toàn bộ,
    cộng kết quả lần gỡ gần nhất. Dựng lại từ nhật ký mỗi lần cài hoặc gỡ."""
    logs = active_logs()
    last = read_last_rollback()
    path = HOME_STACK / "INSTALLED.md"
    if not logs:
        L = ["# Hiện không có gì được cài", "", "*File này do `tools/install.py` tạo; đừng sửa tay.*", ""]
        if last:
            L += [f"Lần gỡ gần nhất: {when(last['ts'])}, kết quả: {last['result']}."]
            L += [f"- Lỗi: {e}" for e in last.get("errors") or []] + [f"- Còn khác: {n}" for n in last.get("notes") or []]
            L += ["", "Các lần cài đã gỡ: " + ", ".join(f"`{x}`" for x in last.get("logs") or []) + "."]
        path.write_text("\n".join(L) + "\n", encoding="utf-8")
        return path
    L = ["# Đã cài gì", "",
         f"*Cập nhật {time.strftime('%H:%M %d/%m/%Y')} từ commit `{git_head()}` của agent-stack. "
         "File này do `tools/install.py` tạo; đừng sửa tay. Mỗi lần cài là một mục bên dưới, cũ nhất trước.*", ""]
    if last:
        L += [f"*Lần gỡ gần nhất: {when(last['ts'])}, kết quả: {last['result']}.*", ""]
    for log in logs:
        data = load_log(log)
        rows = [describe_action(a) for a in data["actions"]]
        L += [f"## Lần cài {when(data['created'])}", "",
              f"- Nhật ký máy đọc: `state/install-logs/{log.name}`",
              f"- Sao lưu: `{short(data['backup_dir'])}`, gồm bản chụp `pristine/` của cấu hình trước khi cài",
              f"- Bước đã chạy: {', '.join(data.get('steps') or [])}",
              f"- Kết quả: {len(rows)} thay đổi, {len(data.get('skipped') or [])} mục bị bỏ qua, "
              f"{len(data.get('failures') or [])} lỗi", "",
              "| # | Loại | Ở đâu | Chi tiết | Gỡ riêng mục này |", "|---:|---|---|---|---|"]
        L += [f"| {i} | {k} | {w} | {d} | {u} |" for i, (k, w, d, u) in enumerate(rows, 1)]
        if data.get("skipped") or data.get("failures"):
            L += ["", "Chưa cài được:"] + [f"- Bỏ qua: {x}" for x in data.get("skipped") or []] \
                + [f"- Lỗi: {x}" for x in data.get("failures") or []]
        L.append("")
    L += ["## Gỡ toàn bộ", "", "```bash", "./install.sh --rollback          # xem trước, không sửa gì",
          "./install.sh --rollback --apply  # gỡ thật mọi lần cài ở trên, mới nhất trước", "```", "",
          "Lệnh gỡ chạy ngược từng bảng ở trên:",
          "- gỡ plugin và marketplace bằng `claude plugin`;",
          "- gỡ các symlink;",
          "- khôi phục file từ bản sao lưu;",
          "- xóa thư mục do lần cài tạo ra, kể cả `vendor/`;",
          "- dọn `enabledPlugins` và `extraKnownMarketplaces` trong `~/.claude/settings.json`;",
          "- dọn cache và dữ liệu của đúng các plugin đã cài trong `~/.claude/plugins/`;",
          "- so với bản chụp trước lần cài đầu tiên và báo những gì còn khác.", "",
          "Muốn gỡ riêng một lần cài: `./install.sh --rollback state/install-logs/<tên>.json --apply`.", "",
          "## Không thuộc lần cài (lần gỡ không đụng tới)", "",
          "- Quyết định duyệt trong `vetted.lock` và báo cáo trong `vet-reports/`: đây là hồ sơ kiểm duyệt.",
          "- `state/`, `.vet-cache/` và các thư mục `backups/install-*`: xóa tay khi không cần nữa.",
          "- Công cụ bạn tự cài bằng brew (gitleaks, osv-scanner, pyright…): gỡ bằng `brew uninstall <tên>`.",
          "- Cấu hình bạn tự sửa sau khi cài."]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


def read_last_rollback():
    return read_json_file(LOG_DIR / "last-rollback.json")


def read_json_file(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def plugins_listing() -> list:
    """Những gì đang có trong ~/.claude/plugins: mục cấp đầu, cộng các mục trong cache/ và data/."""
    root = Path.home() / ".claude" / "plugins"
    if not root.exists():
        return []
    out = [p.name for p in root.iterdir()]
    for sub in ("cache", "data"):
        if (root / sub).is_dir():
            out += [f"{sub}/{p.name}" for p in (root / sub).iterdir()]
    return sorted(out)


def plugin_data_dir(pid: str) -> str:
    """Tên thư mục dữ liệu của plugin: mọi ký tự không phải chữ, số, _ hay - đổi thành - (theo docs)."""
    return "".join(c if c.isalnum() or c in "_-" else "-" for c in pid)


def clean_plugin_leftovers(ids: list, marketplaces: list, listing, apply: bool) -> list:
    """Sau khi claude plugin uninstall và marketplace remove: dọn phần Claude Code để lại, nhưng chỉ
    phần ứng với đúng plugin và marketplace mà lần cài đã thêm; rồi báo những gì còn mới so với trước khi cài.
    listing = danh sách plugins_listing() chụp trước khi cài (None nếu không có bản chụp)."""
    root = Path.home() / ".claude" / "plugins"
    if not root.exists():
        return []
    ours = []
    for mp in marketplaces:
        ours.append(root / "cache" / mp)
    for pid in ids:
        name, _, mp = pid.partition("@")
        # desktop app nạp plugin dạng inline: thư mục dữ liệu khi đó là <tên>-inline
        ours += [root / "cache" / mp / name, root / "data" / plugin_data_dir(pid), root / "data" / f"{name}-inline"]
    if apply:
        for path in ours:
            if path.is_dir() and root in path.resolve().parents:
                shutil.rmtree(path)
        for name in ("installed_plugins.json", "known_marketplaces.json"):
            path = root / name
            data = read_json_file(path) if path.exists() else None
            empty = data in ({}, []) or (isinstance(data, dict) and set(data) <= {"version", "plugins"}
                                         and not data.get("plugins"))
            if listing is not None and name not in listing and empty:
                path.unlink()  # trước khi cài chưa có, giờ cũng không còn gì: xóa cho sạch
        for sub in ("cache/claude-plugins-official", "cache", "data"):
            path = root / sub
            if listing is not None and path.is_dir() and not any(path.iterdir()) and sub not in listing:
                path.rmdir()
        if listing is not None and not listing and root.is_dir() and not any(root.iterdir()):
            root.rmdir()
    if listing is None:
        return []
    left = sorted(set(plugins_listing()) - set(listing))
    return ["~/.claude/plugins còn mục mới so với trước khi cài: " + ", ".join(left)] if left else []


def installed_plugin_ids(actions: list) -> list:
    return [a["cmd"][3] for a in actions if a["type"] == "cmd" and a["cmd"][1:3] == ["plugin", "install"]]


def installed_marketplaces(actions: list) -> list:
    return [a["undo"][-1] for a in actions
            if a["type"] == "cmd" and a["cmd"][1:4] == ["plugin", "marketplace", "add"] and a.get("undo")]


def cleanup_enabled_plugins(data: dict, apply: bool) -> None:
    """Bỏ khỏi settings.json những gì lệnh claude plugin của lần cài này đã thêm: enabledPlugins (install)
    và extraKnownMarketplaces (marketplace add với thư mục cục bộ). Lệnh gỡ của claude có thể để lại {}."""
    settings = Path.home() / ".claude" / "settings.json"
    snap = (data.get("pristine") or {}).get("settings.json")
    before = (read_json_file(Path(snap)) if snap else None) or {}
    current = read_json_file(settings) if settings.exists() else None
    if not isinstance(current, dict):
        return
    changed = False
    for key, names in (("enabledPlugins", installed_plugin_ids(data["actions"])),
                       ("extraKnownMarketplaces", installed_marketplaces(data["actions"]))):
        entries = current.get(key)
        if not isinstance(entries, dict):
            continue
        for name in names:
            if name in entries and name not in (before.get(key) or {}):
                entries.pop(name)
                changed = True
        if not entries and key not in before:
            current.pop(key)
            changed = True
    if changed and apply:
        keep = HOME_STACK / "backups" / f"rollback-{time.strftime('%Y%m%d-%H%M%S')}"
        keep.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings, keep / f"settings-{int(time.time() * 1000)}.json")
        settings.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compare_with_pristine(pristine: dict, marketplaces: list, apply: bool) -> list:
    """So cấu hình hiện tại với bản chụp trước lần cài đầu tiên. Trả về các khác biệt còn lại."""
    notes = []
    home = Path.home() / ".claude"
    settings, snap = home / "settings.json", (pristine or {}).get("settings.json")
    current = read_json_file(settings) if settings.exists() else None
    if current is not None:
        if not snap and current == {}:
            if apply:
                settings.unlink()  # trước khi cài chưa có file này, giờ cũng trống: xóa cho sạch
        elif snap:
            before = read_json_file(Path(snap)) or {}
            diff = sorted(k for k in set(current) | set(before) if current.get(k) != before.get(k))
            if diff:
                notes.append("~/.claude/settings.json còn khác bản trước khi cài ở khóa: " + ", ".join(diff))
    known = read_json_file(home / "plugins" / "known_marketplaces.json")
    if isinstance(known, dict):
        left = sorted(set(marketplaces) & set(known))
        if left:
            notes.append("marketplace vẫn còn đăng ký: " + ", ".join(left))
    return notes


def undo_actions(data: dict, apply: bool) -> tuple:
    """Chạy ngược các thao tác của một lần cài. Trả về (lỗi, ghi chú)."""
    errors, notes = [], []
    for action in reversed(data["actions"]):
        kind = action["type"]
        if kind == "symlink":
            path = Path(action["path"])
            print(f"  - gỡ symlink {short(str(path))}" + (f", khôi phục {short(action['backup'])}" if action.get("backup") else ""))
            if not apply:
                continue
            if path.is_symlink() and os.readlink(path) == action["src"]:
                path.unlink()
                backup = action.get("backup")
                if backup and backup.endswith(".symlink"):
                    path.symlink_to(Path(backup).read_text())
                elif backup and backup.endswith(".dir"):
                    shutil.move(backup, str(path))
                elif backup:
                    shutil.copy2(backup, path)
            elif path.exists() or path.is_symlink():
                errors.append(f"{short(str(path))} đã bị thay sau khi cài; không đụng tới")
        elif kind == "file":
            print(f"  - khôi phục {short(action['path'])}" + ("" if action.get("backup") else " (xóa vì trước đó chưa có)"))
            if apply:
                if action.get("backup"):
                    shutil.copy2(action["backup"], action["path"])
                else:
                    Path(action["path"]).unlink(missing_ok=True)
        elif kind == "cmd" and action.get("undo"):
            print(f"  $ {cmd_text(action['undo'])}")
            if apply:
                try:
                    out = subprocess.run(action["undo"], capture_output=True, text=True)
                    text = (out.stdout + out.stderr).lower()
                    if out.returncode != 0 and not any(w in text for w in ("not found", "not installed", "no such")):
                        errors.append(f"{cmd_text(action['undo'])}: mã {out.returncode}: {text.strip()[:160]}")
                except OSError as exc:
                    errors.append(f"{cmd_text(action['undo'])}: {exc}")
        elif kind == "vendor-dir":
            path = Path(action["path"])
            print(f"  - xóa {short(str(path))}")
            if apply and path.exists():
                if path.resolve() == (HOME_STACK / "vendor").resolve():
                    shutil.rmtree(path)
                else:
                    errors.append(f"{path}: không phải thư mục vendor của agent-stack; không xóa")
        elif kind == "mkdir":
            path = Path(action["path"])
            print(f"  - xóa thư mục {short(str(path))} nếu đã trống")
            if apply and path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    notes.append(f"{short(str(path))} còn file khác (không do lần cài tạo) nên được giữ lại")
    return errors, notes


def rollback(log_arg: str, apply: bool) -> int:
    """Gỡ một lần cài (khi đưa nhật ký) hoặc mọi lần cài còn hiệu lực, mới nhất trước.
    Mã thoát: 0 = sạch; 1 = có bước gỡ lỗi; 2 = gỡ xong nhưng còn khác bản chụp trước khi cài."""
    targets = [Path(log_arg)] if log_arg else list(reversed(active_logs()))
    if not targets:
        print("Không có lần cài nào đang hiệu lực, không có gì để gỡ.")
        return 0
    errors, notes, marketplaces, pristine, ids = [], [], [], None, []
    for log in targets:
        data = load_log(log)
        print(f"Hoàn tác lần cài {when(data['created'])} theo {log.name} ({'THỰC HIỆN' if apply else 'XEM TRƯỚC'})")
        errs, kept = undo_actions(data, apply)
        errors += errs
        notes += kept
        cleanup_enabled_plugins(data, apply)
        marketplaces += installed_marketplaces(data["actions"])
        ids += installed_plugin_ids(data["actions"])
        pristine = data.get("pristine")  # vòng cuối là lần cài cũ nhất: bản chụp gốc
        if apply:
            log.rename(log.with_suffix(".rolled-back.json"))
    if apply:  # xem trước thì cấu hình vẫn đang ở trạng thái đã cài: chưa so được
        notes += compare_with_pristine(pristine, marketplaces, apply)
        notes += clean_plugin_leftovers(ids, marketplaces, (pristine or {}).get("plugins_listing"), apply)
    for note in notes:
        print(f"  ! {note}")
    for err in errors:
        print(f"  ✗ {err}")
    if apply:
        result = "sạch" if not errors and not notes else ("có lỗi" if errors else "xong, còn khác bản chụp trước khi cài")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / "last-rollback.json").write_text(json.dumps({
            "ts": time.time(), "result": result, "errors": errors, "notes": notes,
            "logs": [t.name for t in targets]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Đã ghi kết quả gỡ vào {write_manifest()}.")
    if errors:
        return 1
    return 2 if notes else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kích hoạt agent-stack (mặc định chỉ xem trước).")
    ap.add_argument("--apply", action="store_true", help="thực hiện thay đổi")
    ap.add_argument("--only", help="danh sách bước, ngăn cách bằng dấu phẩy: " + ",".join(STEPS))
    ap.add_argument("--replace-existing", action="store_true", help="thay file/symlink đang có (có sao lưu)")
    ap.add_argument("--restore-workflow-warning", action="store_true", help="bỏ skipWorkflowUsageWarning")
    ap.add_argument("--rollback", nargs="?", const="", metavar="NHẬT_KÝ", help="hoàn tác lần cài gần nhất")
    args = ap.parse_args(argv)
    if args.rollback is not None:
        return rollback(args.rollback, args.apply)
    steps = STEPS if not args.only else tuple(s.strip() for s in args.only.split(",") if s.strip())
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        ap.error(f"bước không hợp lệ: {', '.join(unknown)}")
    return Installer(args.apply, args.replace_existing, args.restore_workflow_warning).run_steps(steps)


if __name__ == "__main__":
    sys.exit(main())
