import json
import sys
import unittest

from tests._util import REPO, TempDirTestCase, jsonl, run_script

sys.path.insert(0, str(REPO / "tools"))
import usage_snapshot as us  # noqa: E402

NOW = "2026-10-01T12:00:00Z"


def assistant(msg_id, model, ts, inp=10, out=100, read=1000, write=0, sidechain=False, req="r1", cwd="/x/proj"):
    return {
        "type": "assistant", "timestamp": ts, "sessionId": "s1", "requestId": req, "isSidechain": sidechain,
        "cwd": cwd, "uuid": msg_id + req,
        "message": {"id": msg_id, "model": model, "usage": {
            "input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": write,
            "cache_creation": {"ephemeral_1h_input_tokens": write, "ephemeral_5m_input_tokens": 0}}},
    }


class PriceTests(unittest.TestCase):
    def test_longest_prefix_with_date_suffix(self):
        self.assertEqual(us.price_for("claude-haiku-4-5-20251001")[0], 1.0)
        self.assertEqual(us.price_for("claude-opus-5-5")[0], 4.0)
        self.assertEqual(us.price_for("claude-opus-5")[0], 5.0)
        self.assertIsNone(us.price_for("gpt-oss"))

    def test_entry_cost_uses_model_specific_cache_read(self):
        # Opus 5.5: 1M token đọc cache = 0,20 USD
        cost = us.entry_cost("claude-opus-5-5", {"cache_read_input_tokens": 1_000_000})
        self.assertAlmostEqual(cost, 0.20)
        # Haiku 4.5: mặc định 0,1 x input = 0,10 USD
        cost = us.entry_cost("claude-haiku-4-5", {"cache_read_input_tokens": 1_000_000})
        self.assertAlmostEqual(cost, 0.10)

    def test_cache_write_1h_costs_double_input(self):
        cost = us.entry_cost("claude-sonnet-5-5", {"cache_creation_input_tokens": 1_000_000,
                                                   "cache_creation": {"ephemeral_1h_input_tokens": 1_000_000}})
        self.assertAlmostEqual(cost, 4.0)


class SnapshotTests(TempDirTestCase):
    def test_dedupe_window_and_subagent_share(self):
        proj = self.tmp / "projects" / "-x-proj"
        jsonl(proj / "a.jsonl", [
            assistant("m1", "claude-sonnet-5-5", "2026-09-30T10:00:00Z"),
            assistant("m1", "claude-sonnet-5-5", "2026-09-30T10:00:01Z"),  # cùng message.id + requestId: tính 1 lần
            assistant("m2", "claude-opus-5-5", "2026-09-30T11:00:00Z", out=1000),
            assistant("m3", "claude-sonnet-5-5", "2026-09-01T11:00:00Z"),  # ngoài cửa sổ 7 ngày
            {"type": "user", "timestamp": "2026-09-30T10:00:00Z", "message": {"content": "bí mật"}},
        ])
        jsonl(proj / "a" / "subagents" / "agent-1.jsonl", [
            assistant("m4", "claude-haiku-4-5-20251001", "2026-09-30T12:00:00Z", sidechain=True),
        ])
        out = run_script(REPO / "tools" / "usage_snapshot.py", "--projects-dir", str(self.tmp / "projects"),
                         "--now", NOW, "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["records"], 3)
        self.assertEqual(data["by_model"]["claude-sonnet-5-5"]["calls"], 1)
        self.assertIn("claude-haiku-4-5-20251001", data["by_model"])
        self.assertGreater(data["subagent_cost_share"], 0)
        self.assertLess(data["subagent_cost_share"], 1)
        self.assertEqual(data["by_project"].keys(), {"proj"})
        self.assertNotIn("bí mật", out.stdout)  # không bao giờ in nội dung hội thoại

    def test_markdown_output(self):
        jsonl(self.tmp / "projects" / "p" / "a.jsonl", [assistant("m1", "claude-sonnet-5-5", "2026-09-30T10:00:00Z")])
        out = run_script(REPO / "tools" / "usage_snapshot.py", "--projects-dir", str(self.tmp / "projects"),
                         "--now", NOW)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("| `claude-sonnet-5-5` | 1 |", out.stdout)
        self.assertIn("Tổng ước tính", out.stdout)


if __name__ == "__main__":
    unittest.main()
