"""Kiểm tĩnh thay cho luật bằng lời trong CLAUDE.md: máy kiểm chắc hơn lời dặn và không tốn token mỗi phiên.

- "Python chỉ dùng thư viện chuẩn": plugin/, tools/, tests/ không import module ngoài stdlib và ngoài repo.
- Mọi file .py git theo dõi biên dịch được bằng python3 của repo (3.11), kể cả file chưa test nào import.
- "Hook không bao giờ làm kẹt phiên": mọi hook trong hooks.json gặp stdin hỏng vẫn thoát 0, không in lỗi.
- Linter: ruff theo `ruff.toml` (bộ luật rộng) cho Python, Biome theo `biome.json` cho lớp giao diện TS. Máy thiếu
  công cụ thì bỏ qua và nói cách cài (`install.sh`, mục brew:ruff, brew:biome).
- Kiến trúc (GĐ3, thay cho luật archctl vì archctl chưa thấy import trần sau `sys.path.insert`): hook chỉ import lib
  và hosts, lib chỉ import lib. Chỗ cũ nằm trong baseline; chỗ mới trượt, chỗ cũ đã sửa phải bỏ khỏi baseline.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

from tests._util import PLUGIN, REPO, TempDirTestCase

# Thư mục phải chạy được bằng python3 không cài thêm gì. evals/ có fixture cố ý dùng gói ngoài (fastapi, redis,
# harbor); claude-ai-skills/ chạy trên claude.ai, nơi có PyMuPDF và pypdf.
STDLIB_ONLY = ("plugin/", "tools/", "tests/")


def tracked_py() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "*.py"], capture_output=True, text=True,
                         check=True).stdout
    # File đã xóa nhưng chưa `git add` vẫn có trong index: bỏ qua thay vì làm test gãy giữa lúc đang sửa.
    return [p for p in out.split("\0") if p and (REPO / p).is_file()]


def local_names(files: list[str]) -> set[str]:
    """Tên module trong các file cho trước: tên file .py, và tên gói (thư mục có __init__.py) như `tests`.

    Không tính tên thư mục thường: fixture trong evals/ có tên trùng gói PyPI (harbor, retry, cache) sẽ che lỗi."""
    names = set()
    for f in files:
        parts = f.split("/")
        names.add(parts[-1].removesuffix(".py"))
        if parts[-1] == "__init__.py" and len(parts) > 1:
            names.add(parts[-2])
    return names


def top_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module.split(".")[0]


# (file, module) đã có trước luật kiến trúc (14/11/2026, bạn chọn "ghi luật + baseline"). Chỉ được bỏ bớt: sửa xong một
# chỗ (dời phần dùng chung vào plugin/lib) thì xóa dòng của nó.
ARCH_BASELINE = {
    ("plugin/hooks/post_edit.py", "checks"),
    ("plugin/hooks/prompt_submit.py", "route"),
    ("plugin/hooks/session_start.py", "cloud_update"),
    ("plugin/hooks/session_start.py", "collect"),
    ("plugin/hooks/session_start.py", "route"),
    ("plugin/hooks/session_start.py", "drift"),
    ("plugin/hooks/session_start.py", "mcp_remote"),
    ("plugin/hooks/stop.py", "risk"),
    ("plugin/lib/agentstack.py", "risk"),
}


def arch_violations() -> set:
    """(file, module) mà hook import ngoài stdlib, `plugin/lib`, `plugin/hosts`; hay lib import ngoài stdlib và lib.
    Tên module so theo tên file (hook, lib nạp script qua `sys.path.insert` rồi `import <tên>`)."""
    lib = {p.stem for p in (PLUGIN / "lib").glob("*.py")}
    hosts = {p.stem for p in (PLUGIN / "hosts").glob("*.py")}
    found = set()
    for folder, allowed in (("hooks", lib | hosts), ("lib", lib)):
        for path in sorted((PLUGIN / folder).glob("*.py")):
            for _, name in top_imports(ast.parse(path.read_text(encoding="utf-8"), str(path))):
                if name not in sys.stdlib_module_names and name not in allowed:
                    found.add((path.relative_to(REPO).as_posix(), name))
    return found


class ArchitectureRules(unittest.TestCase):
    def test_hooks_import_only_lib_and_lib_only_itself(self):
        found = arch_violations()
        new = sorted(f"{f} import {m}" for f, m in found - ARCH_BASELINE)
        self.assertEqual(new, [], "Hook chỉ gọi thư viện chung plugin/lib (và plugin/hosts), lib chỉ gọi lib: dời phần "
                                  "dùng chung vào plugin/lib thay vì import script của skill hay hook khác")

    def test_baseline_only_shrinks(self):
        fixed = sorted(f"{f} import {m}" for f, m in ARCH_BASELINE - arch_violations())
        self.assertEqual(fixed, [], "Chỗ này đã sửa: xóa khỏi ARCH_BASELINE để luật không nới trở lại")

    def test_baseline_never_grows(self):
        """Baseline chỉ được bớt: thêm một chỗ miễn mới vào ARCH_BASELINE là nới luật (14/11/2026 có 9 chỗ)."""
        self.assertLessEqual(len(ARCH_BASELINE), 9)

    def test_rule_sees_a_new_skill_import(self):
        """Luật bắt đúng kiểu import của repo: `sys.path.insert(...skills...)` rồi `import <script>`."""
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "hook.py"
            fake.write_text("import sys\nsys.path.insert(0, 'x/skills/done-gate/scripts')\nimport risk\nimport archgate\n")
            names = {n for _, n in top_imports(ast.parse(fake.read_text()))}
        lib = {p.stem for p in (PLUGIN / "lib").glob("*.py")}
        self.assertEqual({n for n in names if n not in sys.stdlib_module_names and n not in lib}, {"risk"})


class StaticChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = tracked_py()
        # Code chạy thật (plugin/, tools/) chỉ được import module của chính nó; test được nạp thêm script trong
        # evals/ và claude-ai-skills/ (run_eval, extract_paper…).
        cls.shipped = local_names([f for f in cls.files if f.startswith(("plugin/", "tools/"))])
        cls.local = local_names(cls.files)

    def test_found_python_files(self):
        self.assertGreater(len(self.files), 100)

    def test_stdlib_only_outside_evals(self):
        bad = []
        for f in self.files:
            if not f.startswith(STDLIB_ONLY):
                continue
            allowed = self.local if f.startswith("tests/") else self.shipped
            tree = ast.parse((REPO / f).read_text(encoding="utf-8"), f)
            for line, name in top_imports(tree):
                if name not in sys.stdlib_module_names and name not in allowed:
                    bad.append(f"{f}:{line} import {name}")
        self.assertEqual(bad, [], "CLAUDE.md: Python chỉ dùng thư viện chuẩn")

    def test_every_tracked_file_compiles(self):
        """Cảnh báo lúc biên dịch (như escape `\\d` sai trong chuỗi thường) cũng tính là lỗi: bản Python sau sẽ từ chối."""
        bad = []
        for f in self.files:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error")
                    compile((REPO / f).read_text(encoding="utf-8"), f, "exec", dont_inherit=True)
            except (SyntaxError, ValueError, UnicodeDecodeError, Warning) as e:
                bad.append(f"{f}: {e}")
        self.assertEqual(bad, [])

    def test_detects_third_party_import(self):
        """Tự kiểm bộ quét: import gói ngoài phải bị bắt, import stdlib và module trong repo thì không."""
        src = ("import requests\nfrom yaml import safe_load\nimport json\nfrom agentstack import x\n"
               "def f():\n    import harbor\n    import retry\n")
        found = [n for _, n in top_imports(ast.parse(src)) if n not in sys.stdlib_module_names and n not in self.shipped]
        # harbor, retry là tên fixture trong evals/: với plugin/ và tools/ vẫn phải tính là gói ngoài.
        self.assertEqual(sorted(found), ["harbor", "requests", "retry", "yaml"])


class Linters(TempDirTestCase):
    def run_tool(self, name: str, *args: str, stdin: str | None = None, cwd=REPO) -> subprocess.CompletedProcess:
        tool = shutil.which(name)
        if not tool:
            self.skipTest(f"máy chưa có {name}: cài bằng ./install.sh --only tools --apply")
        return subprocess.run([tool, *args], cwd=cwd, input=stdin, capture_output=True, text=True, timeout=120)

    def test_ruff_clean(self):
        self.assertTrue((REPO / "ruff.toml").is_file())
        r = self.run_tool("ruff", "check", "--no-cache", "--output-format", "concise", ".")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_biome_clean(self):
        r = self.run_tool("biome", "lint", "--error-on-warnings", ".")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Checked 5 files", r.stdout + r.stderr, "biome.json phải phủ ui.tsx, kiểu, test của mod, run.mjs")

    def test_linters_catch_real_errors(self):
        """Tự kiểm: cấu hình không được nuốt lỗi thật (tên chưa định nghĩa trong Python, biến thừa trong TS)."""
        r = self.run_tool("ruff", "check", "--no-cache", "--stdin-filename", "plugin/hooks/x.py", "-",
                          stdin="def f():\n    return chua_co\n")
        self.assertIn("F821", r.stdout)
        (self.tmp / "biome.json").write_text((REPO / "biome.json").read_text(encoding="utf-8"), encoding="utf-8")
        (self.tmp / "plugin" / "hooks").mkdir(parents=True)
        (self.tmp / "plugin" / "hooks" / "x.tsx").write_text("export function f(a: number) {\n  const thua = 1\n"
                                                               "  return a\n}\n", encoding="utf-8")
        r = self.run_tool("biome", "lint", ".", cwd=self.tmp)
        self.assertIn("noUnusedVariables", r.stdout + r.stderr)

    def test_biome_skips_worktrees(self):
        """Worktree của phiên khác trong `.claude/worktrees/` có biome.json riêng: biome không được dừng vì cấu hình lồng."""
        cfg = (REPO / "biome.json").read_text(encoding="utf-8")
        (self.tmp / "biome.json").write_text(cfg, encoding="utf-8")
        (self.tmp / "plugin" / "hooks").mkdir(parents=True)
        (self.tmp / "plugin" / "hooks" / "x.tsx").write_text("export const a = 1\n", encoding="utf-8")
        nested = self.tmp / ".claude" / "worktrees" / "w"
        (nested / "plugin" / "hooks").mkdir(parents=True)
        (nested / "biome.json").write_text(cfg, encoding="utf-8")
        (nested / "plugin" / "hooks" / "x.tsx").write_text("export const a = 1\n", encoding="utf-8")
        r = self.run_tool("biome", "lint", "--verbose", "--error-on-warnings", ".", cwd=self.tmp)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("plugin/hooks/x.tsx", out)
        self.assertNotIn(".claude/worktrees", out)

class HooksSurviveBadInput(TempDirTestCase):
    BAD_INPUTS = ("", "{not json", "[1, 2]", "null", "{}", '{"hook_event_name": 42, "cwd": 7}')

    def hook_scripts(self) -> list[str]:
        data = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        scripts = []
        for groups in data["hooks"].values():
            for group in groups:
                for hook in group["hooks"]:
                    for arg in hook.get("args", []):
                        if arg.endswith(".py"):
                            scripts.append(arg.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN)))
        return scripts

    def test_every_registered_hook_exits_zero_on_bad_stdin(self):
        scripts = self.hook_scripts()
        self.assertGreaterEqual(len(scripts), 9)
        env = dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"),
                   AGENT_STACK_PLUGINS_DIR=str(self.tmp / "no-plugins"))
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        bad = []
        for script in scripts:
            for stdin in self.BAD_INPUTS:
                out = subprocess.run([sys.executable, script], input=stdin, capture_output=True, text=True,
                                     env=env, cwd=self.tmp, timeout=30)
                if out.returncode != 0 or out.stderr:
                    name = os.path.basename(script)
                    bad.append(f"{name} stdin={stdin!r}: mã {out.returncode}, stderr {out.stderr[-200:]!r}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
