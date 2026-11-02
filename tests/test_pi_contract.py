"""Hợp đồng agent-stack cho pi (plugin/hosts/pi.json): plugin phải khớp, mọi chỗ lệch phải bị bắt, và hook chạy với
dữ liệu đúng như cầu nối của pi gửi chỉ trả về trường mà cầu nối hiểu."""
import functools
import json
import os
import shutil
import subprocess
import sys
import unittest

from tests._util import PLUGIN, REPO, TempDirTestCase, copy_plugin, git

sys.path.insert(0, str(PLUGIN / "hosts"))
import pi_host  # noqa: E402

CONTRACT = json.loads((PLUGIN / "hosts" / "pi.json").read_text(encoding="utf-8"))


@functools.cache
def pi_frontmatter_module():
    """Đường tới utils/frontmatter.js của pi đã cài (để đọc frontmatter đúng như pi), hay "" nếu máy không có.
    Tính khi test cần: `npm root -g` mất khoảng 0,2 giây."""
    if not shutil.which("node") or not shutil.which("npm"):
        return ""
    try:
        root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    path = os.path.join(root, "@earendil-works", "pi-coding-agent", "dist", "utils", "frontmatter.js")
    return path if os.path.isfile(path) else ""


PLAN = "# PLAN\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Việc tiếp theo:**\n  1. Viết test cho bước cài.\n"


def flat_keys(data, prefix=""):
    out = set()
    for key, value in data.items():
        name = prefix + key
        if isinstance(value, dict):
            out |= flat_keys(value, name + ".")
        else:
            out.add(name)
    return out


class ContractTests(TempDirTestCase):
    def test_repo_plugin_matches_contract(self):
        self.assertEqual(pi_host.check(PLUGIN), [])

    def test_cli_check_passes(self):
        out = subprocess.run([sys.executable, str(PLUGIN / "hosts" / "pi_host.py"), "check"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("Khớp hợp đồng pi", out.stdout)

    def plugin(self):
        return copy_plugin(self.tmp / "plugin")

    def assert_problem(self, plugin, text):
        problems = pi_host.check(plugin)
        self.assertTrue(any(text in p for p in problems), problems)

    def test_new_hook_event_needs_entry(self):
        plugin = self.plugin()
        path = plugin / "hooks" / "hooks.json"
        data = json.loads(path.read_text())
        data["hooks"]["PostToolUse"] = [{"hooks": [{"type": "command", "command": "python3",
                                                    "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/post_tool.py"]}]}]
        path.write_text(json.dumps(data))
        self.assert_problem(plugin, "hook PostToolUse có trong hooks.json mà chưa có mục")

    def test_renamed_hook_script_is_caught(self):
        plugin = self.plugin()
        path = plugin / "hooks" / "hooks.json"
        path.write_text(path.read_text().replace("hooks/stop.py", "hooks/stop_turn.py"))
        (plugin / "hooks" / "stop.py").rename(plugin / "hooks" / "stop_turn.py")
        self.assert_problem(plugin, "hook Stop: hợp đồng gọi stop.py")

    def test_new_guarded_tool_needs_pi_name(self):
        plugin = self.plugin()
        path = plugin / "hooks" / "hooks.json"
        path.write_text(path.read_text().replace("Bash|Write", "Bash|WebFetch|Write"))
        self.assert_problem(plugin, "chặn công cụ WebFetch")

    def test_new_agent_needs_entry(self):
        plugin = self.plugin()
        (plugin / "agents" / "planner.md").write_text("---\nname: planner\ndescription: Lập kế hoạch.\n---\nThân.\n")
        self.assert_problem(plugin, "subagent planner chưa có mục")

    def test_agent_tool_without_pi_name(self):
        plugin = self.plugin()
        path = plugin / "agents" / "reviewer.md"
        path.write_text(path.read_text().replace("tools: Read, Grep", "tools: Read, LSP, Grep"))
        self.assert_problem(plugin, "subagent reviewer: công cụ LSP chưa có tên pi")

    def test_agent_unknown_field(self):
        plugin = self.plugin()
        path = plugin / "agents" / "reviewer.md"
        path.write_text(path.read_text().replace("color: red", "color: red\nhooks: x"))
        self.assert_problem(plugin, "subagent reviewer: trường hooks chưa biết")

    def test_yaml_list_disallowed_tools_still_banned(self):
        plugin = self.plugin()
        path = plugin / "agents" / "researcher.md"
        path.write_text(path.read_text().replace("disallowedTools: Write, Edit, NotebookEdit",
                                                 "disallowedTools:\n  - Write\n  - Edit\n  - NotebookEdit"))
        self.assertEqual(pi_host.check(plugin), [])
        out = self.tmp / "agents"
        pi_host.sync_agents(plugin, out)
        fields, _ = pi_host.split_frontmatter((out / "researcher.md").read_text())
        self.assertNotIn("write", pi_host.names(fields["tools"]))
        self.assertNotIn("edit", pi_host.names(fields["tools"]))

    def test_empty_or_unreadable_tool_list_is_a_problem(self):
        plugin = self.plugin()
        path = plugin / "agents" / "researcher.md"
        path.write_text(path.read_text().replace("disallowedTools: Write, Edit, NotebookEdit", "disallowedTools:"))
        self.assert_problem(plugin, "subagent researcher: trường disallowedTools có mà rỗng")
        path.write_text(path.read_text().replace("disallowedTools:", "disallowedTools:\n  Write"))
        self.assert_problem(plugin, "subagent researcher: dòng frontmatter không đọc được")

    def test_disallowed_tools_win_over_tools(self):
        plugin = self.plugin()
        path = plugin / "agents" / "nguoi-doc-la.md"
        path.write_text(path.read_text().replace("tools: Read\n", "tools: Read, Bash\n"))
        fields, _ = pi_host.split_frontmatter(path.read_text())
        self.assertEqual(pi_host.pi_tools(fields, CONTRACT["agents"]), ["read"])

    def test_missing_description_or_broken_hooks_json_is_a_problem(self):
        plugin = self.plugin()
        path = plugin / "agents" / "reviewer.md"
        text = path.read_text()
        fields, _ = pi_host.split_frontmatter(text)
        path.write_text(text.replace("description: " + fields["description"] + "\n", ""))
        self.assert_problem(plugin, "subagent reviewer: thiếu description")
        (plugin / "hooks" / "hooks.json").write_text("{không phải json")
        self.assert_problem(plugin, "không đọc được hooks/hooks.json")

    def test_new_skill_needs_entry_and_valid_description(self):
        plugin = self.plugin()
        (plugin / "skills" / "moi").mkdir()
        (plugin / "skills" / "moi" / "SKILL.md").write_text("---\nname: moi\ndescription: Mới.\n---\n")
        self.assert_problem(plugin, "skill moi chưa có mục")
        path = plugin / "skills" / "tien-do" / "SKILL.md"
        text = path.read_text()
        fields, _ = pi_host.split_frontmatter(text)
        path.write_text(text.replace(fields["description"], "x" * 1025))
        self.assert_problem(plugin, "skill tien-do: description dài 1025")

    def test_colon_in_unquoted_description_is_a_problem(self):
        # Lỗi thật 02/11/2026: pi bỏ trang-artifact vì description có "để người đọc: kế hoạch"
        plugin = self.plugin()
        path = plugin / "skills" / "tien-do" / "SKILL.md"
        text = path.read_text()
        fields, _ = pi_host.split_frontmatter(text)
        path.write_text(text.replace(fields["description"], "Báo tiến độ: việc dở, việc tiếp theo."))
        self.assert_problem(plugin, "skill tien-do: trường description có ': '")
        path.write_text(text.replace(fields["description"], '"Báo tiến độ: việc dở, việc tiếp theo."'))
        self.assertEqual(pi_host.check(plugin), [])

    def test_pi_own_parser_reads_every_used_file(self):
        pi_fm = pi_frontmatter_module()
        if not pi_fm:
            self.skipTest("máy không có pi để đọc frontmatter bằng parser thật")
        out = self.tmp / "agents"
        pi_host.sync_agents(PLUGIN, out)
        files = [PLUGIN / "skills" / n / "SKILL.md" for n in CONTRACT["skills"]["use"]]
        files += [PLUGIN / "agents" / f"{n}.md" for n in CONTRACT["agents"]["use"]] + sorted(out.glob("*.md"))
        script = ("import {readFileSync} from 'node:fs';"
                  "const {parseFrontmatter} = await import(process.env.PI_FM);"
                  "for (const f of process.argv.slice(1)) { try { const {frontmatter} = parseFrontmatter("
                  "readFileSync(f, 'utf8')); if (!frontmatter.description) console.log('THIẾU', f); }"
                  " catch (e) { console.log('LỖI', f, e.message.split('\\n')[0]); } }")
        res = subprocess.run(["node", "--input-type=module", "-e", script, *map(str, files)], capture_output=True,
                             text=True, env=dict(os.environ, PI_FM=pi_fm), timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "")

    def test_skipped_hook_needs_reason(self):
        plugin = self.plugin()
        path = plugin / "hosts" / "pi.json"
        data = json.loads(path.read_text())
        data["hooks"]["StopFailure"]["skip"] = " "
        path.write_text(json.dumps(data))
        self.assert_problem(plugin, "hook StopFailure bị bỏ mà không ghi lý do")

    def test_agents_render_like_pi_expects(self):
        out = self.tmp / "agents"
        out.mkdir()
        (out / "planner.md").write_text("---\nname: planner\n---\nagent của người dùng, không do agent-stack sinh")
        (out / "cu.md").write_text(pi_host.MARKER + " từ plugin/agents/cu.md; sửa ở nguồn -->\n")
        written = pi_host.sync_agents(PLUGIN, out)
        self.assertEqual(sorted(written), sorted(CONTRACT["agents"]["use"]))
        self.assertFalse((out / "cu.md").exists())  # do agent-stack sinh, không còn dùng
        self.assertTrue((out / "planner.md").exists())  # file lạ thì giữ
        reviewer, _ = pi_host.split_frontmatter((out / "reviewer.md").read_text())
        self.assertEqual(reviewer["tools"], "read, grep, find, ls, bash")
        self.assertEqual(set(reviewer), {"name", "description", "tools"})
        # researcher không khai tools: được mọi công cụ pi trừ phần bị cấm (Write, Edit)
        researcher, body = pi_host.split_frontmatter((out / "researcher.md").read_text())
        self.assertEqual(names := pi_host.names(researcher["tools"]),
                         ["read", "grep", "find", "ls", "bash", "web_search", "web_fetch"])
        self.assertNotIn("write", names)
        self.assertIn("sửa ở nguồn", body.splitlines()[0])


class HookPayloadTests(TempDirTestCase):
    """Chạy từng hook pi dùng với đúng dữ liệu cầu nối gửi (transcript rỗng, AGENT_STACK_HOST=pi)."""

    def setUp(self):
        super().setUp()
        self.project = self.tmp / "proj"
        self.project.mkdir()
        (self.project / "PLAN.md").write_text(PLAN, encoding="utf-8")
        git(self.project, "init", "-q")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "init")

    def run_hook(self, event, extra):
        entry = CONTRACT["hooks"][event]
        payload = {"session_id": "pi-test", "cwd": str(self.project), "hook_event_name": event, "transcript_path": ""}
        self.assertEqual(set(payload), set(CONTRACT["payload_common"]))
        self.assertEqual(set(extra), set(entry["payload"]))
        payload.update(extra)
        env = dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"),
                   AGENT_STACK_PLUGINS_DIR=str(self.tmp / "no-plugins"), **CONTRACT["env"])
        out = subprocess.run(["python3", str(PLUGIN / "hooks" / entry["script"])], input=json.dumps(payload),
                             capture_output=True, text=True, env=env, timeout=30, cwd=self.project)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stderr, "")
        data = json.loads(out.stdout) if out.stdout.strip() else {}
        unknown = flat_keys(data) - set(CONTRACT["outputs_supported"])
        self.assertEqual(unknown, set(), f"{event} trả trường cầu nối pi không hiểu")
        return data

    def test_every_used_hook_runs_with_pi_payload(self):
        samples = {
            "SessionStart": {"source": "startup"},
            "UserPromptSubmit": {"prompt": "sửa lỗi trong hàm parse và chạy test"},
            "PreToolUse": {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            "Stop": {"stop_hook_active": False, "last_assistant_message": "Đã xong."},
            "PreCompact": {"trigger": "auto"},
            "SessionEnd": {"reason": "exit"},
        }
        used = {e for e, v in CONTRACT["hooks"].items() if "skip" not in v}
        self.assertEqual(used, set(samples))
        for event, extra in samples.items():
            with self.subTest(event=event):
                self.run_hook(event, extra)

    def test_session_start_gives_plan_context(self):
        out = self.run_hook("SessionStart", {"source": "startup"})
        self.assertIn("Viết test cho bước cài", out["hookSpecificOutput"]["additionalContext"])

    def test_guard_blocks_unvetted_install_for_pi(self):
        out = self.run_hook("PreToolUse", {"tool_name": "Bash",
                                           "tool_input": {"command": "claude plugin install evil@somewhere"}})
        self.assertIn(out["hookSpecificOutput"]["permissionDecision"], ("deny", "ask"))

    def test_session_start_in_pi_syncs_agents(self):
        agents = self.tmp / "state" / "pi" / "agents"
        self.run_hook("SessionStart", {"source": "startup"})
        self.assertEqual(sorted(p.stem for p in agents.glob("*.md")), sorted(CONTRACT["agents"]["use"]))
        # lần mở sau không ghi lại file không đổi
        before = (agents / "reviewer.md").stat().st_mtime_ns
        self.run_hook("SessionStart", {"source": "resume"})
        self.assertEqual((agents / "reviewer.md").stat().st_mtime_ns, before)

    def test_session_start_outside_pi_does_not_touch_pi_state(self):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"),
                   AGENT_STACK_PLUGINS_DIR=str(self.tmp / "no-plugins"))
        env.pop("AGENT_STACK_HOST", None)
        payload = {"session_id": "cc", "cwd": str(self.project), "source": "startup"}
        out = subprocess.run(["python3", str(PLUGIN / "hooks" / "session_start.py")], input=json.dumps(payload),
                             capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse((self.tmp / "state" / "pi").exists())

    def test_session_start_in_pi_warns_and_keeps_agents_on_drift(self):
        plugin = copy_plugin(self.tmp / "plugin")
        for rel in ("lib", "skills"):
            shutil.copytree(PLUGIN / rel, plugin / rel, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "samples", "evals"))
        agents = self.tmp / "state" / "pi" / "agents"
        agents.mkdir(parents=True)
        (agents / "reviewer.md").write_text("bản tốt cũ")
        (plugin / "agents" / "planner.md").write_text("---\nname: planner\ndescription: Lập kế hoạch.\n---\n")
        payload = {"session_id": "pi-drift", "cwd": str(self.project), "hook_event_name": "SessionStart",
                   "transcript_path": "", "source": "startup"}
        env = dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"), AGENT_STACK_HOME=str(REPO),
                   AGENT_STACK_PLUGINS_DIR=str(self.tmp / "no-plugins"), AGENT_STACK_HOST="pi")
        out = subprocess.run(["python3", str(plugin / "hooks" / "session_start.py")], input=json.dumps(payload),
                             capture_output=True, text=True, env=env, timeout=30, cwd=self.project)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertIn("[agent-stack] pi: plugin lệch hợp đồng", data["hookSpecificOutput"]["additionalContext"])
        self.assertIn("subagent planner chưa có mục", data["hookSpecificOutput"]["additionalContext"])
        self.assertIn("lệch hợp đồng pi", data["systemMessage"])
        self.assertEqual((agents / "reviewer.md").read_text(), "bản tốt cũ")

    def test_guard_on_pi_write_shape(self):
        # edit của pi gửi file_path và content rỗng; hook không được hỏng vì thiếu old_string/new_string
        self.run_hook("PreToolUse", {"tool_name": "Edit", "tool_input": {"file_path": str(self.project / "a.py")}})
        self.run_hook("PreToolUse", {"tool_name": "Write",
                                     "tool_input": {"file_path": str(self.project / "ghi-chu.md"), "content": "x"}})
