"""Hồi quy cho các lỗi review tìm ra ở GĐ4 (opus·xhigh và sonnet·xhigh, 14/11/2026): cổng `stack.py approve` (cờ đặt
trước lệnh con, đường chạy hộ), lời duyệt quá lỏng, mất bản chụp, mức quá thấp, hai stack.json trong một repo, cây tiến
độ, nhật ký router, đường dẫn vùng, `ignore` chồng một phần lên cụm bảo mật, mức dự phòng, file hỏng, symlink treo."""
import json
import os
import sys
import time
from pathlib import Path

from tests._util import PLUGIN, TempDirTestCase, git, run_script
from tests.test_guard import GuardBase
from tests.test_route import A, ProjectFixtures, route

META = {"reason": "r", "evidence": "e", "date": "2026-11-14"}


def scee_stack():
    from tests.test_route_stack import SCEE_STACK
    return SCEE_STACK

STACK = PLUGIN / "skills" / "project-setup" / "scripts" / "stack.py"
S_PATH = "~/Documents/Claude/agent-stack/plugin/skills/project-setup/scripts/stack.py"


class _Lazy:
    def __getattr__(self, name):
        return getattr(route.stack_lib(), name)


S = _Lazy()


class ApproveGateBypasses(GuardBase):
    def test_flags_before_subcommand_and_launchers_are_gated(self):
        self.start("làm tiếp", "b1")
        for cmd in [f"python3 {S_PATH} --project . approve all:abc123", f"python3 {S_PATH} --json approve ignore:schema",
                    f"python3 {S_PATH} --project=. approve ignore:schema", f"python3 {S_PATH} -- approve ignore:schema",
                    f"echo all | xargs python3 {S_PATH} approve", f"find . -exec python3 {S_PATH} approve all \\;",
                    f"bash <<EOF\npython3 {S_PATH} approve all\nEOF",
                    f"echo 'python3 {S_PATH} approve all' | sh",
                    f"python3 -c \"import runpy,sys; sys.argv=['x','approve','all']; runpy.run_path('{S_PATH}')\""]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "b1")
                self.assertIsNotNone(out)
                self.assertEqual(out[0], "deny")

    def test_reading_the_script_is_not_blocked(self):
        self.start("làm tiếp", "r1")
        for cmd in [f"grep -n 'def approve' {S_PATH}", f"cat {S_PATH}", f"python3 {S_PATH} check"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd, "r1"))

    def test_text_arguments_mentioning_approve_pass(self):
        """Tham số văn bản nhắc tới `stack.py approve` (ghi chú review, commit) không phải lệnh chạy hộ."""
        self.start("làm tiếp", "t1")
        for cmd in ["python3 review_log.py add --found 'both:cao:sua:cờ đặt trước lệnh con lọt cổng stack.py approve'",
                    "git commit -m 'chặn stack.py approve chạy qua xargs'"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "t1")
                self.assertFalse(out and "stack.py approve` chỉ chạy trực tiếp" in out[1], out)

    def test_snapshot_dir_cannot_be_removed_or_moved(self):
        snap = self.state / "stack-approved"
        snap.mkdir(parents=True, exist_ok=True)
        (snap / "k.json").write_text("{}")
        self.start("làm tiếp", "d1")
        for cmd in [f"find {snap} -name '*.json' -delete", f"mv {self.state} {self.state}.bak", f"rm -rf {self.state}",
                    "python3 -c \"import stackcfg as S; S.A.write_json_atomic(S.snapshot_path('.'), {})\""]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd, "d1")[0], "deny")


class ConsentWording(TempDirTestCase):
    def test_negation_exclusion_and_stray_words_are_not_approval(self):
        no = [("duyệt mọi mục trừ ignore:schema", "ignore:schema"),
              ("duyệt keyword:lattice nhưng đừng duyệt ignore:schema", "ignore:schema"),
              ("duyệt ignore:schema thì không được", "ignore:schema"),
              ("approve everything except ignore:schema", "ignore:schema"),
              ("duyệt plan rồi chạy test đi", "ignore:test"),
              ("duyệt kế hoạch refactor module auth đi", "ignore:refactor"),
              ("duyệt ignore:refactor sau khi tôi xem lại diff", "ignore:refactor"),
              ("duyệt keyword:lattice", "ignore:lattice"),
              ("duyệt hết các bước trong kế hoạch", "all:abc123"),
              ("duyệt tất cả, trừ ignore:refactor", "all:abc123")]
        for text, target in no:
            with self.subTest(text=text):
                self.assertFalse(A.text_consents(text, "approve", (target,)))
        yes = [("duyệt ignore:schema", "ignore:schema"), ("ok duyệt bỏ qua schema", "ignore:schema"),
               ("duyệt hết abc123", "all:abc123"), ("duyệt ignore:schema và keyword:ro nhan", "keyword:ro nhan")]
        for text, target in yes:
            with self.subTest(text=text):
                self.assertTrue(A.text_consents(text, "approve", (target,)))


class StackFixes(ProjectFixtures):
    def put(self, root, data):
        (root / ".agent").mkdir(exist_ok=True)
        (root / ".agent" / "stack.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_lost_snapshot_is_reported_not_silent(self):
        root = self.python_repo("sửa lỗi traceback ở test_chain khi chạy pytest")
        self.put(root, {"floors": [dict(META, group="debug", model="opus", effort="xhigh")]})
        S.effective(root)
        S.snapshot_path(root).unlink()
        self.put(root, {})
        eff = S.effective(root)
        self.assertTrue(eff["lost"])
        self.assertIn("mất", route.session_hint(root)["context"])

    def test_low_keyword_cannot_create_a_lower_suggestion(self):
        root = self.python_repo()
        self.put(root, {"keywords": [dict(META, phrase="module", model="haiku", effort="low")]})
        text = "sửa phần mã hóa khóa riêng trong module ký số"
        self.assertIsNone(route.suggest_for(text, None, route.project_stack(root)))

    def test_two_stack_files_in_one_repo_keep_separate_snapshots(self):
        root = self.python_repo()
        sub = root / "pkg"
        sub.mkdir()
        self.put(root, {"keywords": [dict(META, phrase="alpha word", model="opus", effort="high")]})
        self.put(sub, {"keywords": [dict(META, phrase="beta word", model="opus", effort="high")]})
        self.assertNotEqual(S.repo_key(root), S.repo_key(sub))
        for _ in range(2):
            a, b = S.effective(root), S.effective(sub)
            self.assertEqual((a["pending"], b["pending"]), ([], []))
            self.assertNotIn("beta word", a["cfg"]["keywords"])
            self.assertNotIn("alpha word", b["cfg"]["keywords"])

    def test_progress_tree_respects_floor(self):
        root = self.python_repo()
        self.put(root, scee_stack())
        sys.path.insert(0, str(PLUGIN / "skills" / "progress" / "scripts"))
        import collect
        hit = collect.router()("sửa lỗi rò nhãn trong chain, traceback ở test_chain", str(root))
        self.assertEqual((hit["model"], hit["effort"]), ("opus", "xhigh"))

    def test_route_log_redacts_secrets(self):
        root = self.python_repo()
        secret = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4"
        route.hook_suggestion(f"sửa lỗi traceback khi gọi api với khóa {secret}", {"cwd": str(root), "session_id": "x"})
        log = (Path(os.environ["AGENT_STACK_STATE"]) / "route-log.jsonl").read_text()
        self.assertNotIn(A.fold(secret), log)

    def test_area_paths_are_normalized_and_stripped(self):
        cfg, _ = S.parse(json.dumps({"areas": [dict(META, name="lõi", paths=["./src/core", "a//b", " /etc", " ../x"],
                                                    model="opus", effort="high")]}))
        self.assertEqual(cfg["areas"]["lõi"]["paths"], ["a/b", "src/core"])

    def test_partial_overlap_ignore_cannot_hide_security_rule(self):
        root = self.python_repo()
        self.put(root, {"ignore": [dict(META, phrase="code review")]})
        eff = route.project_stack(root)
        snap = S.approve(eff["snapshot"], eff["current"], "ignore:code review")
        S.save_snapshot(eff["base"], snap)
        eff = route.project_stack(root)
        self.assertIn("code review", eff["cfg"]["ignore"])
        text = "secure code review of the auth module"
        self.assertEqual(route.suggest_for(text, None, eff)["rule"], route.suggest(text)["rule"])

    def test_fallback_line_never_below_floor(self):
        root = self.python_repo()
        self.put(root, {"floors": [dict(META, group="debug", model="opus", effort="medium")]})
        hit = route.suggest_for("viết test cho hàm parse rồi chạy pytest", A.project_profile(root, use_cache=False),
                                route.project_stack(root))
        self.assertEqual(hit["model"], "opus")
        self.assertTrue(not hit.get("fallback") or hit["fallback"].startswith(route.model_name("opus")), hit)

    def test_broken_file_keeps_approved_ignore(self):
        root = self.python_repo()
        self.put(root, {"ignore": [dict(META, phrase="schema")]})
        eff = route.project_stack(root)
        S.save_snapshot(eff["base"], S.approve(eff["snapshot"], eff["current"], "ignore:schema"))
        (root / ".agent" / "stack.json").write_text("{hỏng")
        route.project_stack(root)
        self.put(root, {"ignore": [dict(META, phrase="schema")]})
        self.assertIn("schema", route.project_stack(root)["cfg"]["ignore"])


class StackCli(TempDirTestCase):
    def setUp(self):
        super().setUp()
        old = os.environ.get("AGENT_STACK_STATE")
        os.environ["AGENT_STACK_STATE"] = str(self.tmp / "state")
        self.addCleanup(lambda: os.environ.pop("AGENT_STACK_STATE", None) if old is None
                        else os.environ.__setitem__("AGENT_STACK_STATE", old))
        self.root = self.tmp / "proj"
        (self.root / ".agent").mkdir(parents=True)
        git(self.root, "init", "-q")

    def stack(self, *args):
        return run_script(STACK, *args, "--project", str(self.root))

    def test_apply_refuses_dangling_symlink(self):
        outside = self.tmp / "outside.json"
        os.symlink(outside, self.root / ".agent" / "stack.json")
        out = self.stack("apply", "--item", json.dumps({"kind": "tool", "name": "ruff", **META}))
        self.assertNotEqual(out.returncode, 0)
        self.assertFalse(outside.exists())

    def test_approve_all_needs_the_list_hash(self):
        (self.root / ".agent" / "stack.json").write_text(json.dumps({"ignore": [dict(META, phrase="schema")]}))
        self.assertIn("duyệt hết", self.stack("check").stdout)
        self.assertEqual(self.stack("approve", "all").returncode, 1)
        self.assertEqual(self.stack("approve", "all:000000").returncode, 1)
        code = S.pending_hash(S.effective(self.root, write=False)["pending"])
        self.assertEqual(self.stack("approve", f"all:{code}").returncode, 0)

    def test_one_review_counts_once(self):
        key, t = S.repo_key(self.root), time.time() - 5000
        state = self.tmp / "state"
        state.mkdir(exist_ok=True)
        rows = [{"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t + i * 60)), "kind": "route",
                 "session": f"s{i}", "key": key, "effort_now": "high", "rule": "debug-simple", "model": "sonnet",
                 "effort": "high", "matched": ["traceback"]} for i in range(4)]
        (state / "route-log.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        (state / "review-log.jsonl").write_text(json.dumps({"ts": int(t + 300), "project": "proj", "findings": [
            {"severity": "cao", "verdict": "sua"}]}) + "\n")
        sys.path.insert(0, str(STACK.parent))
        import stack
        self.assertEqual(stack.learn(self.root)["proposals"], [])


class ReReviewRound1(GuardBase):
    """Review lại vòng 1 (opus·xhigh, 14/11/2026): chặn nhầm lệnh chỉ chứa chữ hay chỉ đọc; còn đường lách qua
    `python -m stack`, `import stack`, stdin của xargs, `find -P/-L`; lời duyệt mã là tiền tố của mã khác."""

    AP = "app" + "rove"

    def test_text_and_read_only_commands_pass(self):
        self.start("làm tiếp", "q1")
        snap_parent = self.state
        for cmd in [f"git commit -m 'chặn stack.py {self.AP} chạy qua xargs, heredoc, echo | sh'",
                    f"git log --grep 'stack.py {self.AP}' | bash -c 'wc -l'",
                    f"find plugin -name stack.py -exec grep -n {self.AP} {{}} +",
                    f"find {snap_parent} -name '*.jsonl' -mmin -60", f"mv /tmp/x.jsonl {snap_parent}/"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "q1")
                self.assertFalse(out and out[0] == "deny" and "stack" in out[1], out)

    def test_remaining_bypasses_are_denied(self):
        self.start("làm tiếp", "q2")
        snap = self.state / "stack-approved"
        snap.mkdir(parents=True, exist_ok=True)
        for cmd in [f"python3 -m stack {self.AP} ignore:x",
                    f"python3 -c 'import stack; stack.main([\"{self.AP}\", \"ignore:x\"])'",
                    f"echo {self.AP} ignore:x | xargs python3 {S_PATH}",
                    f"find -P {snap} -name '*.json' -delete", f"find -L {self.state} -delete",
                    f"env FOO=1 python3 {S_PATH} {self.AP} all"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd, "q2")[0], "deny")

    def test_approval_wording_round1(self):
        self.assertFalse(A.text_consents("duyệt ignore:research-level", "approve", ("ignore:research",)))
        self.assertTrue(A.text_consents("duyệt tất cả abc123", "approve", ("all:abc123",)))
        self.assertTrue(A.text_consents("duyệt ignore:schema, keyword:ro nhan", "approve", ("keyword:ro nhan",)))
        self.assertTrue(A.text_consents("duyệt cả hai: ignore:schema và min_risk", "approve", ("min_risk",)))
        self.assertFalse(A.text_consents("duyệt ignore:schema, rồi chạy test", "approve", ("ignore:test",)))
        self.start("làm tiếp", "q3")
        out = self.bash(f"python3 {S_PATH} {self.AP} all:abc123", "q3")
        self.assertIn("duyệt hết abc123", out[1])


class ReReviewRound2(GuardBase):
    """Review lại vòng 2 (sonnet·high, 14/11/2026): mv -t, find có dấu ngoặc, stack.py do find hay stdin đưa vào {},
    xargs đưa chữ vào shell, __import__, -mstack, -O3, find từ thư mục cha; find -exec chỉ đọc không bị chặn."""

    AP = "app" + "rove"

    def test_round2_bypasses_are_denied(self):
        self.start("làm tiếp", "w2")
        snap = self.state / "stack-approved"
        snap.mkdir(parents=True, exist_ok=True)
        for cmd in [f"mv --target-directory=/tmp {snap}", f"mv -t /tmp {self.state}",
                    f"find . \\( -name x \\) -exec python3 {S_PATH} {self.AP} all \\;",
                    f"find {self.state} \\( -name a -o -name b \\) -delete",
                    f"find plugin -name stack.py -exec python3 {{}} {self.AP} all \\;",
                    f"find plugin -name stack.py | xargs -I{{}} python3 {{}} {self.AP} all",
                    f"echo 'python3 {S_PATH} {self.AP} all' | xargs -I{{}} sh -c {{}}",
                    f"python3 -c \"__import__('stack').main(['{self.AP}', 'all'])\"",
                    f"python3 -mstack {self.AP} x", f"find -O3 {self.state} -delete",
                    f"find {self.state.parent} -name stack-approved -exec rm -rf {{}} +"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd, "w2")[0], "deny")

    def test_read_only_find_exec_passes(self):
        self.start("làm tiếp", "w3")
        for cmd in [f"find {self.state} -name '*.jsonl' -exec wc -l {{}} +",
                    f"find {self.state} -type f -exec ls -la {{}} \\;"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "w3")
                self.assertFalse(out and out[0] == "deny" and "stack" in out[1], out)
