import json
import os
import subprocess
import time
import unittest

from tests._util import PLUGIN, REPO, TempDirTestCase, git
from tests.test_agentstack_lib import PLAN

HOOKS = PLUGIN / "hooks"
PYTHONS = [p for p in ("/usr/bin/python3",) if os.path.exists(p)] + ["python3"]


class HookTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.project = self.tmp / "proj"
        self.project.mkdir()

    def run_hook(self, name, payload, python="python3"):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state))
        start = time.time()
        out = subprocess.run([python, str(HOOKS / name)], input=json.dumps(payload), capture_output=True,
                             text=True, env=env, timeout=30)
        self.elapsed = time.time() - start
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stderr, "")
        return json.loads(out.stdout) if out.stdout.strip() else None

    def with_plan(self):
        (self.project / "PLAN.md").write_text(PLAN, encoding="utf-8")
        git(self.project, "init", "-q")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "init")

    def test_session_start_injects_plan_on_both_pythons(self):
        self.with_plan()
        for i, py in enumerate(PYTHONS):
            out = self.run_hook("session_start.py", {"session_id": f"s{i}", "source": "startup",
                                                     "cwd": str(self.project)}, python=py)
            ctx = out["hookSpecificOutput"]["additionalContext"]
            self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
            self.assertIn("Việc tiếp theo", ctx)
            self.assertIn("📍", out["systemMessage"])
            self.assertLess(self.elapsed, 3)

    def test_session_start_silent_without_plan(self):
        self.assertIsNone(self.run_hook("session_start.py", {"session_id": "s", "cwd": str(self.project)}))

    def test_session_start_dedupes_double_registration(self):
        self.with_plan()
        payload = {"session_id": "dup", "source": "startup", "cwd": str(self.project)}
        self.assertIsNotNone(self.run_hook("session_start.py", payload))
        self.assertIsNone(self.run_hook("session_start.py", payload))

    def test_compact_and_resume_variants(self):
        self.with_plan()
        out = self.run_hook("session_start.py", {"session_id": "c", "source": "compact", "cwd": str(self.project)})
        self.assertTrue(out["hookSpecificOutput"]["additionalContext"].startswith("Vừa compact"))
        out = self.run_hook("session_start.py", {"session_id": "r", "source": "resume", "cwd": str(self.project)})
        self.assertIn("git status", out["hookSpecificOutput"]["additionalContext"].split("resume")[-1])

    def write_limits(self, seven_day, five_hour=10, age=0):
        self.state.mkdir(exist_ok=True)
        (self.state / "limits.json").write_text(json.dumps({"ts": time.time() - age, "rate_limits": {
            "seven_day": {"used_percentage": seven_day, "resets_at": 1790000000},
            "five_hour": {"used_percentage": five_hour, "resets_at": 1780000000}}}))

    def test_prompt_submit_warns_once_per_threshold(self):
        self.write_limits(85)
        out = self.run_hook("prompt_submit.py", {"session_id": "p", "prompt": "làm tiếp"})
        self.assertIn("Hạn mức tuần đã dùng 85%", out["systemMessage"])
        self.assertIn("OpenCode", out["hookSpecificOutput"]["additionalContext"])
        again = self.run_hook("prompt_submit.py", {"session_id": "p", "prompt": "câu khác"})
        self.assertTrue(again is None or "tuần" not in again.get("systemMessage", ""))
        self.write_limits(96)
        higher = self.run_hook("prompt_submit.py", {"session_id": "p", "prompt": "câu thứ ba"})
        self.assertIn("96%", higher["systemMessage"])

    def test_prompt_submit_ignores_stale_limits(self):
        self.write_limits(99, age=3600)
        out = self.run_hook("prompt_submit.py", {"session_id": "q", "prompt": "x"})
        self.assertTrue(out is None or "Hạn mức" not in out.get("systemMessage", ""))

    def test_stop_reminds_after_several_changes_then_rate_limits(self):
        self.with_plan()
        past = time.time() - 3600
        os.utime(self.project / "PLAN.md", (past, past))
        for i in range(3):
            (self.project / f"f{i}.py").write_text("x\n")
        out = self.run_hook("stop.py", {"session_id": "st", "cwd": str(self.project)})
        self.assertIn("3 file", out["systemMessage"])
        self.assertNotIn("hookSpecificOutput", out)  # không thêm context: tránh Claude chạy thêm lượt
        self.assertIsNone(self.run_hook("stop.py", {"session_id": "st", "cwd": str(self.project)}))
        self.assertIsNone(self.run_hook("stop.py", {"session_id": "x", "cwd": str(self.project),
                                                    "stop_hook_active": True}))

    def test_session_end_is_fast_and_logged(self):
        self.assertIsNone(self.run_hook("session_end.py", {"session_id": "e", "cwd": "/x", "reason": "other"}))
        self.assertLess(self.elapsed, 1.0)
        line = (self.state / "sessions.jsonl").read_text().strip().splitlines()[-1]
        self.assertEqual(json.loads(line)["session"], "e")

    def test_bad_input_never_breaks_session(self):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state))
        for name in ("session_start.py", "prompt_submit.py", "pre_compact.py", "stop.py", "session_end.py"):
            out = subprocess.run(["python3", str(HOOKS / name)], input="not json", capture_output=True,
                                 text=True, env=env, timeout=30)
            self.assertEqual(out.returncode, 0, name)


class HooksConfig(unittest.TestCase):
    def test_hooks_json_points_to_existing_scripts(self):
        data = json.loads((HOOKS / "hooks.json").read_text())
        for event, groups in data["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    with self.subTest(event=event):
                        script = hook["args"][0].replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
                        self.assertTrue(os.path.exists(script), script)
                        self.assertLessEqual(hook["timeout"], 10)

    def test_statusline_writes_limits(self):
        state = REPO / ".tmp" / f"sl-{os.getpid()}"
        payload = {"model": {"display_name": "Sonnet 5.5"}, "effort": {"level": "medium"},
                   "context_window": {"used_percentage": 23.4},
                   "rate_limits": {"five_hour": {"used_percentage": 41}, "seven_day": {"used_percentage": 88}}}
        out = subprocess.run(["python3", str(REPO / "statusline" / "statusline.py")], input=json.dumps(payload),
                             capture_output=True, text=True, timeout=30,
                             env=dict(os.environ, AGENT_STACK_STATE=str(state), NO_COLOR="1"))
        self.assertEqual(out.stdout, "Sonnet 5.5 · medium · ctx 23% · 5h 41% · 7d 88%")
        saved = json.loads((state / "limits.json").read_text())
        self.assertEqual(saved["rate_limits"]["seven_day"]["used_percentage"], 88)
        import shutil
        shutil.rmtree(state, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
