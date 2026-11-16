"""GĐ6 việc A (16/11/2026), slug `post-edit-archctl-trung`: post_edit bỏ gọi archctl khi hook `archctl check --hook` mà
`archctl init` sinh trong `.claude/settings*.json` của project chắc chắn chạy và kiểm cùng file, để vi phạm không bị báo
hai lần. Mọi ca khác giữ nguyên hành vi cũ (gọi archctl, báo vi phạm).

Dùng lại harness `ArchHookBase` của test_archgate (archctl giả ghi lời gọi vào `FAKE_ARCH_LOG`). Mỗi test tự đặt rõ
`CLAUDE_PROJECT_DIR` và `AGENT_STACK_HOST`, không dựa vào môi trường ngoài. Ca bỏ: không có lời gọi archctl nào và
`additionalContext` rỗng. Ca báo: có dòng `✗ VI PHẠM` và đúng một lời gọi archctl đúng đối số.
"""
import json
import os
import unittest

from tests._util import git
from tests.test_archgate import BASE_PATH, RULES, VIOLATION, ArchHookBase, make_fake

FLAG = "✗ VI PHẠM  Web -> Report"
HOOK = "archctl check --hook"
DEFAULT_MATCHER = "Edit|Write|MultiEdit|Bash"
NO_MATCHER = object()  # khóa `matcher` vắng mặt
ALL_TOOLS = ("Edit", "Write", "MultiEdit", "Bash")
FILE_TOOLS = ("Edit", "Write", "MultiEdit")
NEW_TEXT = "from app.report.data import X\n"


def config(command=HOOK, matcher=DEFAULT_MATCHER, event="PostToolUse") -> dict:
    """Nội dung giống `archctl init` sinh (phần liên quan, thêm permissions.deny như file thật)."""
    entry = {"hooks": [{"type": "command", "command": command, "timeout": 30}]}
    if matcher is not NO_MATCHER:
        entry["matcher"] = matcher
    return {"permissions": {"deny": ["Edit(.arch/**)"]}, "hooks": {event: [entry]}}


class ArchDedupeBase(ArchHookBase):
    def setUp(self):
        super().setUp()
        self.view = self.project / "app" / "web" / "view.py"
        self.n = 0

    # ---- dựng settings ----
    def put(self, cfg, name="settings.json"):
        path = self.project / ".claude" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg))
        return path

    def put_raw(self, data, name="settings.json"):
        path = self.project / ".claude" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return path

    def env_for(self, **extra):
        """Môi trường cho hook chạy dưới Claude Code với archctl giả (báo vi phạm) đứng đầu PATH."""
        extra.setdefault("CLAUDE_PROJECT_DIR", str(self.project))
        extra.setdefault("AGENT_STACK_HOST", "claude-code")
        return self.fake_env(1, VIOLATION, **extra)

    # ---- chạy một công cụ ----
    def sid(self):
        self.n += 1
        return f"dd{self.n}"

    def run_tool(self, tool, env, cwd=None, target=None):
        """Đổi file thật rồi gửi payload của `tool`; trả additionalContext. Bash bắt đầu lượt trước (nhánh Bash cần
        dấu cây). Mỗi lần dùng nhật ký archctl và phiên mới."""
        self.log.unlink(missing_ok=True)
        sid = self.sid()
        target = target or self.view
        cwd = cwd or self.project
        target.write_text(NEW_TEXT)
        if tool == "Bash":
            self.start("làm tiếp", sid)
            payload_input = {"command": "sed -i '' s/Y/X/ app/web/view.py"}
        elif tool == "Edit":
            payload_input = {"file_path": str(target), "new_string": NEW_TEXT.strip()}
        elif tool == "Write":
            payload_input = {"file_path": str(target), "content": NEW_TEXT}
        else:
            payload_input = {"file_path": str(target),
                             "edits": [{"old_string": "Y = 2", "new_string": NEW_TEXT.strip()}]}
        return self.post_at(cwd, tool, payload_input, sid, **env)

    def post_at(self, cwd, tool, tool_input, sid, **env):
        out = self.hook("post_edit.py", {"session_id": sid, "cwd": str(cwd), "tool_name": tool,
                                         "tool_input": tool_input, "tool_response": {},
                                         "hook_event_name": "PostToolUse"}, **env)
        return out["hookSpecificOutput"]["additionalContext"] if out else ""

    # ---- kiểm kết quả ----
    def expect_reported(self, tool, ctx, target=None, root=None):
        root = root or self.project
        self.assertIn(FLAG, ctx)
        want = f"check --root {root} --changed" if tool == "Bash" else f"check --root {root} {target or self.view}"
        self.assertEqual(self.calls(), [want])

    def expect_skipped(self, ctx):
        self.assertEqual(self.calls(), [])
        self.assertEqual(ctx, "")

    def make_other(self):
        """Project khác có luật riêng và git riêng, nằm ngoài thư mục làm việc."""
        other = self.tmp / "other"
        for rel, text in {".arch/system.arch": RULES, "app/__init__.py": "", "app/web/__init__.py": "",
                          "app/report/__init__.py": "", "app/web/view.py": "Y = 2\n",
                          "app/report/data.py": "X = 1\n"}.items():
            path = other / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        git(other, "init", "-q")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "arch")
        return other

    def make_svc(self):
        """Monorepo: gốc project có luật, `svc/` có bộ luật lồng riêng."""
        svc = self.project / "svc"
        for rel, text in {".arch/system.arch": RULES, "app/__init__.py": "", "app/web/__init__.py": "",
                          "app/report/__init__.py": "", "app/web/view.py": "Y = 2\n"}.items():
            path = svc / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "svc")
        return svc


class HookCoversTool(ArchDedupeBase):
    def test_hook_in_settings_json_skips_archctl_for_every_tool(self):
        # spec:post-edit-archctl-trung#S1
        self.put(config())
        for tool in ALL_TOOLS:
            with self.subTest(tool=tool):
                self.expect_skipped(self.run_tool(tool, self.env_for()))

    def test_hook_in_settings_local_json_skips_archctl_for_every_tool(self):
        # spec:post-edit-archctl-trung#S1
        self.put(config(), "settings.local.json")
        for tool in ALL_TOOLS:
            with self.subTest(tool=tool):
                self.expect_skipped(self.run_tool(tool, self.env_for()))

    def test_missing_empty_or_star_matcher_covers_every_tool(self):
        # spec:post-edit-archctl-trung#S1
        for matcher in (NO_MATCHER, "", "*"):
            self.put(config(matcher=matcher))
            for tool in ALL_TOOLS:
                with self.subTest(matcher=None if matcher is NO_MATCHER else matcher, tool=tool):
                    self.expect_skipped(self.run_tool(tool, self.env_for()))

    def test_matcher_alternatives_cover_exactly_the_tools_they_name(self):
        # spec:post-edit-archctl-trung#S1
        for matcher, covered in (("Edit", {"Edit"}), ("Write", {"Write"}), ("Bash", {"Bash"}),
                                 ("Edit|Write", {"Edit", "Write"}), ("Edit|Write|MultiEdit", set(FILE_TOOLS)),
                                 ("MultiEdit|Bash", {"MultiEdit", "Bash"}), ("Edit|Bash", {"Edit", "Bash"}),
                                 ("Edit|Write|MultiEdit|Bash|mcp__x", set(ALL_TOOLS))):
            self.put(config(matcher=matcher))
            for tool in ALL_TOOLS:
                with self.subTest(matcher=matcher, tool=tool):
                    ctx = self.run_tool(tool, self.env_for())
                    if tool in covered:
                        self.expect_skipped(ctx)
                    else:
                        self.expect_reported(tool, ctx)

    def test_any_covering_entry_is_enough(self):
        # spec:post-edit-archctl-trung#S1
        cfg = config(matcher="Edit")
        cfg["hooks"]["PostToolUse"].append({"matcher": "Bash", "hooks": [{"type": "command", "command": HOOK}]})
        self.put(cfg)
        for tool in ("Edit", "Bash"):
            with self.subTest(tool=tool):
                self.expect_skipped(self.run_tool(tool, self.env_for()))
        with self.subTest(tool="Write"):
            self.expect_reported("Write", self.run_tool("Write", self.env_for()))

    def test_hook_among_other_hooks_and_events_is_found(self):
        # spec:post-edit-archctl-trung#S1
        cfg = config()
        cfg["hooks"]["PostToolUse"].insert(0, {"matcher": "Edit", "hooks": [{"type": "command", "command": "echo hi"}]})
        cfg["hooks"]["PostToolUse"][1]["hooks"].insert(0, {"type": "command", "command": "ruff check ."})
        cfg["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "echo stop"}]}]
        self.put(cfg)
        self.expect_skipped(self.run_tool("Edit", self.env_for()))

    def test_quoted_and_spaced_command_still_counts(self):
        # spec:post-edit-archctl-trung#S1
        for command in ("archctl   check   --hook", "archctl check --hook --root .", "archctl 'check' \"--hook\""):
            self.put(config(command=command))
            with self.subTest(command=command):
                self.expect_skipped(self.run_tool("Edit", self.env_for()))

    def test_file_inside_cwd_subdir_is_covered_but_sibling_dir_is_not(self):
        # spec:post-edit-archctl-trung#S1
        self.put(config())
        self.expect_skipped(self.run_tool("Edit", self.env_for(), cwd=self.project / "app"))
        # spec:post-edit-archctl-trung#S6
        data = self.project / "app" / "report" / "data.py"
        ctx = self.run_tool("Edit", self.env_for(), cwd=self.project / "app" / "web", target=data)
        self.expect_reported("Edit", ctx, target=data)

    def test_settings_just_under_the_size_cap_is_still_read(self):
        # spec:post-edit-archctl-trung#S1
        cfg = config()
        cfg["pad"] = "x" * 200_000
        self.put(cfg)
        self.assertLess(len(json.dumps(cfg)), 262_144)
        self.expect_skipped(self.run_tool("Edit", self.env_for()))

    def test_symlink_to_a_file_inside_the_project_is_read(self):
        # spec:post-edit-archctl-trung#S1
        real = self.project / "tools" / "claude-settings.json"
        real.parent.mkdir()
        real.write_text(json.dumps(config()))
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "settings.json").symlink_to(real)
        self.expect_skipped(self.run_tool("Edit", self.env_for()))

    def test_claude_code_host_default_name_is_the_same_as_missing_host(self):
        # spec:post-edit-archctl-trung#S1
        self.put(config())
        self.expect_skipped(self.run_tool("Edit", self.env_for(AGENT_STACK_HOST="claude-code")))


class HookDoesNotCoverOrDoesNotCount(ArchDedupeBase):
    def test_legacy_changed_hook_does_not_count(self):
        # spec:post-edit-archctl-trung#S2
        self.put(config(command="archctl check --changed"))
        for tool in ALL_TOOLS:
            with self.subTest(tool=tool):
                self.expect_reported(tool, self.run_tool(tool, self.env_for()))

    def test_hook_with_a_path_instead_of_the_bare_name_does_not_count(self):
        # spec:post-edit-archctl-trung#S2
        for command in (f"{self.bin}/archctl check --hook", "/usr/local/bin/archctl check --hook",
                        "./archctl check --hook", ".venv/bin/archctl check --hook", "~/bin/archctl check --hook"):
            self.put(config(command=command))
            for tool in ("Edit", "Bash"):
                with self.subTest(command=command, tool=tool):
                    self.expect_reported(tool, self.run_tool(tool, self.env_for()))

    def test_other_commands_do_not_count(self):
        # spec:post-edit-archctl-trung#S2
        for command in ("echo archctl check --hook", "archctl-wrapper check --hook", "myarchctl check --hook",
                        "archctl --hook", "archctl check", "archctl verify --hook", "python3 -m archctl check --hook",
                        "sudo archctl check --hook", ""):
            self.put(config(command=command))
            with self.subTest(command=command):
                self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))

    def test_no_settings_file_or_no_archctl_hook_keeps_reporting(self):
        # spec:post-edit-archctl-trung#S2
        for tool in ALL_TOOLS:
            with self.subTest(case="no settings", tool=tool):
                self.expect_reported(tool, self.run_tool(tool, self.env_for()))
        cases = {"no hooks key": {"permissions": {"deny": []}},
                 "empty hooks": {"hooks": {}},
                 "other event": config(event="Stop"),
                 "pre tool use": config(event="PreToolUse"),
                 "other command": config(command="echo hi")}
        for name, cfg in cases.items():
            self.put(cfg)
            for tool in ("Edit", "Bash"):
                with self.subTest(case=name, tool=tool):
                    self.expect_reported(tool, self.run_tool(tool, self.env_for()))

    def test_archctl_inside_project_first_on_path_is_not_skipped(self):
        # spec:post-edit-archctl-trung#S2
        self.put(config())
        inside = make_fake(self.project / ".venv" / "bin")
        env = self.env_for()
        env["PATH"] = f"{inside.parent}:{self.bin}:{BASE_PATH}"
        for tool in ALL_TOOLS:
            with self.subTest(tool=tool):
                self.expect_reported(tool, self.run_tool(tool, env))

    def test_archctl_inside_project_only_on_path_still_gets_the_missing_note(self):
        # spec:post-edit-archctl-trung#S2
        # spec:post-edit-archctl-trung#S7
        self.put(config())
        inside = make_fake(self.project / ".venv" / "bin")
        env = self.env_for()
        env["PATH"] = f"{inside.parent}:{BASE_PATH}"
        ctx = self.run_tool("Edit", env)
        self.assertIn("máy chưa có archctl", ctx)
        self.assertEqual(self.calls(), [])

    def test_settings_are_read_from_claude_project_dir_not_from_cwd(self):
        # spec:post-edit-archctl-trung#S2
        self.put(config())
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        for tool in ("Edit", "Bash"):
            with self.subTest(tool=tool):
                self.expect_reported(tool, self.run_tool(tool, self.env_for(CLAUDE_PROJECT_DIR=str(elsewhere))))

    def test_matcher_that_does_not_cover_the_tool_still_reports(self):
        # spec:post-edit-archctl-trung#S3
        self.put(config(matcher="Edit|Write"))
        for tool in ("Bash", "MultiEdit"):
            with self.subTest(tool=tool):
                self.expect_reported(tool, self.run_tool(tool, self.env_for()))

    def test_matcher_must_match_the_whole_tool_name(self):
        # spec:post-edit-archctl-trung#S3
        for matcher, tool in (("Edit", "MultiEdit"), ("Bas", "Bash"), ("Multi", "MultiEdit"), ("Write|Edi", "Edit"),
                              ("edit", "Edit"), ("Bash(git *)", "Bash"), ("Notebook.*", "Edit")):
            self.put(config(matcher=matcher))
            with self.subTest(matcher=matcher, tool=tool):
                self.expect_reported(tool, self.run_tool(tool, self.env_for()))

    def test_regex_matchers_are_never_run_and_never_cover(self):
        # spec:post-edit-archctl-trung#S3
        for matcher in (".*", "Edit.*", "(Edit|Write)", "[EW].*", "Edit|Wri.*", "*Edit", "Edit|Write|MultiEdit|Ba.*",
                        ".*Edit", "^Edit$", "Edit|Write|MultiEdit|Bash.", "(((.*)*)*)*x"):
            self.put(config(matcher=matcher))
            for tool in ALL_TOOLS:
                with self.subTest(matcher=matcher, tool=tool):
                    self.expect_reported(tool, self.run_tool(tool, self.env_for()))
                    self.assertLess(self.elapsed, 5.0)

    def test_matcher_that_is_not_a_string_or_not_a_valid_short_regex_never_covers(self):
        # spec:post-edit-archctl-trung#S3
        long_but_matching = "Edit" + "|Nope" * 50  # 254 ký tự, khớp Edit nếu không có trần 200
        self.assertGreater(len(long_but_matching), 200)
        for matcher in (5, True, None, ["Edit"], {"a": 1}, "(", "[", "Edit|(", "*Edit", long_but_matching):
            self.put(config(matcher=matcher))
            with self.subTest(matcher=matcher):
                self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))


class SettingsAreUntrusted(ArchDedupeBase):
    def test_broken_or_wrongly_typed_settings_count_as_no_hook(self):
        # spec:post-edit-archctl-trung#S4
        entry_ok = {"hooks": [{"type": "command", "command": HOOK}]}
        cases = {"json hỏng": "{", "rỗng": "", "không phải utf-8": b"\xff\xfe\x00{",
                 "null": "null", "list gốc": "[]", "chuỗi gốc": '"archctl check --hook"',
                 "hooks là list": json.dumps({"hooks": [entry_ok]}),
                 "PostToolUse là dict": json.dumps({"hooks": {"PostToolUse": entry_ok}}),
                 "PostToolUse là chuỗi": json.dumps({"hooks": {"PostToolUse": HOOK}}),
                 "mục không phải dict": json.dumps({"hooks": {"PostToolUse": [5, "x", None, [entry_ok]]}}),
                 "hooks con là dict": json.dumps({"hooks": {"PostToolUse": [{"hooks": entry_ok["hooks"][0]}]}}),
                 "hooks con là chuỗi": json.dumps({"hooks": {"PostToolUse": [{"hooks": HOOK}]}}),
                 "phần tử hooks con là chuỗi": json.dumps({"hooks": {"PostToolUse": [{"hooks": [HOOK]}]}}),
                 "command là số": json.dumps(config(command=5)),
                 "command là list": json.dumps(config(command=["archctl", "check", "--hook"])),
                 "command là null": json.dumps(config(command=None)),
                 "thiếu command": json.dumps({"hooks": {"PostToolUse": [{"hooks": [{"type": "command"}]}]}}),
                 "matcher là số": json.dumps(config(matcher=5)),
                 "lồng rất sâu": "[" * 100_000}
        for name, body in cases.items():
            self.put_raw(body)
            for tool in ("Edit", "Bash"):
                with self.subTest(case=name, tool=tool):
                    self.expect_reported(tool, self.run_tool(tool, self.env_for()))

    def test_broken_settings_local_json_is_ignored_too(self):
        # spec:post-edit-archctl-trung#S4
        for body in ("{", "[" * 100_000, json.dumps({"hooks": []})):
            self.put_raw(body, "settings.local.json")
            with self.subTest(body=body[:20]):
                self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))

    def test_settings_over_the_size_cap_count_as_no_hook(self):
        # spec:post-edit-archctl-trung#S4
        cfg = config()
        cfg["pad"] = "x" * 300_000
        text = json.dumps(cfg)
        self.assertGreater(len(text), 262_144)
        for name in ("settings.json", "settings.local.json"):
            self.put_raw(text, name)
            for tool in ("Edit", "Bash"):
                with self.subTest(name=name, tool=tool):
                    self.expect_reported(tool, self.run_tool(tool, self.env_for()))
            (self.project / ".claude" / name).unlink()

    def test_fifo_as_settings_does_not_hang_the_hook(self):
        # spec:post-edit-archctl-trung#S4
        (self.project / ".claude").mkdir()
        os.mkfifo(self.project / ".claude" / "settings.json")
        self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))
        self.assertLess(self.elapsed, 5.0)

    def test_fifo_as_settings_local_json_does_not_hang_the_hook(self):
        # spec:post-edit-archctl-trung#S4
        self.put(config(command="archctl check --changed"))
        os.mkfifo(self.project / ".claude" / "settings.local.json")
        self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))
        self.assertLess(self.elapsed, 5.0)

    def test_directory_as_settings_counts_as_no_hook(self):
        # spec:post-edit-archctl-trung#S4
        (self.project / ".claude" / "settings.json").mkdir(parents=True)
        self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))

    def test_symlink_pointing_outside_the_project_is_not_read(self):
        # spec:post-edit-archctl-trung#S4
        outside = self.tmp / "outside.json"
        outside.write_text(json.dumps(config()))
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "settings.json").symlink_to(outside)
        for tool in ("Edit", "Bash"):
            with self.subTest(tool=tool):
                self.expect_reported(tool, self.run_tool(tool, self.env_for()))

    def test_symlinked_settings_local_json_pointing_outside_is_not_read(self):
        # spec:post-edit-archctl-trung#S4
        outside = self.tmp / "outside.json"
        outside.write_text(json.dumps(config()))
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "settings.local.json").symlink_to(outside)
        self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))

    def test_claude_dir_symlinked_outside_the_project_is_not_read(self):
        # spec:post-edit-archctl-trung#S4
        folder = self.tmp / "outside-claude"
        folder.mkdir()
        (folder / "settings.json").write_text(json.dumps(config()))
        (self.project / ".claude").symlink_to(folder)
        self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))


class OtherHosts(ArchDedupeBase):
    def test_pi_host_keeps_reporting_even_with_the_hook(self):
        # spec:post-edit-archctl-trung#S5
        self.put(config())
        self.put(config(), "settings.local.json")
        for tool in ALL_TOOLS:
            with self.subTest(tool=tool):
                self.expect_reported(tool, self.run_tool(tool, self.env_for(AGENT_STACK_HOST="pi")))

    def test_no_claude_project_dir_keeps_reporting_even_with_the_hook(self):
        # spec:post-edit-archctl-trung#S5
        self.put(config())
        for tool in ALL_TOOLS:
            with self.subTest(tool=tool):
                self.expect_reported(tool, self.run_tool(tool, self.env_for(CLAUDE_PROJECT_DIR="")))

    def test_pi_without_project_dir_keeps_reporting(self):
        # spec:post-edit-archctl-trung#S5
        self.put(config())
        env = self.env_for(AGENT_STACK_HOST="pi", CLAUDE_PROJECT_DIR="")
        self.expect_reported("Edit", self.run_tool("Edit", env))


class WhatTheProjectHookDoesNotCheck(ArchDedupeBase):
    def test_file_outside_the_working_directory_is_still_checked(self):
        # spec:post-edit-archctl-trung#S6
        self.put(config())
        other = self.make_other()
        target = other / "app" / "web" / "view.py"
        for tool in FILE_TOOLS:
            with self.subTest(tool=tool):
                ctx = self.run_tool(tool, self.env_for(), cwd=self.project, target=target)
                self.expect_reported(tool, ctx, target=target, root=other)

    def test_file_reached_through_a_symlink_out_of_the_working_directory_is_still_checked(self):
        # spec:post-edit-archctl-trung#S6
        self.put(config())
        other = self.make_other()
        (self.project / "app" / "link").symlink_to(other / "app")
        target = self.project / "app" / "link" / "web" / "view.py"
        ctx = self.run_tool("Edit", self.env_for(), cwd=self.project, target=target)
        self.assertIn(FLAG, ctx)
        self.assertEqual(len(self.calls()), 1)

    def test_bash_skips_the_cwd_root_but_checks_a_nested_root_that_changed(self):
        # spec:post-edit-archctl-trung#S6
        self.put(config())
        svc = self.make_svc()
        self.log.unlink(missing_ok=True)
        sid = self.sid()
        self.start("làm tiếp", sid)
        (svc / "app" / "web" / "view.py").write_text(NEW_TEXT)
        ctx = self.post_at(self.project, "Bash", {"command": "sed -i '' s/Y/X/ svc/app/web/view.py"}, sid,
                           **self.env_for())
        self.assertIn(FLAG, ctx)
        self.assertEqual(self.calls(), [f"check --root {svc} --changed"])

    def test_bash_in_nested_root_still_checks_the_outer_root_when_it_changed(self):
        # spec:post-edit-archctl-trung#S6
        self.put(config())
        svc = self.make_svc()
        self.log.unlink(missing_ok=True)
        sid = self.sid()
        self.start("làm tiếp", sid)
        self.view.write_text(NEW_TEXT)
        ctx = self.post_at(svc, "Bash", {"command": "sed -i '' s/Y/X/ ../app/web/view.py"}, sid, **self.env_for())
        self.assertIn(FLAG, ctx)
        self.assertEqual(self.calls(), [f"check --root {self.project} --changed"])

    def test_bash_that_changes_only_the_cwd_root_in_a_monorepo_is_skipped(self):
        # spec:post-edit-archctl-trung#S1
        self.put(config())
        self.make_svc()
        self.expect_skipped(self.run_tool("Bash", self.env_for()))


class MissingArchctl(ArchDedupeBase):
    def test_missing_archctl_is_mentioned_once_per_session_even_with_the_hook(self):
        # spec:post-edit-archctl-trung#S7
        self.put(config())
        env = {"PATH": BASE_PATH, "CLAUDE_PROJECT_DIR": str(self.project), "AGENT_STACK_HOST": "claude-code"}
        self.assertIn("máy chưa có archctl", self.edit_view(sid="m1", **env))
        self.assertEqual(self.edit_view(sid="m1", **env), "", "cùng phiên: không nhắc lại")
        self.assertIn("máy chưa có archctl", self.edit_view(sid="m2", **env), "phiên khác thì nhắc lại")

    def test_missing_archctl_with_settings_local_hook_and_bash(self):
        # spec:post-edit-archctl-trung#S7
        self.put(config(), "settings.local.json")
        env = {"PATH": BASE_PATH, "CLAUDE_PROJECT_DIR": str(self.project), "AGENT_STACK_HOST": "claude-code"}
        self.start("làm tiếp", "mb1")
        self.view.write_text(NEW_TEXT)
        first = self.post("Bash", {"command": "sed -i '' s/Y/X/ app/web/view.py"}, "mb1", **env)
        self.assertIn("máy chưa có archctl", first)
        self.assertEqual(self.post("Bash", {"command": "sed -i '' s/X/Y/ app/web/view.py"}, "mb1", **env), "")


class ReviewRoundOneFixes(ArchDedupeBase):
    """Thêm sau review kép 16/11/2026 (opus·xhigh, sonnet·xhigh): các ca hook của archctl không chạy, không kiểm cùng
    file hay không tới model, mà bản đầu vẫn bỏ gọi archctl (im lặng sai)."""

    def test_untrusted_root_is_skipped_by_archctl_so_post_edit_still_reports(self):
        # spec:post-edit-archctl-trung#S6
        # archctl chỉ nhận gốc ở thư mục tổ tiên khi gốc, `.arch/`, file luật không ai cũng ghi được (`trusted_root`).
        self.put(config())
        for folder in (self.project, self.project / ".arch"):
            mode = folder.stat().st_mode
            folder.chmod(mode | 0o002)
            try:
                for tool, cwd in (("Edit", self.project), ("Bash", self.project / "app")):
                    with self.subTest(folder=folder.name, tool=tool):
                        self.expect_reported(tool, self.run_tool(tool, self.env_for(), cwd=cwd))
            finally:
                folder.chmod(mode)

    def test_bash_when_git_status_fails_is_still_checked(self):
        # spec:post-edit-archctl-trung#S6
        # Hook của archctl im lặng sau Bash khi `git status` lỗi (`.git` hỏng, "dubious ownership").
        broken = self.tmp / "broken-git"
        for rel, text in {".arch/system.arch": RULES, "app/web/view.py": "Y = 2\n",
                          ".claude/settings.json": json.dumps(config()),
                          ".git": "gitdir: /nonexistent-agent-stack-dedupe-test\n"}.items():
            path = broken / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.log.unlink(missing_ok=True)
        sid = self.sid()
        self.start("làm tiếp", sid)
        (broken / "app" / "web" / "view.py").write_text(NEW_TEXT)
        ctx = self.post_at(broken, "Bash", {"command": "sed -i '' s/Y/X/ app/web/view.py"}, sid,
                           **self.env_for(CLAUDE_PROJECT_DIR=str(broken)))
        self.expect_reported("Bash", ctx, root=broken)

    def test_handler_fields_that_change_when_or_how_the_hook_runs_do_not_count(self):
        # spec:post-edit-archctl-trung#S2
        for extra in ({"if": "Edit(docs/**)"}, {"once": True}, {"args": ["check", "--hook"]}, {"async": True},
                      {"asyncRewake": True}, {"shell": "bash"}, {"timeout": 0}, {"timeout": "30"},
                      {"timeout": True}, {"type": "http"}):
            cfg = config()
            cfg["hooks"]["PostToolUse"][0]["hooks"][0].update(extra)
            self.put(cfg)
            with self.subTest(extra=extra):
                self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))

    def test_status_message_and_plain_timeout_still_count(self):
        # spec:post-edit-archctl-trung#S1
        for extra in ({"statusMessage": "kiểm kiến trúc"}, {"timeout": 5}, {"timeout": 12.5}):
            cfg = config()
            cfg["hooks"]["PostToolUse"][0]["hooks"][0].update(extra)
            self.put(cfg)
            with self.subTest(extra=extra):
                self.expect_skipped(self.run_tool("Edit", self.env_for()))
        cfg = config()
        del cfg["hooks"]["PostToolUse"][0]["hooks"][0]["timeout"]
        self.put(cfg)
        self.expect_skipped(self.run_tool("Edit", self.env_for()))

    def test_hook_command_with_redirects_pipes_or_extra_words_does_not_count(self):
        # spec:post-edit-archctl-trung#S2
        for command in ("archctl check --hook > /dev/null", "archctl check --hook >/dev/null 2>&1",
                        "archctl check --hook | cat >/dev/null", "archctl check --hook --bogus",
                        "archctl check --root --hook", "archctl check --hook && true", "archctl check --hook; echo x",
                        "archctl check --hook app/web/view.py", "archctl check --hook --strict",
                        "archctl check --hook --root"):
            self.put(config(command=command))
            with self.subTest(command=command):
                self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))

    def test_root_flag_forms_still_count(self):
        # spec:post-edit-archctl-trung#S1
        for command in ("archctl check --root . --hook", "archctl check --hook --root=.", "archctl check --root=. --hook"):
            self.put(config(command=command))
            with self.subTest(command=command):
                self.expect_skipped(self.run_tool("Edit", self.env_for()))

    def test_very_long_hook_command_does_not_slow_the_hook(self):
        # spec:post-edit-archctl-trung#S4
        self.put(config(command="archctl check --hook '" + "a" * 240_000 + "'"))
        self.assertLess((self.project / ".claude" / "settings.json").stat().st_size, 262_144)
        self.expect_reported("Edit", self.run_tool("Edit", self.env_for()))
        self.assertLess(self.elapsed, 1.5)

    def test_large_file_is_still_checked(self):
        # spec:post-edit-archctl-trung#S6
        # Payload của Edit chứa cả file; trên 16 MiB thì hook của archctl bỏ qua. Chỉ bỏ gọi khi file không quá 2 MB.
        self.put(config())
        big = self.project / "app" / "web" / "big.py"
        big.write_text(NEW_TEXT + "#" * 2_100_000 + "\n")
        self.log.unlink(missing_ok=True)
        ctx = self.post_at(self.project, "Edit", {"file_path": str(big), "new_string": NEW_TEXT.strip()}, self.sid(),
                           **self.env_for())
        self.expect_reported("Edit", ctx, target=big)


if __name__ == "__main__":
    unittest.main()
