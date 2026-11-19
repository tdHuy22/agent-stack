"""Luật cắt vòng lặp của done-gate (việc 2 trong PLAN §0, F1b 20/11/2026) và đo thời gian từng phần của mutation
(việc 1b, mục c).

- review_log.py: kết quả `ghi` (lỗi thật mức thấp, ghi để sửa sau) chỉ nhận mức thap; `pending` liệt kê chúng.
- mutation.py: JSON `phases` và dòng `- thời gian:` (trước dòng `Mutation:`), không có khi chưa chạy.
- Tài liệu: done-gate nói tối đa 2 vòng sửa rồi review lại, README khớp; hai SKILL.md chỉ cách dùng bộ test thu hẹp.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time

from tests._util import PLUGIN, REPO, TempDirTestCase
from tests.test_mutation import CMD, MutationBase

SCRIPTS = PLUGIN / "skills" / "done-gate" / "scripts"
REVIEW_LOG = SCRIPTS / "review_log.py"
sys.path.insert(0, str(SCRIPTS))
import mutation as M  # noqa: E402
import review_log as RL  # noqa: E402


class LowFindingsAreLogged(TempDirTestCase):
    def run_log(self, *args, cwd=None):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"))
        return subprocess.run([sys.executable, str(REVIEW_LOG), *args], capture_output=True, text=True, env=env,
                              cwd=str(cwd or self.tmp))

    def records(self):
        path = self.tmp / "state" / "review-log.jsonl"
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def add(self, *found, task="việc", cwd=None):
        args = ["add", "--writer", "opus", "--level", "vua", "--reviewers", "sonnet:high", "--task", task]
        for f in found:
            args += ["--found", f]
        return self.run_log(*args, cwd=cwd)

    def test_ghi_accepted_for_low_severity(self):
        out = self.add("sonnet:thap:ghi:x.py:3 tên biến khó hiểu")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.records()[0]["findings"],
                         [{"by": "sonnet", "severity": "thap", "verdict": "ghi", "text": "x.py:3 tên biến khó hiểu"}])

    def test_ghi_refused_for_medium_or_high(self):
        for severity in ("vua", "cao"):
            with self.subTest(severity=severity):
                out = self.add(f"sonnet:{severity}:ghi:lỗi thật")
                self.assertEqual(out.returncode, 2, out.stdout)
                self.assertIn("chỉ cho lỗi mức thap", out.stderr)
        self.assertEqual(self.records(), [], "lần ghi bị từ chối không được để lại dòng nào")

    def test_pending_lists_only_ghi_of_this_project_newest_first(self):
        proj, other = self.tmp / "proj", self.tmp / "khac"
        for d in (proj, other):
            (d / ".git").mkdir(parents=True)
        self.assertEqual(self.add("sonnet:thap:ghi:cũ", "sonnet:vua:sua:đã sửa", task="một", cwd=proj).returncode, 0)
        time.sleep(1.1)  # ts tính bằng giây
        self.assertEqual(self.add("sonnet:thap:ghi:mới", "sonnet:thap:bac-bo:báo nhầm", task="hai", cwd=proj)
                         .returncode, 0)
        self.assertEqual(self.add("sonnet:thap:ghi:của project khác", cwd=other).returncode, 0)
        out = self.run_log("pending", cwd=proj)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2, out.stdout)
        self.assertTrue(lines[0].endswith("hai: mới"), lines)
        self.assertTrue(lines[1].endswith("một: cũ"), lines)
        everywhere = self.run_log("pending", "--all-projects", cwd=proj).stdout
        self.assertIn("[khac]: của project khác", everywhere)

    def test_pending_empty_message(self):
        out = self.run_log("pending")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Không có lỗi mức thấp nào", out.stdout)

    def test_ghi_counts_as_real_finding_in_summary(self):
        recs = [{"ts": 1, "writer": "opus", "level": "vua", "reviewers": ["sonnet"], "configs": ["sonnet:high"],
                 "findings": [{"by": "sonnet", "severity": "thap", "verdict": "ghi", "text": "x"}]}]
        s = RL.summarize(recs)
        self.assertEqual(s["by_config"]["sonnet:high"]["real"], 1)
        self.assertEqual(s["by_config"]["sonnet:high"]["false"], 0)


class MutationPhases(MutationBase):
    def setUp(self):
        super().setUp()
        self.init_repo()
        self.change_code()
        self.cmd = ["--cmd", shlex.join(CMD)]  # dạng `python3 -m unittest <module>`: có bước ghi vết

    def test_json_has_phase_seconds(self):
        out = self.mut("--json", *self.cmd, *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data = json.loads(out.stdout)
        phases = data.get("phases")
        self.assertIsInstance(phases, dict, data)
        for key in ("copy", "mutants", "collect"):
            self.assertIn(key, phases)
            self.assertGreaterEqual(phases[key], 0)
        self.assertEqual(data["selection"], "theo dòng", data)  # bước ghi vết đã chạy thì có thời gian của nó
        self.assertGreaterEqual(phases["trace"], 0)

    def test_no_trace_phase_when_selection_off_by_flag(self):
        data = json.loads(self.mut("--json", "--no-select", *self.cmd, *self.fake_args()).stdout)
        self.assertNotIn("trace", data["phases"])

    def test_text_line_before_status_line(self):
        out = self.mut(*self.cmd, *self.fake_args())
        lines = [x for x in out.stdout.splitlines() if x.strip()]
        timing = [x for x in lines if x.startswith("- thời gian:")]
        self.assertEqual(len(timing), 1, out.stdout)
        self.assertIn("chạy đột biến", timing[0])
        self.assertTrue(lines[-1].startswith("Mutation:"), lines[-1])

    def test_skipped_run_has_no_timing_line(self):
        out = self.mut(*self.cmd, "--mutmut", str(self.tmp / "khong-co"))
        self.assertNotIn("thời gian:", out.stdout)
        self.assertIn("chưa chạy:", out.stdout)

    def test_phase_lines_order_and_rounding(self):
        lines = M.phase_lines({"phases": {"mutants": 600.4, "trace": 119.6, "retry": 2.0}})
        self.assertEqual(lines, ["- thời gian: ghi vết (gồm chạy riêng từng test) 120 giây, chạy đột biến 600 giây, "
                                 "chạy lại một mình 2 giây"])
        self.assertEqual(M.phase_lines({}), [])


class RulesInDocs(TempDirTestCase):
    def read(self, rel):
        return (REPO / rel).read_text(encoding="utf-8")

    def test_done_gate_caps_rereview_at_two_rounds(self):
        text = self.read("plugin/skills/done-gate/SKILL.md")
        self.assertIn("tối đa 2 vòng sửa rồi review lại", text)
        self.assertIn("Hết 2 vòng", text)
        self.assertNotIn("3 vòng", text)
        self.assertIn("thap:ghi:", text, "lỗi mức thấp phải có chỗ ghi")
        self.assertIn("không tự thêm test, mở vòng sửa hay phiên mới", text)

    def test_readme_matches_round_cap(self):
        text = self.read("README.md")
        self.assertIn("tối đa 2 vòng sửa rồi review lại", text)
        self.assertNotIn("tối đa 3 vòng sửa", text)

    def test_both_skills_explain_narrow_suite(self):
        for rel in ("plugin/skills/done-gate/SKILL.md", "plugin/skills/session-keeper/SKILL.md"):
            with self.subTest(rel=rel):
                text = self.read(rel)
                for words in ("narrow.py", " run", "narrow.py status", "narrow.py record", "sh -c", "make",
                              "đúng một lần", "không thay biên nhận cả bộ"):
                    self.assertIn(words, text)
