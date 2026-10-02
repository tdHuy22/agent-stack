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
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = run_eval.self_test(run_eval.load_tasks("all"))
        self.assertEqual(code, 0, buf.getvalue())

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
        return {"config": cfg, "passed": passed, "cost_usd": cost, "seconds": 10, "cluster": "dat"}

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
        row, patch = run_eval.run_one({"name": "A", "model": "sonnet", "effort": "medium"}, task, work, 0.5)
        self.assertTrue(row["passed"], row)
        self.assertEqual(row["cluster"], "dat")
        self.assertEqual(row["cost_usd"], 0.05)
        self.assertEqual(row["answer"], "Đã sửa.")
        self.assertEqual((row["input_digest"], row["grader_digest"]), run_eval.digests(task))
        self.assertIn(b"(page - 1) * per_page", patch)
        args = json.loads((self.tmp / "args.json").read_text())
        for flag in ("--model", "--effort", "--no-session-persistence", "--max-budget-usd", "--setting-sources"):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--model") + 1], "sonnet")


class Isolation(TempDirTestCase):
    """Model không được thấy CLAUDE.md của repo, grader hay lời giải."""

    def test_default_work_root_is_outside_repo(self):
        root = run_eval.default_work_root().resolve()
        self.assertNotIn(run_eval.REPO, root.parents)
        self.assertEqual([x for x in run_eval.context_leaks(root) if "agent-stack" in x], [])

    def test_work_root_inside_repo_is_refused(self):
        leaks = run_eval.context_leaks(run_eval.REPO / ".tmp" / "eval")
        self.assertTrue(any("nằm trong agent-stack" in x for x in leaks), leaks)
        self.assertTrue(any(x.endswith("CLAUDE.md") for x in leaks), leaks)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = run_eval.main(["--configs", "A", "--tasks", "code-off-by-one", "--work-root",
                                  str(run_eval.REPO / ".tmp" / "eval")])
        self.assertEqual(code, 2, buf.getvalue())

    def test_instruction_file_in_parent_is_reported(self):
        self.write("outer/AGENTS.md", "luật")
        self.assertTrue(any(x.endswith("outer/AGENTS.md") for x in run_eval.context_leaks(self.tmp / "outer" / "w")))

    def test_freeze_and_replay_roundtrip(self):
        task = run_eval.TASKS / "code-off-by-one"
        work = self.tmp / "w1"
        run_eval.prepare(task, work)
        (work / "pager.py").write_text((work / "pager.py").read_text() + "# sửa\n")
        (work / "notes").mkdir()
        (work / "notes" / "new.txt").write_text("file mới\n")
        (work / "__pycache__").mkdir()
        (work / "__pycache__" / "x.pyc").write_bytes(bytes([0, 1, 2]))
        patch = run_eval.freeze(work)
        self.assertNotIn(b"__pycache__", patch)
        replay = self.tmp / "w2"
        run_eval.prepare(task, replay)
        ok, err = run_eval.apply_patch(replay, patch)
        self.assertTrue(ok, err)
        self.assertTrue((replay / "pager.py").read_text().endswith("# sửa\n"))
        self.assertEqual((replay / "notes" / "new.txt").read_text(), "file mới\n")


class Classification(unittest.TestCase):
    def test_clusters(self):
        self.assertEqual(run_eval.classify({}, timed_out=True)[0], "van-hanh")
        self.assertEqual(run_eval.classify({"is_error": True, "result": "OAuth session expired"}, False)[0], "moi-truong")
        self.assertEqual(run_eval.classify({"is_error": True, "subtype": "error_max_budget_usd"}, False),
                         ("van-hanh", "chạm trần chi phí mỗi lượt"))
        # câu trả lời bình thường có nhắc "rate limit" (việc doc-ratelimit) không phải lỗi môi trường
        self.assertEqual(run_eval.classify({"result": "Rate limit là 100 request/phút."}, False), ("", ""))


class Matrix(unittest.TestCase):
    def rows(self, configs="AC", tasks=("t1", "t2"), reps=2, **extra):
        return [dict({"config": c, "task": t, "passed": True, "cost_usd": 0.1, "seconds": 5, "cluster": "dat",
                      "input_digest": "i", "grader_digest": "g"}, **extra)
                for c in configs for t in tasks for _ in range(reps)]

    def test_complete_matrix_has_no_problems(self):
        self.assertEqual(run_eval.matrix_problems(self.rows()), [])

    def test_missing_cell_blocks_choice(self):
        rows = [r for r in self.rows() if not (r["config"] == "C" and r["task"] == "t2")]
        problems = run_eval.matrix_problems(rows)
        self.assertTrue(any("thiếu 1 ô" in p for p in problems), problems)
        self.assertNotIn("← chọn", run_eval.summarize(rows))

    def test_environment_failure_blocks_choice(self):
        rows = self.rows()
        rows[0] = dict(rows[0], cluster="moi-truong", passed=False)
        self.assertTrue(any("môi trường" in p for p in run_eval.matrix_problems(rows)))

    def test_uneven_repeats_and_changed_grader(self):
        rows = self.rows() + [self.rows(configs="A", tasks=("t1",), reps=1, grader_digest="g2")[0]]
        problems = " | ".join(run_eval.matrix_problems(rows))
        self.assertIn("không đều", problems)
        self.assertIn("--regrade", problems)

    def test_operational_failures_count_as_fail_and_are_shown(self):
        rows = self.rows()
        rows[0] = dict(rows[0], cluster="van-hanh", passed=False)
        table = run_eval.summarize(rows)
        self.assertIn("| A | 4 | 75% | 1 |", table)


class Regrade(TempDirTestCase):
    def test_regrade_uses_current_grader(self):
        task = run_eval.TASKS / "code-off-by-one"
        results = self.tmp / "results"
        work = self.tmp / "w"
        run_eval.prepare(task, work)
        run_eval.overlay_solution(task, work)
        patch_rel = "s/A/code-off-by-one-0.patch"
        (results / "s" / "A").mkdir(parents=True)
        (results / patch_rel).write_bytes(run_eval.freeze(work))
        inp, _ = run_eval.digests(task)
        row = {"config": "A", "task": "code-off-by-one", "rep": 0, "passed": False, "why": "grader cũ",
               "cluster": "chat-luong", "answer": "", "patch": patch_rel, "input_digest": inp, "grader_digest": "cu"}
        src = results / "s.jsonl"
        src.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(run_eval.main(["--regrade", str(src)]), 0)
        new = json.loads((results / "s.regraded.jsonl").read_text(encoding="utf-8"))
        self.assertTrue(new["passed"], buf.getvalue())
        self.assertEqual(new["grader_digest"], run_eval.digests(task)[1])
        self.assertIn("trượt → đạt", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
