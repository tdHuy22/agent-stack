"""Bộ đo riêng cho skill trong evals/ (suite), so hai phiên bản plugin, và grader của bộ reuse-best."""
import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

from tests._util import REPO, TempDirTestCase

sys.path.insert(0, str(REPO / "evals"))
import run_eval  # noqa: E402

REUSE_TASKS = ["reuse-constraint", "reuse-gap", "reuse-scale", "reuse-stdlib"]

# Giả lập stream-json có gọi skill: tool_use mang id, kết quả của skill quay về trong một tool_result.
FAKE_CLAUDE_SKILL = """#!/usr/bin/env python3
import json, sys, os
args = sys.argv[1:]
open(os.environ["FAKE_ARGS"], "w").write(json.dumps(args))
report = ("tools/md_links.py: anchor_exists() luôn trả True (TODO), không kiểm anchor. "
          "Dùng lychee với --include-fragments.")
events = [
    {"type": "system", "subtype": "init"},
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "toolu_1", "name": "Skill", "input": {"skill": "agent-stack:reuse-best"}}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": [{"type": "text", "text": report}]}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_other", "content": "kết quả của Read, không phải skill"}]}},
    {"type": "result", "result": report, "total_cost_usd": 0.3, "num_turns": 5, "is_error": False},
]
for e in events:
    print(json.dumps(e))
"""


def make_plugin(root, version="9.9.9"):
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "agent-stack", "version": version}))
    (root / "skills" / "reuse-best").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "reuse-best" / "SKILL.md").write_text("---\nname: reuse-best\n---\nbản thử\n")
    return root


class SuiteSelection(TempDirTestCase):
    def fake_tasks(self):
        for name, meta in (("t-normal", {}), ("t-skill", {"suite": "x"}), ("t-other", {"suite": "y"})):
            self.write(f"tasks/{name}/task.md", "đề")
            self.write(f"tasks/{name}/meta.json", json.dumps(meta))
        return self.tmp / "tasks"

    def test_suite_tasks_stay_out_of_config_runs(self):
        with mock.patch.object(run_eval, "TASKS", self.fake_tasks()):
            names = lambda tasks: [t.name for t in tasks]  # noqa: E731
            self.assertEqual(names(run_eval.load_tasks("all")), ["t-normal", "t-other", "t-skill"])
            self.assertEqual(names(run_eval.load_tasks("all", suites=False)), ["t-normal"])
            self.assertEqual(names(run_eval.load_tasks("suite:x")), ["t-skill"])
            self.assertEqual(names(run_eval.load_tasks("t-skill,t-normal")), ["t-normal", "t-skill"])
            self.assertEqual(run_eval.load_tasks("suite:khong-co"), [])
            self.assertEqual(run_eval.load_tasks("suite:"), [], "tên bộ đo rỗng không được trả về cả bộ chọn cấu hình")

    def test_real_reuse_best_suite(self):
        self.assertEqual([t.name for t in run_eval.load_tasks("suite:reuse-best")], REUSE_TASKS)
        config_tasks = {t.name for t in run_eval.load_tasks("all", suites=False)}
        self.assertFalse(config_tasks & set(REUSE_TASKS), "việc đo skill lọt vào bộ chọn cấu hình")
        self.assertIn("code-off-by-one", config_tasks)

    def test_broken_meta_is_not_a_suite(self):
        self.write("t/meta.json", "{hỏng")
        self.assertEqual(run_eval.task_suite(self.tmp / "t"), "")
        self.assertEqual(run_eval.task_suite(self.tmp / "khong-co"), "")


class PluginVersions(TempDirTestCase):
    def test_digest_tracks_content_but_not_eval_results_or_caches(self):
        root = make_plugin(self.tmp / "p")
        first = run_eval.plugin_digest(root)
        self.write("p/evals/results/x.json", "{}")
        self.write("p/skills/reuse-best/scripts/__pycache__/scout.cpython-311.pyc", "x")
        self.write("p/.agent-stack-home", "/somewhere")
        self.assertEqual(run_eval.plugin_digest(root), first)
        self.write("p/skills/reuse-best/SKILL.md", "---\nname: reuse-best\n---\nbản sửa\n")
        self.assertNotEqual(run_eval.plugin_digest(root), first)

    def test_plugin_root_replaces_only_agent_stack(self):
        cfg = {"name": "X", "plugin": True, "plugins": ["vendor"]}
        self.assertEqual(run_eval.plugin_paths(cfg), [REPO / "plugin", REPO / "vendor"])
        self.assertEqual(run_eval.plugin_paths(cfg, self.tmp / "old"), [self.tmp / "old", REPO / "vendor"])
        self.assertEqual(run_eval.plugin_paths({"name": "A"}, self.tmp / "old"), [])

    def test_mixed_plugin_versions_block_comparison(self):
        rows = [{"config": c, "task": "t", "passed": True, "cost_usd": 0.1, "seconds": 1, "cluster": "dat",
                 "input_digest": "i", "grader_digest": "g", "plugin_digests": {"plugin": d}}
                for c, d in (("E", "aaa"), ("E", "bbb"), ("A", "ccc"))]
        problems = " | ".join(run_eval.matrix_problems(rows))
        self.assertIn("plugin khác phiên bản", problems)
        self.assertIn("E", problems)
        tagged = [dict(r, config="E@old") if r["plugin_digests"]["plugin"] == "aaa" else r for r in rows]
        self.assertNotIn("plugin khác phiên bản", " | ".join(run_eval.matrix_problems(tagged)))

    def test_main_requires_tag_and_a_real_plugin_dir(self):
        def run(*extra):
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                code = run_eval.main(["--configs", "E", "--tasks", "suite:reuse-best", *extra])
            return code, buf.getvalue()
        root = make_plugin(self.tmp / "old")
        code, out = run("--plugin-root", str(self.tmp / "khong-co"), "--tag", "cu")
        self.assertEqual(code, 2, out)
        code, out = run("--plugin-root", str(root))
        self.assertEqual(code, 2, out)
        self.assertIn("--tag", out)
        code, out = run("--plugin-root", str(root), "--tag", "cu")
        self.assertEqual(code, 0, out)
        self.assertIn("E@cu", out)
        self.assertIn(str(root.resolve()), out)
        self.assertIn("× 4 việc", out)
        code, out = run("--tasks", "suite:khong-co")
        self.assertEqual(code, 2, out)
        code, out = run("--tasks", "suite:reuse_best", "--self-test")
        self.assertEqual(code, 2, "self-test với tên bộ đo gõ sai phải báo lỗi, không được thoát 0")


class SkillRun(TempDirTestCase):
    def test_run_one_loads_given_plugin_and_keeps_skill_output(self):
        fake = self.tmp / "claude"
        fake.write_text(FAKE_CLAUDE_SKILL)
        fake.chmod(0o755)
        os.environ["AGENT_STACK_CLAUDE_BIN"] = str(fake)
        os.environ["FAKE_ARGS"] = str(self.tmp / "args.json")
        self.addCleanup(os.environ.pop, "AGENT_STACK_CLAUDE_BIN", None)
        self.addCleanup(os.environ.pop, "FAKE_ARGS", None)
        root = make_plugin(self.tmp / "old")
        task = run_eval.TASKS / "reuse-gap"
        work = self.tmp / "work"
        run_eval.prepare(task, work)
        stream = self.tmp / "streams" / "reuse-gap-0.stream.jsonl"
        cfg = {"name": "E@cu", "model": "sonnet", "effort": "medium", "plugin": True}
        row, patch = run_eval.run_one(cfg, task, work, 0.5, plugin_root=root, stream_file=stream)
        args = json.loads((self.tmp / "args.json").read_text())
        self.assertEqual(args[args.index("--plugin-dir") + 1], str(root))
        self.assertEqual(row["skills_used"], ["agent-stack:reuse-best"])
        self.assertEqual(len(row["skill_outputs"]), 1, "chỉ giữ kết quả của lần gọi skill, không lấy tool khác")
        self.assertIn("anchor_exists", row["skill_outputs"][0]["text"])
        self.assertEqual(row["plugin_digests"], {"plugin": run_eval.plugin_digest(root)})
        self.assertEqual(row["suite"], "reuse-best")
        self.assertTrue(row["passed"], row["why"])
        self.assertEqual(patch.strip(), b"")
        self.assertIn('"tool_result"', stream.read_text())

    def test_parse_output_handles_string_results_and_unknown_ids(self):
        lines = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "a", "name": "Skill", "input": {"skill": "s1"}},
                {"type": "tool_use", "name": "Skill", "input": {"skill": "s2"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "x" * (run_eval.SKILL_OUTPUT_CHARS + 50)},
                {"type": "tool_result", "content": "không có id"}]}},
            {"type": "result", "result": "xong"},
        ]
        data, skills, outputs = run_eval.parse_output("\n".join(json.dumps(x) for x in lines))
        self.assertEqual(data["result"], "xong")
        self.assertEqual(skills, ["s1", "s2"])
        self.assertEqual([o["skill"] for o in outputs], ["s1"])
        self.assertEqual(len(outputs[0]["text"]), run_eval.SKILL_OUTPUT_CHARS)
        self.assertEqual(run_eval.parse_output('{"result": "một JSON"}'), ({"result": "một JSON"}, [], []))
        self.assertEqual(run_eval.parse_output("không phải JSON"), (None, [], []))


class SuiteSummary(unittest.TestCase):
    def rows(self):
        out = []
        for config, passes in (("E@cu", (False, True)), ("E@moi", (True, True))):
            for rep, ok in enumerate(passes):
                for task in ("reuse-gap", "reuse-scale"):
                    out.append({"config": config, "task": task, "passed": ok if task == "reuse-gap" else True,
                                "cost_usd": 0.4, "seconds": 90, "cluster": "dat" if ok else "chat-luong",
                                "input_digest": "i", "grader_digest": "g", "suite": "reuse-best", "rep": rep})
        return out

    def test_skill_suites_report_per_task_and_pick_no_config(self):
        table = run_eval.summarize(self.rows())
        self.assertNotIn("← chọn", table)
        self.assertIn("Bộ đo skill", table)
        self.assertIn("| reuse-gap | 1/2 | 2/2 |", table)
        self.assertIn("| reuse-scale | 2/2 | 2/2 |", table)

    def test_config_runs_still_pick_cheapest(self):
        rows = [dict(r, suite=None) for r in self.rows()]
        for r in rows:
            r.pop("suite")
        self.assertIn("← chọn", run_eval.summarize(rows))


class TraceStats(TempDirTestCase):
    """trace_stats.py đếm đúng những gì đã thấy trong lượt chạy thật ngày 07/10/2026."""

    def stream(self):
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "s", "name": "Skill", "input": {"skill": "agent-stack:reuse-best"}}]}},
            {"type": "assistant", "parent_tool_use_id": "s", "message": {"content": [
                {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "S=/x/scout.py; python3 $S github x"}},
                {"type": "tool_use", "id": "b2", "name": "Bash",
                 "input": {"command": "python3 /x/scripts/scout.py github \"toml parser python\" --language python"}},
                {"type": "tool_use", "id": "b3", "name": "Bash", "input": {"command": "python3 /x/scout.py repo hukkin/tomli"}},
                {"type": "tool_use", "id": "b4", "name": "Bash", "input": {"command": "gh repo view hukkin/tomli"}},
                {"type": "tool_use", "id": "w", "name": "WebFetch", "input": {"url": "https://github.com/x"}},
                {"type": "tool_use", "id": "r", "name": "Read", "input": {"file_path": "/w/a.py"}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "b2", "content": "| Repo |\nKhông có kết quả (GitHub vẫn trả lời)"},
                {"type": "tool_result", "tool_use_id": "s", "content": [{"type": "text", "text":
                    "tomli: chưa kiểm số sao. Theo hiểu biết của mình nó có --include-fragments; gh bị chặn."}]}]}},
            {"type": "result", "permission_denials": [{"tool_name": "Bash"}, {"tool_name": "WebFetch"}]},
        ]
        return "\n".join(json.dumps(e) for e in events)

    def test_stream_stats(self):
        import trace_stats
        stats = trace_stats.stream_stats(self.stream())
        self.assertEqual(stats, {"bash": 4, "compound": 1, "denied": 2, "scout_github": 2, "scout_repo": 1,
                                 "scout_papers": 0, "empty_search": 1, "gh_or_web": 2, "unverified": 3})

    def test_table_from_results_file(self):
        import trace_stats
        self.write("r/20261007-1/E@cu/reuse-gap-0.stream.jsonl", self.stream())
        rows = [{"config": "E@cu", "task": "reuse-gap", "rep": 0, "passed": True, "cost_usd": 0.2, "seconds": 40,
                 "patch": "20261007-1/E@cu/reuse-gap-0.patch"},
                {"config": "E@cu", "task": "reuse-gap", "rep": 1, "passed": False, "cost_usd": 0.3, "seconds": 50,
                 "patch": "20261007-1/E@cu/reuse-gap-1.patch"}]
        self.write("r/20261007-1.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
        runs = trace_stats.load([self.tmp / "r" / "20261007-1.jsonl"])
        self.assertEqual(len(runs), 1, "lượt không có luồng sự kiện thì bỏ qua")
        table = trace_stats.render(runs)
        self.assertIn("| E@cu | 1 | 100% | 0.200 | 40.0 | 4.0 | 1.0 | 2.0 |", table)
        self.assertIn("--save-streams", trace_stats.render([]))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(trace_stats.main([]), 2)


class ScratchDirs(unittest.TestCase):
    def test_each_call_gets_its_own_dir(self):
        a, b = run_eval.scratch_dir("t-"), run_eval.scratch_dir("t-")
        self.addCleanup(lambda: [p.rmdir() for p in (a, b)])
        self.assertNotEqual(a, b)
        self.assertEqual(a.parent, REPO / ".tmp")


class ReuseBestGraders(unittest.TestCase):
    """Grader phải chấm theo ý, không theo chữ: câu đúng viết kiểu khác vẫn đạt, câu sai có đủ từ khóa vẫn trượt."""

    def grade(self, task, answer):
        return run_eval.load_check(run_eval.TASKS / task)(None, answer)

    def assertGrades(self, task, good, bad):
        for answer in good:
            with self.subTest(task=task, kind="đúng", answer=answer[:60]):
                ok, why = self.grade(task, answer)
                self.assertTrue(ok, why)
        for answer in bad:
            with self.subTest(task=task, kind="sai", answer=answer[:60]):
                self.assertFalse(self.grade(task, answer)[0])

    def test_reuse_gap(self):
        self.assertGrades("reuse-gap", good=[
            "tools/md_links.py looks complete, but anchor_exists() is a stub that always returns True and external "
            "links are skipped. Use lychee with --include-fragments.",
            "md_links.py không thật sự kiểm anchor: hàm anchor_exists còn TODO. Nên dùng markdown-link-check.",
            "Trong repo có tools/md_links.py nhưng thiếu phần kiểm anchor và bỏ qua link ngoài; linkinator làm đủ cả hai.",
            "md_links.py chưa kiểm tra fragment (#canary vẫn qua). Đề xuất: lychee-action.",
            # câu đúng reviewer thấy bị chấm oan ở bản grader đầu
            "md_links.py bỏ qua việc so slug của heading: anchor_exists là hàm rỗng. Chọn lychee.",
            "Anchor: chưa được kiểm, vì anchor_exists (md_links.py:31-33) luôn return True. Dùng lychee.",
            # câu thật của skill (eval 07/10/2026), bị chấm oan khi "còn" bị coi là chữ nối
            "- Link tới `#muc`: chưa bắt được. `anchor_exists` còn TODO và luôn trả `True` (`md_links.py:31-33`).\n"
            "Dùng lychee cho link ngoài.",
            "- Loại 2 (`#mục`): `anchor_exists` (`md_links.py:31-33`) còn TODO và luôn trả `True`, nên link hỏng "
            "không bị bắt.\nQuyết định: dùng lại lychee.",
        ], bad=[
            "Dùng lại tools/md_links.py: nó đã kiểm link tới file và anchor; chỉ cần thêm phần link ngoài bằng lychee.",
            "md_links.py kiểm anchor; chưa kiểm link ngoài. Thêm lychee cho link ngoài.",
            "md_links.py đã kiểm cả file và anchor, chỉ thiếu link ngoài; dùng lychee.",
            "Dùng lychee với --include-fragments; anchor_exists luôn trả True.",
            "tools/md_links.py không kiểm anchor (anchor_exists luôn trả True). Sửa hàm đó rồi thêm phần link ngoài.",
            # câu của model đã tin docstring, lọt qua bản grader đầu (review 07/10/2026)
            "tools/md_links.py đã kiểm link file và anchor; chỉ chưa được viết phần link ngoài. Bổ sung lychee.",
            "tools/md_links.py không kiểm link ngoài, còn anchor thì đã kiểm đủ. Thêm lychee cho link ngoài.",
            "md_links.py kiểm file và heading; link ngoài là TODO. Dùng lychee cho link ngoài.",
            "md_links.py kiểm anchor nhưng chưa kiểm link ngoài. Dùng lychee cho phần đó.",
        ])

    def test_reuse_constraint(self):
        self.assertGrades("reuse-constraint", good=[
            "tomllib không có trên Python 3.9, và CONTRIBUTING.md cấm thêm gói ngoài. Đề xuất đổi release.toml sang JSON.",
            "tomllib requires Python 3.11 but the project supports 3.9 and is stdlib-only, so tomli cannot be added "
            "without your approval.",
            "tomllib chỉ có từ 3.11; project chạy Python 3.9 trên máy build offline, nên chép tomli vào repo cần bạn duyệt.",
            "tomllib requires 3.11; the project targets Python 3.9 and forbids third-party dependencies, so use JSON.",
            "tomllib cần 3.11 mà project chạy 3.9 và không cho thêm dependency ngoài. Đề xuất: tự viết bộ đọc tập con.",
            "tomllib chỉ có từ 3.11, project chạy 3.9 và chỉ dùng thư viện chuẩn. Các lựa chọn: thêm tomli vào "
            "requirements (bị loại vì trái luật), hoặc đổi sang JSON. Chọn JSON.",
            # câu thật của skill (eval 07/10/2026)
            "- `tomllib` chỉ có từ Python 3.11. `CONTRIBUTING.md:5` bắt chạy trên Python 3.9 của macOS, không gói ngoài, "
            "không cần mạng.\n- `tomli` là backport. Cài bằng pip thì thêm phụ thuộc, trái `CONTRIBUTING.md:5`.",
        ], bad=[
            "Dùng tomllib (thư viện chuẩn từ Python 3.11).",
            "tomllib có từ 3.11, project chạy 3.9 nên pip install tomli.",
            "Dùng tomli cho Python 3.9, vì đây là thư viện chuẩn trên các bản mới.",
            "Project chỉ dùng thư viện chuẩn và chạy Python 3.9: dùng tomllib.",
            # nhắc tên CONTRIBUTING mà quyết định trái luật (review 07/10/2026)
            "Ràng buộc từ project: Python 3.9 (pyproject.toml), CI 3.9/3.12, CONTRIBUTING.md. tomllib chỉ có từ 3.11. "
            "Quyết định: thêm tomli>=2 vào dependencies.",
            "tomllib chỉ có từ 3.11, project chạy 3.9 (CI, CONTRIBUTING) nên pip install tomli.",
            "tomllib chỉ có từ 3.11; project chạy 3.9 và chỉ dùng thư viện chuẩn. Quyết định: thêm tomli vào requirements.",
        ])

    def test_reuse_scale(self):
        self.assertGrades("reuse-scale", good=[
            "app/ratelimit.py lưu trong bộ nhớ nên mỗi worker có bộ đếm riêng; dùng Redis (INCR + EXPIRE).",
            "SlidingWindowLimiter is per-process; with 4 gunicorn workers and 3 replicas the limit is not shared. "
            "Use Redis via the limits library.",
            "Không dùng lại SlidingWindowLimiter: các tiến trình không dùng chung bộ đếm, mỗi key được tới 1.200 "
            "request/phút. Chuyển sang slowapi với kho Redis.",
            # câu đúng reviewer thấy bị chấm oan ở bản grader đầu
            "app/ratelimit.py chỉ đúng khi có một tiến trình: 4 workers × 3 replicas thì giới hạn thực là 12 lần. "
            "Dùng Redis.",
            "SlidingWindowLimiter: 12 process đếm độc lập nên giới hạn bị nhân 12. Đếm trong Redis.",
        ], bad=[
            "Dùng lại app/ratelimit.py (SlidingWindowLimiter, trong bộ nhớ) cho route; chạy với gunicorn.",
            "Dùng slowapi với Redis.",
            "app/ratelimit.py đếm trong bộ nhớ, đủ dùng; project cũng có Redis cho cache.",
            "app/ratelimit.py: mỗi worker gọi allow() trước khi xử lý request, gắn vào dependency api_key.",
            # chép lại đề ("vượt … thì trả 429") và phủ định Redis (review 07/10/2026)
            "Quyết định: dùng lại SlidingWindowLimiter trong app/ratelimit.py (đếm trong bộ nhớ): vượt 100 request/phút "
            "thì trả 429. Không cần thêm Redis.",
            "Dùng lại SlidingWindowLimiter cho từng worker riêng; không dùng Redis.",
        ])

    def test_reuse_stdlib(self):
        self.assertGrades("reuse-stdlib", good=[
            "Quyết định: dùng hashlib + os.walk, không thêm gói.",
            "Decision: use the standard library, hashlib.sha256 after grouping by size.",
            "Ứng viên: fdupes (brew install fdupes), bị loại vì là chương trình dòng lệnh. "
            "Quyết định: tự viết bằng hashlib và filecmp.",
            # câu đúng có phủ định, bị chấm oan ở bản grader đầu
            "Quyết định: tự viết bằng hashlib + os.walk, không cần pip install gì thêm.",
            "Quyết định: dùng thư viện chuẩn (hashlib), không phải brew install fdupes.",
            "Đề xuất các ứng viên: fdupes (brew install fdupes) bị loại vì là CLI; chọn hashlib.",
        ], bad=[
            "Quyết định: pip install dupeguru rồi gọi từ script.",
            "hashlib làm được nhưng chậm. Quyết định: brew install fdupes rồi gọi từ script.",
            "Dùng thư viện ngoài để tìm file trùng.",
            # thêm gói mà không dùng lệnh cài (review 07/10/2026)
            "Quyết định: dùng thư viện xxhash (nhanh hơn hashlib), thêm vào requirements.",
            "hashlib là đủ về lý thuyết. Đề xuất: thêm dependency `dupeguru` vào pyproject.",
        ])


if __name__ == "__main__":
    unittest.main()
