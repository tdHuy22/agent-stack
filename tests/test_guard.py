"""GĐ20: skill cần thiết tự chạy. Hook PreToolUse (pretool_guard.py) chặn cài đồ chưa vet, hỏi trước khi git checkout
trên cây bẩn, chặn ghi báo cáo lỗ hổng vào project, nhắc threat model trước khi code; hook Stop buộc chạy done-gate
khi lượt đổi code có rủi ro."""
import json
import os
import re
import subprocess
import time
from pathlib import Path

from tests._util import PLUGIN, TempDirTestCase, git

HOOKS = PLUGIN / "hooks"
RISK = PLUGIN / "skills" / "done-gate" / "scripts" / "risk.py"
RECEIPT = PLUGIN / "skills" / "session-keeper" / "scripts" / "receipt.py"
LOGIN = "def login(user, password):\n" + "".join(f"    step_{i} = check(user, password, {i})\n" for i in range(30))


class GuardBase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.stack = self.tmp / "stack"
        self.stack.mkdir()
        (self.stack / ".agent-stack-root").write_text("")
        (self.stack / "catalog.json").write_text(json.dumps({"items": [
            {"key": "o/r:plugins/ok", "kind": "vendor-plugin", "scope": "user",
             "install": {"marketplace": "agent-stack-vendor-local", "plugin": "ok"}},
            {"key": "o/r:plugins/cho", "kind": "claude-plugin", "scope": "project",
             "install": {"marketplace": "m", "plugin": "cho"}}]}))
        (self.stack / "vetted.lock").write_text(json.dumps({"entries": {
            "o/r:plugins/ok": {"human_review": {"status": "approved"}},
            "o/r:plugins/cho": {"human_review": {"status": "pending"}}}}))
        self.project = self.tmp / "proj"
        (self.project / "app").mkdir(parents=True)
        (self.project / "app" / "views.py").write_text("x = 1\n")
        git(self.project, "init", "-q")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "init")

    def env(self, **extra):
        return dict(os.environ, AGENT_STACK_STATE=str(self.state), AGENT_STACK_HOME=str(self.stack),
                    AGENT_STACK_PLUGINS_DIR=str(self.tmp / "no-plugins"), **extra)

    def hook(self, name, payload, raw=None, **env):
        start = time.time()
        out = subprocess.run(["python3", str(HOOKS / name)], input=raw if raw is not None else json.dumps(payload),
                             capture_output=True, text=True, env=self.env(**env), timeout=30)
        self.elapsed = time.time() - start
        self.assertEqual((out.returncode, out.stderr), (0, ""))
        return json.loads(out.stdout) if out.stdout.strip() else None

    def guard(self, tool, tool_input, sid="g1"):
        out = self.hook("pretool_guard.py", {"session_id": sid, "cwd": str(self.project), "tool_name": tool,
                                             "tool_input": tool_input, "hook_event_name": "PreToolUse"})
        return (out["hookSpecificOutput"]["permissionDecision"], out["hookSpecificOutput"]["permissionDecisionReason"]) \
            if out else None

    def bash(self, command, sid="g1"):
        return self.guard("Bash", {"command": command}, sid)

    def start(self, prompt, sid):
        self.hook("prompt_submit.py", {"session_id": sid, "cwd": str(self.project), "prompt": prompt})


class InstallGuard(GuardBase):
    def test_unvetted_or_unapproved_install_is_denied_and_points_to_vet_skill(self):
        for cmd in ("claude plugin install evil@somewhere", "cd x && claude plugin install cho@m --scope project",
                    "claude mcp add foo -- npx foo-mcp", "npx -y skills add someone/skill"):
            with self.subTest(cmd=cmd):
                decision, reason = self.bash(cmd)
                self.assertEqual(decision, "deny")
                self.assertIn("vet-skill", reason)

    def test_approved_and_own_plugins_pass_silently(self):
        for cmd in ("claude plugin install ok@agent-stack-vendor-local --scope user",
                    "claude plugin install --scope project ok@agent-stack-vendor-local",
                    "claude plugin install agent-stack@agent-stack-local --scope user",
                    "claude plugin list", "ls -la", "echo claude plugin install x@y > note.txt && cat note.txt",
                    'git commit -m "GĐ20: chặn claude plugin install chưa duyệt"',
                    "cat > doc.md <<'EOF'\nclaude plugin install foo@bar\nEOF\necho xong"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd), "chỉ lệnh thật sự chạy claude mới bị xét")
        self.assertLess(self.elapsed, 2)

    def test_install_hidden_behind_prefixes_or_subshell_is_still_caught(self):
        for cmd in ("FOO=1 sudo claude plugin install evil@mk", 'bash -c "claude plugin install evil@mk"',
                    "ls\nclaude mcp add-json x '{}'", "npx -y skills@1.2 add a/b",
                    "/usr/local/bin/claude plugin install evil@mk"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd)[0], "deny")

    def test_unknown_marketplace_asks_but_own_marketplace_passes(self):
        self.assertEqual(self.bash("claude plugin marketplace add trailofbits/skills")[0], "ask")
        self.assertIsNone(self.bash(f"claude plugin marketplace add {self.stack / 'vendor'}"))


class CheckoutGuard(GuardBase):
    def test_moving_head_or_restoring_files_on_dirty_tree_asks(self):
        self.assertIsNone(self.bash("git checkout HEAD~0"), "cây sạch: không hỏi")
        (self.project / "app" / "views.py").write_text("x = 2\n")
        decision, reason = self.bash("git checkout HEAD~0")
        self.assertEqual(decision, "ask")
        self.assertIn("git show <ref>:<file>", reason)
        decision, reason = self.bash("git checkout -- app/views.py")
        self.assertEqual(decision, "ask")
        self.assertIn("làm mất thay đổi chưa commit", reason)
        self.assertEqual(self.bash("git switch main")[0], "ask")
        self.assertIsNone(self.bash("git checkout -b nhanh-moi"), "tạo nhánh mới giữ nguyên cây")
        self.assertIsNone(self.bash("git status"))
        self.assertIsNone(self.bash('git commit -am "quay lại: git checkout main"'), "chữ trong thông điệp commit")
        self.assertEqual(self.bash("git --no-pager -C . checkout HEAD~0")[0], "ask")

    def test_fsmonitor_of_a_foreign_repo_is_never_run(self):
        marker = self.tmp / "fsmonitor-ran"
        git(self.project, "config", "core.fsmonitor", f"touch {marker}; false")
        (self.project / "app" / "views.py").write_text("x = 3\n")
        self.assertEqual(self.bash("git checkout HEAD~0")[0], "ask")
        self.assertFalse(marker.exists(), "hook không được chạy lệnh core.fsmonitor của repo")

    def test_untracked_files_alone_do_not_count_as_dirty(self):
        (self.project / "moi.txt").write_text("chưa track\n")
        self.assertIsNone(self.bash("git checkout HEAD~0"))


class WriteGuard(GuardBase):
    def test_creating_a_tag_or_release_is_stopped_once_with_the_audit_reminder(self):
        cases = {"git tag v1.0": "`v1.0`", 'git tag -a v1.0 -m "phát hành v1"': "`v1.0`",
                 'git tag -m "release v2" v2.0 HEAD~1': "`v2.0`", "git -C proj tag -f v3": "`v3`",
                 "cd proj && git tag v4 && git push --tags": "`v4`",
                 'gh release create --notes "bản đầu" v1.0': "`v1.0`", "gh release create v2.0 -t Tên": "`v2.0`",
                 'git tag -am "Release 1" v1.0': "`v1.0`", 'git tag -sm "x" v1.1': "`v1.1`", "git tag -fam x v1.2": "`v1.2`",
                 "git tag -mxong v1.3": "`v1.3`", "git tag --message=x v1.4 2>&1": "`v1.4`",
                 "gh -R o/r release create v5": "`v5`"}
        for i, (cmd, name) in enumerate(cases.items()):
            with self.subTest(cmd=cmd):
                self.start("Phát hành bản mới cho repo này", f"rel{i}")
                decision, reason = self.bash(cmd, f"rel{i}")
                self.assertEqual(decision, "deny", "từ chối thì lời nhắc mới tới được Claude")
                self.assertIn(name, reason)
                self.assertIn("/static-analysis:semgrep", reason)
                self.assertIn("/claude-security", reason)
                self.assertIn("hỏi họ đã audit", reason)

    def test_release_passes_only_after_the_user_replies(self):
        self.start("Gắn tag v1.0 cho bản này", "rel")
        self.assertEqual(self.bash("git tag v1.0", "rel")[0], "deny")
        self.assertEqual(self.bash('git tag -a v1.0 -m "lần hai"', "rel")[0], "deny", "chạy lại trong cùng lượt vẫn bị chặn")
        self.start("<task-notification>agent nền xong</task-notification>", "rel")
        self.assertEqual(self.bash("git tag v1.0", "rel")[0], "deny", "tin hệ thống không phải câu trả lời của người dùng")
        self.start("Đã audit rồi, tạo tag đi", "rel")
        self.assertIsNone(self.bash("git tag v1.0", "rel"))
        self.assertIsNone(self.bash("git tag -f v1.0 && git push origin v1.0", "rel"))
        self.assertEqual(self.bash("git tag v2.0", "rel")[0], "deny", "tag khác phải được nhắc riêng")
        self.assertEqual(self.bash("git -C /khac tag v1.0", "rel")[0], "deny", "repo khác phải được nhắc riêng")
        self.assertEqual(self.bash("git tag v1.0", "phien-khac")[0], "deny", "phiên khác không dùng chung mốc chặn")

    def test_slash_command_counts_as_the_users_reply(self):
        self.start("/loop 5m /progress", "sl")
        self.assertEqual(self.bash("git tag v1.0", "sl")[0], "deny", "phiên mở bằng lệnh slash vẫn bị chặn, không rơi về ask")
        self.start("/claude-security", "sl")
        self.assertIsNone(self.bash("git tag v1.0", "sl"))

    def test_gate_follows_cd_and_repo_root(self):
        other = self.tmp / "other"
        other.mkdir()
        git(other, "init", "-q")
        self.start("Gắn tag v1.0", "cd")
        self.assertEqual(self.bash("git tag v1.0", "cd")[0], "deny")
        self.start("Đã audit, tạo đi", "cd")
        self.assertIsNone(self.bash("cd app && git tag v1.0", "cd"), "thư mục con của cùng repo không bị nhắc lại")
        self.assertIsNone(self.bash("git -C app tag v1.0", "cd"))
        self.assertEqual(self.bash(f"cd {other} && git tag v1.0", "cd")[0], "deny", "cd sang repo khác phải được nhắc riêng")

    def test_untracked_session_falls_back_to_asking_the_user(self):
        for sid in ("", "../thoat"):
            with self.subTest(sid=sid):
                decision, reason = self.bash("git tag v1.0", sid)
                self.assertEqual(decision, "ask")
                self.assertIn("`v1.0`", reason)
                self.assertIn("/claude-security", reason)

    def test_a_blocked_command_is_not_hidden_behind_a_tag_reminder(self):
        self.start("Gắn tag rồi cài plugin", "mix")
        for sid in ("mix", "g1"):
            with self.subTest(sid=sid):
                decision, reason = self.bash("git tag v1 && claude plugin install evil@x", sid)
                self.assertEqual(decision, "deny")
                self.assertIn("vet-skill", reason)

    def test_listing_deleting_or_mentioning_tags_passes_silently(self):
        for cmd in ("git tag", "git tag -l 'v1.*'", "git tag -n5", "git tag -d v1", "git tag --contains HEAD",
                    "git tag --sort=-v:refname", "git tag --list --format='%(refname)'", "gh release list",
                    'echo "git tag v1"', 'git commit -m "chuẩn bị git tag v1.0"', "git tag 2>/dev/null",
                    "git tag > tags.txt", 'git tag -li "v1*"', "git tag -ln3 | sort"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))

    def test_vulnerability_report_must_not_land_in_project(self):
        decision, reason = self.guard("Write", {"file_path": str(self.project / "PROJ_DIFFERENTIAL_REVIEW_2026-10-09.md"),
                                                "content": "x"})
        self.assertEqual(decision, "deny")
        self.assertIn(".tmp/", reason)
        self.assertEqual(self.guard("Write", {"file_path": str(self.project / ".tmp" / "PROJ_DIFFERENTIAL_REVIEW.md")})[0],
                         "deny", ".tmp/ chưa được git bỏ qua thì vẫn có thể bị commit")
        (self.project / ".gitignore").write_text(".tmp/\n")
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / ".tmp" / "PROJ_DIFFERENTIAL_REVIEW.md"),
                                               "content": "x"}))
        import tempfile
        self.assertIsNone(self.guard("Write", {"file_path": str(Path(tempfile.gettempdir()) / "X_DIFFERENTIAL_REVIEW.md")}))
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / "README.md"), "content": "x"}))

    def test_new_markdown_for_readers_is_nudged_to_html_once(self):
        self.start("Viết báo cáo kết quả đo cho tôi", "md1")
        report = {"file_path": str(self.project / "bao-cao-do.md"), "content": "# Kết quả"}
        decision, reason = self.guard("Write", report, "md1")
        self.assertEqual(decision, "deny")
        self.assertIn("bao-cao-do.html", reason)
        self.assertIn("reader-page", reason)
        self.assertIsNone(self.guard("Write", report, "md1"), "ghi lại thì cho qua: Claude đã cân nhắc")
        self.start("Viết thêm ghi chú", "md1")
        self.assertEqual(self.guard("Write", report, "md1")[0], "deny", "lượt mới thì nhắc lại")

    def test_required_markdown_and_existing_files_pass(self):
        self.start("Cập nhật tài liệu", "md2")
        (self.project / "notes.md").write_text("cũ\n")
        skill = self.project / "tools" / "x"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: x\n---\n")
        for path in ("README.md", "CLAUDE.md", "docs/CHANGELOG.md", ".agent/HANDOFF.md", ".claude/plans/p.md", "TODO.md",
                     "PROGRESS.md",
                     "plugin/skills/y/references/a.md", ".github/ISSUE_TEMPLATE/bug.md", "PLAN.md", "notes.md",
                     "tools/x/guide.md", "app/views.py", "page.html"):
            with self.subTest(path=path):
                self.assertIsNone(self.guard("Write", {"file_path": str(self.project / path), "content": "x"}, "md2"))
        self.assertIsNone(self.guard("Edit", {"file_path": str(self.project / "new.md"), "old_string": "a",
                                              "new_string": "b"}, "md2"), "chỉ nhắc khi tạo file bằng Write")

    def test_project_under_a_folder_named_agents_is_not_exempt(self):
        # Simplify GĐ30: thư mục đặc biệt chỉ tính phần đường dẫn bên trong project.
        proj = self.tmp / "agents" / "p2"
        proj.mkdir(parents=True)
        self.hook("prompt_submit.py", {"session_id": "md3", "cwd": str(proj), "prompt": "Viết báo cáo"})
        out = self.hook("pretool_guard.py", {"session_id": "md3", "cwd": str(proj), "tool_name": "Write",
                                             "tool_input": {"file_path": str(proj / "bao-cao.md"), "content": "x"},
                                             "hook_event_name": "PreToolUse"})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIsNone(self.hook("pretool_guard.py", {
            "session_id": "md3", "cwd": str(proj), "tool_name": "Write", "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": str(proj / "skills" / "x" / "notes.md"), "content": "x"}}))
        # cwd là thư mục con: gốc project (từ bản ghi lượt) quyết, không phải cwd
        (proj / "src").mkdir()
        out = self.hook("pretool_guard.py", {"session_id": "md3", "cwd": str(proj / "src"),
                                             "tool_name": "Write", "hook_event_name": "PreToolUse",
                                             "tool_input": {"file_path": str(proj / "docs" / "ke-hoach-moi.md")}})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_session_rooted_in_a_special_folder_is_exempt(self):
        import sys
        sys.path.insert(0, str(HOOKS))
        import pretool_guard
        A = pretool_guard.lib()
        claude_dir = self.tmp / "home" / ".claude"
        self.assertTrue(pretool_guard.markdown_required(claude_dir / "note.md", str(claude_dir), A))
        self.assertFalse(pretool_guard.markdown_required(self.tmp / "agents" / "p" / "a.md", str(self.tmp / "agents" / "p"), A))

    def plan(self, criteria=""):
        (self.project / "PLAN.md").write_text("# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Đang dở:** a\n"
                                              + criteria, encoding="utf-8")

    def test_criteria_nudge_once_before_first_source_edit(self):
        self.plan()
        self.start("thêm tính năng xuất CSV cho trang báo cáo", "c1")
        target = {"file_path": str(self.project / "app" / "csv.py"), "content": "x"}
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / "tests" / "test_csv.py")}, "c1"),
                          "file test không bị nhắc")
        decision, reason = self.guard("Write", target, "c1")
        self.assertEqual(decision, "deny")
        self.assertIn("chưa có tiêu chí xong", reason)
        self.assertIn("`PLAN.md`", reason)
        self.assertNotIn("threat model", reason)
        self.assertIsNone(self.guard("Write", target, "c1"), "chỉ nhắc một lần mỗi lượt")

    def test_no_criteria_nudge_when_written_without_plan_or_for_small_work(self):
        self.plan("- **Tiêu chí xong** (xuất CSV, nguồn: lời bạn): 1) `python3 -m app.csv` ra file CSV\n")
        self.start("thêm tính năng xuất CSV cho trang báo cáo", "c2")
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / "app" / "csv.py")}, "c2"))
        self.plan()
        self.start("sửa typo trong README", "c3")
        self.assertIsNone(self.guard("Edit", {"file_path": str(self.project / "app" / "views.py")}, "c3"))
        (self.project / "PLAN.md").unlink()
        self.start("thêm tính năng xuất CSV cho trang báo cáo", "c4")
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / "app" / "csv.py")}, "c4"),
                          "không có file kế hoạch: chốt việc tự viết tiêu chí và báo là viết ở cuối việc")

    def test_subagent_in_a_worktree_inside_the_project_is_not_nudged(self):
        self.plan()
        worktree = self.project / ".claude" / "worktrees" / "w1"
        (worktree / "app").mkdir(parents=True)
        (worktree / ".git").write_text("gitdir: ../../../.git/worktrees/w1\n")
        self.start("Thêm tính năng upload ảnh đại diện cho người dùng", "c6")
        self.assertIsNone(self.guard("Write", {"file_path": str(worktree / "app" / "upload.py")}, "c6"),
                          "phiên chính lo threat model và §0; subagent không được sửa file kế hoạch")
        self.assertEqual(self.guard("Write", {"file_path": str(self.project / "app" / "upload.py")}, "c6")[0],
                         "deny", "file của chính project vẫn bị nhắc")

    def test_threat_model_and_criteria_nudges_come_together(self):
        self.plan()
        self.start("Thêm tính năng upload ảnh đại diện cho người dùng", "c5")
        target = {"file_path": str(self.project / "app" / "upload.py"), "content": "x"}
        decision, reason = self.guard("Write", target, "c5")
        self.assertEqual(decision, "deny")
        self.assertIn("threat-model", reason)
        self.assertIn("chưa có tiêu chí xong", reason)
        self.assertIsNone(self.guard("Write", target, "c5"), "một lần từ chối cho cả hai")

    def test_threat_model_nudge_once_before_first_source_edit(self):
        self.start("Thêm tính năng upload ảnh đại diện cho người dùng", "tm1")
        target = {"file_path": str(self.project / "app" / "upload.py"), "content": "x"}
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / "tests" / "test_upload.py")}, "tm1"),
                          "file test không bị nhắc")
        decision, reason = self.guard("Write", target, "tm1")
        self.assertEqual(decision, "deny")
        self.assertIn("threat-model", reason)
        self.assertIsNone(self.guard("Write", target, "tm1"), "chỉ nhắc một lần mỗi lượt")

    def test_no_nudge_when_threat_model_written_or_feature_is_plain(self):
        self.start("Thêm tính năng upload ảnh đại diện cho người dùng", "tm2")
        time.sleep(0.05)
        (self.project / ".agent").mkdir(exist_ok=True)  # hook UserPromptSubmit đã tạo nó để ghi lượt đang chạy
        (self.project / ".agent" / "threat-model.md").write_text("## mục mới\n")
        self.assertIsNone(self.guard("Edit", {"file_path": str(self.project / "app" / "views.py")}, "tm2"))
        self.start("Thêm tính năng xuất CSV cho trang báo cáo", "tm3")
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / "app" / "csv.py")}, "tm3"))

    def test_project_with_its_own_threat_model_skill_is_pointed_to_it(self):
        own = self.project / ".claude" / "skills" / "threat-model"
        own.mkdir(parents=True)
        (own / "SKILL.md").write_text("---\nname: threat-model\n---\n")
        self.start("Làm chức năng đăng nhập bằng mật khẩu cho admin", "tm4")
        decision, reason = self.guard("Write", {"file_path": str(self.project / "app" / "login.py")}, "tm4")
        self.assertEqual(decision, "deny")
        self.assertIn("skill threat-model của project này", reason)

    def test_bad_input_never_breaks_the_session(self):
        for raw in ("", "không phải json", "[]", json.dumps({"tool_name": "Bash", "tool_input": "chuỗi"}),
                    json.dumps({"tool_name": "Write", "tool_input": {}})):
            with self.subTest(raw=raw[:20]):
                self.assertIsNone(self.hook("pretool_guard.py", None, raw=raw))


class StopBase(GuardBase):
    """Lượt giả cho hook Stop: bắt đầu lượt, dừng, chạy chốt việc, ghi biên nhận, giao reviewer."""

    def turn(self, sid):
        self.hook("prompt_submit.py", {"session_id": sid, "cwd": str(self.project), "prompt": "sửa giúp mình phần này"})
        time.sleep(1.1)  # mtime của file đổi phải sau lúc bắt đầu lượt

    def stop(self, sid, active=False):
        return self.hook("stop.py", {"session_id": sid, "cwd": str(self.project), "stop_hook_active": active,
                                     "last_assistant_message": "Xong.\n\n➡️ Tiếp: chờ bạn"})

    def chot(self):
        done = subprocess.run(["python3", str(RISK), str(self.project)], capture_output=True, text=True,
                              env=self.env(), timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)

    def receipt(self, *cmd, label=None):
        args = ["--label", label] if label else []
        out = subprocess.run(["python3", str(RECEIPT), "run", "--project", str(self.project), *args, "--", *cmd],
                             capture_output=True, text=True, env=self.env(), timeout=60)
        return out.returncode

    def reviewer(self, sid):
        self.hook("subagent_start.py", {"session_id": sid, "cwd": str(self.project),
                                        "agent_type": "agent-stack:reviewer"})

    def evidence(self, sid):
        """Bằng chứng done-gate đòi từ mức vừa: biên nhận đạt cho code hiện tại và một lần giao reviewer."""
        time.sleep(1.1)  # biên nhận ghi thời điểm theo giây: phải sau mtime của file vừa sửa
        self.assertEqual(self.receipt("python3", "-c", "pass"), 0)
        self.reviewer(sid)


class StopRequiresChotViec(StopBase):
    def test_risky_code_change_without_done_gate_is_blocked_once(self):
        self.turn("s1")
        (self.project / "app" / "auth").mkdir()
        (self.project / "app" / "auth" / "login.py").write_text(LOGIN)
        out = self.stop("s1")
        self.assertEqual(out["decision"], "block")
        self.assertIn("chưa chạy done-gate", out["reason"])
        self.assertIn("mức rủi ro cao", out["reason"])
        self.assertIsNone(self.stop("s1", active=True), "lần dừng thứ hai không chặn nữa")

    def test_done_gate_with_evidence_passes(self):
        self.turn("s2")
        (self.project / "app" / "auth").mkdir()
        (self.project / "app" / "auth" / "login.py").write_text(LOGIN)
        self.chot()
        self.evidence("s2")
        self.assertIsNone(self.stop("s2"))

    def test_stop_gate_never_runs_fsmonitor_of_the_project(self):
        marker = self.tmp / "fsmonitor-ran"
        git(self.project, "config", "core.fsmonitor", f"touch {marker}; false")
        self.turn("s6")
        (self.project / "app" / "auth").mkdir()
        (self.project / "app" / "auth" / "login.py").write_text(LOGIN)
        self.assertEqual(self.stop("s6")["decision"], "block")
        self.assertFalse(marker.exists())

    def test_only_lines_new_since_last_done_gate_are_scored(self):
        self.turn("d1")
        (self.project / "app" / "auth").mkdir()
        login = self.project / "app" / "auth" / "login.py"
        login.write_text(LOGIN)
        self.chot()
        self.evidence("d1")
        self.assertIsNone(self.stop("d1"))
        self.turn("d2")  # lượt sau: chỉ đổi tên một biến trong file đã chốt, chưa commit
        login.write_text(LOGIN.replace("step_3 ", "buoc_3 "))
        self.assertIsNone(self.stop("d2"), "không ép chốt lại diff cũ vì một dòng sửa nhỏ")
        self.turn("d3")  # lượt sau nữa: thêm dòng nguy hiểm mới
        login.write_text(login.read_text() + "    eval(user)\n")
        out = self.stop("d3")
        self.assertEqual(out["decision"], "block")
        self.assertIn("eval", out["reason"])

    def test_fix_after_review_is_flagged_until_rescored_with_new(self):
        # Tái hiện 28/10/2026: chốt việc chạy risk.py, sửa theo review thêm dòng nguy hiểm trong cùng lượt (hook im vì
        # risk.py đã chạy trong lượt), lượt sau chỉ commit thì bị nhắc; agent tưởng nhắc sai.
        self.turn("f1")
        (self.project / "app" / "auth").mkdir()
        login = self.project / "app" / "auth" / "login.py"
        login.write_text(LOGIN)
        self.chot()
        login.write_text(login.read_text() + "    eval(user)\n")
        self.evidence("f1")
        self.assertIsNone(self.stop("f1"))
        self.turn("f2")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "chỉ commit")
        out = self.stop("f2")
        self.assertEqual(out["decision"], "block")
        self.assertIn("đổi hay commit", out["reason"])
        self.assertIn("mà chưa chạy done-gate", out["reason"], "mod giao diện nhận câu nhắc theo cụm này")
        cmd = re.search(r"`risk\.py (--new --base [0-9a-f]{12})`", out["reason"])
        self.assertIsNotNone(cmd, "lượt đã commit: câu nhắc phải in sẵn --base")
        # Quên --base: diff rỗng, không được tính là đã chốt việc.
        empty = subprocess.run(["python3", str(RISK), str(self.project), "--new"],
                               capture_output=True, text=True, env=self.env(), timeout=30)
        self.assertIn("Không có thay đổi", empty.stdout)
        self.assertEqual(self.stop("f2")["decision"], "block")
        done = subprocess.run(["python3", str(RISK), str(self.project), *cmd.group(1).split()],
                              capture_output=True, text=True, env=self.env(), timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("1 file, +1/−0", done.stdout, "chỉ chấm dòng sửa sau lần chấm trước")
        self.assertIn("eval", done.stdout)
        self.reviewer("f2")  # phần sửa mức vừa trở lên phải được review lại; biên nhận của f1 vẫn khớp nội dung
        self.assertIsNone(self.stop("f2"))

    def test_new_from_a_subdirectory_reads_the_project_marks(self):
        self.turn("g1")
        (self.project / "app" / "auth").mkdir()
        (self.project / "app" / "auth" / "login.py").write_text(LOGIN)
        self.chot()
        done = subprocess.run(["python3", str(RISK), str(self.project / "app"), "--new"],
                              capture_output=True, text=True, env=self.env(), timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Không có thay đổi", done.stdout, "dòng đã chấm ở gốc project không bị chấm lại")

    def test_diff_programs_from_repo_config_never_run_and_content_is_still_scored(self):
        ext, conv = self.tmp / "ext-ran", self.tmp / "textconv-ran"
        git(self.project, "config", "diff.external", f"sh -c 'touch {ext}' --")
        git(self.project, "config", "diff.y.textconv", f"sh -c 'touch {conv}; cat' --")
        (self.project / ".git" / "info" / "attributes").write_text("* diff=y\n")
        self.turn("e1")
        (self.project / "app" / "run.py").write_text("import subprocess\nsubprocess.run(cmd, shell=True)\n" * 3)
        out = self.stop("e1")
        self.assertEqual(out["decision"], "block")
        self.assertIn("qua shell", out["reason"], "vẫn đọc được dòng thêm vào dù có diff.external")
        self.assertFalse(ext.exists() or conv.exists())

    def test_repo_with_its_own_clean_filter_is_not_scored(self):
        git(self.project, "config", "filter.x.clean", f"sh -c 'touch {self.tmp / 'clean-ran'}; cat'")
        (self.project / ".git" / "info" / "attributes").write_text("*.py filter=x\n")
        self.turn("e2")
        (self.project / "app" / "auth").mkdir()
        (self.project / "app" / "auth" / "login.py").write_text(LOGIN)
        self.assertIsNone(self.stop("e2"), "git diff sẽ chạy clean filter của repo lạ: bỏ chấm")

    def test_low_risk_change_is_not_blocked(self):
        self.turn("s3")
        (self.project / "README.md").write_text("# Ghi chú\n")
        self.assertIsNone(self.stop("s3"))

    def test_change_committed_during_turn_is_still_checked(self):
        self.turn("s4")
        (self.project / "app" / "auth").mkdir()
        (self.project / "app" / "auth" / "login.py").write_text(LOGIN)
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "commit vội")
        out = self.stop("s4")
        self.assertEqual(out["decision"], "block")
        self.assertIn("done-gate", out["reason"])

    def test_preexisting_risky_change_is_not_blamed_on_this_turn(self):
        (self.project / "app" / "auth").mkdir()
        (self.project / "app" / "auth" / "login.py").write_text(LOGIN)  # có từ trước lượt
        self.turn("s5")
        (self.project / "README.md").write_text("# Ghi chú\n")
        self.assertIsNone(self.stop("s5"))


class StopRequiresEvidence(StopBase):
    """Lượt đã chạy done-gate ở mức vừa trở lên mà thiếu bằng chứng: hook Stop nhắc một lần (cải tiến 1 của trang
    đánh giá pipeline, 03/11/2026)."""

    def risky(self):
        (self.project / "app" / "auth").mkdir()
        login = self.project / "app" / "auth" / "login.py"
        login.write_text(LOGIN)
        return login

    def test_risk_py_alone_is_not_enough_and_the_reminder_comes_once(self):
        # Tái hiện ví dụ 1: chạy bước chấm rủi ro rồi báo xong, không test, không review.
        self.turn("v1")
        self.risky()
        self.chot()
        out = self.stop("v1")
        self.assertEqual(out["decision"], "block")
        self.assertIn("nhưng còn thiếu bằng chứng", out["reason"], "mod giao diện nhận câu nhắc theo cụm này")
        self.assertIn("không có biên nhận đạt", out["reason"])
        self.assertIn("agent-stack:reviewer", out["reason"])
        self.assertIn("chưa có biên nhận đạt, chưa review", out["systemMessage"])
        self.assertLess(self.elapsed, 3)
        self.assertIsNone(self.stop("v1", active=True), "chỉ nhắc một lần mỗi lượt")
        self.assertIsNone(self.stop("v1"))

    def test_evidence_is_checked_after_the_gate_blocked_and_done_gate_ran(self):
        # Đường thường gặp: hook chặn vì chưa chốt việc, Claude chạy risk.py rồi dừng lại (stop_hook_active).
        self.turn("v2")
        self.risky()
        self.assertIn("mà chưa chạy done-gate", self.stop("v2")["reason"])
        self.chot()
        out = self.stop("v2", active=True)
        self.assertEqual(out["decision"], "block")
        self.assertIn("mức rủi ro cao", out["reason"])
        self.assertIsNone(self.stop("v2", active=True))

    def test_code_edited_after_the_tests_needs_a_new_receipt(self):
        self.turn("v3")
        login = self.risky()
        self.chot()
        self.evidence("v3")
        login.write_text(login.read_text() + "    step_x = 1\n")
        out = self.stop("v3")
        self.assertIn("không có biên nhận đạt", out["reason"])
        self.assertNotIn("agent-stack:reviewer", out["reason"], "reviewer đã chạy trong lượt")

    def test_docs_edited_after_the_tests_keep_the_receipt(self):
        self.turn("v4")
        self.risky()
        self.chot()
        self.evidence("v4")
        (self.project / "README.md").write_text("# Ghi chú sau khi test\n")
        (self.project / ".agent").mkdir(exist_ok=True)
        (self.project / ".agent" / "threat-model.md").write_text("## mục mới\n")
        # Trang cho người đọc ở gốc repo (như HUONG-DAN.html) là tài liệu nhờ dấu của reader-page; hook từng chặn
        # nhầm ở chính phiên làm việc này (03/11/2026).
        (self.project / "HUONG-DAN.html").write_text('<main data-loai="giai-thich"><p>Hướng dẫn</p></main>\n')
        self.assertIsNone(self.stop("v4"))

    def test_updating_plan_after_the_tests_keeps_the_receipt(self):
        # Reviewer tái hiện 03/11/2026: done-gate chạy test (bước 4) rồi mới cập nhật §0 (bước 6); hook chặn vì §0
        # trước, rồi ở lần dừng thứ hai lại chặn sai vì "chưa có biên nhận đạt" (file kế hoạch bị bỏ khi dò file đổi).
        (self.project / "PLAN.md").write_text("# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n- Xong: chưa có\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "kế hoạch")
        self.turn("v11")
        self.risky()
        self.chot()
        self.evidence("v11")
        self.assertIn("Cập nhật §0", self.stop("v11")["reason"])
        (self.project / "PLAN.md").write_text("# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n- Xong: đăng nhập\n")
        self.assertIsNone(self.stop("v11", active=True))

    def test_commit_after_the_tests_keeps_the_receipt(self):
        self.turn("v12")
        self.risky()
        self.chot()
        self.evidence("v12")
        (self.project / "README.md").write_text("# Ghi chú sau khi test\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "đăng nhập")
        self.assertIsNone(self.stop("v12"))

    def test_deleting_code_after_the_tests_needs_a_new_receipt(self):
        self.turn("v13")
        (self.project / "app" / "views.py").unlink()
        self.risky()
        self.chot()
        self.evidence("v13")
        (self.project / "app" / "auth" / "login.py").unlink()
        out = self.stop("v13")
        self.assertIn("không có biên nhận đạt", out["reason"])

    def test_check_failing_on_current_code_is_named(self):
        self.turn("v5")
        self.risky()
        self.chot()
        self.evidence("v5")
        self.assertEqual(self.receipt("python3", "-c", "import sys; sys.exit(3)", label="lint"), 3)
        out = self.stop("v5")
        self.assertIn("`lint` (mã 3)", out["reason"])
        self.assertNotIn("không có biên nhận đạt", out["reason"], "biên nhận đạt khác vẫn còn đúng")

    def test_failing_reproduction_before_the_fix_is_not_a_gap(self):
        self.turn("v6")
        login = self.risky()
        time.sleep(1.1)
        self.assertEqual(self.receipt("python3", "-c", "import sys; sys.exit(1)", label="tai-hien"), 1)
        time.sleep(1.1)
        login.write_text(login.read_text() + "    fixed = True\n")
        self.chot()
        self.evidence("v6")
        self.assertIsNone(self.stop("v6"))

    def test_receipt_counts_when_the_fingerprint_cannot_be_computed(self):
        # Reviewer 03/11/2026: repo git lồng chưa ignore làm hash-object lỗi, mọi biên nhận không có dấu vân tay.
        nested = self.project / "nested"
        nested.mkdir()
        git(nested, "init", "-q")
        self.turn("v14")
        self.risky()
        self.chot()
        self.evidence("v14")
        self.assertIsNone(self.stop("v14"), "biên nhận chạy trong lượt được tính khi không tính được dấu vân tay")

    def test_low_level_done_gate_needs_no_evidence(self):
        self.turn("v7")
        (self.project / "README.md").write_text("# Ghi chú\n")
        self.chot()
        self.assertIsNone(self.stop("v7"))

    def test_pi_has_no_subagent_hook_so_reviewer_is_not_required(self):
        self.turn("v8")
        self.risky()
        self.chot()
        time.sleep(1.1)
        self.assertEqual(self.receipt("python3", "-c", "pass"), 0)
        out = self.hook("stop.py", {"session_id": "v8", "cwd": str(self.project), "stop_hook_active": False,
                                    "last_assistant_message": "Xong."}, AGENT_STACK_HOST="pi")
        self.assertIsNone(out)

    def test_evidence_check_never_runs_commands_of_the_repo(self):
        self.turn("v9")
        self.risky()
        self.chot()
        time.sleep(1.1)
        self.assertEqual(self.receipt("python3", "-c", "pass"), 0)  # có biên nhận thì hook mới tính dấu vân tay
        marker = self.tmp / "fsmonitor-ran"
        git(self.project, "config", "core.fsmonitor", f"touch {marker}; false")
        out = self.stop("v9")
        self.assertIn("agent-stack:reviewer", out["reason"])
        self.assertNotIn("không có biên nhận đạt", out["reason"], "đã tính dấu vân tay và thấy biên nhận còn đúng")
        self.assertFalse(marker.exists())

    def test_repo_with_its_own_clean_filter_is_not_checked(self):
        self.turn("v10")
        self.risky()
        self.chot()
        git(self.project, "config", "filter.x.clean", f"sh -c 'touch {self.tmp / 'clean-ran'}; cat'")
        (self.project / ".git" / "info" / "attributes").write_text("*.py filter=x\n")
        # Chỉ kiểm được là bỏ kiểm bằng chứng: `git status` ở đầu hook (có từ trước) đã có thể chạy filter, phần còn
        # lại của mối đe dọa đã ghi trong threat model; hash-object của dấu vân tay thì chạy filter trên mọi file đổi.
        self.assertIsNone(self.stop("v10"), "tính dấu vân tay sẽ chạy clean filter của repo lạ: bỏ kiểm")

    def test_asserts_committed_after_done_gate_are_not_counted_as_removed(self):
        # Reviewer tái hiện 03/11/2026: assert đã qua chốt việc rồi được commit không còn là dòng thêm vào; lượt sau
        # chỉ thêm test mới mà bị báo "nới assert".
        (self.project / "tests").mkdir()
        test_file = self.project / "tests" / "test_x.py"
        self.turn("w3")
        test_file.write_text("def test_f(self):\n    self.assertEqual(f(1), 1)\n")
        self.chot()
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "test f")
        self.assertIsNone(self.stop("w3"))
        self.turn("w4")
        test_file.write_text(test_file.read_text() + "def test_g(self):\n    self.assertTrue(g())\n"
                             "    self.assertIn(1, h())\n")
        self.assertIsNone(self.stop("w4"))

    def test_loosened_assert_after_done_gate_is_flagged_next_turn(self):
        # Tái hiện ví dụ 3: test đã qua chốt việc, lượt sau đổi assertEqual thành assertIn cho đạt (+1/−1 dòng).
        (self.project / "tests").mkdir()
        test_file = self.project / "tests" / "test_level.py"
        self.turn("w1")
        test_file.write_text("def test_level(self):\n    self.assertEqual(r['level'], 'cao')\n")
        self.chot()
        self.assertIsNone(self.stop("w1"), "chỉ có file test mới: mức thấp")
        self.turn("w2")
        test_file.write_text("def test_level(self):\n    self.assertIn(r['level'], ('vua', 'cao'))\n")
        out = self.stop("w2")
        self.assertEqual(out["decision"], "block")
        self.assertIn("nới assert", out["reason"])
