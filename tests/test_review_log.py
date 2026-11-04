"""Test cho nhật ký review của done-gate (review_log.py): ghi lỗi nào do reviewer nào tìm, rồi tổng hợp."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase

SCRIPT = PLUGIN / "skills" / "done-gate" / "scripts" / "review_log.py"


class ReviewLog(TempDirTestCase):
    def run_log(self, *args):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"))
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env,
                              cwd=str(self.tmp))

    def records(self):
        path = self.tmp / "state" / "review-log.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def test_add_then_summary_counts_by_reviewer(self):
        out = self.run_log("add", "--writer", "claude-opus-5-5", "--level", "cao", "--reviewers", "opus,sonnet",
                           "--task", "hook git", "--found", "opus:vua:sua:thiếu kiểm rebase",
                           "--found", "sonnet:cao:sua:rm -rf lọt qua: thư mục symlink",
                           "--found", "both:thap:sua:thông điệp sai", "--found", "sonnet:vua:bac-bo:báo nhầm")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.run_log("add", "--writer", "sonnet", "--level", "cao", "--reviewers", "opus,sonnet")
                         .returncode, 0)
        self.assertEqual(self.run_log("add", "--writer", "opus", "--level", "vua", "--reviewers", "sonnet",
                                      "--found", "sonnet:thap:sua:x").returncode, 0)
        recs = self.records()
        self.assertEqual(len(recs), 3)
        self.assertEqual((recs[0]["writer"], recs[0]["reviewers"]), ("opus", ["opus", "sonnet"]))
        self.assertEqual(recs[0]["findings"][1], {"by": "sonnet", "severity": "cao", "verdict": "sua",
                                                  "text": "rm -rf lọt qua: thư mục symlink"})
        s = json.loads(self.run_log("summary", "--json").stdout)
        self.assertEqual((s["runs"], s["dual_runs"]), (3, 2))
        self.assertEqual(s["real"], {"opus": 1, "sonnet": 1, "both": 1})
        self.assertEqual(s["false"], {"opus": 0, "sonnet": 1, "both": 0})
        # Opus viết: lỗi chỉ Sonnet tìm là của reviewer khác model.
        self.assertEqual((s["other_only"], s["same_only"]), (1, 1))
        text = self.run_log("summary").stdout
        self.assertIn("Review kép: 2 lần", text)
        self.assertIn("chỉ Opus tìm 1, chỉ Sonnet tìm 1, cả hai 1", text)
        self.assertIn("chưa đủ để kết luận", text)

    def test_fable_counts_as_opus_and_hoi_counts_as_real_and_days_filter(self):
        self.run_log("add", "--writer", "claude-fable-5-1", "--level", "cao", "--reviewers", "opus,sonnet",
                     "--found", "sonnet:vua:hoi:đụng ý định", "--found", "opus:thap:sua:x")
        self.run_log("add", "--writer", "claude-haiku-5-5", "--level", "cao", "--reviewers", "opus,sonnet",
                     "--found", "opus:vua:sua:y")
        s = json.loads(self.run_log("summary", "--json").stdout)
        self.assertEqual(s["real"], {"opus": 2, "sonnet": 1, "both": 0})
        # Fable viết (như Opus): lỗi chỉ Sonnet tìm là khác model; Haiku viết (như Sonnet): lỗi chỉ Opus tìm là khác model.
        self.assertEqual((s["other_only"], s["same_only"], s["unknown_writer"]), (2, 1, 0))
        path = self.tmp / "state" / "review-log.jsonl"
        old = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        old["ts"] -= 10 * 86400
        path.write_text(json.dumps(old) + "\n" + path.read_text(encoding="utf-8").splitlines()[1] + "\n",
                        encoding="utf-8")
        recent = json.loads(self.run_log("summary", "--days", "7", "--json").stdout)
        self.assertEqual((recent["runs"], recent["real"]["opus"]), (1, 1))

    def test_bad_found_is_rejected_and_nothing_written(self):
        for bad in ("gpt:vua:sua:x", "opus:rat-cao:sua:x", "opus:vua:ok:x", "opus:vua"):
            with self.subTest(bad=bad):
                out = self.run_log("add", "--writer", "opus", "--level", "vua", "--reviewers", "opus",
                                   "--found", bad)
                self.assertEqual(out.returncode, 2)
                self.assertIn("Không ghi", out.stderr)
        # Gán lỗi cho reviewer không chạy, hay "both" khi chỉ có một reviewer.
        self.assertEqual(self.run_log("add", "--writer", "opus", "--level", "vua", "--reviewers", "sonnet",
                                      "--found", "opus:vua:sua:x").returncode, 2)
        self.assertEqual(self.run_log("add", "--writer", "opus", "--level", "vua", "--reviewers", "sonnet",
                                      "--found", "both:vua:sua:x").returncode, 2)
        self.assertEqual(self.records(), [])

    def test_summary_without_dual_runs_and_with_broken_lines(self):
        state = self.tmp / "state"
        state.mkdir()
        (state / "review-log.jsonl").write_text('không phải json\n{"ts": "x"}\n', encoding="utf-8")
        out = self.run_log("summary")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Chưa có lần review kép", out.stdout)


if __name__ == "__main__":
    import unittest
    unittest.main()
