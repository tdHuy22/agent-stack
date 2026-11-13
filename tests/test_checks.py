"""Bộ chạy kiểm tĩnh `checks.py` (done-gate bước 4) và hook `post_edit.py` (13/11/2026).

Repo thử dựng trong .tmp/ bằng git thật. PATH chỉ còn /usr/bin:/bin để mô phỏng máy thiếu ruff, gitleaks, semgrep:
thiếu công cụ phải ra mã 2 và dòng "Chưa kiểm ... vì thiếu ...", không bao giờ là đạt.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests._util import PLUGIN, TMP_ROOT

SCRIPTS = PLUGIN / "skills" / "done-gate" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import checks  # noqa: E402

CHECKS = SCRIPTS / "checks.py"
HOOK = PLUGIN / "hooks" / "post_edit.py"
BARE_PATH = "/usr/bin:/bin"


def git(root: Path, *args: str):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                            GIT_COMMITTER_EMAIL="t@t"))


class RepoCase(unittest.TestCase):
    def setUp(self):
        TMP_ROOT.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="checks-", dir=TMP_ROOT))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        git(self.root, "init", "-q", "-b", "main")

    def write(self, rel: str, text: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "c")

    def run_checks(self, *args, path=BARE_PATH):
        out = subprocess.run([sys.executable, str(CHECKS), "--root", str(self.root), *args], capture_output=True,
                             text=True, timeout=120, env=dict(os.environ, PATH=path))
        return out.returncode, out.stdout + out.stderr

    def plan(self):
        ctx = checks.make_ctx(self.root.resolve())
        return ctx, checks.build_plan(ctx)


class DiffTest(unittest.TestCase):
    def test_parse_diff_added_and_deleted_hunks(self):
        diff = ("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -3,0 +4,2 @@\n+a\n+b\n"
                "@@ -10,2 +11,0 @@\n-c\n-d\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
        self.assertEqual(checks.parse_diff(diff), {"x.py": {4, 5, 11, 12}})

    def test_in_diff_respects_span_and_whole_file(self):
        changed = {"a.py": {10}, "new.py": None}
        self.assertTrue(checks.in_diff(changed, checks.Diag("a.py", 8, span=3)))
        self.assertFalse(checks.in_diff(changed, checks.Diag("a.py", 11)))
        self.assertTrue(checks.in_diff(changed, checks.Diag("new.py", 99)))
        self.assertFalse(checks.in_diff(changed, checks.Diag("other.py", 1)))


class MocTest(RepoCase):
    def test_heading_bullet_and_prose(self):
        self.write("PLAN.md", "# P\n\n## 0. Đang ở đâu\n\n- **Đang dở:** nhắc `cargo clippy` trong Mốc kiểm tra mà "
                              "không phải mốc.\n- **Mốc kiểm tra:** `npm test` và `cargo test`.\n")
        self.write("CLAUDE.md", "### Mốc kiểm tra\n\nChạy `cargo clippy --workspace -- -D warnings`.\n\n## Khác\n`ruff check`\n")
        cmds = checks.moc_commands(checks.moc_text(self.root))
        self.assertEqual(cmds, ["npm test", "cargo test", "cargo clippy --workspace -- -D warnings"])
        cov = checks.coverage(cmds)
        self.assertIn(("rust", "lint"), cov)
        self.assertNotIn(("python", "lint"), cov)
        self.assertNotIn(("ts", "type"), cov)  # `npm test` không phải kiểm kiểu


class PlanTest(RepoCase):
    def test_python_without_ruff_reports_missing_not_pass(self):
        self.write("app.py", "x = 1\n")
        self.commit()
        self.write("app.py", "x = 1\n\n\ndef f(items=[]):\n    return undefined_name + len(items)\n")
        code, out = self.run_checks()
        self.assertEqual(code, 2, out)
        self.assertIn("Chưa kiểm Python lint vì thiếu ruff; cài: brew install ruff", out)
        self.assertIn("CHƯA KIỂM ĐỦ", out)
        self.assertNotIn("Kết quả: không có lỗi chặn ·", out)

    def test_json_syntax_error_blocks_with_line(self):
        self.write("cfg.json", '{"a": 1}\n')
        self.commit()
        self.write("cfg.json", '{"a": 1,\n "b": }\n')
        code, out = self.run_checks()
        self.assertEqual(code, 1, out)
        self.assertIn("✗ cfg.json:2", out)

    def test_my_pet_like_project_runs_typecheck_and_clippy(self):
        self.write("PLAN.md", "## 0. Đang ở đâu\n\n- **Mốc kiểm tra:** `npm test` (148) và `cargo test` (45).\n")
        self.write("package.json", json.dumps({"scripts": {"test": "vitest run", "typecheck": "tsc --noEmit"}}))
        self.write("tsconfig.json", "{}\n")
        self.write("Cargo.toml", '[workspace]\nmembers = ["src-tauri"]\n')
        self.write("src-tauri/Cargo.toml", '[package]\nname = "x"\nversion = "0.1.0"\n')
        self.write("src/a.ts", "export const a = 1;\n")
        self.write("src-tauri/src/main.rs", "fn main() {}\n")
        self.commit()
        self.write("src/a.ts", "export const a: number = 'x';\n")
        self.write("src-tauri/src/main.rs", "fn main() { let unused = 1; }\n")
        ctx, plan = self.plan()
        tools = [c.tool for c in plan.checks]
        self.assertIn("npm run typecheck", tools)
        rust = [c for c in plan.checks if c.lang == "rust" and c.kind == "lint"]
        if shutil.which("cargo-clippy"):
            self.assertEqual([c.tool for c in rust], ["cargo clippy"])
            self.assertIn("--workspace", rust[0].argv)
            self.assertEqual(rust[0].cwd, self.root.resolve())
        else:
            self.assertIn(("rust", "lint", "cargo-clippy"), [m[:3] for m in plan.missing])

    def test_archctl_like_project_only_uses_moc_for_rust(self):
        self.write("PLAN.md", "### Mốc kiểm tra\n\n`cargo test --workspace`; "
                              "`cargo clippy --workspace --all-targets -- -D warnings`.\n")
        self.write("Cargo.toml", '[package]\nname = "x"\nversion = "0.1.0"\n')
        self.write("src/lib.rs", "pub fn a() {}\n")
        self.commit()
        self.write("src/lib.rs", "pub fn a() { let unused = 1; }\n")
        ctx, plan = self.plan()
        self.assertEqual([c for c in plan.checks if c.lang == "rust"], [])
        self.assertEqual({(lang, kind) for lang, kind, _, _ in plan.covered},
                         {("rust", "lint"), ("rust", "type"), ("rust", "format")})

    def test_untracked_file_counts_as_whole_file(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("tools/new.sh", "echo hi\n")
        ctx, _ = self.plan()
        self.assertEqual(ctx.changed, {"tools/new.sh": None})


class ReviewRegressionTest(RepoCase):
    """Lỗi review opus·xhigh 13/11/2026, mỗi test tái hiện đúng kịch bản reviewer nêu."""

    def fake_bin(self, name: str, body: str) -> str:
        d = self.root.parent / f"{self.root.name}-bin"
        d.mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        f = d / name
        f.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        f.chmod(0o755)
        return str(d)

    def test_ruff_invalid_syntax_blocks(self):  # lỗi 1
        if not shutil.which("ruff"):
            self.skipTest("máy chưa có ruff")
        self.write("a.py", "x = 1\n")
        self.commit()
        self.write("a.py", "x = 1\ndef f(:\n    pass\n")
        code, out = self.run_checks("--offline", path=os.environ["PATH"])
        self.assertEqual(code, 1, out)
        self.assertIn("✗ a.py:2", out)

    def test_build_failure_without_location_blocks(self):  # lỗi 2: build.rs panic, cargo thoát 101
        self.write("Cargo.toml", '[package]\nname = "x"\nversion = "0.1.0"\n')
        self.write("src/main.rs", "fn main() {}\n")
        self.commit()
        self.write("src/main.rs", 'fn main() { let x: u32 = "s"; }\n')
        fake = self.fake_bin("cargo", 'echo "error: failed to run custom build command for x" >&2; exit 101')
        shutil.copy(Path(fake) / "cargo", Path(fake) / "cargo-clippy")
        code, out = self.run_checks("--offline", path=f"{fake}:{BARE_PATH}")
        self.assertEqual(code, 1, out)
        self.assertIn("lệnh trượt (mã 101)", out)

    def test_go_vet_prefix_is_parsed(self):  # lỗi 2: dòng "vet: ./main.go:4:14: ..."
        diags = checks.parse_generic("", "# x\nvet: ./main.go:4:14: cannot use \"s\" (untyped string constant)\n")
        self.assertEqual([(d.path, d.line) for d in diags], [("./main.go", 4)])

    def test_tsconfig_solution_checks_references(self):  # lỗi 3: mẫu Vite
        self.write("package.json", json.dumps({"scripts": {"build": "tsc -b && vite build"}}))
        self.write("tsconfig.json", '{\n  // solution\n  "files": [],\n  "references": [{"path": "./tsconfig.app.json"},'
                                    ' {"path": "./tsconfig.node.json"}]\n}\n')
        self.write("tsconfig.app.json", '{"include": ["src"]}\n')
        self.write("tsconfig.node.json", '{"include": ["vite.config.ts"]}\n')
        self.write("src/a.ts", "export const a = 1;\n")
        self.commit()
        self.write("src/a.ts", "export const a: number = 'x';\n")
        self.write("node_modules/.bin/tsc", "#!/bin/sh\nexit 0\n").chmod(0o755)
        _, plan = self.plan()
        names = [c.tool for c in plan.checks if c.kind == "type"]
        self.assertEqual(names, ["tsc --noEmit -p tsconfig.app.json", "tsc --noEmit -p tsconfig.node.json"])

    def test_ruff_named_by_project_uses_default_rules(self):  # lỗi 4
        self.write(".pre-commit-config.yaml", "repos:\n- repo: https://github.com/astral-sh/ruff-pre-commit\n")
        self.write("a.py", "x = 1\n")
        self.commit()
        self.write("a.py", "x = 1\n\n\ndef add(a, b):\n    return a + b\n")
        _, plan = self.plan()
        ruff = [c for c in plan.checks if c.tool == "ruff"]
        if not shutil.which("ruff"):
            self.skipTest("máy chưa có ruff")
        self.assertTrue(ruff[0].enforced)
        self.assertNotIn("ALL", ruff[0].argv)

    def test_newer_python_is_not_compiled_by_older_interpreter(self):  # lỗi 5
        self.write("pyproject.toml", '[project]\nname = "x"\nrequires-python = ">=3.99"\n')
        self.write("a.py", "x = 1\n")
        self.commit()
        self.write("a.py", "type Alias = list[int]\n")
        code, out = self.run_checks("--offline")
        self.assertEqual(code, 2, out)
        self.assertNotIn("✗", out)
        self.assertIn("project cần Python ≥ 3.99", out)

    def test_hook_ignores_ruff_inside_repo(self):  # lỗi 6
        marker = self.root / "ran.txt"
        self.write("vendor/bin/ruff", f"#!/bin/sh\ntouch {marker}\necho '[]'\n").chmod(0o755)
        self.write(".venv/bin/ruff", f"#!/bin/sh\ntouch {marker}\necho '[]'\n").chmod(0o755)
        path = self.write("a.py", "x = 1\n")
        subprocess.run([sys.executable, str(HOOK)], input=json.dumps(
            {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}}),
            capture_output=True, text=True, timeout=10, env=dict(os.environ, PATH=BARE_PATH))
        self.assertFalse(marker.exists())

    def test_hook_fast_on_many_matches(self):  # lỗi 7: replace_all trên file lớn, chuỗi trùng hàng chục nghìn chỗ
        path = self.write("big.json", "[" + ",\n".join(["null"] * 40000) + "]\n")
        t0 = time.time()
        out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(
            {"tool_name": "Edit", "cwd": str(self.root),
             "tool_input": {"file_path": str(path), "new_string": "null", "replace_all": True}}),
            capture_output=True, text=True, timeout=10, env=dict(os.environ, PATH=BARE_PATH))
        self.assertEqual(out.returncode, 0)
        self.assertLess(time.time() - t0, 2.0)

    def test_structured_patch_gives_exact_lines(self):  # lỗi 11
        sys.path.insert(0, str(HOOK.parent))
        import post_edit  # noqa: E402
        response = {"structuredPatch": [{"oldStart": 4, "oldLines": 3, "newStart": 4, "newLines": 3,
                                         "lines": [" a", "-return 2", "+pass", " b"]}]}
        self.assertEqual(post_edit.patch_lines(response), {5})
        self.assertEqual(post_edit.patch_lines({"structuredPatch": [{"newStart": 7, "lines": [" a", "-b"]}]}), {8})
        self.assertEqual(post_edit.patch_lines(None), set())

    def test_lint_script_that_fixes_is_not_run(self):  # lỗi 8
        self.write("package.json", json.dumps({"scripts": {"lint": "eslint . --fix"}}))
        self.write("a.js", "x\n")
        self.commit()
        self.write("a.js", "y\n")
        _, plan = self.plan()
        self.assertFalse([c for c in plan.checks if c.kind == "lint"])
        self.assertTrue(any("tự sửa file" in n for n in plan.notes))

    def test_habit_rules_do_not_block(self):  # lỗi 9
        self.assertFalse(checks.block_ruff(checks.Diag("a.py", 1, code="B007"), False))
        self.assertFalse(checks.block_ruff(checks.Diag("a.py", 1, code="B028"), False))
        self.assertTrue(checks.block_ruff(checks.Diag("a.py", 1, code="B006"), False))

    def test_broken_linter_is_exit_2_not_blocking(self):  # lỗi 10: semgrep cấu hình sai thoát 7
        self.write(".semgrep.yml", "rules: [oops\n")
        self.write("a.py", "x = 1\n")
        self.commit()
        self.write("a.py", "x = 2\n")
        fake = self.fake_bin("semgrep", 'echo "invalid config" >&2; exit 7')
        code, out = self.run_checks(path=f"{fake}:{BARE_PATH}")
        self.assertEqual(code, 2, out)
        self.assertIn("lệnh hỏng", out)


class SecondReviewTest(RepoCase):
    """Lỗi review sonnet·xhigh 13/11/2026 (V1–V10)."""

    def test_unsupported_language_is_not_a_pass(self):  # V1
        self.write("a.txt", "x\n")
        self.commit()
        self.write("A.scala", 'object A { val x: Int = "oops" }\n')
        code, out = self.run_checks("--offline")
        self.assertEqual(code, 2, out)
        self.assertIn("agent-stack chưa có công cụ cho Scala", out)

    def test_ts_without_tsconfig_reports_type_unchecked(self):  # V1
        self.write("deno.json", "{}\n")
        self.write("a.ts", "export const a = 1;\n")
        self.commit()
        self.write("a.ts", "export const a: number = 'x';\n")
        _, plan = self.plan()
        self.assertIn(("ts", "type", "tsconfig.json"), [m[:3] for m in plan.missing])

    def test_zsh_shebang_uses_zsh_n(self):  # V2
        self.write("a.txt", "x\n")
        self.commit()
        self.write("run.sh", "#!/bin/zsh\nsetopt extendedglob\nprint -r -- ${(j:,:)@}\n")
        _, plan = self.plan()
        self.assertEqual([c.tool for c in plan.checks if c.lang == "shell"], ["zsh -n"])

    def test_jsx_in_js_is_not_node_checked(self):  # V3
        self.write("package.json", json.dumps({"dependencies": {"react": "18"}}))
        self.write("src/App.js", "export default 1;\n")
        self.commit()
        self.write("src/App.js", 'export default () => <div className="a">hi</div>;\n')
        _, plan = self.plan()
        self.assertFalse([c for c in plan.checks if c.tool == "node --check"])

    def test_gitleaks_respects_allowlist_paths(self):  # V4
        if not shutil.which("gitleaks"):
            self.skipTest("máy chưa có gitleaks")
        self.write(".gitleaks.toml", '[extend]\nuseDefault = true\n[[allowlists]]\npaths = [\'\'\'^tests/\'\'\']\n')
        self.write("a.txt", "x\n")
        self.commit()
        key = "AKIA" + "QYLPMN5HFIQR7XYZ"
        self.write("tests/fix.py", f'KEY = "{key}"\n')
        self.write("src/leak.py", f'KEY = "{key}"\n')
        code, out = self.run_checks("--offline", path=os.environ["PATH"])
        self.assertIn("✗ src/leak.py:1", out)
        self.assertNotIn("✗ tests/fix.py", out)  # allowlist `^tests/` của project được tôn trọng
        self.assertNotIn(key, out)

    def test_run_cmd_does_not_wait_for_background_children(self):  # V6
        t0 = time.time()
        code, out, _, _ = checks.run_cmd(["sh", "-c", "(sleep 5 &) ; echo done"], self.root, 3)
        self.assertEqual((code, out.strip()), (0, "done"))
        self.assertLess(time.time() - t0, 2.5)
        t0 = time.time()
        code, _, _, _ = checks.run_cmd(["sh", "-c", "sleep 5"], self.root, 0.5)
        self.assertIsNone(code)
        self.assertLess(time.time() - t0, 3)

    def test_killed_checks_kills_its_tools(self):  # V5
        marker = self.root / "survived"
        self.write("package.json", json.dumps({"scripts": {"typecheck": f"sleep 3 && touch {marker}"}}))
        self.write("tsconfig.json", "{}\n")
        self.write("a.ts", "export const a = 1;\n")
        self.commit()
        self.write("a.ts", "export const a = 2;\n")
        proc = subprocess.Popen([sys.executable, str(CHECKS), "--root", str(self.root), "--offline"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.2)
        proc.terminate()
        proc.wait(timeout=10)
        time.sleep(2.5)
        self.assertFalse(marker.exists())

    def test_dash_file_name_is_not_an_option(self):  # V7
        if not shutil.which("ruff"):
            self.skipTest("máy chưa có ruff")
        self.write("a.txt", "x\n")
        self.commit()
        self.write("--output-file=INJECTED.py", "x = undefined_name\n")
        code, out = self.run_checks("--offline", path=os.environ["PATH"])
        self.assertFalse((self.root / "INJECTED.py").exists())
        self.assertIn("F821", out)

    def test_mnemonic_prefix_config_is_ignored(self):  # V8
        git(self.root, "config", "diff.mnemonicPrefix", "true")
        self.write("cfg.json", '{"a": 1}\n')
        self.commit()
        self.write("cfg.json", '{"a": }\n')
        code, out = self.run_checks("--offline")
        self.assertEqual(code, 1, out)

    def test_write_of_tracked_file_reports_only_changed_lines(self):  # V9
        if not shutil.which("ruff"):
            self.skipTest("máy chưa có ruff")
        path = self.write("a.py", "def f():\n    return undefined_a\n")
        self.commit()
        path.write_text("def f():\n    return undefined_a\n\n\ndef g():\n    return undefined_b\n", encoding="utf-8")
        out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(
            {"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}}),
            capture_output=True, text=True, timeout=10).stdout
        self.assertIn("a.py:6", out)
        self.assertNotIn("a.py:2", out)

    def test_json_with_comments_is_not_a_syntax_error(self):  # V10
        self.write("a.txt", "x\n")
        self.commit()
        self.write("turbo.json", '{\n  // pipeline\n  "a": 1\n}\n')
        self.write("other.json", '{\n  // ghi chú\n  "a": 1\n}\n')
        code, out = self.run_checks("--offline")
        self.assertNotIn("✗", out)


class ThirdReviewTest(RepoCase):
    """Lỗi review lại phần sửa (sonnet·high, 13/11/2026)."""

    def test_empty_references_still_checks_root_config(self):  # 1
        self.write("tsconfig.json", '{"include": ["src"], "references": []}\n')
        self.write("src/a.ts", "export const a = 1;\n")
        self.write("node_modules/.bin/tsc", "#!/bin/sh\nexit 0\n").chmod(0o755)
        self.write("package.json", "{}\n")
        self.commit()
        self.write("src/a.ts", "export const a = 2;\n")
        _, plan = self.plan()
        self.assertEqual([c.tool for c in plan.checks if c.kind == "type"], ["tsc --noEmit -p tsconfig.json"])

    def test_jsx_without_any_checker_is_not_a_pass(self):  # 2
        self.write("package.json", json.dumps({"dependencies": {"react": "18"}}))
        self.write("src/App.jsx", "export default 1;\n")
        self.commit()
        self.write("src/App.jsx", "export default <div>;\n")
        code, out = self.run_checks("--offline")
        self.assertEqual(code, 2, out)
        self.assertIn("JSX/Svelte chưa kiểm cú pháp", out)

    def test_framework_idioms_do_not_block(self):  # 3
        for code in ("B008", "B017"):
            self.assertFalse(checks.block_ruff(checks.Diag("a.py", 1, code=code), False), code)

    def test_dash_name_safe_for_js_tools(self):  # 4
        self.write("package.json", json.dumps({"scripts": {}}))
        self.write("eslint.config.js", "export default [];\n")
        self.write("node_modules/.bin/eslint", "#!/bin/sh\necho '[]'\n").chmod(0o755)
        self.write("a.txt", "x\n")
        self.commit()
        self.write("-x.js", "x\n")
        _, plan = self.plan()
        lint = [c for c in plan.checks if c.tool == "eslint"][0]
        self.assertIn("./-x.js", lint.argv)
        self.assertNotIn("-x.js", lint.argv)


class TriageTest(unittest.TestCase):
    def test_lint_only_changed_lines_but_compile_errors_anywhere(self):
        lint = checks.Check("python", "lint", "x", block=checks.block_all)
        typ = checks.Check("ts", "type", "y", block=checks.block_errors, anywhere=True)
        changed = {"a.py": {3}}
        r = checks.Result(lint)
        checks.triage(lint, [checks.Diag("a.py", 3), checks.Diag("a.py", 9)], changed, r)
        self.assertEqual((len(r.block), r.dropped), (1, 1))
        r = checks.Result(typ)
        checks.triage(typ, [checks.Diag("b.ts", 7, level="error"), checks.Diag("b.ts", 8, level="warning")], changed, r)
        self.assertEqual(len(r.block), 1)
        self.assertTrue(r.block[0].outside)
        self.assertEqual(r.dropped, 1)

    def test_style_rules_warn_unless_project_enforces(self):
        d = checks.Diag("a.py", 1, code="E501", msg="line too long")
        self.assertFalse(checks.block_ruff(d, False))
        self.assertTrue(checks.block_ruff(d, True))
        self.assertTrue(checks.block_ruff(checks.Diag("a.py", 1, code="F821"), False))


class ParserTest(unittest.TestCase):
    def test_generic_formats(self):
        out = ("src/main.rs:3:9: warning: unused variable: `x`\n"
               "src/main.rs:5:1: error[E0425]: cannot find value `y` in this scope\n"
               "a.sh:2:6: note: Double quote to prevent globbing. [SC2086]\n"
               "src/a.ts(10,5): error TS2322: Type 'string' is not assignable to type 'number'.\n"
               "warning: `x` (bin) generated 1 warning\n")
        diags = checks.parse_generic(out, "")
        got = [(d.path, d.line, d.level, d.code) for d in diags]
        self.assertEqual(got, [("src/main.rs", 3, "warning", ""), ("src/main.rs", 5, "error", "E0425"),
                               ("a.sh", 2, "info", "SC2086"), ("src/a.ts", 10, "error", "TS2322")])

    def test_json_tools(self):
        ruff = json.dumps([{"filename": "/r/a.py", "location": {"row": 4, "column": 12}, "code": "F821",
                            "message": "Undefined name"}])
        self.assertEqual(checks.parse_ruff(ruff, "")[0].code, "F821")
        eslint = json.dumps([{"filePath": "/r/a.ts", "messages": [{"line": 2, "column": 1, "severity": 1,
                                                                   "ruleId": "no-unused-vars", "message": "m"}]}])
        self.assertEqual(checks.parse_eslint(eslint, "")[0].level, "warning")
        leak = json.dumps([{"File": "/t/src/a.py", "StartLine": 7, "RuleID": "generic-api-key",
                            "Description": "Generic API Key", "Secret": "REDACTED"}])
        d = checks.parse_gitleaks(leak, "")[0]
        self.assertEqual((d.line, d.level), (7, "error"))
        self.assertNotIn("REDACTED", d.msg)
        sg = json.dumps({"results": [
            {"path": "a.py", "start": {"line": 3, "col": 1}, "check_id": "p.compat",
             "extra": {"severity": "ERROR", "message": "m", "metadata": {"category": "compatibility"}}},
            {"path": "a.py", "start": {"line": 4, "col": 1}, "check_id": "p.sqli",
             "extra": {"severity": "ERROR", "message": "m", "metadata": {"category": "security"}}}]})
        self.assertEqual([d.level for d in checks.parse_semgrep(sg, "")], ["warning", "error"])

    def test_format_diff(self):
        out = "--- a.py\n+++ a.py\n@@ -5,3 +5,3 @@\n-x=1\n+x = 1\n"
        d = checks.parse_udiff(out, "")[0]
        self.assertEqual((d.path, d.line, d.span, d.level), ("a.py", 5, 3, "style"))


class GapsTest(unittest.TestCase):
    def test_unfamiliar_project_gets_suggestions(self):
        root = Path(tempfile.mkdtemp(prefix="gaps-", dir=TMP_ROOT))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        files = ["main.tf", "vars.tf", "out.tf", "examples/a.py", "examples/b.py", "examples/c.py"]
        gaps = checks.project_gaps(root, files)
        self.assertEqual(gaps["unsupported"], [("Terraform", 3, "terraform validate, tflint")])
        self.assertEqual(gaps["langs"], [])  # code mẫu không tính là ngôn ngữ của project
        self.assertIn("file luật (CLAUDE.md hay AGENTS.md)", gaps["layers"])
        context, short = checks.gaps_text(gaps)
        self.assertIn("Terraform", context)
        self.assertIn("chưa phủ Terraform", short)

    def test_complete_project_is_silent(self):
        root = Path(tempfile.mkdtemp(prefix="gaps-", dir=TMP_ROOT))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "CLAUDE.md").write_text("## Mốc kiểm tra\n\n`go test ./...`\n", encoding="utf-8")
        gaps = checks.project_gaps(root, ["CLAUDE.md", "README.md"])
        self.assertIsNone(checks.gaps_text(gaps))


class HookTest(RepoCase):
    def hook(self, payload, path=BARE_PATH):
        t0 = time.time()
        out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                             timeout=10, env=dict(os.environ, PATH=path))
        return out.returncode, out.stdout, time.time() - t0

    def test_python_error_on_edited_line_is_reported_fast(self):
        path = self.write("a.py", "x = 1\n")
        self.commit()
        path.write_text("x = 1\ndef f(:\n    pass\n", encoding="utf-8")
        code, out, secs = self.hook({"tool_name": "Edit", "cwd": str(self.root),
                                     "tool_input": {"file_path": str(path), "new_string": "def f(:\n    pass"}})
        self.assertEqual(code, 0)
        self.assertLess(secs, 2.0)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("a.py:2", ctx)

    def test_clean_file_is_silent(self):
        path = self.write("ok.py", "x = 1\n")
        code, out, secs = self.hook({"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}})
        self.assertEqual((code, out), (0, ""))
        self.assertLess(secs, 2.0)

    def test_shell_syntax_error_without_shellcheck(self):
        path = self.write("run.sh", "#!/bin/bash\nif [ 1 ]; then\n")
        code, out, _ = self.hook({"tool_name": "Write", "cwd": str(self.root), "tool_input": {"file_path": str(path)}})
        self.assertEqual(code, 0)
        self.assertIn("bash -n", out)

    def test_shellcheck_reports_only_edited_line(self):
        if not shutil.which("shellcheck"):
            self.skipTest("máy chưa có shellcheck")
        # SC2164 (cd không có || exit) là mức warning: hook báo; mức info/style chỉ done-gate báo.
        path = self.write("run.sh", "#!/bin/bash\ncd /tmp\necho ok\n")
        self.commit()
        path.write_text("#!/bin/bash\ncd /tmp\necho ok\ncd /var\n", encoding="utf-8")
        code, out, _ = self.hook({"tool_name": "Edit", "cwd": str(self.root),
                                  "tool_input": {"file_path": str(path), "new_string": "echo ok\ncd /var"}},
                                 path=os.environ["PATH"])
        self.assertEqual(code, 0)
        self.assertIn("run.sh:4", out)
        self.assertNotIn("run.sh:2", out)

    def test_ruff_reports_only_edited_line(self):
        if not shutil.which("ruff"):
            self.skipTest("máy chưa có ruff")
        path = self.write("a.py", "def f():\n    return undefined_a\n")
        self.commit()
        path.write_text("def f():\n    return undefined_a\n\n\ndef g():\n    return undefined_b\n", encoding="utf-8")
        code, out, secs = self.hook({"tool_name": "Edit", "cwd": str(self.root),
                                     "tool_input": {"file_path": str(path), "new_string": "def g():\n    return undefined_b"}},
                                    path=os.environ["PATH"])
        self.assertEqual(code, 0)
        self.assertLess(secs, 2.0)
        self.assertIn("a.py:6", out)
        self.assertNotIn("a.py:2", out)

    def test_other_tools_and_bad_input_exit_zero_silently(self):
        for payload in ({"tool_name": "Bash", "tool_input": {"command": "ls"}}, {"tool_name": "Edit"},
                        {"tool_name": "Write", "tool_input": {"file_path": str(self.root / "missing.py")}}):
            code, out, _ = self.hook(payload)
            self.assertEqual((code, out), (0, ""), payload)


if __name__ == "__main__":
    unittest.main()
