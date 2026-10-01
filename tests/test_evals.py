import json
import os
import sys
import unittest

from tests._util import REPO, TempDirTestCase

sys.path.insert(0, str(REPO / "evals"))
import run_eval  # noqa: E402

FAKE_CLAUDE = """#!/usr/bin/env python3
import json, sys, os
args = sys.argv[1:]
open(os.environ["FAKE_ARGS"], "w").write(json.dumps(args))
# giả lập model sửa đúng lỗi off-by-one
src = open("pager.py").read().replace("start = page * per_page", "start = (page - 1) * per_page")
open("pager.py", "w").write(src)
print(json.dumps({"result": "Đã sửa.", "total_cost_usd": 0.05, "num_turns": 3, "is_error": False}))
"""


class Graders(unittest.TestCase):
    def test_self_test_passes(self):
        self.assertEqual(run_eval.self_test(run_eval.load_tasks("all")), 0)

    def grade(self, name, answer, overlay=None):
        task = run_eval.TASKS / name
        work = REPO / ".tmp" / f"grade-{name}-{os.getpid()}"
        run_eval.prepare(task, work)
        for rel, text in (overlay or {}).items():
            (work / rel).write_text(text, encoding="utf-8")
        try:
            return run_eval.load_check(task)(work, answer)[0]
        finally:
            import shutil
            shutil.rmtree(work, ignore_errors=True)

    def test_weak_tests_do_not_pass_mutation_grader(self):
        weak = ("import unittest\nfrom text import slugify\n\nclass T(unittest.TestCase):\n"
                "    def test_lower(self):\n        self.assertEqual(slugify('Hello'), 'hello')\n")
        self.assertFalse(self.grade("qa-write-tests", "", {"test_text.py": weak}))

    def test_false_positive_on_safe_function_fails(self):
        answer = "get_user: SQL injection do ghép chuỗi.\nget_order: cũng là lỗ hổng injection."
        self.assertFalse(self.grade("sec-sqli", answer))

    def test_old_number_from_changelog_fails(self):
        self.assertFalse(self.grade("doc-ratelimit", "Tối đa 60 request mỗi phút, header X-RateLimit-Remaining, mã 429."))

    def test_editing_tests_is_caught(self):
        cheat = "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
        self.assertFalse(self.grade("code-off-by-one", "", {"test_pager.py": cheat}))


class Selection(unittest.TestCase):
    def row(self, cfg, passed, cost):
        return {"config": cfg, "passed": passed, "cost_usd": cost, "seconds": 10}

    def test_cheapest_within_one_task_of_best_wins(self):
        rows = ([self.row("C", True, 0.30)] * 10 + [self.row("C", False, 0.30)] * 0
                + [self.row("A", True, 0.12)] * 9 + [self.row("A", False, 0.12)]
                + [self.row("H", True, 0.04)] * 6 + [self.row("H", False, 0.04)] * 4)
        table = run_eval.summarize(rows, n_tasks=10)
        chosen = [ln for ln in table.splitlines() if "← chọn" in ln]
        self.assertEqual(len(chosen), 1)
        self.assertTrue(chosen[0].startswith("| A |"), table)


class RunnerEndToEnd(TempDirTestCase):
    def test_run_one_with_fake_claude(self):
        fake = self.tmp / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        os.environ["AGENT_STACK_CLAUDE_BIN"] = str(fake)
        os.environ["FAKE_ARGS"] = str(self.tmp / "args.json")
        self.addCleanup(os.environ.pop, "AGENT_STACK_CLAUDE_BIN", None)
        self.addCleanup(os.environ.pop, "FAKE_ARGS", None)
        task = run_eval.TASKS / "code-off-by-one"
        work = self.tmp / "work"
        run_eval.prepare(task, work)
        row = run_eval.run_one({"name": "A", "model": "sonnet", "effort": "medium"}, task, work, 0.5)
        self.assertTrue(row["passed"], row)
        self.assertEqual(row["cost_usd"], 0.05)
        args = json.loads((self.tmp / "args.json").read_text())
        for flag in ("--model", "--effort", "--no-session-persistence", "--max-budget-usd", "--setting-sources"):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--model") + 1], "sonnet")


if __name__ == "__main__":
    unittest.main()
