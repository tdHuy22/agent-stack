"""Skill project-setup (GĐ4): `stack.py scan|check|apply|approve|learn`, và các chỗ dùng `.agent/stack.json` khác:
done-gate (`risk.py` thư mục lõi và mức tối thiểu, `checks.py` công cụ khai báo)."""
import json
import os
import sys
import time
from unittest import mock

from tests._util import PLUGIN, TempDirTestCase, git, run_script

STACK = PLUGIN / "skills" / "project-setup" / "scripts" / "stack.py"
for sub in ("lib", "skills/done-gate/scripts", "skills/project-setup/scripts", "skills/task-router/scripts"):
    sys.path.insert(0, str(PLUGIN / sub))
import checks  # noqa: E402
import risk  # noqa: E402


class _Lazy:
    """Module mới của GĐ4 nạp lúc chạy test (stack.py của skill, stackcfg qua router như hook dùng)."""

    def __init__(self, load):
        self._load = load

    def __getattr__(self, name):
        return getattr(self._load(), name)


ST = _Lazy(lambda: __import__("stack"))
S = _Lazy(lambda: __import__("route").stack_lib())

META = {"reason": "r", "evidence": "e", "date": "2026-11-14"}


class Base(TempDirTestCase):
    def setUp(self):
        super().setUp()
        for key, value in (("AGENT_STACK_STATE", str(self.tmp / "state")),):
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.pop(k, None) if o is None else os.environ.__setitem__(k, o))
        self.root = self.tmp / "proj"
        files = {"app/core/a.py": "out_schema = 1\nschema = 2\nx_schema = 3\n" * 10, "app/b.py": "y = 2\n",
                 "app/c.py": "z = 3\n", "tests/test_a.py": "import unittest\n",
                 "docs/NOTE.md": "Lỗi rò nhãn ở chain. Cần làm rõ nhãn.\n", "PLAN.md": "# Kế hoạch\n"}
        for rel, text in files.items():
            self.write(f"proj/{rel}", text)
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")

    def stack(self, *args):
        return run_script(STACK, *args, "--project", str(self.root))

    def put(self, data):
        self.write("proj/.agent/stack.json", json.dumps(data, ensure_ascii=False))


class Scan(Base):
    def test_scan_counts_router_phrases_in_code(self):
        r = ST.scan(self.root)
        self.assertIn("schema", [c["phrase"] for c in r["ignore_candidates"]])
        self.assertEqual(r["fingerprint"]["tests"], True)
        self.assertFalse(r["archctl"]["suggest"])
        self.assertIn("app/core", r["core_candidates"])

    def test_archctl_suggested_for_two_components_or_compose(self):
        self.write("proj/svc/package.json", "{}")
        self.write("proj/pyproject.toml", "[project]\n")
        git(self.root, "add", "-A")
        self.assertTrue(ST.scan(self.root)["archctl"]["suggest"])
        self.write("proj/svc/package.json", "")
        (self.root / "svc" / "package.json").unlink()
        self.write("proj/docker-compose.yml", "services: {}\n")
        git(self.root, "add", "-A")
        self.assertTrue(ST.scan(self.root)["archctl"]["suggest"])


class ApplyApprove(Base):
    def test_apply_writes_one_item_with_reason_and_date(self):
        out = self.stack("apply", "--item", json.dumps({"kind": "keyword", "phrase": "rò nhãn", "model": "opus",
                                                         "effort": "xhigh", "reason": "lõi", "evidence": "NOTE.md:1"}))
        self.assertEqual(out.returncode, 0, out.stdout)
        data = json.loads((self.root / ".agent" / "stack.json").read_text())
        self.assertEqual(data["keywords"][0]["phrase"], "rò nhãn")
        self.assertTrue(data["keywords"][0]["date"])

    def test_apply_refuses_missing_evidence_bad_level_and_protected_ignore(self):
        for item in ({"kind": "keyword", "phrase": "rò nhãn", "model": "opus", "effort": "xhigh", "reason": "r"},
                     {"kind": "keyword", "phrase": "rò nhãn", "model": "fable", "effort": "max", **META},
                     {"kind": "ignore", "phrase": "bảo mật", **META},
                     {"kind": "tool", "name": "rm -rf /", **META}):
            with self.subTest(item=item):
                self.assertEqual(self.stack("apply", "--item", json.dumps(item, ensure_ascii=False)).returncode, 2)
        self.assertFalse((self.root / ".agent" / "stack.json").exists())

    def test_ignore_waits_for_approval(self):
        self.stack("apply", "--item", json.dumps({"kind": "ignore", "phrase": "schema", **META}))
        out = self.stack("check")
        self.assertIn("⏸ chờ duyệt: `ignore:schema`", out.stdout)
        self.assertEqual(S.effective(self.root, write=False)["cfg"]["ignore"], {})
        self.assertEqual(self.stack("approve", "ignore:lattice").returncode, 1)
        self.assertEqual(self.stack("approve", "ignore:schema").returncode, 0)
        self.assertIn("schema", S.effective(self.root, write=False)["cfg"]["ignore"])
        self.assertNotIn("⏸", self.stack("check").stdout)

    def test_remove_is_loosening(self):
        self.stack("apply", "--item", json.dumps({"kind": "tool", "name": "ruff", **META}))
        self.stack("apply", "--remove", "tool:ruff")
        eff = S.effective(self.root, write=False)
        self.assertIn("ruff", eff["cfg"]["tools"])
        self.assertEqual([p["id"] for p in eff["pending"]], ["tool:ruff"])

    def test_check_warns_fold_collisions_and_drift(self):
        self.put({"keywords": [dict(META, phrase="rò nhãn", model="opus", effort="xhigh")],
                  "fingerprint": {"kinds": ["rust"], "tests": True, "security": False, "archctl": False}})
        out = self.stack("check").stdout
        self.assertIn("bỏ dấu trùng nhau", out)
        self.assertIn("rõ nhãn", out)
        self.assertIn("hồ sơ đã đổi", out)

    def test_fingerprint_written(self):
        self.stack("apply", "--fingerprint")
        fp = json.loads((self.root / ".agent" / "stack.json").read_text())["fingerprint"]
        self.assertEqual((fp["kinds"], fp["tests"]), (["python"], True))


class Learn(Base):
    def log(self, rows, name="route-log.jsonl"):
        path = self.tmp / "state" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def ts(self, t):
        return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))

    def test_three_raised_efforts_become_a_keyword_proposal(self):
        key, t = S.repo_key(self.root), time.time() - 5000
        rows = []
        for i in range(3):
            rows += [{"ts": self.ts(t + i * 100), "kind": "route", "session": f"s{i}", "key": key, "effort_now": "low",
                      "rule": "debug-simple", "model": "haiku", "effort": "low", "matched": ["traceback"]},
                     {"ts": self.ts(t + i * 100 + 10), "kind": "route", "session": f"s{i}", "key": key,
                      "effort_now": "xhigh", "rule": None, "matched": []}]
        rows.append({"ts": self.ts(t), "kind": "route", "session": "x", "key": "khac", "effort_now": "low",
                     "rule": "debug-simple", "model": "haiku", "effort": "low", "matched": ["traceback"]})
        self.log(rows)
        props = ST.learn(self.root)["proposals"]
        self.assertEqual(len(props), 1)
        self.assertEqual((props[0]["kind"], props[0]["phrase"], props[0]["effort"]), ("keyword", "traceback", "xhigh"))
        self.assertEqual(S.learn_count(self.root), 1)

    def test_two_is_not_enough_and_lowered_effort_proposes_ignore(self):
        key, t = S.repo_key(self.root), time.time() - 5000
        rows = []
        for i in range(3):
            rows += [{"ts": self.ts(t + i * 100), "kind": "route", "session": f"o{i}", "key": key, "effort_now": "xhigh",
                      "rule": "architecture-critical", "model": "opus", "effort": "xhigh", "matched": ["schema"]},
                     {"ts": self.ts(t + i * 100 + 5), "kind": "route", "session": f"o{i}", "key": key,
                      "effort_now": "high", "rule": None, "matched": []}]
        self.log(rows[:4])
        self.assertEqual(ST.learn(self.root)["proposals"], [])
        self.log(rows[4:])
        props = ST.learn(self.root)["proposals"]
        self.assertEqual([(p["kind"], p["phrase"], p["loosen"]) for p in props], [("ignore", "schema", True)])

    def test_failed_tests_and_review_findings_count(self):
        key, t = S.repo_key(self.root), time.time() - 5000
        self.log([{"ts": self.ts(t + i), "kind": "route", "session": f"t{i}", "key": key, "effort_now": "high",
                   "rule": "feature", "model": "haiku", "effort": "low", "fallback": True, "matched": ["viet ham"]}
                  for i in range(3)])
        self.log([{"ts": self.ts(t + 50), "kind": "stop", "session": "t0", "evidence": ["test trượt"]},
                  {"ts": self.ts(t + 50), "kind": "stop", "session": "t1", "evidence": ["test trượt"]}], "events.jsonl")
        self.log([{"ts": int(t + 60), "project": "proj", "findings": [{"severity": "cao", "verdict": "sua"}]}],
                 "review-log.jsonl")
        props = ST.learn(self.root)["proposals"]
        self.assertEqual([(p["kind"], p["phrase"]) for p in props], [("keyword", "viet ham")])
        self.assertIn("test trượt", props[0]["evidence"])
        self.assertIn("review", props[0]["evidence"])


class DoneGateUses(Base):
    def change(self, path, text="x = 1\n"):
        return {"path": path, "added": 1, "deleted": 0, "text": text}

    def test_core_dir_is_high_and_min_risk_floor(self):
        self.put({"areas": [dict(META, name="lõi", paths=["app/core"], model="opus", effort="high")],
                  "process": {"min_risk": "vua"}})
        project = risk.project_risk(self.root)
        self.assertEqual(project, {"core": ["app/core"], "min_risk": "vua"})
        self.assertEqual(risk.assess([self.change("app/core/a.py")], project=project)["level"], "cao")
        self.assertEqual(risk.assess([self.change("app/corex.py")], project=project)["level"], "vua")
        doc = {"path": "docs/NOTE.md", "added": 1, "deleted": 0, "text": "chữ\n"}
        self.assertEqual(risk.assess([doc])["level"], "thap")
        self.assertEqual(risk.assess([doc], project=project)["level"], "vua")

    def test_unapproved_loosening_of_core_keeps_high(self):
        self.put({"areas": [dict(META, name="lõi", paths=["app/core"], model="opus", effort="high")]})
        S.effective(self.root)  # hook đã thấy bản siết
        self.put({"areas": []})
        self.assertEqual(risk.project_risk(self.root)["core"], ["app/core"])

    def test_no_stack_means_no_project_risk(self):
        self.assertIsNone(risk.project_risk(self.root))

    def test_declared_tool_missing_on_machine_counts_as_missing(self):
        self.put({"tools": ["ruff", "rm -rf /", "khong-co-trong-danh-muc", {"name": "ktlint", **META}]})
        self.assertEqual(checks.stack_tools(self.root), ["ktlint", "ruff"])
        plan = checks.Plan()
        ctx = mock.Mock(root=self.root)
        with mock.patch.object(checks, "find_bin", side_effect=lambda t, *d: None if t == "ktlint" else "/bin/x"):
            checks.plan_stack_tools(ctx, plan)
        self.assertEqual([m[2] for m in plan.missing], ["ktlint"])
        self.assertEqual(checks.summarize(plan, [])["exit"], 2)
