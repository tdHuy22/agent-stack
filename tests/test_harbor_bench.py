"""Test cho evals/harbor: harbor_bench.py (bản chép, cấu hình, kiểm việc, chọn việc, export, so sánh), tuf.sh (phần không cần
ssh) và agent_stack_agents.py (chỉ đọc cú pháp: file này import harbor nên test không import nó)."""
import ast
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import unittest
import warnings

from tests._util import PLUGIN, REPO, TempDirTestCase, run_script

HARBOR = REPO / "evals" / "harbor"
SCRIPT = HARBOR / "harbor_bench.py"
_spec = importlib.util.spec_from_file_location("harbor_bench", SCRIPT)
B = importlib.util.module_from_spec(_spec)
sys.modules["harbor_bench"] = B
_spec.loader.exec_module(B)

FAKE_KEY = "sk-ant-oat01-" + "Ab1" * 12
VER = "2.1.311"


def init_line(plugin=True, agents=False, version=VER):
    ev = {"type": "system", "subtype": "init", "claude_code_version": version,
          "plugins": [{"name": "agent-stack"}] if plugin else [],
          "agents": ["general-purpose", "Explore"] + (["agent-stack:reviewer", "agent-stack:researcher"] if agents else [])}
    return json.dumps(ev)


ARM_SETUP = {   # (plugin nạp, subagent agent-stack hiện, cấu trúc container)
    B.PLAIN: (False, False, {"plugin_dir": "no", "user_claude_md": "no", "hooks_json": "no", "agents_dir": "no"}),
    B.STACK: (True, True, {"plugin_dir": "yes", "user_claude_md": "yes", "hooks_json": "yes", "agents_dir": "yes"}),
    B.NOHOOKS: (True, True, {"plugin_dir": "yes", "user_claude_md": "yes", "hooks_json": "no", "agents_dir": "yes"}),
    B.NOAGENTS: (True, False, {"plugin_dir": "yes", "user_claude_md": "yes", "hooks_json": "yes", "agents_dir": "no"}),
}


class Base(TempDirTestCase):
    def trial(self, job, agent, task, reward=1.0, exception=None, cost=0.1, n=0, python3="3.12.3", commit="abc1234",
              version=VER, extra_stream=(), init=True, source=None):
        """Một lượt giả đúng cấu trúc result.json của Harbor 0.25 và log stream-json của Claude Code."""
        d = self.tmp / job / f"{task}__{SHORT(agent)}{n}"
        res = {"task_name": task, "source": source, "agent_info": {"name": agent, "version": version},
               "verifier_result": None if reward is None else {"rewards": {"reward": reward}},
               "agent_result": {"n_input_tokens": 1000, "n_cache_tokens": 500, "n_output_tokens": 200, "cost_usd": cost},
               "exception_info": {"exception_type": exception} if exception else None,
               "agent_execution": {"started_at": "2026-11-06T10:00:00Z", "finished_at": "2026-11-06T10:01:30Z"}}
        self.write(f"{job}/{d.name}/result.json", json.dumps(res))
        if agent in ARM_SETUP:
            plugin, agents, struct = ARM_SETUP[agent]
            lines = ['{"type":"other"}']
            if init:
                lines.append(init_line(plugin, agents, version))
            lines += list(extra_stream)
            self.write(f"{job}/{d.name}/agent/claude-code.txt", "\n".join(lines) + "\n")
            env = "".join(f"{k}={v}\n" for k, v in {"variant": agent, "python3": python3, "payload_commit": commit,
                                                   **struct}.items())
            self.write(f"{job}/{d.name}/agent/agent-stack-env.txt", env)
        return d


def SHORT(agent):
    return B.SHORT.get(agent, agent)


class PayloadTests(Base):
    """TM-76: bản chép chỉ có danh sách cho phép; hai biến thể dựng từ cùng bản chép."""

    def fake_repo(self):
        src = self.tmp / "repo"
        self.write("repo/.agent-stack-root", "")
        self.write("repo/plugin/hooks/hooks.json", "{}")
        self.write("repo/plugin/hooks/session_start.py", "print(1)")
        self.write("repo/plugin/agents/reviewer.md", "x")
        self.write("repo/plugin/.claude-plugin/plugin.json", "{}")
        self.write("repo/plugin/hooks/__pycache__/x.cpython-311.pyc", "x")
        self.write("repo/global/CLAUDE.global.md", "x")
        self.write("repo/routing-table.md", "x")
        self.write("repo/vetted.lock", "x")
        for secret in (".agent/threat-model.md", "PLAN.md", "state/limits.json", ".env", ".env.local", "evals/README.md",
                       "tests/x.py", ".git/config", "KE-HOACH.md"):
            self.write(f"repo/{secret}", "RIENG")
        return src

    def test_only_allow_list_goes_in_and_variants_differ_in_one_place(self):
        src = self.fake_repo()
        dst = self.tmp / "payload"
        self.assertEqual(B.build_payload(src, dst, "abc1234"), [])
        for variant in ("full", "nohooks", "noagents"):
            root = dst / variant
            self.assertEqual(sorted(p.name for p in root.iterdir()),
                             sorted([".agent-stack-root", ".payload-commit", "global", "plugin", "routing-table.md", "vetted.lock"]))
            for forbidden in (".agent", "PLAN.md", "state", ".env", ".env.local", "evals", "tests", ".git", "KE-HOACH.md"):
                self.assertFalse((root / forbidden).exists(), f"{variant}: {forbidden}")
            self.assertEqual((root / ".payload-commit").read_text().strip(), "abc1234")
            self.assertEqual([p for p in root.rglob("*") if p.name == "__pycache__"], [])
        self.assertTrue((dst / "full/plugin/hooks/hooks.json").exists() and (dst / "full/plugin/agents").is_dir())
        self.assertFalse((dst / "nohooks/plugin/hooks/hooks.json").exists())
        self.assertTrue((dst / "nohooks/plugin/hooks/session_start.py").exists())   # chỉ bỏ cấu hình hook, giữ script
        self.assertTrue((dst / "nohooks/plugin/agents/reviewer.md").exists())
        self.assertFalse((dst / "noagents/plugin/agents").exists())
        self.assertTrue((dst / "noagents/plugin/hooks/hooks.json").exists())

    def test_verify_payload_catches_private_files_inside_allowed_dirs(self):
        root = self.tmp / "p"
        self.write("p/.agent-stack-root", "")
        self.write("p/plugin/.env.production", "x")
        self.write("p/plugin/.agent/HANDOFF.md", "x")
        self.write("p/global/PLAN.md", "x")
        self.write("p/PLAN.md", "x")
        text = "\n".join(B.verify_payload(root))
        for needle in (".env.production", ".agent", "PLAN.md", "mục thừa ở gốc: PLAN.md"):
            self.assertIn(needle, text)

    def test_cli_refuses_a_directory_that_is_not_a_repo_copy(self):
        (self.tmp / "x").mkdir()
        r = run_script(SCRIPT, "build-payload", str(self.tmp / "x"), str(self.tmp / "o"), "--commit", "c")
        self.assertNotEqual(r.returncode, 0)

    def test_real_repo_payload_is_clean_and_premises_hold(self):
        dst = self.tmp / "payload"
        self.assertEqual(B.build_payload(REPO, dst, "test"), [])
        # nohooks chỉ bỏ hooks.json: đúng khi plugin.json không trỏ hook và không skill, subagent nào khai hook riêng
        manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
        self.assertNotIn("hooks", manifest)
        self.assertNotIn("agents", manifest)
        for f in list((PLUGIN / "agents").glob("*.md")) + list((PLUGIN / "skills").glob("*/SKILL.md")):
            front = f.read_text(encoding="utf-8").split("---")[1] if f.read_text(encoding="utf-8").startswith("---") else ""
            self.assertNotRegex(front, r"(?m)^hooks\s*:", f.name)
        self.assertFalse((dst / "nohooks/plugin/hooks/hooks.json").exists())
        self.assertTrue((dst / "noagents/plugin/hooks/hooks.json").exists())
        self.assertEqual(sorted(p.name for p in (PLUGIN / "agents").glob("*.md")),
                         sorted(f"{n}.md" for n in B.STACK_AGENTS))


class ConfigTests(Base):
    def tasks_file(self, text="# c\nviec-a\nviec-b  # ghi chú\n"):
        return self.write("tasks-swerebench.txt", text)

    def make(self, kind, **kw):
        out = self.tmp / "cfg" / f"{kind}.json"
        args = ["make-configs", "--kind", kind, "--name", kw.pop("name", kind), "--out", str(out)]
        for k, v in kw.items():
            args += [f"--{k}", str(v)]
        r = run_script(SCRIPT, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(out.read_text())

    def test_main_config_runs_four_arms_in_one_job_that_differ_only_in_agent_class(self):
        main = self.write("main.txt", "tblite:a\ntblite:b\nswerebench:x__y-1\n")
        cfg = self.make("main", tasks=main, attempts=3)
        self.assertEqual((cfg["job_name"], cfg["n_attempts"]), ("main", 3))
        self.assertEqual([a["import_path"].split(":")[1] for a in cfg["agents"]],
                         ["ClaudeCodePlain", "ClaudeCodeAgentStack", "ClaudeCodeAgentStackNoHooks",
                          "ClaudeCodeAgentStackNoAgents"])
        first = cfg["agents"][0]
        for a in cfg["agents"]:
            self.assertEqual(a["model_name"], "anthropic/claude-sonnet-5-5")
            self.assertEqual(a["kwargs"], first["kwargs"])
        self.assertEqual(first["kwargs"], {"version": B.DEFAULTS["version"], "reasoning_effort": "medium", "max_budget_usd": "1"})
        self.assertEqual(first["env"], {"CLAUDE_FORCE_OAUTH": "1"})
        for a in cfg["agents"][1:]:
            self.assertEqual(set(a["env"]) - set(first["env"]), {"AGENT_STACK_NO_BACKGROUND"})
        self.assertEqual(cfg["datasets"], [{"path": "datasets/tblite", "task_names": ["a", "b"]},
                                           {"path": "datasets/swerebench", "task_names": ["x__y-1"]}])
        text = json.dumps(cfg)
        self.assertNotIn("sk-ant", text)
        self.assertNotRegex(text, r"OAUTH_TOKEN")   # chỉ CLAUDE_FORCE_OAUTH, không có tên biến chứa khóa
        self.assertEqual(cfg["retry"]["max_retries"], 0)

    def test_pilot_runs_only_the_plain_arm_on_all_tblite_and_the_swerebench_list(self):
        cfg = self.make("pilot", swerebench=self.tasks_file())
        self.assertEqual([a["import_path"] for a in cfg["agents"]], ["agent_stack_agents:ClaudeCodePlain"])
        self.assertEqual(cfg["datasets"], [{"path": "datasets/tblite"},
                                           {"path": "datasets/swerebench", "task_names": ["viec-a", "viec-b"]}])
        self.assertEqual(cfg["n_attempts"], 1)

    def test_oracle_config_uses_the_same_tasks_without_a_model(self):
        cfg = self.make("oracle", name="pilot-oracle", swerebench=self.tasks_file())
        self.assertEqual(cfg["agents"], [{"name": "oracle"}])
        self.assertEqual(cfg["datasets"][1]["task_names"], ["viec-a", "viec-b"])

    def test_pilot_refuses_while_the_swerebench_list_is_still_empty(self):
        r = run_script(SCRIPT, "make-configs", "--kind", "pilot", "--name", "pilot", "--swerebench",
                       str(HARBOR / "tasks-swerebench.txt"), "--out", str(self.tmp / "p.json"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("không có tên việc nào", r.stderr)

    def test_task_spec_validation(self):
        for text in ("a\nb\na\n", "tblite:a\ntblite:*\n", "lạ:a\n", "tblite:a b\n", "tblite:../x\n", "# chỉ có chú thích\n",
                     "tblite:a;rm -rf\n"):
            with self.subTest(text=text):
                with self.assertRaises(SystemExit):
                    B.read_task_spec(self.write("t.txt", text))
        self.assertEqual(B.read_task_spec(self.write("t.txt", "tblite:*\nswerebench:i__j-1\n")),
                         {"tblite": ["*"], "swerebench": ["i__j-1"]})

    def test_plan_counts_trials_and_states_the_ceiling(self):
        for n in ("a", "b", "c"):
            self.write(f"datasets/tblite/{n}/task.toml", "")
        main = self.write("main.txt", "tblite:*\nswerebench:x-1\nswerebench:x-2\n")
        cfg = self.make("main", tasks=main, attempts=2)
        (self.tmp / "datasets/swerebench").mkdir(parents=True)
        r = run_script(SCRIPT, "plan", str(self.tmp / "cfg/main.json"), "--root", str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("40 lượt = 5 việc × 4 cấu hình × 2 lần", r.stdout)   # 3 việc TBLite + 2 SWE-rebench
        self.assertIn("$40", r.stdout)

    def test_pinned_versions_are_declared(self):
        self.assertEqual(B.HARBOR_VERSION, "0.25.0")
        self.assertRegex(B.DEFAULTS["version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue(B.DATASETS["swerebench"]["ref"].startswith("sha256:"))
        meta = self.tmp / "meta.json"
        cfg = self.make("pilot", swerebench=self.tasks_file())
        self.write("datasets/tblite.lock.json", json.dumps({"name": "tblite", "sha256": "ab" * 32}))
        payload = self.tmp / "payload" / "full"
        payload.mkdir(parents=True)
        (payload / ".payload-commit").write_text("c0ffee1\n")
        r = run_script(SCRIPT, "meta", str(self.tmp / "cfg/pilot.json"), "--out", str(meta), "--payload",
                       str(self.tmp / "payload"), "--root", str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads(meta.read_text())
        self.assertEqual((m["claude_code"], m["payload_commit"], m["harbor_pinned"]), (B.DEFAULTS["version"], "c0ffee1", "0.25.0"))
        self.assertEqual(m["datasets"]["tblite"]["sha256"], "ab" * 32)
        self.assertEqual(m["max_budget_usd"], "1")


class VetTests(Base):
    """TM-74: việc khai container đặc quyền, mạng máy chủ, gắn thư mục ngoài… bị từ chối."""

    def task(self, name="t", compose=None, toml="[task]\nname = \"x\"\n", dockerfile="FROM python:3.12\n"):
        self.write(f"ds/{name}/task.toml", toml)
        self.write(f"ds/{name}/environment/Dockerfile", dockerfile)
        if compose is not None:
            self.write(f"ds/{name}/environment/docker-compose.yaml", compose)
        return self.tmp / "ds" / name

    def test_clean_tasks_pass(self):
        clean = "services:\n  main:\n    image: x\n    volumes:\n      - ./data:/data\n      - cache:/cache\n    environment:\n      A: b\nvolumes:\n  cache:\n"
        self.assertEqual(B.vet_task(self.task("a")), [])
        self.assertEqual(B.vet_task(self.task("b", compose=clean)), [])
        self.assertEqual(B.vet_task(self.task("c", dockerfile="FROM swerebench/sweb.eval.x86_64.a:latest\nRUN mkdir -p /logs\n")), [])

    def test_each_dangerous_compose_setting_is_refused(self):
        cases = {
            "privileged": "services:\n  main:\n    privileged: true\n",
            "network_mode: host": "services:\n  main:\n    network_mode: host\n",
            "pid": "services:\n  main:\n    pid: \"host\"\n",
            "cap_add": "services:\n  main:\n    cap_add:\n      - SYS_ADMIN\n",
            "docker.sock": "services:\n  main:\n    volumes:\n      - /var/run/docker.sock:/var/run/docker.sock\n",
            "absolute bind": "services:\n  main:\n    volumes:\n      - /home/tuf:/mnt\n",
            "home bind": "services:\n  main:\n    volumes:\n      - ~/.ssh:/root/.ssh\n",
            "parent bind": "services:\n  main:\n    volumes:\n      - ../..:/mnt\n",
            "long form": "services:\n  main:\n    volumes:\n      - type: bind\n        source: /etc\n        target: /e\n",
            "inline list": "services:\n  main:\n    volumes: [\"/etc:/e\"]\n",
            "devices": "services:\n  main:\n    devices:\n      - /dev/sda\n",
            "unconfined": "services:\n  main:\n    security_opt:\n      - seccomp=unconfined\n",
        }
        for label, compose in cases.items():
            with self.subTest(label):
                self.assertTrue(B.vet_task(self.task("bad", compose=compose)), label)

    def test_dockerfile_and_task_toml_findings(self):
        self.assertTrue(B.vet_task(self.task("a", dockerfile="FROM x\nRUN --security=insecure true\n")))
        self.assertTrue(B.vet_task(self.task("b", dockerfile="FROM x\nCOPY /var/run/docker.sock /s\n")))
        # biến của máy chủ trong env: khóa đăng nhập có thể bị đưa vào container của việc
        self.assertTrue(B.vet_task(self.task("c", toml="[environment.env]\nX = \"${CLAUDE_CODE_OAUTH_TOKEN}\"\n")))
        self.assertTrue(B.vet_task(self.task("d", toml="[verifier.env]\nX = \"${HOME}\"\n")))
        self.assertTrue(B.vet_task(self.task("e", toml="[environment]\nprivileged = true\n")))
        self.assertTrue(B.vet_task(self.task("f", toml="không phải toml [[")))
        self.assertIn("thiếu task.toml", B.vet_task(self.tmp / "ds-khong-co"))

    def test_symlink_pointing_outside_the_task_is_refused(self):
        d = self.task("s")
        os.symlink("/etc/passwd", d / "tests-link")
        os.symlink("../../outside", d / "tests-link2")
        os.symlink("task.toml", d / "ok-link")
        text = "\n".join(B.vet_task(d))
        self.assertIn("tests-link", text)
        self.assertIn("tests-link2", text)
        self.assertNotIn("ok-link", text)

    def test_cli_vet_reports_and_drop_removes_the_bad_ones(self):
        self.task("good")
        self.task("bad", compose="services:\n  main:\n    privileged: true\n")
        r = run_script(SCRIPT, "vet", str(self.tmp / "ds"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("✗ bad", r.stderr)
        r = run_script(SCRIPT, "vet", str(self.tmp / "ds"), "--drop")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(B.list_tasks(self.tmp / "ds"), ["good"])
        self.assertIn("bad", (self.tmp / "ds.rejected.txt").read_text())

    def test_vet_config_checks_exactly_the_tasks_the_job_will_run(self):
        self.task("good")
        self.task("bad", compose="services:\n  main:\n    network_mode: host\n")
        cfg = self.write("c.json", json.dumps({"datasets": [{"path": "ds", "task_names": ["good"]}]}))
        self.assertEqual(run_script(SCRIPT, "vet-config", str(cfg), "--root", str(self.tmp)).returncode, 0)
        cfg = self.write("c2.json", json.dumps({"datasets": [{"path": "ds", "task_names": ["good", "bad"]}]}))
        self.assertEqual(run_script(SCRIPT, "vet-config", str(cfg), "--root", str(self.tmp)).returncode, 1)
        cfg = self.write("c3.json", json.dumps({"datasets": [{"path": "ds"}]}))
        self.assertEqual(run_script(SCRIPT, "vet-config", str(cfg), "--root", str(self.tmp)).returncode, 1)


class DatasetTests(Base):
    def test_flatten_finds_tasks_at_any_depth_and_rejects_duplicates(self):
        self.write("dl/org/name/task-a/task.toml", "")
        self.write("dl/org/name/task-a/environment/Dockerfile", "FROM x")
        self.write("dl/org/name/task-b/task.toml", "")
        out = self.tmp / "flat"
        r = run_script(SCRIPT, "flatten", str(self.tmp / "dl"), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(B.list_tasks(out), ["task-a", "task-b"])
        self.assertTrue((out / "task-a/environment/Dockerfile").is_file())
        self.write("dl2/x/t/task.toml", "")
        self.write("dl2/y/t/task.toml", "")
        self.assertEqual(run_script(SCRIPT, "flatten", str(self.tmp / "dl2"), "--out", str(self.tmp / "o2")).returncode, 1)
        self.assertEqual(run_script(SCRIPT, "flatten", str(self.tmp / "nothing"), "--out", str(self.tmp / "o3")).returncode, 1)

    def test_lock_pins_the_content_and_refuses_a_changed_dataset(self):
        self.write("d/t/task.toml", "a")
        lock = self.tmp / "d.lock.json"
        args = ("lock", str(self.tmp / "d"), "--name", "tblite", "--ref", "latest", "--lock", str(lock))
        self.assertEqual(run_script(SCRIPT, *args).returncode, 0)
        self.assertEqual(run_script(SCRIPT, *args).returncode, 0)          # cùng nội dung: khớp
        pinned = json.loads(lock.read_text())
        self.assertEqual((pinned["tasks"], len(pinned["sha256"])), (1, 64))
        self.write("d/t/task.toml", "b")
        r = run_script(SCRIPT, *args)
        self.assertEqual(r.returncode, 1)
        self.assertIn("khác bản đã ghim", r.stderr)


class PickTests(Base):
    def make_dataset(self, months):
        """months: {tháng: số việc}. Mỗi việc có tests/config.json với created_at."""
        for month, count in months.items():
            for i in range(count):
                name = f"owner__repo-{month.replace('-', '')}{i:02d}"
                self.write(f"ds/{name}/task.toml", "[task]\nname = \"x\"\n")
                self.write(f"ds/{name}/environment/Dockerfile", "FROM x\n")
                self.write(f"ds/{name}/tests/config.json", json.dumps({"instance_id": name, "created_at": f"{month}-15 10:00:00"}))
        return self.tmp / "ds"

    def test_picks_from_the_latest_month_with_enough_tasks_deterministically(self):
        ds = self.make_dataset({"2026-08": 30, "2026-09": 30, "2026-10": 10})   # tháng 10 chưa đủ 25
        names, month, counts = B.pick_swerebench(ds, 25)
        self.assertEqual(month, "2026-09")
        self.assertEqual(len(names), 25)
        self.assertTrue(all("202609" in n for n in names))
        self.assertEqual(counts, {"2026-08": 30, "2026-09": 30, "2026-10": 10})
        self.assertEqual(names, B.pick_swerebench(ds, 25)[0])                         # cùng hạt: cùng kết quả
        self.assertNotEqual(names, B.pick_swerebench(ds, 25, seed=1)[0])
        self.assertEqual(names, sorted(names))

    def test_vetting_failures_are_not_picked_and_cli_prints_a_documented_list(self):
        ds = self.make_dataset({"2026-10": 26})
        bad = sorted(B.list_tasks(ds))[0]
        self.write(f"ds/{bad}/environment/docker-compose.yaml", "services:\n  main:\n    privileged: true\n")
        with self.assertRaises(SystemExit):          # còn 25 sạch thì được, 26 trừ 1 = 25 -> đủ
            B.pick_swerebench(ds, 26)
        r = run_script(SCRIPT, "pick-swerebench", str(ds), "--n", "25")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        header = [ln for ln in lines if ln.startswith("#")]
        names = [ln for ln in lines if not ln.startswith("#")]
        self.assertEqual(len(names), 25)
        self.assertNotIn(bad, names)
        text = "\n".join(header)
        self.assertIn("2026-10", text)
        self.assertIn(f"random.Random({B.SEED})", text)
        # danh sách ghi ra đọc lại được bằng chính read_task_spec
        f = self.write("tasks-swerebench.txt", r.stdout)
        self.assertEqual(B.read_task_spec(f, "swerebench")["swerebench"], names)

    def test_missing_data_stops_with_a_clear_error(self):
        (self.tmp / "empty").mkdir()
        with self.assertRaises(SystemExit):
            B.pick_swerebench(self.tmp / "empty", 25)

    def test_committed_list_is_either_pending_or_valid(self):
        text = (HARBOR / "tasks-swerebench.txt").read_text(encoding="utf-8")
        names = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        self.assertIn(len(names), (0, 25))
        if names:
            self.assertEqual(len(set(names)), 25)
        else:
            self.assertIn("random.Random(20261106)", text)


class WatchTests(Base):
    """TM-77: dừng job khi lỗi hạn mức hay rate limit vượt ngưỡng."""

    def limit_trials(self, n, exc="ApiUsageLimitError"):
        for i in range(n):
            self.trial("jobs/j", B.PLAIN, f"t{i}", reward=0.0, exception=exc)
        return self.tmp / "jobs" / "j"

    def test_counts_only_usage_and_rate_limit_errors(self):
        job = self.limit_trials(2)
        self.trial("jobs/j", B.PLAIN, "x", exception="ApiRateLimitError")
        self.trial("jobs/j", B.PLAIN, "y", exception="AgentTimeoutError")
        self.assertEqual(B.count_limit_errors(job), 3)

    def test_terminates_the_process_group_over_the_threshold(self):
        job = self.limit_trials(4)
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        code = B.watch(job, proc.pid, limit=3, interval=0.01)
        self.assertEqual(code, 3)
        self.assertEqual(proc.wait(timeout=10), -signal.SIGTERM)
        self.assertIn("4 lượt lỗi", (self.tmp / "jobs" / "j.stopped").read_text())

    def test_does_nothing_at_or_below_the_threshold_and_ends_with_the_job(self):
        job = self.limit_trials(3)
        proc = subprocess.Popen(["sleep", "0.3"], start_new_session=True)
        calls = []
        code = B.watch(job, proc.pid, limit=3, interval=0.05, sleep=lambda s: (calls.append(s), proc.wait())[0])
        self.assertEqual(code, 0)
        self.assertEqual(proc.returncode, 0)
        self.assertFalse((self.tmp / "jobs" / "j.stopped").exists())


class ExportTests(Base):
    """TM-73: che mọi chuỗi sk-ant-… trong MỌI file kéo về."""

    def test_masks_the_key_in_every_exported_file_and_copies_nothing_else(self):
        d = self.trial("pilot", B.STACK, "t")
        for name, body in (("agent/claude-code.txt", f'{{"type":"user","content":"CLAUDE_CODE_OAUTH_TOKEN={FAKE_KEY}"}}\n'),
                           ("agent/agent-stack-env.txt", f"variant=x\nnote={FAKE_KEY}\n"),
                           ("config.json", json.dumps({"agent": {"env": {"CLAUDE_CODE_OAUTH_TOKEN": "x" * 20}}, "k": FAKE_KEY})),
                           ("verifier/reward.txt", f"1 {FAKE_KEY}\n")):
            self.write(f"pilot/{d.name}/{name}", body)
        self.write("pilot/config.json", json.dumps({"leak": FAKE_KEY}))
        self.write("pilot/result.json", json.dumps({"leak": "ANTHROPIC_API_KEY=abcdefgh12345678"}))
        self.write("pilot.meta.json", json.dumps({"claude_code": VER, "k": FAKE_KEY}))
        self.write(f"pilot/{d.name}/agent/sessions/khac.jsonl", FAKE_KEY)      # không nằm trong danh sách xuất
        self.write(f"pilot/{d.name}/agent/trajectory.json", FAKE_KEY)
        out = self.tmp / "out"
        r = run_script(SCRIPT, "export", str(self.tmp / "pilot"), str(self.tmp / "khong-co"), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"che khóa trong \d+ file")
        exported = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
        self.assertIn("pilot/bench-meta.json", exported)
        self.assertIn(f"pilot/{d.name}/agent/agent-stack-env.txt", exported)
        self.assertNotIn(f"pilot/{d.name}/agent/sessions/khac.jsonl", exported)
        self.assertNotIn(f"pilot/{d.name}/agent/trajectory.json", exported)
        for f in out.rglob("*"):
            if f.is_file():
                data = f.read_bytes()
                self.assertNotIn(b"sk-ant-", data, f)
                self.assertNotIn(FAKE_KEY.encode(), data, f)
                self.assertNotRegex(data.decode(), r"ANTHROPIC_API_KEY=abcdefgh", f)
        # kết quả đã xuất vẫn so được
        self.assertEqual(B.load_trials([out / "pilot"])[0]["task"], "t")
        self.assertEqual(run_script(SCRIPT, "export", str(self.tmp / "pilot"), "--out", str(out)).returncode, 1)   # không ghi đè

    def test_mask_forms(self):
        for text in (FAKE_KEY, "sk-ant-api03-abcdefgh_ij-kl", 'CLAUDE_CODE_OAUTH_TOKEN="aaaaaaaabbbbbbbb"',
                     "ANTHROPIC_AUTH_TOKEN: zzzzzzzzzzzz", "x sk-ant-oat01-" + "z" * 80 + " y"):
            masked = B.mask_secrets(text.encode()).decode()
            self.assertNotRegex(masked, r"sk-ant-|aaaaaaaabbbbbbbb|zzzzzzzzzzzz", text)
        self.assertEqual(B.mask_secrets(b"sk-ant is a prefix"), b"sk-ant is a prefix")

    def test_symlinks_in_the_log_dir_are_not_followed(self):
        d = self.trial("pilot", B.PLAIN, "t")
        secret = self.write("host-secret.txt", "mật khẩu máy chủ")
        (d / "agent" / "reward.txt").symlink_to(secret)
        out = self.tmp / "out"
        r = run_script(SCRIPT, "export", str(self.tmp / "pilot"), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p for p in out.rglob("reward.txt")], [])
        self.assertNotIn("mật khẩu", "".join(p.read_text() for p in out.rglob("*") if p.is_file()))

    def test_fails_when_the_job_has_no_finished_trial_yet(self):
        (self.tmp / "pilot" / "t__dang-chay").mkdir(parents=True)
        self.write("pilot/result.json", "{}")   # chỉ có file cấp job
        r = run_script(SCRIPT, "export", str(self.tmp / "pilot"), "--out", str(self.tmp / "out"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Chưa có kết quả", r.stderr)


class CompareTests(Base):
    def fill(self, job, outcomes, **kw):
        """outcomes: {việc: {bản: điểm}}"""
        for task, per_arm in outcomes.items():
            for arm, reward in per_arm.items():
                self.trial(job, arm, task, reward=float(reward), **kw)

    def test_pairs_every_arm_against_plain_and_ablations_against_the_full_stack(self):
        P, S, H, A = B.PLAIN, B.STACK, B.NOHOOKS, B.NOAGENTS
        self.fill("job", {"t1": {P: 1, S: 1, H: 1, A: 1}, "t2": {P: 1, S: 0, H: 1, A: 1}, "t3": {P: 0, S: 1, H: 0, A: 0},
                          "t4": {P: 0, S: 0, H: 0, A: 0}, "t5": {P: 1, S: 0, H: 0, A: 1}})
        res = B.compare(B.load_trials([self.tmp / "job"]))
        self.assertEqual(res["arms"], list(B.ARMS))
        self.assertEqual(res["pairs"], 5)
        by = {(c["a"], c["b"]): c for c in res["comparisons"]}
        self.assertEqual(len(by), 5)
        c = by[(P, S)]
        self.assertEqual((c["worse"], c["better"]), (["t2", "t5"], ["t3"]))
        self.assertAlmostEqual(c["p_value"], B.exact_binomial_p(2, 1))
        c = by[(H, S)]      # bản đủ so với bản bỏ hook
        self.assertEqual((c["worse"], c["better"]), (["t2"], ["t3"]))
        c = by[(A, S)]      # bản đủ so với bản bỏ subagent
        self.assertEqual((c["worse"], c["better"]), (["t2", "t5"], ["t3"]))
        c = by[(P, H)]
        self.assertEqual((c["worse"], c["better"]), (["t5"], []))
        self.assertAlmostEqual(res["stats"][P]["pass_rate"], 0.6)
        self.assertAlmostEqual(res["stats"][S]["pass_rate"], 0.4)
        self.assertEqual(res["stats"][S]["agent_calls"]["total"], 0)
        text = B.report(res)
        self.assertIn("stack so với plain: kém hơn ở 2 việc, tốt hơn ở 1 việc", text)
        self.assertIn("nohooks", text)
        self.assertIn("Bonferroni", text)
        self.assertNotIn("⚠️", text)

    def test_oracle_failures_and_ungraded_trials_drop_the_task(self):
        P, S = B.PLAIN, B.STACK
        for task in ("ok", "bad-grader", "env-broken", "timeout"):
            self.trial("job", P, task, reward=1.0)
        self.trial("job", S, "ok", reward=1.0)
        self.trial("job", S, "bad-grader", reward=0.0)
        self.trial("job", S, "env-broken", reward=None, exception="EnvironmentStartTimeoutError")
        self.trial("job", S, "timeout", reward=0.0, exception="AgentTimeoutError")    # hết giờ mà grader vẫn chấm: giữ
        for task, reward in (("ok", 1.0), ("bad-grader", 0.0), ("env-broken", 1.0), ("timeout", 1.0)):
            self.trial("oracle", "oracle", task, reward=reward)
        res = B.compare(B.load_trials([self.tmp / "job"]), B.load_trials([self.tmp / "oracle"]), arms=[P, S])
        self.assertEqual([r["task"] for r in res["rows"]], ["ok", "timeout"])
        why = dict(res["excluded"])
        self.assertEqual(why["bad-grader"], "lời giải mẫu không đạt")
        self.assertIn("EnvironmentStartTimeoutError", why["env-broken"])
        self.assertEqual(res["comparisons"][0]["worse"], ["timeout"])
        self.assertEqual(res["stats"][S]["n_exceptions"], 1)

    def test_infrastructure_errors_drop_the_task_and_limit_errors_are_counted(self):
        P, S = B.PLAIN, B.STACK
        cases = (("limit", "ApiUsageLimitError"), ("rate", "ApiRateLimitError"), ("auth", "AgentAuthenticationError"),
                 ("ctx", "ContextWindowExceededError"), ("exit", "NonZeroAgentExitCodeError"))
        for task, exc in cases:
            self.trial("job", P, task, reward=1.0)
            self.trial("job", S, task, reward=0.0, exception=exc)
        res = B.compare(B.load_trials([self.tmp / "job"]), arms=[P, S])
        self.assertEqual([r["task"] for r in res["rows"]], ["ctx", "exit"])
        self.assertEqual(res["stats"][S]["infra_dropped"], 3)
        self.assertEqual(res["stats"][S]["limit_errors"], 2)
        self.assertEqual(res["limit_errors"], 2)
        self.assertIn("lỗi hạn mức/rate limit", B.report(res))
        self.trial("job", S, "more", reward=0.0, exception="ApiRateLimitError")
        self.trial("job", S, "more2", reward=0.0, exception="ApiRateLimitError")
        self.assertIn("ngưỡng dừng job là 3", B.report(B.compare(B.load_trials([self.tmp / "job"]), arms=[P, S])))

    def test_tasks_without_usable_python_drop_out_of_hook_arms_only_and_are_counted(self):
        P, S, H, A = B.PLAIN, B.STACK, B.NOHOOKS, B.NOAGENTS
        self.fill("job", {"ok": {P: 1, S: 1, H: 1, A: 1}})
        for arm in B.ARMS:
            self.trial("job", arm, "no-py", python3="")
            self.trial("job", arm, "py38", python3="3.8.10")
        res = B.compare(B.load_trials([self.tmp / "job"]))
        self.assertEqual([r["task"] for r in res["rows"]], ["ok"])
        why = dict(res["excluded"])
        self.assertIn("hook không chạy", why["no-py"])
        self.assertIn("hook không chạy", why["py38"])
        self.assertEqual(res["stats"][S]["hooks_missing"], 2)
        self.assertEqual(res["stats"][A]["hooks_missing"], 2)
        self.assertIn("Lượt thiếu hook", B.report(res))
        # nohooks và plain không cần hook, nên chỉ hai bản kia bị loại việc; cả hai bản không hook đứng riêng thì giữ
        res = B.compare(B.load_trials([self.tmp / "job"]), arms=[P, H])
        self.assertEqual(sorted(r["task"] for r in res["rows"]), ["no-py", "ok", "py38"])

    def test_python_version_threshold(self):
        for ok in ("3.9.2", "3.9", "3.11.15", "3.12.3", "3.13.0"):
            self.assertTrue(B.python_ok(ok), ok)
        for bad in ("", "3.8.10", "2.7.18", "abc", "3"):
            self.assertFalse(B.python_ok(bad), bad)

    def test_refuses_to_merge_different_claude_code_versions_or_payload_commits(self):
        self.trial("a", B.PLAIN, "t")
        self.trial("a", B.STACK, "t")
        self.trial("b", B.PLAIN, "t2", version="2.1.320")
        r = run_script(SCRIPT, "compare", str(self.tmp / "a"), str(self.tmp / "b"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("khác phiên bản Claude Code", r.stderr)
        self.assertEqual(run_script(SCRIPT, "compare", str(self.tmp / "a")).returncode, 0)
        self.trial("c", B.STACK, "t3", commit="def5678")
        r = run_script(SCRIPT, "compare", str(self.tmp / "a"), str(self.tmp / "c"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("khác commit bản chép", r.stderr)

    def test_refuses_when_job_metadata_disagrees_or_real_version_differs_from_the_pin(self):
        self.trial("a", B.PLAIN, "t")
        self.trial("b", B.PLAIN, "t2")
        self.write("a.meta.json", json.dumps({"claude_code": VER, "payload_commit": "c1", "datasets": {"tblite": {"sha256": "1"}}}))
        self.write("b.meta.json", json.dumps({"claude_code": VER, "payload_commit": "c1", "datasets": {"tblite": {"sha256": "2"}}}))
        r = run_script(SCRIPT, "compare", str(self.tmp / "a"), str(self.tmp / "b"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("khác nội dung bộ việc tblite", r.stderr)
        self.write("b.meta.json", json.dumps({"claude_code": "2.1.999"}))
        self.write("a.meta.json", json.dumps({"claude_code": "2.1.999"}))
        r = run_script(SCRIPT, "compare", str(self.tmp / "a"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("khác bản đã ghim", r.stderr)

    def test_meta_next_to_job_dir_or_inside_exported_job_is_read(self):
        self.trial("a", B.PLAIN, "t")
        self.write("a.meta.json", json.dumps({"claude_code": VER}))
        self.assertEqual(B.load_metas([self.tmp / "a"]), [{"claude_code": VER}])
        self.write("e/bench-meta.json", json.dumps({"claude_code": VER, "x": 1}))
        self.assertEqual(B.load_metas([self.tmp / "e"])[0]["x"], 1)

    def test_plain_arm_that_sees_agent_stack_and_arms_that_do_not_match_their_definition_are_flagged(self):
        d = self.trial("job", B.PLAIN, "t")
        (d / "agent" / "claude-code.txt").write_text(init_line(plugin=True, agents=True) + "\n")
        self.trial("job", B.STACK, "t")
        text = B.report(B.compare(B.load_trials([self.tmp / "job"])))
        self.assertIn("Bản trơn thấy agent-stack", text)
        # noagents mà vẫn thấy subagent agent-stack, hay nohooks mà container có hooks.json
        d = self.trial("job2", B.NOAGENTS, "t")
        (d / "agent" / "claude-code.txt").write_text(init_line(plugin=True, agents=True) + "\n")
        d = self.trial("job2", B.NOHOOKS, "t")
        (d / "agent" / "agent-stack-env.txt").write_text("python3=3.12.3\nplugin_dir=yes\nuser_claude_md=yes\nhooks_json=yes\nagents_dir=yes\n")
        self.trial("job2", B.PLAIN, "t")
        res = B.compare(B.load_trials([self.tmp / "job2"]))
        self.assertEqual(res["stats"][B.NOAGENTS]["init_mismatch"], 1)
        self.assertEqual(res["stats"][B.NOHOOKS]["structure_bad"], 1)
        text = B.report(res)
        self.assertIn("noagents không đúng định nghĩa", text)
        self.assertIn("nohooks không đúng định nghĩa", text)

    def test_stream_log_counts_subagent_and_skill_calls_and_budget_hits(self):
        calls = [json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Task", "input": {"subagent_type": "agent-stack:reviewer"}},
            {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "Explore"}},
            {"type": "tool_use", "name": "Skill", "input": {"skill": "agent-stack:done-gate"}},
            {"type": "tool_use", "name": "Bash", "input": {}}]}}),
            json.dumps({"type": "result", "subtype": "error_max_budget_usd", "is_error": True, "total_cost_usd": 1.02})]
        self.trial("job", B.STACK, "t", reward=0.0, exception="NonZeroAgentExitCodeError", extra_stream=calls)
        self.trial("job", B.PLAIN, "t", reward=0.0)
        res = B.compare(B.load_trials([self.tmp / "job"]))
        s = res["stats"][B.STACK]
        self.assertEqual((s["agent_calls"]["total"], s["stack_agent_calls"]["total"], s["skill_calls"]["total"]), (2, 1, 1))
        self.assertEqual((s["budget_hit"], res["stats"][B.PLAIN]["budget_hit"]), (1, 0))
        self.assertEqual(s["n_exceptions"], 1)   # chạm trần ngân sách là kết quả thật của bản đó, không phải lỗi hạ tầng

    def test_several_attempts_compare_pass_rates_per_task(self):
        for n, (a, b) in enumerate(((1, 1), (1, 0), (0, 0))):
            self.trial("job", B.PLAIN, "t", reward=float(a), n=n)
            self.trial("job", B.STACK, "t", reward=float(b), n=n)
        res = B.compare(B.load_trials([self.tmp / "job"]))
        self.assertAlmostEqual(res["rows"][0]["rates"][B.PLAIN], 2 / 3)
        self.assertAlmostEqual(res["rows"][0]["rates"][B.STACK], 1 / 3)
        self.assertEqual(res["comparisons"][0]["worse"], ["t"])

    def test_exact_mcnemar(self):
        self.assertEqual(B.exact_binomial_p(0, 0), 1.0)
        self.assertAlmostEqual(B.exact_binomial_p(0, 6), 0.03125)
        self.assertAlmostEqual(B.exact_binomial_p(2, 3), 1.0)
        self.assertAlmostEqual(B.exact_binomial_p(1, 9), 0.021484375)

    def test_cli_compare_json_and_empty_dir(self):
        self.trial("job", B.PLAIN, "t")
        self.trial("job", B.STACK, "t")
        r = run_script(SCRIPT, "compare", str(self.tmp / "job"), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["pairs"], 1)
        (self.tmp / "empty").mkdir()
        self.assertEqual(run_script(SCRIPT, "compare", str(self.tmp / "empty")).returncode, 1)


class SelectTests(Base):
    def run_pilot(self, rows):
        """rows: [(việc, điểm, chi phí, ngoại lệ, python3)]; việc có '__' là của SWE-rebench."""
        for task, reward, cost, exc, py in rows:
            self.trial("pilot", B.PLAIN, task, reward=reward, cost=cost, exception=exc, python3=py)
        return B.load_trials([self.tmp / "pilot"])

    def test_keeps_only_borderline_tasks_and_explains_every_drop(self):
        rows = [("e1", 1.0, 0.05, None, "3.12.3"), ("e2", 1.0, 0.06, None, "3.12.3"),      # đạt, rẻ: chắc đạt
                ("m1", 1.0, 0.40, None, "3.12.3"), ("m2", 1.0, 0.50, None, "3.12.3"),      # đạt, tốn công: giữ
                ("f1", 0.0, 0.04, None, "3.12.3"), ("f2", 0.0, 0.03, None, "3.12.3"),      # trượt, rẻ: giữ
                ("h1", 0.0, 0.80, None, "3.12.3"), ("h2", 0.0, 0.90, None, "3.12.3"),      # trượt, tốn: chắc trượt
                ("limit", 0.0, 0.1, "ApiUsageLimitError", "3.12.3"), ("nopy", 1.0, 0.5, None, ""),
                ("o__bad-1", 0.0, 0.1, None, "3.12.3")]
        res = B.classify_pilot(self.run_pilot(rows))
        self.assertEqual(sorted(res["keep"]["tblite"]), ["f1", "f2", "m1", "m2"])
        why = {t: w for _ds, t, w in res["drop"]}
        self.assertIn("chắc đạt", why["e1"])
        self.assertIn("chắc trượt", why["h1"])
        self.assertIn("ApiUsageLimitError", why["limit"])
        self.assertIn("python3", why["nopy"])
        self.assertIn("chắc trượt", why["o__bad-1"])

    def test_medians_are_taken_per_dataset_and_oracle_failures_drop(self):
        rows = [("a", 1.0, 0.05, None, "3.12.3"), ("b", 1.0, 0.07, None, "3.12.3"), ("c", 1.0, 0.09, None, "3.12.3"),
                ("x__1", 1.0, 1.0, None, "3.12.3"), ("x__2", 1.0, 2.0, None, "3.12.3"), ("x__3", 1.0, 3.0, None, "3.12.3")]
        trials = self.run_pilot(rows)
        oracle = [{"task": "b", "reward": 0.0, "agent": "oracle"}]
        res = B.classify_pilot(trials, oracle)
        self.assertEqual(sorted(res["keep"]["tblite"]), ["c"])          # trung vị TBLite 0,07; b bị oracle loại
        self.assertEqual(sorted(res["keep"]["swerebench"]), ["x__2", "x__3"])
        self.assertIn("lời giải mẫu", dict((t, w) for _d, t, w in res["drop"])["b"])

    def test_several_attempts_keep_rates_strictly_between_zero_and_one(self):
        for n, r in enumerate((1, 1, 0)):
            self.trial("pilot", B.PLAIN, "mix", reward=float(r), n=n)
        for n in range(3):
            self.trial("pilot", B.PLAIN, "always", reward=1.0, n=n)
            self.trial("pilot", B.PLAIN, "never", reward=0.0, n=n)
        res = B.classify_pilot(B.load_trials([self.tmp / "pilot"]))
        self.assertEqual(res["keep"], {"tblite": ["mix"]})

    def test_cli_writes_a_main_list_that_make_configs_reads_back(self):
        self.run_pilot([("m1", 1.0, 0.4, None, "3.12.3"), ("m2", 1.0, 0.3, None, "3.12.3"), ("f1", 0.0, 0.01, None, "3.12.3"),
                        ("e1", 1.0, 0.02, None, "3.12.3"), ("s__a-1", 0.0, 0.1, None, "3.12.3")])
        out = self.tmp / "tasks-main.txt"
        r = run_script(SCRIPT, "select", str(self.tmp / "pilot"), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        spec = B.read_task_spec(out)
        self.assertEqual(sorted(spec["tblite"]), ["f1", "m1", "m2"])
        self.assertIn("tiêu chí tự đề xuất".lower(), out.read_text().lower())
        r = run_script(SCRIPT, "make-configs", "--kind", "main", "--name", "main", "--tasks", str(out), "--attempts", "2",
                       "--out", str(self.tmp / "main.json"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_limit_per_dataset_is_seeded(self):
        rows = [(f"t{i}", 0.0, 0.01 * (i + 1), None, "3.12.3") for i in range(10)]
        trials = self.run_pilot(rows)
        a = B.classify_pilot(trials, limit_per_ds=4)["keep"]["tblite"]
        self.assertEqual((len(a), a), (4, B.classify_pilot(trials, limit_per_ds=4)["keep"]["tblite"]))


class TufScriptTests(unittest.TestCase):
    TUF = HARBOR / "tuf.sh"

    def run_sh(self, *args):
        return subprocess.run(["sh", str(self.TUF), *args], capture_output=True, text=True, timeout=30,
                              env={"PATH": "/usr/bin:/bin", "HARBOR_HOST": "khong-ton-tai.invalid"})

    def text(self):
        return self.TUF.read_text(encoding="utf-8")

    def test_syntax_and_usage_list_every_command(self):
        self.assertEqual(subprocess.run(["sh", "-n", str(self.TUF)]).returncode, 0)
        r = self.run_sh()
        self.assertEqual(r.returncode, 2)
        for word in ("setup", "sync", "data", "pick", "check", "oracle", "pilot", "select", "run", "status", "stop", "fetch",
                     "compare", "prune"):
            self.assertIn(f"tuf.sh {word}", r.stdout)
        self.assertNotIn("set -eu", r.stdout)

    def test_rejects_unsafe_job_names_unknown_flags_and_bad_numbers(self):
        for args in (("status", "a;rm -rf ~"), ("status", "../x"), ("run", "--bogus"), ("run", "--attempts", "0"),
                     ("run", "--attempts", "x"), ("run", "--attempts"), ("select", "--limit", "a;b"),
                     ("pilot", "other"), ("fetch", "$(id)")):
            with self.subTest(args=args):
                self.assertEqual(self.run_sh(*args).returncode, 2)

    def test_harbor_pin_matches_the_python_side(self):
        t = self.text()
        self.assertIn(f"HARBOR_VERSION={B.HARBOR_VERSION}", t)
        self.assertIn(f"HARBOR_WHEEL_SHA256={B.HARBOR_WHEEL_SHA256}", t)
        self.assertIn("sha256sum -c", t)
        self.assertIn('"harbor==$HARBOR_VERSION"', t)

    def test_model_calls_need_yes_and_print_the_plan_first(self):
        t = self.text()
        for kind in ("pilot", "run"):
            body = t[t.index(f"  {kind})\n"):]
            body = body[:body.index(";;")]
            self.assertIn("prepare_job", body)
            self.assertLess(body.index("prepare_job"), body.index('"$YES" -eq 1'))
            self.assertLess(body.index('"$YES" -eq 1'), body.index("launch_job"))
        self.assertIn("$HB plan", t)
        self.assertIn("$HB vet-config", t)      # TM-74: kiểm việc ngay trước khi chạy

    def test_token_checks_never_print_the_value(self):
        t = self.text()
        self.assertIn("stat -c %a .env", t)
        self.assertIn('[ "$perm" = 600 ]', t)
        for ln in t.splitlines():
            if ".env" in ln and not ln.lstrip().startswith("#"):
                self.assertNotRegex(ln, r"\b(cat|head|tail|sed|awk|cut)\b[^|]*\.env\b", ln)
                if "OAUTH" in ln and "grep" in ln:
                    self.assertRegex(ln, r"grep -q", ln)
        self.assertIn("sk-ant-", t)               # fetch kiểm lại lần cuối trên Mac

    def test_background_job_is_grouped_so_ssh_returns_at_once_and_a_watcher_runs(self):
        t = self.text()
        body = t[t.index("launch_job() {"):t.index("\n}\n", t.index("launch_job() {"))]
        self.assertIn("nohup setsid", body)
        self.assertEqual(body.count("< /dev/null &"), 2)      # harbor và watch, cả hai tách khỏi ssh
        self.assertIn("AGENT_STACK_PAYLOAD=", body)
        self.assertIn("harbor_bench.py watch", body)
        self.assertIn("--env-file .env", body)
        self.assertIn("validate-config", body)
        self.assertIn("meta configs/", body)

    def test_stop_signals_the_whole_group_and_lists_leftover_containers(self):
        t = self.text()
        body = t[t.index("  stop)\n"):]
        body = body[:body.index(";;")]
        self.assertIn('kill -TERM -- "-\\$pid"', body)
        self.assertIn("docker ps", body)
        self.assertNotIn("docker stop $", body)

    def test_sync_ships_only_the_allow_list(self):
        t = self.text()
        line = next(ln for ln in t.splitlines() if "archive HEAD" in ln)
        self.assertEqual(line.split("archive HEAD")[1].split("|")[0].split(), list(B.PAYLOAD_ALLOW))
        self.assertIn("build-payload", t)

    def test_fetch_masks_on_the_remote_before_pulling(self):
        t = self.text()
        body = t[t.index("  fetch)\n"):]
        body = body[:body.index(";;")]
        self.assertLess(body.index("export"), body.index("tar -xzf"))


class AgentFileTests(unittest.TestCase):
    """agent_stack_agents.py import harbor nên không import được ở đây: đọc cú pháp."""

    def setUp(self):
        self.src = (HARBOR / "agent_stack_agents.py").read_text(encoding="utf-8")
        self.tree = ast.parse(self.src)
        self.classes = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef)}

    def const(self, cls, attr):
        for n in self.classes[cls].body:
            if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == attr for t in n.targets):
                return ast.literal_eval(n.value)
        return None

    def name_of(self, cls):
        for n in self.classes[cls].body:
            if isinstance(n, ast.FunctionDef) and n.name == "name":
                return ast.literal_eval(n.body[0].value)

    def test_four_agents_with_the_names_the_bench_expects(self):
        for arm, cls in B.CLASS_OF.items():
            self.assertIn(cls, self.classes)
            self.assertEqual(self.name_of(cls), arm)

    def test_variants_map_to_payload_dirs(self):
        self.assertEqual(self.const("ClaudeCodeAgentStack", "VARIANT"), "full")
        self.assertEqual(self.const("ClaudeCodeAgentStackNoHooks", "VARIANT"), "nohooks")
        self.assertEqual(self.const("ClaudeCodeAgentStackNoAgents", "VARIANT"), "noagents")
        self.assertEqual({B.STACK: "full", B.NOHOOKS: "nohooks", B.NOAGENTS: "noagents"}, B.VARIANT_OF)
        self.assertEqual(set(B.PAYLOAD_VARIANTS), set(B.VARIANT_OF.values()))

    def test_only_the_stack_agents_load_the_plugin_and_the_plain_one_removes_rules(self):
        plain = ast.get_source_segment(self.src, self.classes["ClaudeCodePlain"])
        stack = ast.get_source_segment(self.src, self.classes["ClaudeCodeAgentStack"])
        self.assertNotIn("--plugin-dir", plain)
        self.assertIn("rm -rf", plain)
        self.assertIn("CLAUDE.md", plain)
        self.assertIn("--plugin-dir", stack)
        self.assertIn("CLAUDE.global.md", stack)
        for sub in ("ClaudeCodeAgentStackNoHooks", "ClaudeCodeAgentStackNoAgents"):
            self.assertEqual(self.classes[sub].bases[0].id, "ClaudeCodeAgentStack")

    def test_uses_only_harbor_api_verified_at_v0_25_0(self):
        for needle in ("exec_as_agent", "exec_as_root", "environment_logs_dir", "upload_dir", "build_cli_flags",
                       "from harbor.agents.installed.claude_code import ClaudeCode"):
            self.assertIn(needle, self.src)
        self.assertIn("agent-stack-env.txt", self.src)
        self.assertIn("python3", self.src)

    def test_env_file_keys_match_what_compare_reads(self):
        for key in ("variant=", "python3=", "payload_commit=", "user_claude_md=", "plugin_dir=", "hooks_json=", "agents_dir="):
            self.assertIn(key, self.src)


class HostCompatTests(unittest.TestCase):
    """Hook của agent-stack phải chạy được trong container có python3 từ MIN_PYTHON: không cú pháp hay API mới hơn."""

    def test_hooks_and_lib_avoid_syntax_newer_than_the_minimum(self):
        major, minor = B.MIN_PYTHON
        for f in list((PLUGIN / "hooks").glob("*.py")) + list((PLUGIN / "lib").glob("*.py")):
            src = f.read_text(encoding="utf-8")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)      # cảnh báo escape trong docstring có sẵn của plugin
                tree = ast.parse(src, feature_version=(major, minor))     # từ chối cú pháp mới hơn (match, ngoặc nhóm…)
            for node in ast.walk(tree):
                self.assertNotIsInstance(node, getattr(ast, "Match", ()), f.name)
            self.assertNotRegex(src, r"\bimport tomllib\b|from tomllib\b", f.name)


if __name__ == "__main__":
    unittest.main()
