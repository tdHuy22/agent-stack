"""Test cho evals/harbor: harbor_bench.py (bản chép, cấu hình, kiểm việc, chọn việc, export, so sánh), tuf.sh (phần không cần
ssh) và agent_stack_agents.py (chỉ đọc cú pháp: file này import harbor nên test không import nó)."""
import argparse
import ast
import base64
import contextlib
import importlib.util
import io
import json
import os
import re
import signal
import subprocess
import sys
import time
import tempfile
import unittest
import unittest.mock
import warnings
from pathlib import Path

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
    B.PLAIN: (False, False, {"plugin_dir": "no", "user_claude_md": "no", "config_claude_md": "no", "hooks_json": "no",
                             "agents_dir": "no"}),
    B.STACK: (True, True, {"plugin_dir": "yes", "user_claude_md": "yes", "config_claude_md": "yes", "hooks_json": "yes",
                           "agents_dir": "yes"}),
    B.NOHOOKS: (True, True, {"plugin_dir": "yes", "user_claude_md": "yes", "config_claude_md": "yes", "hooks_json": "no",
                             "agents_dir": "yes"}),
    B.NOAGENTS: (True, False, {"plugin_dir": "yes", "user_claude_md": "yes", "config_claude_md": "yes", "hooks_json": "yes",
                               "agents_dir": "no"}),
}


class Base(TempDirTestCase):
    def trial(self, job, agent, task, reward=1.0, exception=None, cost=0.1, n=0, python3="3.12.3", commit="abc1234",
              version=VER, extra_stream=(), init=True, source=None, full=None):
        """Một lượt giả đúng cấu trúc result.json của Harbor 0.25 và log stream-json của Claude Code."""
        d = self.tmp / job / f"{task}__{SHORT(agent)}{n}"
        res = {"task_name": full or task, "source": source, "agent_info": {"name": agent, "version": version},
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

    def test_symlinks_inside_allowed_dirs_are_refused(self):
        src = self.fake_repo()
        os.symlink("/etc/passwd", src / "plugin" / "link-to-host-file")
        problems = B.build_payload(src, self.tmp / "payload", "abc1234")
        self.assertTrue(any("symlink" in p and "link-to-host-file" in p for p in problems), problems)

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
        self.assert_infra_retry_and_serial_builds(cfg)
        # cài agent và dựng môi trường được nới hạn giờ, như nhau cho mọi cấu hình (ca 06/11/2026 trên tuf); hạn dựng ×4 vì
        # giờ chờ tới lượt dựng (dựng lần lượt, ca 07/11/2026) cũng tính vào hạn này
        self.assertEqual(cfg["agent_setup_timeout_multiplier"], 3.0)
        self.assertEqual(cfg["environment_build_timeout_multiplier"], 4.0)
        self.assertNotIn("agent_timeout_multiplier", cfg)

    def assert_infra_retry_and_serial_builds(self, cfg):
        """Thử lại chỉ lỗi Docker và quá giờ trước khi agent làm bài; agent thoát lỗi, hết giờ làm bài, lỗi API thì không."""
        retry = cfg["retry"]
        self.assertEqual(retry["max_retries"], 2)
        self.assertEqual(sorted(retry["include_exceptions"]),
                         ["AgentInstallError", "AgentSetupTimeoutError", "EnvironmentStartTimeoutError",
                          "RuntimeError"])
        for never in ("NonZeroAgentExitCodeError", "AgentTimeoutError", "VerifierTimeoutError", "ContextWindowExceededError",
                      *B.INFRA_ERRORS):
            self.assertNotIn(never, retry["include_exceptions"])
        self.assertGreaterEqual(retry["min_wait_sec"], 30)
        self.assertEqual(cfg["environment"], {"delete": True,
                                              "import_path": "serial_build_env:SerialBuildDockerEnvironment"})

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
        self.assert_infra_retry_and_serial_builds(cfg)
        self.assertEqual(cfg["environment_build_timeout_multiplier"], 4.0)

    def test_pilot_refuses_while_the_swerebench_list_is_still_empty(self):
        # danh sách chỉ có phần đầu giải thích, như trước khi `tuf.sh pick` chạy (file thật của repo nay đã có 25 việc)
        empty = self.tmp / "tasks-swerebench-empty.txt"
        empty.write_text("# 25 việc SWE-rebench: chưa chọn, chạy tuf.sh pick\n", encoding="utf-8")
        r = run_script(SCRIPT, "make-configs", "--kind", "pilot", "--name", "pilot", "--swerebench",
                       str(empty), "--out", str(self.tmp / "p.json"))
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
        self.assertIn("pip_freeze_sha256", m)      # None khi venv không có pip; có thì là mã băm 64 ký tự của danh sách gói
        self.assertTrue(m["pip_freeze_sha256"] is None or len(m["pip_freeze_sha256"]) == 64)
        self.assertIsInstance(m["difficulty"], dict)


class VetTests(Base):
    """TM-74: việc khai container đặc quyền, mạng máy chủ, gắn thư mục ngoài… bị từ chối."""

    def task(self, name="t", compose=None, toml="[task]\nname = \"x\"\n", dockerfile="FROM python:3.12\n"):
        self.write(f"ds/{name}/task.toml", toml)
        self.write(f"ds/{name}/environment/Dockerfile", dockerfile)
        if compose is not None:
            self.write(f"ds/{name}/environment/docker-compose.yaml", compose)
        return self.tmp / "ds" / name

    def test_tasks_without_compose_pass(self):
        self.assertEqual(B.vet_task(self.task("a")), [])
        self.assertEqual(B.vet_task(self.task("c", dockerfile="FROM swerebench/sweb.eval.x86_64.a:latest\nRUN mkdir -p /logs\n")), [])

    def test_every_compose_file_is_refused_by_default_whatever_it_says(self):
        """Mỗi dạng lách mà regex bỏ sót (review 06/11/2026) đều bị từ chối vì có file compose, không cần hiểu nội dung."""
        evasions = {
            "flow style": "services:\n  main: {image: x, privileged: true}\n",
            "quoted key": "services:\n  main:\n    \"privileged\": true\n",
            "home variable bind": "services:\n  main:\n    volumes:\n      - $HOME:/h\n",
            "named volume bind": "services:\n  main:\n    volumes:\n      - v:/h\nvolumes:\n  v:\n    driver_opts: {o: bind, device: /, type: none}\n",
            "include": "include:\n  - ../../../../.ssh/other.yaml\n",
            "extends": "services:\n  main:\n    extends:\n      file: ../../x.yaml\n      service: s\n",
            "env_file to harbor .env": "services:\n  main:\n    env_file: ../../../../.env\n",
            "secrets file": "secrets:\n  k:\n    file: ../../../../.ssh/id_ed25519\nservices:\n  main:\n    secrets: [k]\n",
            "configs file": "configs:\n  c:\n    file: ../../../../.env\n",
            "build context": "services:\n  main:\n    build:\n      context: ../../..\n",
            "additional_contexts": "services:\n  main:\n    build:\n      context: .\n      additional_contexts:\n        h: ../../..\n",
            "build network": "services:\n  main:\n    build:\n      network: host\n",
            "volumes_from": "services:\n  main:\n    volumes_from: [other]\n",
            "sysctls": "services:\n  main:\n    sysctls:\n      net.ipv4.ip_forward: 1\n",
            "cgroup_parent": "services:\n  main:\n    cgroup_parent: /\n",
            "quoted security_opt": "services:\n  main:\n    \"security_opt\": [\"seccomp=unconfined\"]\n",
            "network_mode host": "services:\n  main:\n    network_mode: host\n",
            "privileged": "services:\n  main:\n    privileged: true\n",
            "docker.sock": "services:\n  main:\n    volumes:\n      - /var/run/docker.sock:/var/run/docker.sock\n",
            "absolute bind": "services:\n  main:\n    volumes:\n      - /home/tuf:/mnt\n",
            "harmless-looking": "services:\n  main:\n    image: x\n    volumes:\n      - ./data:/data\n",
            "empty": "",
        }
        for label, compose in evasions.items():
            with self.subTest(label):
                probs = B.vet_task(self.task("bad", compose=compose))
                self.assertTrue(any(p.startswith(B.COMPOSE_PROBLEM) for p in probs), probs)
                self.assertTrue(any("sha256 " + B.hashlib.sha256(compose.encode()).hexdigest() in p for p in probs))

    def test_compose_files_are_found_under_any_name_or_place(self):
        for i, rel in enumerate(("docker-compose.yaml", "docker-compose.yml", "compose.yaml", "compose.yml",
                                 "docker-compose.override.yml", "docker-compose.prod.yaml", "environment/stack.yaml",
                                 "environment/sub/anything.yml", "environment/docker-compose.yaml", "x/Compose.YML")):
            with self.subTest(rel):
                d = self.task(f"c{i}")
                self.write(f"ds/c{i}/{rel}", "services: {}\n")
                self.assertTrue(any(B.COMPOSE_PROBLEM in p for p in B.vet_task(d)), rel)
        d = self.task("plain")
        self.write("ds/plain/environment/notes.txt", "compose is mentioned here")
        self.write("ds/plain/tests/test_outputs.py", "x = 1")
        self.assertEqual(B.vet_task(d), [])

    def test_hand_approved_compose_passes_only_with_the_exact_hash_for_that_task(self):
        text = "services:\n  main:\n    image: x\n"
        digest = B.hashlib.sha256(text.encode()).hexdigest()
        d = self.task("ok", compose=text)
        self.assertEqual(B.vet_task(d, {"ok": {digest}}), [])
        self.assertTrue(B.vet_task(d, {"ok": {"0" * 64}}))                       # băm sai
        self.assertTrue(B.vet_task(d, {"khac": {digest}}))                        # băm đúng nhưng cho việc khác
        self.assertTrue(B.vet_task(d, {}))
        self.write("ds/ok/environment/docker-compose.yaml", text + "    privileged: true\n")   # nội dung đổi sau khi duyệt
        self.assertTrue(B.vet_task(d, {"ok": {digest}}))
        # việc có hai file compose: duyệt một file thì file kia vẫn làm việc bị loại; các kiểm khác vẫn chạy với việc đã duyệt
        d2 = self.task("two", compose=text)
        self.write("two-extra", "")
        self.write("ds/two/docker-compose.override.yml", "services: {}\n")
        self.assertEqual(len(B.vet_task(d2, {"two": {digest}})), 1)
        d3 = self.task("dock", compose=text, dockerfile="FROM x\nCOPY /var/run/docker.sock /s\n")
        self.assertTrue(any("socket" in p for p in B.vet_task(d3, {"dock": {digest}})))

    def test_allow_list_file_format_and_the_committed_list(self):
        digest = "ab" * 32
        f = self.write("allow.txt", f"# chú thích\nviec-a {digest}   # đã đọc\n\nviec-a {'cd' * 32}\nviec-b {digest}\n")
        self.assertEqual(B.load_allow(f), {"viec-a": {digest, "cd" * 32}, "viec-b": {digest}})
        for bad in ("viec-a\n", f"viec-a {digest} thừa\n", "viec-a xyz\n", f"../x {digest}\n", f"viec-a {digest.upper()}\n"):
            with self.subTest(bad=bad):
                with self.assertRaises(SystemExit):
                    B.load_allow(self.write("bad.txt", bad))
        self.assertEqual(B.load_allow(self.tmp / "khong-co.txt"), {})
        self.assertEqual(B.load_allow(HARBOR / "compose-allow.txt"), {})      # bản commit: chưa duyệt việc nào
        self.assertIn("sha256", (HARBOR / "compose-allow.txt").read_text(encoding="utf-8"))

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

    def test_compose_disguised_behind_a_symlink_inside_the_task_is_refused(self):
        """Review vòng 1 (06/11/2026): docker-compose.yaml là symlink tới file trong việc, tên và đuôi không phải yaml."""
        bad = "services:\n  main:\n    env_file: ../../../../.env\n    volumes: [\"/:/host\"]\n"
        d = self.task("sym1")
        self.write("ds/sym1/environment/notes.txt", bad)
        os.symlink("notes.txt", d / "environment" / "docker-compose.yaml")
        d2 = self.task("sym2")
        self.write("ds/sym2/tests/data.cfg", bad)
        os.symlink("../tests/data.cfg", d2 / "environment" / "docker-compose.yaml")
        d3 = self.task("sym3")
        os.symlink("Dockerfile", d3 / "environment" / "Containerfile")
        for t in (d, d2, d3):
            text = "\n".join(B.vet_task(t, {}))
            self.assertIn("symlink trong environment/", text, t.name)
        self.assertEqual(B.vet_names(self.tmp / "ds", None, {}).keys() & {"sym1", "sym2", "sym3"},
                         {"sym1", "sym2", "sym3"})
        # environment/ là symlink tới thư mục khác trong việc
        d4 = self.tmp / "ds" / "sym4"
        self.write("ds/sym4/task.toml", "[task]\nname = \"x\"\n")
        self.write("ds/sym4/real/Dockerfile", "FROM python:3.12\n")
        os.symlink("real", d4 / "environment")
        self.assertIn("environment: là symlink", "\n".join(B.vet_task(d4, {})))

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
        # người dùng thấy bộ việc bị bớt bao nhiêu và việc nào
        self.assertIn("1/2 việc bị loại vì có file compose chưa duyệt: bad", r.stderr)
        self.assertIn("trong đó 1 vì compose", r.stdout)

    def test_cli_vet_allow_file_keeps_the_approved_task(self):
        text = "services:\n  main:\n    image: x\n"
        self.task("approved", compose=text)
        self.task("other", compose=text)
        allow = self.write("allow.txt", f"approved {B.hashlib.sha256(text.encode()).hexdigest()}\n")
        r = run_script(SCRIPT, "vet", str(self.tmp / "ds"), "--drop", "--allow", str(allow))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(B.list_tasks(self.tmp / "ds"), ["approved"])

    def test_vet_config_checks_exactly_the_tasks_the_job_will_run(self):
        self.task("good")
        self.task("bad", compose="services:\n  main:\n    network_mode: host\n")
        text = "services:\n  main:\n    image: x\n"
        self.task("approved", compose=text)
        cfg = self.write("c.json", json.dumps({"datasets": [{"path": "ds", "task_names": ["good"]}]}))
        self.assertEqual(run_script(SCRIPT, "vet-config", str(cfg), "--root", str(self.tmp)).returncode, 0)
        cfg = self.write("c2.json", json.dumps({"datasets": [{"path": "ds", "task_names": ["good", "bad"]}]}))
        self.assertEqual(run_script(SCRIPT, "vet-config", str(cfg), "--root", str(self.tmp)).returncode, 1)
        cfg = self.write("c3.json", json.dumps({"datasets": [{"path": "ds"}]}))
        self.assertEqual(run_script(SCRIPT, "vet-config", str(cfg), "--root", str(self.tmp)).returncode, 1)
        cfg = self.write("c4.json", json.dumps({"datasets": [{"path": "ds", "task_names": ["good", "approved"]}]}))
        self.assertEqual(run_script(SCRIPT, "vet-config", str(cfg), "--root", str(self.tmp)).returncode, 1)
        allow = self.write("allow.txt", f"approved {B.hashlib.sha256(text.encode()).hexdigest()}\n")
        r = run_script(SCRIPT, "vet-config", str(cfg), "--root", str(self.tmp), "--allow", str(allow))
        self.assertEqual(r.returncode, 0, r.stderr)


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

    def test_counts_agent_exits_that_report_http_429_but_not_quoted_text(self):
        """Ca 09/11/2026: hết hạn mức phiên của gói Max, Claude Code thoát mã 1 với `"api_error_status":429`, Harbor xếp
        vào `NonZeroAgentExitCodeError`; watcher bỏ sót, 45 lượt hỏng tới khi job bị dừng tay."""
        job = self.tmp / "jobs" / "j"
        msgs = {
            "hit": 'Command failed (exit 1): claude ...\nstdout: {"type":"result","is_error":true,'
                   '"api_error_status":429,"api_error":"usage_limit_reached","result":"You\'ve hit your session limit"}',
            "quoted": 'Command failed (exit 1): claude ...\nstdout: {"type":"user","content":"grep \\"api_error_status\\":429 log"}',
            "other": 'Command failed (exit 1): claude ...\nstdout: {"type":"result","api_error_status":500}',
        }
        for name, msg in msgs.items():
            d = self.trial("jobs/j", B.PLAIN, name, reward=None, exception="NonZeroAgentExitCodeError")
            res = json.loads((d / "result.json").read_text())
            res["exception_info"]["exception_message"] = msg
            (d / "result.json").write_text(json.dumps(res))
        self.assertEqual(B.count_limit_errors(job), 1)

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


    def test_low_disk_prunes_the_build_cache_and_keeps_watching(self):
        """Ca 09/11/2026: ổ đầy ở lượt 110/153 làm Harbor dừng cả job; cache dựng tích 7,8 GB từ đầu job."""
        job = self.limit_trials(0)
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        self.addCleanup(lambda: proc.poll() is None and (proc.kill(), proc.wait()))
        frees, pruned, ticks = iter([25.0, 45.0, None, 17.2, 20.0]), [], []

        def tick(_):
            ticks.append(1)
            if len(ticks) == 5:
                proc.kill()
                proc.wait()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = B.watch(job, proc.pid, limit=3, interval=0, sleep=tick, min_free_gb=30, free=lambda _: next(frees),
                           prune=lambda keep: pruned.append(keep) or "Total reclaimed space: 7.6GB")
        self.assertEqual(code, 0)
        # 25 GB: chỉ cache cũ hơn 30 phút; 45 GB và không đọc được: không dọn; 17,2 GB (dưới 2/3 ngưỡng): mọi cache;
        # đúng 20 GB (bằng 2/3 ngưỡng): vẫn chỉ cache cũ
        self.assertEqual(pruned, ["30m", None, "30m"])
        self.assertIn("ổ còn 25.0 GB, dưới 30 GB: dọn cache dựng cũ hơn 30 phút", out.getvalue())
        self.assertIn("ổ còn 17.2 GB, dưới 30 GB: dọn mọi cache dựng không dùng", out.getvalue())
        self.assertIn("Total reclaimed space: 7.6GB", out.getvalue())

    def test_prune_build_cache_filters_by_age_unless_keep_is_none(self):
        """Ca 09/11/2026 11:30: cache SWE-rebench mới tích 14 GB, `until=30m` không xóa được gì, ổ còn 17 GB."""
        calls = []

        def run(cmd, **_):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "Total:\t14.03GB\n", "")
        with unittest.mock.patch.object(B.subprocess, "run", run):
            self.assertEqual(B.prune_build_cache(), "Total:\t14.03GB")
            self.assertEqual(B.prune_build_cache(None), "Total:\t14.03GB")
        self.assertEqual(calls, [["docker", "builder", "prune", "-f", "--filter", "until=30m"],
                                 ["docker", "builder", "prune", "-f"]])

    def test_disk_check_is_off_by_default_and_free_gb_handles_a_missing_job_dir(self):
        job = self.limit_trials(0)
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        self.addCleanup(lambda: proc.poll() is None and (proc.kill(), proc.wait()))
        ticks = []

        def tick(_):
            ticks.append(1)
            if len(ticks) == 2:
                proc.kill()
                proc.wait()
        code = B.watch(job, proc.pid, interval=0, sleep=tick, free=lambda _: 1.0, prune=lambda keep: self.fail("không được dọn"))
        self.assertEqual((code, len(ticks)), (0, 2))          # vòng lặp có chạy, ổ 1 GB mà vẫn không dọn
        self.assertGreater(B.free_gb(self.tmp / "chưa" / "có"), 0)


class ResumeExecTests(Base):
    """Ca 09/11/2026: `harbor jobs resume` đọc config.json mà Harbor đã che CLAUDE_FORCE_OAUTH thành ****."""

    AGENT = "agent_stack_agents:ClaudeCodePlain"

    def setup_job(self, original_env):
        job = self.tmp / "jobs" / "p"
        self.write("jobs/p/config.json", json.dumps({"agents": [{"import_path": self.AGENT,
                                                                 "env": {"CLAUDE_FORCE_OAUTH": "****"}}]}))
        for name, result in (("t1__a", '{"x": 1}'), ("t2__b", "")):
            self.write(f"jobs/p/{name}/config.json", json.dumps({"agent": {"import_path": self.AGENT,
                                                                         "env": {"CLAUDE_FORCE_OAUTH": "****"}}}))
            self.write(f"jobs/p/{name}/result.json", result)
        orig = self.write("configs/p.json", json.dumps({"agents": [{"import_path": self.AGENT, "env": original_env}]}))
        return job, orig

    def test_redacted_env_is_restored_in_job_and_trial_configs_from_the_original(self):
        job, orig = self.setup_job({"CLAUDE_FORCE_OAUTH": "1"})
        done = B.restore_redacted_env(job, orig)
        self.assertEqual(len(done), 3)
        self.assertEqual(json.loads((job / "config.json").read_text())["agents"][0]["env"], {"CLAUDE_FORCE_OAUTH": "1"})
        self.assertEqual(json.loads((job / "t1__a" / "config.json").read_text())["agent"]["env"]["CLAUDE_FORCE_OAUTH"], "1")
        self.assertEqual(B.restore_redacted_env(job, orig), [])          # chạy lại: không còn gì để khôi phục

    def test_every_agent_of_a_four_arm_job_is_restored(self):
        job, _ = self.setup_job({"CLAUDE_FORCE_OAUTH": "1"})
        arms = [f"agent_stack_agents:{c}" for c in B.CLASS_OF.values()]
        self.write("jobs/p/config.json", json.dumps({"agents": [{"import_path": a, "env": {"CLAUDE_FORCE_OAUTH": "****"}}
                                                               for a in arms]}))
        orig = self.write("configs/p.json", json.dumps({"agents": [{"import_path": a, "env": {"CLAUDE_FORCE_OAUTH": "1"}}
                                                                  for a in arms]}))
        B.restore_redacted_env(job, orig)
        envs = [a["env"]["CLAUDE_FORCE_OAUTH"] for a in json.loads((job / "config.json").read_text())["agents"]]
        self.assertEqual(envs, ["1"] * 4)

    def test_an_original_value_that_looks_like_a_key_is_never_written(self):
        job, orig = self.setup_job({"CLAUDE_FORCE_OAUTH": "sk-ant-oat01-" + "Q" * 20})
        with self.assertRaises(ValueError):
            B.restore_redacted_env(job, orig)
        self.assertIn("****", (job / "config.json").read_text())
        self.assertNotIn("sk-ant", "".join(p.read_text() for p in job.rglob("config.json")))

    def test_trials_with_an_empty_result_are_set_aside_not_deleted(self):
        job, _ = self.setup_job({"CLAUDE_FORCE_OAUTH": "1"})
        self.assertEqual(B.set_aside_incomplete(job), ["t2__b"])
        self.assertFalse((job / "t2__b").exists())
        self.assertTrue((self.tmp / "jobs" / "p.incomplete" / "t2__b" / "config.json").is_file())
        self.assertTrue((job / "t1__a").is_dir())

    def test_limit_error_trials_are_set_aside_so_resume_reruns_them(self):
        """Ca 09/11/2026: 45 lượt hỏng vì hết hạn mức; giữ lại thì resume bỏ qua (tính trượt) và watcher dừng job ngay."""
        job, _ = self.setup_job({"CLAUDE_FORCE_OAUTH": "1"})
        for name, exc in (("t3__c", "ApiUsageLimitError"), ("t4__d", "AgentTimeoutError")):
            self.write(f"jobs/p/{name}/result.json", json.dumps({"exception_info": {"exception_type": exc}}))
        self.write("jobs/p/t5__e/result.json", json.dumps({"exception_info": {
            "exception_type": "NonZeroAgentExitCodeError",
            "exception_message": 'stdout: {"type":"result","is_error":true,"api_error_status":429}'}}))
        self.write("jobs/p.limit/t3__c/result.json", "{}")          # lần dừng trước đã dời một lượt cùng tên
        self.assertEqual(B.set_aside_limit_errors(job), ["t3__c", "t5__e"])
        self.assertFalse((job / "t3__c").exists())
        self.assertTrue((self.tmp / "jobs" / "p.limit" / "t3__c.1" / "result.json").is_file())
        self.assertTrue((job / "t4__d").is_dir())
        self.assertEqual(B.count_limit_errors(job), 0)


class StatusTests(Base):
    """Mục 8: status cho biết harbor và watcher còn sống không; log in ra được lọc."""

    def test_status_shows_both_pids_and_warns_when_only_the_watcher_died(self):
        job = self.tmp / "jobs" / "j"
        self.trial("jobs/j", B.PLAIN, "t")
        alive = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: (alive.kill(), alive.wait()))
        dead = subprocess.Popen(["true"])
        dead.wait()
        (self.tmp / "jobs" / "j.pid").write_text(f"{alive.pid}\n")
        (self.tmp / "jobs" / "j.watch.pid").write_text(f"{dead.pid}\n")
        r = run_script(SCRIPT, "status", str(job))
        self.assertIn(f"harbor: PID {alive.pid} đang chạy", r.stdout)
        self.assertIn(f"watcher: PID {dead.pid} ĐÃ DỪNG", r.stdout)
        self.assertIn("⚠️ watcher đã dừng", r.stdout)
        (self.tmp / "jobs" / "j.watch.pid").write_text(f"{alive.pid}\n")
        r = run_script(SCRIPT, "status", str(job))
        self.assertIn("watcher: PID", r.stdout)
        self.assertNotIn("⚠️", r.stdout)
        (self.tmp / "jobs" / "j.watch.pid").unlink()
        self.assertIn("watcher: không thấy j.watch.pid", run_script(SCRIPT, "status", str(job)).stdout)

    def test_status_counts_retries_from_the_job_log(self):
        """Harbor xóa thư mục lượt hỏng trước khi thử lại; dấu vết duy nhất là dòng DEBUG trong job.log."""
        job = self.tmp / "jobs" / "j"
        self.trial("jobs/j", B.PLAIN, "t")
        self.write("jobs/j/job.log", "\n".join([
            "2026-11-07 DEBUG Trial a__x1 failed with exception RuntimeError. Retrying in 30.00 seconds...",
            "2026-11-07 DEBUG Trial b__x2 failed with exception RuntimeError. Retrying in 60.00 seconds...",
            "2026-11-07 DEBUG Trial c__x3 failed with exception EnvironmentStartTimeoutError. Retrying in 30.00 seconds...",
            "2026-11-07 DEBUG Exception AgentTimeoutError is not in include_exceptions, not retrying"]) + "\n")
        self.assertEqual(B.count_retries(job), {"RuntimeError": 2, "EnvironmentStartTimeoutError": 1})
        # lần thử lại dùng lại đúng tên lượt: ghép với result.json cuối để biết cấu hình
        self.write("jobs/j/a__x1/result.json", json.dumps({"task_name": "a", "agent_info": {"name": B.STACK}}))
        self.write("jobs/j/b__x2/result.json", json.dumps({"task_name": "b", "agent_info": {"name": B.STACK}}))
        self.write("jobs/j/c__x3/result.json", json.dumps({"task_name": "c", "agent_info": {"name": B.PLAIN}}))
        self.assertEqual(B.retries_by_arm(job), {"stack": 2, "plain": 1})
        r = run_script(SCRIPT, "status", str(job))
        self.assertIn("đã thử lại vì lỗi hạ tầng: EnvironmentStartTimeoutError 1, RuntimeError 2; theo cấu hình: plain 1, stack 2",
                      r.stdout)
        (job / "c__x3" / "result.json").unlink()
        self.assertEqual(B.retries_by_arm(job), {"stack": 2, "?": 1})
        (job / "job.log").unlink()
        self.assertNotIn("thử lại", run_script(SCRIPT, "status", str(job)).stdout)

    def test_scrub_masks_keys_and_drops_control_characters(self):
        dirty = (f"tiến độ \x1b[31mđỏ\x1b[0m\r50%\x1b]0;tiêu đề giả\x07 khóa {FAKE_KEY} ok\x00\x08\x7f\x9b xong\tđây\n"
                 "\x1b[2J\x1b[Hdòng hai CLAUDE_CODE_OAUTH_TOKEN=abcdefgh12345678\n").encode()
        r = subprocess.run([sys.executable, str(SCRIPT), "scrub"], input=dirty, capture_output=True, timeout=30)
        out = r.stdout.decode()
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("\x1b", out)
        for c in "\x00\x08\x7f\x9b\x07":
            self.assertNotIn(c, out)
        self.assertNotIn("sk-ant-", out)
        self.assertNotIn("abcdefgh12345678", out)
        self.assertIn("tiến độ đỏ", out)
        self.assertIn("xong\tđây", out)
        self.assertIn("50%", out)


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

    TOKEN = "Zq7-realtokenvalue_0123456789ABCDEFGHIJ"      # khóa giả không có tiền tố sk-ant-: chỉ khớp theo giá trị

    def env_file(self, body=None):
        return self.write("harbor.env", body or f"CLAUDE_CODE_OAUTH_TOKEN={self.TOKEN}\n")

    def test_real_token_from_env_is_masked_in_raw_and_base64_forms_and_never_printed(self):
        token = self.TOKEN.encode()
        variants = B.secret_variants(token)
        for off in range(3):
            for enc in (base64.b64encode, base64.urlsafe_b64encode):
                blob = enc(b"A" * off + b"xin chao " + token + b" tail")
                self.assertTrue(any(v in blob for v in variants), (off, enc))
        d = self.trial("pilot", B.PLAIN, "t")
        self.write(f"pilot/{d.name}/agent/claude-code.txt", f"env: {self.TOKEN}\n")
        for i in range(3):
            blob = base64.b64encode(b"B" * i + b"cat .env " + token + b" end").decode()
            self.write(f"pilot/{d.name}/agent/note{i}/reward.txt", f"b64: {blob}\n")
        out = self.tmp / "out"
        r = run_script(SCRIPT, "export", str(self.tmp / "pilot"), "--out", str(out), "--env-file", str(self.env_file()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(self.TOKEN, r.stdout + r.stderr)
        for f in B._walk_files(out):
            data = f.read_bytes()
            self.assertNotIn(token, data, f)
            self.assertFalse(any(v in data for v in variants), f)
        # không có --env-file thì khóa không mang tiền tố sk-ant- lọt qua: đó là lý do cần giá trị thật
        out2 = self.tmp / "out2"
        self.assertEqual(run_script(SCRIPT, "export", str(self.tmp / "pilot"), "--out", str(out2)).returncode, 0)
        self.assertIn(self.TOKEN, (out2 / "pilot" / d.name / "agent" / "claude-code.txt").read_text())
        r = run_script(SCRIPT, "residual", str(out2), "--env-file", str(self.env_file()))
        self.assertEqual(r.returncode, 1)
        self.assertIn("giá trị khóa trong .env", r.stderr)
        self.assertNotIn(self.TOKEN, r.stdout + r.stderr)
        self.assertEqual(run_script(SCRIPT, "residual", str(out), "--env-file", str(self.env_file())).returncode, 0)

    def test_residual_scans_every_file_including_binary_and_ignores_short_lookalikes(self):
        self.write("d/a.txt", "sk-ant-xxx là chuỗi giả trong repo, và sk-ant là tiền tố\n")
        self.assertEqual(run_script(SCRIPT, "residual", str(self.tmp / "d")).returncode, 0)
        (self.tmp / "d" / "blob.bin").write_bytes(b"\x00\x01\xff" + FAKE_KEY.encode() + b"\x00")
        self.write("d/sub/deep/log.txt", f"x {FAKE_KEY}")
        r = run_script(SCRIPT, "residual", str(self.tmp / "d"), str(self.tmp / "khong-co"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("blob.bin", r.stderr)
        self.assertIn("log.txt", r.stderr)
        self.assertNotIn(FAKE_KEY, r.stdout + r.stderr)

    def test_export_stops_and_removes_the_copy_when_masking_leaves_a_key(self):
        d = self.trial("pilot", B.PLAIN, "t")
        self.write(f"pilot/{d.name}/agent/claude-code.txt", f"khóa {FAKE_KEY}\n")
        out = self.tmp / "out"
        args = argparse.Namespace(jobs=[str(self.tmp / "pilot")], out=str(out), env_file=None)
        with unittest.mock.patch.object(B, "mask_secrets", lambda data, extra=(): data):
            self.assertEqual(B.cmd_export(args), 1)
        self.assertFalse(out.exists())

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

    def test_oracle_passing_once_across_runs_is_enough_and_never_passing_drops_the_task(self):
        """Ca 07/11/2026: ba lần chạy lời giải mẫu, mỗi lần hỏng một nhóm việc khác vì Docker sập."""
        P, S = B.PLAIN, B.STACK
        for task in ("flaky-infra", "never", "both-ok"):
            for arm in (P, S):
                self.trial("job", arm, task, reward=1.0)
        self.trial("o1", "oracle", "flaky-infra", reward=None, exception="RuntimeError")
        self.trial("o2", "oracle", "flaky-infra", reward=1.0)
        self.trial("o1", "oracle", "never", reward=0.0)
        self.trial("o2", "oracle", "never", reward=None, exception="RuntimeError")
        self.trial("o1", "oracle", "both-ok", reward=1.0)
        self.trial("o2", "oracle", "both-ok", reward=1.0)
        oracle = B.load_trials([self.tmp / "o1", self.tmp / "o2"])
        res = B.compare(B.load_trials([self.tmp / "job"]), oracle, arms=[P, S])
        self.assertEqual([r["task"] for r in res["rows"]], ["both-ok", "flaky-infra"])
        self.assertEqual(dict(res["excluded"])["never"], "lời giải mẫu không đạt")
        # dòng lệnh nhận --oracle nhiều lần
        r = run_script(SCRIPT, "compare", str(self.tmp / "job"), "--oracle", str(self.tmp / "o1"), "--oracle",
                       str(self.tmp / "o2"), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([x["task"] for x in json.loads(r.stdout)["rows"]], ["both-ok", "flaky-infra"])

    def test_pilot_report_keeps_the_vietnamese_set_in_its_own_group(self):
        cfg = {"datasets": [{"path": "datasets/tblite", "task_names": ["t1"]}, {"path": "datasets/vi"}]}
        self.write("datasets/tblite/t1/task.toml", '[metadata]\ndifficulty = "medium"\n')
        self.write("datasets/vi/code-a/task.toml", '[metadata]\ndifficulty = "medium"\n')
        self.assertEqual(B.difficulty_map(cfg, self.tmp), {"t1": "medium", "code-a": "vi"})

    def test_compare_can_be_limited_to_one_task_list(self):
        P, S = B.PLAIN, B.STACK
        for task, (rp, rs) in {"code-a": (0.0, 1.0), "viet-b": (0.0, 1.0), "tb-x": (1.0, 0.0)}.items():
            self.trial("job", P, task, reward=rp)
            self.trial("job", S, task, reward=rs)
        lst = self.write("tasks-vi.txt", "vi:code-a\nvi:viet-b\n")
        r = run_script(SCRIPT, "compare", str(self.tmp / "job"), "--tasks", str(lst), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual([x["task"] for x in res["rows"]], ["code-a", "viet-b"])
        c = next(c for c in res["comparisons"] if c["a"] == P and c["b"] == S)
        self.assertEqual((c["worse"], c["better"]), ([], ["code-a", "viet-b"]))
        # chỉ số phụ cạnh reward (reward.json của bộ tiếng Việt) đi vào bảng, không đổi đạt/trượt
        for arm, n in ((P, 3), (S, 1)):
            d = next((self.tmp / "job").glob(f"viet-b__{SHORT(arm)}0"))
            res_json = json.loads((d / "result.json").read_text())
            res_json["verifier_result"]["rewards"]["van_ai"] = n
            (d / "result.json").write_text(json.dumps(res_json))
        r = run_script(SCRIPT, "compare", str(self.tmp / "job"), "--tasks", str(lst))
        self.assertRegex(r.stdout, r"Dấu hiệu văn AI mỗi bài viết \(TB\)\s+3\.00\s+1\.00")
        self.assertIn("tốt hơn ở 2 việc", r.stdout)
        other = self.write("tasks-none.txt", "vi:khong-co\n")
        self.assertEqual(run_script(SCRIPT, "compare", str(self.tmp / "job"), "--tasks", str(other)).returncode, 1)

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

    def test_task_names_with_an_org_prefix_are_cut_to_the_directory_name_everywhere(self):
        """Harbor đặt task_name = config.task.name (org/tên); task_names của job và thư mục xuất dùng tên ngắn."""
        self.assertEqual(B.task_key("org/abc"), "abc")
        self.assertEqual(B.task_key("abc"), "abc")
        self.assertEqual(B.task_key("a/b/c"), "c")
        for arm in (B.PLAIN, B.STACK):
            self.trial("job", arm, "abc", reward=1.0, full="org/abc")
            self.trial("job", arm, "def", reward=0.0, full="org/def")
        self.trial("oracle", "oracle", "abc", reward=1.0, full="org/abc")
        self.trial("oracle", "oracle", "def", reward=0.0, full="org/def")      # lời giải mẫu không đạt: loại
        trials = B.load_trials([self.tmp / "job"])
        self.assertEqual({t["task"] for t in trials}, {"abc", "def"})
        self.assertEqual({t["task_full"] for t in trials}, {"org/abc", "org/def"})
        res = B.compare(trials, B.load_trials([self.tmp / "oracle"]), arms=[B.PLAIN, B.STACK])
        self.assertEqual([r["task"] for r in res["rows"]], ["abc"])
        self.assertEqual(dict(res["excluded"])["def"], "lời giải mẫu không đạt")
        # tên đã cắt đi thẳng vào danh sách việc của job (NAME_RE không cho dấu '/')
        f = self.write("main.txt", "".join(f"tblite:{t}\n" for t in sorted({t["task"] for t in trials})))
        self.assertEqual(B.read_task_spec(f), {"tblite": ["abc", "def"]})

    def test_one_infra_failed_attempt_drops_the_whole_task_even_when_others_were_graded(self):
        P, S = B.PLAIN, B.STACK
        for n in range(2):
            self.trial("job", P, "mixed", reward=1.0, n=n)
            self.trial("job", P, "clean", reward=1.0, n=n)
            self.trial("job", S, "clean", reward=1.0, n=n)
        self.trial("job", S, "mixed", reward=1.0, n=0)
        self.trial("job", S, "mixed", reward=0.0, n=1, exception="ApiOverloadedError")
        res = B.compare(B.load_trials([self.tmp / "job"]), arms=[P, S])
        self.assertEqual([r["task"] for r in res["rows"]], ["clean"])
        self.assertIn("ApiOverloadedError", dict(res["excluded"])["mixed"])
        # hỏng ở bản kia (plain) cũng loại việc, và lượt không có điểm cũng vậy
        self.trial("job", P, "other", reward=1.0, n=0)
        self.trial("job", P, "other", reward=None, n=1)
        for n in range(2):
            self.trial("job", S, "other", reward=1.0, n=n)
        res = B.compare(B.load_trials([self.tmp / "job"]), arms=[P, S])
        self.assertIn("other", dict(res["excluded"]))

    def test_unclassified_api_errors_are_infrastructure(self):
        for exc in ("UnknownApiError", "ApiProviderResourceNotFoundError"):
            self.assertIn(exc, B.INFRA_ERRORS)
            self.trial("job", B.PLAIN, exc, reward=1.0)
            self.trial("job", B.STACK, exc, reward=0.0, exception=exc)
        self.assertEqual(B.compare(B.load_trials([self.tmp / "job"]), arms=[B.PLAIN, B.STACK])["rows"], [])
        for exc in ("AgentTimeoutError", "ContextWindowExceededError", "NonZeroAgentExitCodeError", "OutputTokenExceededError"):
            self.assertNotIn(exc, B.INFRA_ERRORS)

    def test_pip_freeze_difference_is_a_warning_and_never_a_refusal(self):
        self.trial("a", B.PLAIN, "t")
        self.trial("b", B.PLAIN, "t2")
        self.write("a.meta.json", json.dumps({"claude_code": VER, "pip_freeze_sha256": "1" * 64}))
        self.write("b.meta.json", json.dumps({"claude_code": VER, "pip_freeze_sha256": "2" * 64}))
        r = run_script(SCRIPT, "compare", str(self.tmp / "a"), str(self.tmp / "b"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("⚠️ pip freeze", r.stderr)
        self.write("b.meta.json", json.dumps({"claude_code": VER, "pip_freeze_sha256": "1" * 64}))
        self.assertNotIn("pip freeze", run_script(SCRIPT, "compare", str(self.tmp / "a"), str(self.tmp / "b")).stderr)

    def test_report_names_the_test_it_really_runs(self):
        for task, a, b in (("t1", 1, 0), ("t2", 0, 1)):
            self.trial("one", B.PLAIN, task, reward=float(a))
            self.trial("one", B.STACK, task, reward=float(b))
        text = B.report(B.compare(B.load_trials([self.tmp / "one"])))
        self.assertIn("McNemar chính xác p =", text)
        self.assertNotIn("kiểm dấu chính xác", text)
        for n in range(2):
            self.trial("two", B.PLAIN, "t", reward=1.0, n=n)
            self.trial("two", B.STACK, "t", reward=float(n), n=n)
        res = B.compare(B.load_trials([self.tmp / "two"]))
        self.assertTrue(res["multi_attempt"])
        self.assertIn("kiểm dấu chính xác theo tỉ lệ đạt từng việc p =", B.report(res))
        # cùng một hàm tính cho cả hai: p của kiểm dấu chính xác trên số việc lệch
        self.assertAlmostEqual(res["comparisons"][0]["p_value"], B.exact_binomial_p(1, 0))

    def test_claude_md_in_the_harbor_config_dir_is_checked_not_only_home(self):
        d = self.trial("job", B.STACK, "t")
        env = (d / "agent" / "agent-stack-env.txt")
        env.write_text(env.read_text().replace("config_claude_md=yes", "config_claude_md=no"))
        trial = B.load_trials([self.tmp / "job"])[0]
        self.assertEqual(trial["structure"], ["config_claude_md=no (cần yes)"])
        d = self.trial("job2", B.PLAIN, "t")
        env = (d / "agent" / "agent-stack-env.txt")
        env.write_text(env.read_text().replace("config_claude_md=no", "config_claude_md=yes"))
        self.assertTrue(B.load_trials([self.tmp / "job2"])[0]["structure"])

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
    """Mục 5: việc cho job lớn chọn theo nhãn độ khó mà bộ đo công bố, không đọc kết quả của bản nào."""

    def tblite(self, name, toml):
        self.write(f"datasets/tblite/{name}/task.toml", toml)

    def swe(self, name):
        self.write(f"datasets/swerebench/{name}/task.toml", '[task]\nname = "swe-rebench/x"\n[metadata]\ndifficulty = "medium"\n')

    def test_difficulty_is_read_flexibly_from_task_toml_and_json(self):
        cases = {
            "meta-table": ('[metadata]\ndifficulty = "Hard"\n', "hard"),
            "task-table": ('[task]\nname = "a/b"\ndifficulty = "extreme"\n', "extreme"),
            "root": ('difficulty = "medium"\n', "medium"),
            "deep": ('[a.b.c]\ndifficulty = "easy"\n', "easy"),
            "suffix": ('[metadata]\ndifficulty = "Hard (pass rate 10-39%)"\n', "hard"),
            "tags": ('[metadata]\ntags = ["python", "medium"]\n', "medium"),
            "none": ('[metadata]\ncategory = "x"\n', None),
            "odd": ('[metadata]\ndifficulty = 3\n', None),
        }
        for name, (toml, want) in cases.items():
            with self.subTest(name):
                self.tblite(name, toml)
                self.assertEqual(B.task_difficulty(self.tmp / "datasets/tblite" / name), want)
        self.tblite("from-json", "[task]\nname = 'x'\n")
        self.write("datasets/tblite/from-json/metadata.json", json.dumps({"info": {"difficulty": "extreme"}}))
        self.assertEqual(B.task_difficulty(self.tmp / "datasets/tblite/from-json"), "extreme")
        self.tblite("broken", "không phải toml [[")
        self.assertIsNone(B.task_difficulty(self.tmp / "datasets/tblite/broken"))

    def test_keeps_medium_hard_extreme_plus_all_swerebench_and_ignores_easy(self):
        for name, lv in (("e1", "easy"), ("e2", "easy"), ("m1", "medium"), ("h1", "hard"), ("h2", "hard"), ("x1", "extreme")):
            self.tblite(name, f'[metadata]\ndifficulty = "{lv}"\n')
        self.tblite("nolabel", "[task]\nname = 'x'\n")
        for n in ("s__1", "s__2"):
            self.swe(n)
        res = B.select_main(self.tmp / "datasets", ["s__2", "s__1"])
        self.assertEqual(res["tblite"], ["h1", "h2", "m1", "x1"])
        self.assertEqual(res["swerebench"], ["s__1", "s__2"])
        self.assertEqual(res["unlabeled"], ["nolabel"])
        self.assertEqual(res["counts"], {"easy": 2, "medium": 1, "hard": 2, "extreme": 1, "không nhãn": 1})
        self.assertEqual(B.select_main(self.tmp / "datasets", ["s__1"], ("hard",))["tblite"], ["h1", "h2"])

    def test_stops_when_no_label_can_be_read_or_a_swerebench_task_vanished(self):
        self.tblite("a", "[task]\nname = 'x'\n")
        self.swe("s__1")
        with self.assertRaises(SystemExit) as cm:
            B.select_main(self.tmp / "datasets", ["s__1"])
        self.assertIn("nhãn độ khó", str(cm.exception))
        self.tblite("b", '[metadata]\ndifficulty = "hard"\n')
        with self.assertRaises(SystemExit) as cm:
            B.select_main(self.tmp / "datasets", ["s__1", "s__gone"])
        self.assertIn("s__gone", str(cm.exception))

    def test_cli_writes_a_documented_list_that_make_configs_reads_and_never_looks_at_results(self):
        self.tblite("m1", '[metadata]\ndifficulty = "medium"\n')
        self.tblite("e1", '[metadata]\ndifficulty = "easy"\n')
        self.swe("s__1")
        swe = self.write("tasks-swerebench.txt", "# chú thích\ns__1\n")
        r = run_script(SCRIPT, "select", str(self.tmp / "datasets"), "--swerebench", str(swe))
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual([ln for ln in lines if not ln.startswith("#")], ["tblite:m1", "swerebench:s__1"])
        header = "\n".join(ln for ln in lines if ln.startswith("#"))
        self.assertIn("KHÔNG từ kết quả", header)
        self.assertIn("Haiku 4.5", header)
        self.assertIn("1 việc TBLite + 1 SWE-rebench", r.stderr)
        out = self.write("tasks-main.txt", r.stdout)
        r = run_script(SCRIPT, "make-configs", "--kind", "main", "--name", "main", "--tasks", str(out), "--attempts", "2",
                       "--out", str(self.tmp / "main.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        cfg = json.loads((self.tmp / "main.json").read_text())
        self.assertEqual(cfg["datasets"], [{"path": "datasets/tblite", "task_names": ["m1"]},
                                           {"path": "datasets/swerebench", "task_names": ["s__1"]}])
        # lệnh select không nhận thư mục kết quả nào, và code không còn đường chọn theo kết quả pilot
        self.assertNotEqual(run_script(SCRIPT, "select", str(self.tmp / "pilot")).returncode, 0)
        self.assertFalse(hasattr(B, "classify_pilot"))
        self.assertEqual(run_script(SCRIPT, "select", str(self.tmp / "datasets"), "--swerebench", str(swe), "--levels",
                                    "easy,bogus").returncode, 2)

    def oracle_job(self, job, results, sha="aaa"):
        for task, (reward, exc) in results.items():
            self.trial(job, "oracle", task, reward=reward, exception=exc, full=f"org/{task}")
        self.write(f"{job}.meta.json", json.dumps({"job": job, "datasets": {"tblite": {"sha256": sha}}}))
        return self.tmp / job

    def test_filter_keeps_tasks_whose_reference_solution_passed_once_and_lists_the_rest(self):
        cand = self.write("tasks-candidates.txt", "# ứng viên\ntblite:ok-once\ntblite:no-solution\ntblite:docker-only\n"
                          "tblite:never-run\nswerebench:s__1\ntblite:fail-then-infra\n")
        o1 = self.oracle_job("a-oracle", {"ok-once": (None, "RuntimeError"), "no-solution": (0.0, None),
                                          "docker-only": (None, "EnvironmentStartTimeoutError"), "s__1": (None, "RuntimeError"),
                                          "fail-then-infra": (0.0, None)})
        o2 = self.oracle_job("b-oracle", {"ok-once": (1.0, None), "docker-only": (None, "RuntimeError"), "s__1": (1.0, None),
                                          "fail-then-infra": (None, "RuntimeError"),
                                          "solution-timeout": (0.0, "AgentTimeoutError")})
        main, recheck = self.tmp / "tasks-main.txt", self.tmp / "tasks-recheck.txt"
        r = run_script(SCRIPT, "filter-oracle", str(o1), str(o2), "--candidates", str(cand), "--root", str(self.tmp),
                       "--out-main", str(main), "--out-recheck", str(recheck))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Giữ 2, bỏ 2, chờ chạy lại 2", r.stderr)
        self.assertEqual(B.read_task_spec(main), {"tblite": ["ok-once"], "swerebench": ["s__1"]})
        self.assertEqual(B.read_task_spec(recheck, None), {"tblite": ["docker-only", "never-run"]})
        text = main.read_text()
        self.assertIn("KHÔNG theo kết quả của cấu hình nào", text)
        self.assertIn("a-oracle, b-oracle", text)
        self.assertIn("# bỏ, lời giải mẫu trượt hay lỗi: tblite:no-solution", text)
        self.assertIn("# bỏ, lời giải mẫu trượt hay lỗi: tblite:fail-then-infra", text)
        self.assertIn("# chờ chạy lại, chưa chấm được lần nào: tblite:never-run", text)
        # danh sách ra đọc được bằng make-configs, như tuf.sh run main sẽ làm
        r = run_script(SCRIPT, "make-configs", "--kind", "main", "--name", "main", "--tasks", str(main), "--out",
                       str(self.tmp / "m.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(B.oracle_status(B.load_trials([o2]))["solution-timeout"], "truot")

    def test_oracle_errors_of_the_task_itself_count_as_failed_but_a_stopped_job_does_not(self):
        """Ca pilot-oracle 06/11: VerifierTimeoutError không có điểm; Harbor không thử lại lỗi này, chạy lại cũng vậy."""
        self.oracle_job("c-oracle", {"grader-slow": (None, "VerifierTimeoutError"), "no-reward": (None, "RewardFileNotFoundError"),
                                     "stopped": (None, "CancelledError"), "docker": (None, "RuntimeError")})
        st = B.oracle_status(B.load_trials([self.tmp / "c-oracle"]))
        self.assertEqual(st, {"grader-slow": "truot", "no-reward": "truot", "stopped": "chua-cham", "docker": "chua-cham"})

    def test_filter_refuses_oracle_runs_on_different_task_content(self):
        cand = self.write("tasks-candidates.txt", "tblite:a\n")
        o1 = self.oracle_job("a-oracle", {"a": (1.0, None)}, sha="aaa")
        o2 = self.oracle_job("b-oracle", {"a": (1.0, None)}, sha="bbb")
        out = ["--out-main", str(self.tmp / "m.txt"), "--out-recheck", str(self.tmp / "r.txt")]
        r = run_script(SCRIPT, "filter-oracle", str(o1), str(o2), "--candidates", str(cand), "--root", str(self.tmp), *out)
        self.assertEqual(r.returncode, 2)
        self.assertIn("khác nội dung bộ việc tblite", r.stderr)
        self.assertFalse((self.tmp / "m.txt").exists())
        # bộ việc hiện tại khác bộ việc của lần oracle cũng bị từ chối
        self.write("datasets/tblite.lock.json", json.dumps({"sha256": "zzz"}))
        r = run_script(SCRIPT, "filter-oracle", str(o1), "--candidates", str(cand), "--root", str(self.tmp), *out)
        self.assertEqual(r.returncode, 2)
        # không có lượt oracle nào
        r = run_script(SCRIPT, "filter-oracle", str(self.tmp / "empty"), "--candidates", str(cand), *out)
        self.assertEqual(r.returncode, 1)

    def test_select_and_pilot_take_the_whole_vietnamese_set_when_it_was_gathered(self):
        self.tblite("m1", '[metadata]\ndifficulty = "medium"\n')
        self.swe("s__1")
        for n in ("code-a", "viet-b"):
            self.write(f"datasets/vi/{n}/task.toml", '[metadata]\ndifficulty = "easy"\n')   # nhãn không lọc bộ tự viết
        swe = self.write("tasks-swerebench.txt", "s__1\n")
        r = run_script(SCRIPT, "select", str(self.tmp / "datasets"), "--swerebench", str(swe))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([ln for ln in r.stdout.splitlines() if not ln.startswith("#")],
                         ["tblite:m1", "swerebench:s__1", "vi:code-a", "vi:viet-b"])
        self.assertIn("+ 2 tiếng Việt = 4 việc", r.stderr)
        for kind in ("pilot", "oracle"):
            r = run_script(SCRIPT, "make-configs", "--kind", kind, "--name", kind, "--swerebench", str(swe), "--root",
                           str(self.tmp), "--out", str(self.tmp / f"{kind}.json"))
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = json.loads((self.tmp / f"{kind}.json").read_text())
            self.assertEqual(cfg["datasets"][-1], {"path": "datasets/vi"})
        # chưa gom bộ tiếng Việt thì pilot như cũ; datasets (danh sách tải từ Hub) không bao giờ có bộ tự viết
        r = run_script(SCRIPT, "make-configs", "--kind", "pilot", "--name", "p", "--swerebench", str(swe), "--root",
                       str(self.tmp / "nowhere"), "--out", str(self.tmp / "p.json"))
        self.assertEqual([d["path"] for d in json.loads((self.tmp / "p.json").read_text())["datasets"]],
                         ["datasets/tblite", "datasets/swerebench"])
        self.assertEqual([ln.split("\t")[0] for ln in run_script(SCRIPT, "datasets").stdout.splitlines()],
                         ["tblite", "swerebench"])

    def test_pilot_report_groups_by_label_and_only_suggests_when_a_group_saturates(self):
        labels = {"e1": "easy", "e2": "easy", "e3": "easy", "e4": "easy", "e5": "easy", "h1": "hard", "h2": "hard", "s__1": "swerebench"}
        for t in labels:
            self.trial("pilot", B.PLAIN, t, reward=0.0 if t.startswith("h") else 1.0, cost=0.2 if t.startswith("h") else 0.05)
        self.write("pilot.meta.json", json.dumps({"claude_code": VER, "difficulty": labels}))
        before = {p.name for p in self.tmp.rglob("*")}
        r = run_script(SCRIPT, "pilot-report", str(self.tmp / "pilot"))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertRegex(out, r"easy\s+5\s+100%")
        self.assertRegex(out, r"hard\s+2\s+0%")
        self.assertIn("nhóm 'easy' bão hòa", out)
        self.assertIn("tasks-main.txt không đổi", out)
        self.assertNotIn("nhóm 'hard' bão hòa", out)
        self.assertEqual({p.name for p in self.tmp.rglob("*")}, before)          # không ghi gì
        main = self.write("tasks-main.txt", "tblite:a\ntblite:b\nswerebench:c\n")
        r = run_script(SCRIPT, "pilot-report", str(self.tmp / "pilot"), "--main-tasks", str(main), "--attempts", "2")
        self.assertIn("3 việc × 4 cấu hình × 2 lần = 24 lượt", r.stdout)


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
        for word in ("setup", "sync", "data", "pick", "check", "oracle", "pilot", "pilot-report", "select", "filter", "run",
                     "status", "stop", "fetch", "compare", "prune"):
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
                    self.assertRegex(ln, r"grep -q|wc -l|grep -oE '\^\[A-Za-z_\]\[A-Za-z0-9_\]\*='", ln)
        fetch = t[t.index("  fetch)\n"):]
        fetch = fetch[:fetch.index(";;")]
        self.assertIn("harbor_bench.py\" residual", fetch)   # Mac quét lại bằng đúng mẫu của export, không phải grep riêng
        self.assertNotIn("grep", fetch)
        self.assertIn("--env-file .env", fetch)             # export trên TUF che cả giá trị khóa thật trong .env

    def test_background_job_is_grouped_so_ssh_returns_at_once_and_a_watcher_runs(self):
        t = self.text()
        body = t[t.index("launch_job() {"):t.index("\n}\n", t.index("launch_job() {"))]
        self.assertIn("nohup setsid", body)
        self.assertEqual(body.count("< /dev/null &"), 2)      # harbor và watch, cả hai tách khỏi ssh
        self.assertIn("AGENT_STACK_PAYLOAD=", body)
        self.assertIn("harbor_bench.py watch", body)
        self.assertIn("run_harbor.sh", body)                # harbor chạy qua môi trường lọc, .env chỉ khi mode=token
        self.assertEqual(body.count("kill -0"), 2)          # sau khi khởi động kiểm cả harbor lẫn watcher
        self.assertIn("watch.pid", body)
        self.assertIn("validate-config", body)
        self.assertIn("meta configs/", body)

    def test_harbor_runs_under_a_filtered_environment_and_loads_env_only_for_model_jobs(self):
        t = (HARBOR / "run_harbor.sh").read_text(encoding="utf-8")
        self.assertEqual(subprocess.run(["sh", "-n", str(HARBOR / "run_harbor.sh")]).returncode, 0)
        self.assertIn("exec env -i", t)
        token_line = next(ln for ln in t.splitlines() if "token)" in ln)
        none_line = next(ln for ln in t.splitlines() if ln.strip().startswith("none)"))
        self.assertIn("--env-file .env", token_line)
        self.assertNotIn("--env-file", none_line)
        for var in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "AWS_", "GITHUB"):
            self.assertNotIn(var, t.split("for v in")[1].split("; do")[0])

    def test_stop_signals_the_whole_group_and_lists_leftover_containers(self):
        t = self.text()
        body = t[t.index("  stop)\n"):]
        body = body[:body.index(";;")]
        self.assertIn("docker ps", body)
        self.assertNotIn("docker stop $", body)

    def test_group_kill_lines_work_under_dash(self):
        """Ca 07/11/2026: `kill -TERM -- -PID` báo "Illegal number: -" trong dash (sh của Ubuntu trên tuf), job không dừng."""
        import shutil
        dash = shutil.which("dash")
        if not dash:
            self.skipTest("máy này không có dash")
        lines = [ln.strip() for ln in self.text().splitlines() if "kill " in ln and '"-\\$' in ln]
        self.assertEqual(len(lines), 2)                                   # dừng job, và dọn khi khởi động hỏng
        for line in lines:
            kill = line[line.index("kill "):].split("&&")[0].split(" 2>")[0].replace("\\$", "$")
            # nhóm tiến trình riêng (như setsid) có cả cháu: tín hiệu phải tới cả nhóm, không chỉ tiến trình đầu nhóm
            child = subprocess.Popen(["/bin/sh", "-c", "sleep 30 & echo $!; wait"], stdout=subprocess.PIPE, text=True,
                                     start_new_session=True)
            grandchild = int(child.stdout.readline())
            try:
                r = subprocess.run([dash, "-c", f"pid={child.pid}; hpid={child.pid}; {kill}"],
                                   capture_output=True, text=True, timeout=10)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(child.wait(timeout=5), -signal.SIGTERM)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        os.kill(grandchild, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.1)
                else:
                    self.fail(f"tiến trình cháu {grandchild} vẫn sống: tín hiệu không tới cả nhóm")
            finally:
                for pid in (child.pid, grandchild):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                child.wait(timeout=5)

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


class TufBehaviourTests(TempDirTestCase):
    """Chạy tuf.sh thật với `ssh` giả (chạy lệnh ngay trên máy này, HOME đổi sang thư mục tạm) và harbor giả. Chỉ kiểm
    hành vi của script; không có Docker, không có Harbor thật."""

    TOKEN = "sk-ant-oat01-" + "Zq7" * 14
    LOCAL_JOB = "zzfetchtest"

    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        self.rd = self.home / "harbor-eval"
        (self.rd / ".venv" / "bin").mkdir(parents=True)
        os.symlink(sys.executable, self.rd / ".venv" / "bin" / "python")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        stub = self.tmp / "stub"
        for rel in ("harbor", "harbor/models", "harbor/models/job"):
            self.write(f"stub/{rel}/__init__.py", "")
        self.write("stub/harbor/models/job/config.py",
                   "class _C:\n    agents = []\nclass JobConfig:\n    @staticmethod\n    def model_validate_json(t):\n        return _C()\n")
        self.write("stub/harbor-0.25.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: harbor\nVersion: 0.25.0\n")
        # Qua cat để stdin của shell xa là ống (như ssh thật): với stdin là file, libc của python con đặt lại vị trí đọc khi thoát
        # và shell đọc lại dòng cũ của script.
        self.shim("ssh", f'host=$1; shift\ncat | env HOME={self.home} PYTHONPATH={stub} sh -c "$*"\n')
        self.shim("setsid", 'exec "$@"\n')
        self.shim("stat", 'if /usr/bin/stat --version >/dev/null 2>&1; then exec /usr/bin/stat "$@"; fi\n'
                  'if [ "$1" = -c ] && [ "$2" = %a ]; then exec /usr/bin/stat -f %Lp "$3"; fi\nexec /usr/bin/stat "$@"\n')
        ag = self.rd / "agent-stack"
        (ag / "payload" / "full").mkdir(parents=True)
        (ag / "payload" / "full" / ".agent-stack-root").write_text("")
        (ag / "payload" / "full" / ".payload-commit").write_text("abc1234\n")
        for f in ("harbor_bench.py", "agent_stack_agents.py", "run_harbor.sh", "compose-allow.txt"):
            (ag / f).write_text((HARBOR / f).read_text(encoding="utf-8"), encoding="utf-8")
        (ag / "tasks-swerebench.txt").write_text("swe-a\n")
        (ag / "tasks-main.txt").write_text("tblite:t1\nswerebench:swe-a\n")
        for ds, names in (("tblite", ("t1", "t2")), ("swerebench", ("swe-a",))):
            for n in names:
                self.write(f"home/harbor-eval/datasets/{ds}/{n}/task.toml", '[metadata]\ndifficulty = "hard"\n')
        self.harbor("echo \"$@\" > \"$HOME/harbor-args.txt\"\nenv | sort > \"$HOME/harbor-env.txt\"\nsleep 6\n")
        self.env_file(f"CLAUDE_CODE_OAUTH_TOKEN={self.TOKEN}\n")
        self.addCleanup(shutil_rmtree, REPO / ".tmp" / "harbor-jobs" / "jobs" / self.LOCAL_JOB)

    def shim(self, name, body):
        p = self.bin / name
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(0o755)

    def harbor(self, body):
        p = self.rd / ".venv" / "bin" / "harbor"
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(0o755)

    def env_file(self, text, mode=0o600):
        p = self.rd / ".env"
        p.write_text(text)
        p.chmod(mode)

    def tuf(self, *args, extra_env=None):
        env = {"PATH": f"{self.bin}:{os.path.dirname(sys.executable)}:/usr/bin:/bin", "HARBOR_HOST": "fake",
               "HARBOR_WATCH_INTERVAL": "1", "HOME": os.environ.get("HOME", "/"),
               # 0: không kiểm ổ, watcher không dọn cache dựng của Docker (test chạy trên máy thật của bạn)
               "HARBOR_MIN_FREE_GB": "0", **(extra_env or {})}
        return subprocess.run(["sh", str(HARBOR / "tuf.sh"), *args], capture_output=True, text=True, timeout=120, env=env,
                              stdin=subprocess.DEVNULL)

    def args_file(self):
        return self.home / "harbor-args.txt"

    def test_run_uses_its_own_task_list_when_present(self):
        """run probe dùng tasks-probe.txt (lượt thử nhỏ), run main dùng tasks-main.txt."""
        (self.rd / "agent-stack" / "tasks-probe.txt").write_text("# thử\ntblite:t2\n")
        r = self.tuf("run", "probe", "--yes", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cfg = json.loads((self.rd / "configs" / "probe.json").read_text())
        names = sorted(n for d in cfg["datasets"] for n in d.get("task_names", []))
        self.assertEqual(names, ["t2"])
        self.assertEqual(len(cfg["agents"]), 4)
        r = self.tuf("run", "main")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cfg = json.loads((self.rd / "configs" / "main.json").read_text())
        self.assertEqual(sorted(n for d in cfg["datasets"] for n in d.get("task_names", [])), ["swe-a", "t1"])

    def test_run_with_a_missing_task_list_refuses_instead_of_falling_back_to_main(self):
        """Ca 06/11/2026: sync bị từ chối nên tasks-probe.txt chưa lên TUF, run probe lặng lẽ thành 388 lượt của main."""
        r = self.tuf("run", "probe", "--yes", "--force")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Chưa có tasks-probe.txt", r.stderr)
        self.assertFalse((self.rd / "configs" / "probe.json").exists())
        self.assertFalse(self.args_file().exists())

    def test_oracle_never_loads_env_and_pilot_does(self):
        self.env_file(f"CLAUDE_CODE_OAUTH_TOKEN={self.TOKEN}\nOTHER_KEY=hunter2value\n")      # oracle không đọc .env nên không bị chặn
        r = self.tuf("oracle", "--yes", "--force")
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-800:])
        self.assertIn("Đã chạy nền job pilot-oracle", r.stdout)
        args = self.args_file().read_text().split()
        self.assertEqual(args, ["run", "-c", "configs/pilot-oracle.json", "-q", "-y"])
        self.assertNotIn("--env-file", args)
        cfg = json.loads((self.rd / "configs" / "pilot-oracle.json").read_text())
        self.assertEqual(cfg["agents"], [{"name": "oracle"}])

    def test_model_job_loads_env_through_a_filtered_environment(self):
        r = self.tuf("pilot", "--yes", "--force", extra_env={"DECOY_SECRET": "not-for-containers", "AWS_SECRET_ACCESS_KEY": "zzz"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.args_file().read_text().split(), ["run", "-c", "configs/pilot.json", "--env-file", ".env", "-q", "-y"])
        env = (self.home / "harbor-env.txt").read_text()
        for needle in ("DECOY_SECRET", "AWS_SECRET_ACCESS_KEY", "not-for-containers", self.TOKEN, "OAUTH"):
            self.assertNotIn(needle, env)
        for needle in ("PATH=", "HOME=", "AGENT_STACK_PAYLOAD=", "PYTHONPATH="):
            self.assertIn(needle, env)
        self.assertTrue((self.rd / "jobs" / "pilot.watch.pid").is_file())
        self.assertTrue((self.rd / "jobs" / "pilot.meta.json").is_file())
        meta = json.loads((self.rd / "jobs" / "pilot.meta.json").read_text())
        self.assertEqual(meta["difficulty"]["t1"], "hard")

    def started_job(self, name):
        """Dựng jobs/<name> như sau khi Harbor dừng giữa chừng: config.json, bản chép agent-stack, log cũ."""
        (self.rd / "jobs" / name).mkdir(parents=True)
        (self.rd / "jobs" / name / "config.json").write_text("{}")
        (self.rd / "jobs" / f"{name}.payload" / "full").mkdir(parents=True)
        (self.rd / "jobs" / f"{name}.payload" / "full" / ".payload-commit").write_text("63b4e6d\n")
        (self.rd / "jobs" / f"{name}.log").write_text("log lần đầu\n")
        # python-dotenv giả: .venv/bin/python ở đây là python của máy, không có thư viện của Harbor
        (self.rd / "agent-stack" / "dotenv.py").write_text(
            "import os\ndef load_dotenv(path, override=False):\n    for ln in open(path):\n"
            "        k, _, v = ln.strip().partition('=')\n        if k and not k.startswith('#'):\n"
            "            os.environ[k] = v if override or k not in os.environ else os.environ[k]\n")

    def test_resume_continues_the_job_with_its_own_payload_and_loads_env_like_harbor_run(self):
        """Ca 09/11/2026: ổ đầy, Harbor dừng ở lượt 110/153; `harbor jobs resume` không có --env-file."""
        self.started_job("pilot")
        agent = {"import_path": "agent_stack_agents:ClaudeCodePlain"}
        (self.rd / "jobs" / "pilot" / "config.json").write_text(json.dumps({"agents": [{**agent, "env": {"CLAUDE_FORCE_OAUTH": "****"}}]}))
        (self.rd / "configs").mkdir(exist_ok=True)
        (self.rd / "configs" / "pilot.json").write_text(json.dumps({"agents": [{**agent, "env": {"CLAUDE_FORCE_OAUTH": "1"}}]}))
        r = self.tuf("resume", "pilot")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Chưa chạy. Thêm --yes", r.stdout)
        self.assertIn("****", (self.rd / "jobs" / "pilot" / "config.json").read_text())   # không --yes: không đụng gì
        self.assertFalse(self.args_file().exists())
        r = self.tuf("resume", "pilot", "--yes", "--force", extra_env={"DECOY_SECRET": "not-for-containers"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Đã chạy nền job pilot", r.stdout)
        self.assertIn("commit 63b4e6d", r.stdout)            # bản chép cũ của job, không chép lại từ agent-stack/payload
        self.assertEqual(self.args_file().read_text().split(), ["jobs", "resume", "-p", "jobs/pilot"])
        env = (self.home / "harbor-env.txt").read_text()
        self.assertIn(f"CLAUDE_CODE_OAUTH_TOKEN={self.TOKEN}", env)   # như harbor run sau load_dotenv(.env, override=True)
        self.assertNotIn("DECOY_SECRET", env)                 # vẫn sau env -i
        self.assertFalse((self.rd / "jobs" / "pilot.meta.json").exists())
        self.assertTrue((self.rd / "jobs" / "pilot.log").read_text().startswith("log lần đầu\n"))   # nối, không ghi đè
        cfg = json.loads((self.rd / "jobs" / "pilot" / "config.json").read_text())
        self.assertEqual(cfg["agents"][0]["env"], {"CLAUDE_FORCE_OAUTH": "1"})          # Harbor che thành ****
        self.assertIn("khôi phục giá trị env bị Harbor che", (self.rd / "jobs" / "pilot.log").read_text())

    def test_resume_of_an_oracle_job_never_loads_env_and_a_job_without_its_payload_is_refused(self):
        self.started_job("pilot-oracle")
        r = self.tuf("resume", "pilot-oracle", "--yes", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("OAUTH", (self.home / "harbor-env.txt").read_text())
        self.args_file().unlink()
        self.started_job("other")
        shutil_rmtree(self.rd / "jobs" / "other.payload")
        r = self.tuf("resume", "other", "--yes", "--force")
        self.assertEqual(r.returncode, 1)
        self.assertIn("jobs/other.payload", r.stderr)
        (self.rd / "jobs" / "pilot-oracle.stopped").write_text("Dừng: 4 lượt lỗi hạn mức\n")
        r = self.tuf("resume", "pilot-oracle", "--yes", "--force")
        self.assertEqual(r.returncode, 1)
        self.assertIn("đã bị watcher dừng vì lỗi hạn mức", r.stderr)
        r = self.tuf("resume", "never", "--yes", "--force")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Không thấy jobs/never/config.json", r.stderr)
        self.assertFalse(self.args_file().exists())

    def test_launch_refuses_when_the_disk_is_low_unless_forced(self):
        self.shim("df", 'printf "Avail\\n  12G\\n"\n')
        self.started_job("pilot")
        r = self.tuf("resume", "pilot", "--yes", extra_env={"HARBOR_MIN_FREE_GB": "30"})
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("còn 12 GB, dưới 30 GB", r.stderr)
        self.assertFalse(self.args_file().exists())
        r = self.tuf("resume", "pilot", "--yes", "--force", extra_env={"HARBOR_MIN_FREE_GB": "10"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("dưới", r.stderr)

    def test_env_with_any_other_key_or_env_local_is_refused_without_printing_values(self):
        self.env_file(f"CLAUDE_CODE_OAUTH_TOKEN={self.TOKEN}\n# ghi chú\n\nANTHROPIC_API_KEY=hunter2value\nraw-secret-line\n")
        self.started_job("resumed")
        for cmd in (("pilot", "--yes", "--force"), ("run", "--yes", "--force"), ("resume", "resumed", "--yes", "--force")):
            r = self.tuf(*cmd)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            out = r.stdout + r.stderr
            self.assertIn("2 dòng ngoài CLAUDE_CODE_OAUTH_TOKEN", out)
            self.assertIn("ANTHROPIC_API_KEY", out)
            for secret in ("hunter2value", "raw-secret-line", self.TOKEN):
                self.assertNotIn(secret, out)
            self.assertFalse(self.args_file().exists())
        self.env_file(f"CLAUDE_CODE_OAUTH_TOKEN={self.TOKEN}\n")
        (self.rd / ".env.local").write_text("X=1\n")
        self.started_job("resumed-oracle")
        for cmd in (("pilot", "--yes", "--force"), ("resume", "resumed", "--yes", "--force"),
                    ("resume", "resumed-oracle", "--yes", "--force")):    # oracle không qua require_token
            r = self.tuf(*cmd)
            self.assertEqual(r.returncode, 1, cmd)
            self.assertIn(".env.local", r.stderr)
            self.assertFalse(self.args_file().exists())

    def test_env_with_a_lone_carriage_return_hiding_a_second_key_is_refused(self):
        """Review vòng 1: python-dotenv tách dòng ở \\r đơn, grep thì không."""
        self.env_file(f"CLAUDE_CODE_OAUTH_TOKEN={self.TOKEN}\rOTHER_SECRET=xyzvalue\n")
        r = self.tuf("pilot", "--yes", "--force")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ký tự CR", r.stderr)
        self.assertNotIn("xyzvalue", r.stdout + r.stderr)
        self.assertFalse(self.args_file().exists())

    def test_oracle_refuses_env_local_too(self):
        (self.rd / ".env.local").write_text("X=1\n")
        r = self.tuf("oracle", "--yes", "--force")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(".env.local", r.stderr)
        self.assertFalse(self.args_file().exists())

    def test_wide_permissions_or_missing_token_are_refused(self):
        self.env_file(f"CLAUDE_CODE_OAUTH_TOKEN={self.TOKEN}\n", mode=0o644)
        r = self.tuf("pilot", "--yes", "--force")
        self.assertEqual(r.returncode, 1)
        self.assertIn("quyền 644", r.stderr)
        self.assertNotIn(self.TOKEN, r.stdout + r.stderr)
        self.env_file("")
        self.assertIn("Chưa có CLAUDE_CODE_OAUTH_TOKEN", self.tuf("pilot", "--yes", "--force").stderr)
        self.assertFalse(self.args_file().exists())

    def test_without_yes_nothing_is_launched_and_the_plan_is_printed(self):
        for cmd, what in ((("oracle",), "lời giải mẫu"), (("pilot",), "pilot"), (("run",), "job lớn")):
            r = self.tuf(*cmd)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("Chưa chạy. Thêm --yes", r.stdout)
            self.assertIn("Trần chi phí" if cmd != ("oracle",) else "Lời giải mẫu: không gọi model", r.stdout)
            self.assertFalse(self.args_file().exists(), cmd)
            self.assertFalse((self.rd / "jobs").exists() and any((self.rd / "jobs").glob("*.pid")), cmd)

    def test_job_dies_at_start_is_reported_and_stopped(self):
        self.harbor("exit 0\n")
        r = self.tuf("pilot", "--yes", "--force")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("harbor hay watcher không chạy sau khi khởi động", r.stderr)

    def test_data_sync_and_prune_refuse_while_a_job_is_running(self):
        sleeper = subprocess.Popen(["sleep", "60"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait()))
        (self.rd / "jobs").mkdir()
        (self.rd / "jobs" / "main.pid").write_text(f"{sleeper.pid}\n")
        for cmd in ("data", "sync", "prune"):
            r = self.tuf(cmd, "--force")
            self.assertEqual(r.returncode, 3, (cmd, r.stdout, r.stderr))
            self.assertIn("Còn job đang chạy", r.stderr)
        r = self.tuf("pilot", "--yes", "--force")      # job khác cũng không được khởi động chồng lên
        self.assertEqual(r.returncode, 3)
        self.assertFalse(self.args_file().exists())
        # pid cũ đã chết thì không chặn
        dead = subprocess.Popen(["true"])
        dead.wait()
        (self.rd / "jobs" / "main.pid").write_text(f"{dead.pid}\n")
        r = self.tuf("prune", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Chưa xóa", r.stdout)

    def test_fetch_keeps_short_lookalikes_masks_real_keys_and_rescans_on_the_mac(self):
        job = self.rd / "jobs" / self.LOCAL_JOB
        trial = job / "t1__abc"
        (trial / "agent").mkdir(parents=True)
        (trial / "result.json").write_text(json.dumps({"task_name": "org/t1", "agent_info": {"name": B.PLAIN}}))
        (trial / "agent" / "claude-code.txt").write_text(
            f'{{"type":"user","content":"đọc sk-ant-xxx trong README; khóa thật {self.TOKEN} và CLAUDE_CODE_OAUTH_TOKEN=abcdefgh12345678"}}\n')
        (self.rd / "jobs" / f"{self.LOCAL_JOB}.meta.json").write_text(json.dumps({"claude_code": VER}))
        r = self.tuf("fetch", self.LOCAL_JOB)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        local = REPO / ".tmp" / "harbor-jobs" / "jobs" / self.LOCAL_JOB
        self.assertTrue((local / "t1__abc" / "result.json").is_file(), "bản kéo về không được xóa chỉ vì chuỗi sk-ant-xxx ngắn")
        text = (local / "t1__abc" / "agent" / "claude-code.txt").read_text()
        self.assertIn("sk-ant-xxx", text)
        self.assertNotIn(self.TOKEN, text)
        self.assertNotIn("abcdefgh12345678", text)
        self.assertTrue((local / "bench-meta.json").is_file())

    def test_oracle_recheck_runs_only_the_recheck_list_and_refuses_an_empty_one(self):
        (self.rd / "agent-stack" / "tasks-recheck.txt").write_text("# chờ chạy lại\ntblite:t2\n")
        r = self.tuf("oracle", "recheck", "--yes", "--force")
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-800:])
        cfg = json.loads((self.rd / "configs" / "recheck-oracle.json").read_text())
        self.assertEqual(cfg["datasets"], [{"path": "datasets/tblite", "task_names": ["t2"]}])
        self.assertEqual(cfg["agents"], [{"name": "oracle"}])
        self.assertEqual(cfg["retry"]["max_retries"], 2)
        # chạy lần hai: kết quả lần đầu giữ nguyên (filter gộp mọi jobs/*-oracle), job mới tên recheck2-oracle, cùng danh sách
        (self.rd / "jobs" / "recheck-oracle").mkdir(parents=True, exist_ok=True)
        pids = [int((self.rd / "jobs" / f"recheck-oracle{x}.pid").read_text()) for x in ("", ".watch")]
        for _ in range(100):                      # harbor giả chạy 6 giây; job còn chạy thì tuf.sh từ chối job mới
            if not any(B.pid_alive(p) for p in pids):
                break
            time.sleep(0.2)
        r = self.tuf("oracle", "recheck", "--yes", "--force")
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-800:])
        self.assertIn("Đã chạy nền job recheck2-oracle", r.stdout)
        cfg = json.loads((self.rd / "configs" / "recheck2-oracle.json").read_text())
        self.assertEqual(cfg["datasets"], [{"path": "datasets/tblite", "task_names": ["t2"]}])
        (self.rd / "agent-stack" / "tasks-recheck.txt").write_text("# không còn việc nào chờ\n")
        for p in self.rd.glob("jobs/recheck-oracle*"):
            shutil_rmtree(p) if p.is_dir() else p.unlink()
        r = self.tuf("oracle", "recheck", "--yes", "--force")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("tasks-recheck.txt không có việc nào", r.stderr)

    def test_filter_writes_both_lists_next_to_the_script(self):
        """Chạy bản chép của tuf.sh trong thư mục tạm: filter ghi tasks-main.txt cạnh script, không đụng file thật của repo."""
        here = self.tmp / "repo" / "evals" / "harbor"
        here.mkdir(parents=True)
        (here / "tuf.sh").write_text((HARBOR / "tuf.sh").read_text(encoding="utf-8"))
        (self.rd / "agent-stack" / "tasks-candidates.txt").write_text("tblite:t1\ntblite:t2\nswerebench:swe-a\n")
        for task, reward, exc in (("t1", 1.0, None), ("t2", 0.0, None), ("swe-a", None, "RuntimeError")):
            d = self.rd / "jobs" / "pilot-oracle" / f"{task}__abc1234"
            d.mkdir(parents=True)
            (d / "result.json").write_text(json.dumps({
                "task_name": f"org/{task}", "agent_info": {"name": "oracle"},
                "verifier_result": None if reward is None else {"rewards": {"reward": reward}},
                "exception_info": {"exception_type": exc} if exc else None}))
        env = {"PATH": f"{self.bin}:{os.path.dirname(sys.executable)}:/usr/bin:/bin", "HARBOR_HOST": "fake",
               "HOME": os.environ.get("HOME", "/")}
        r = subprocess.run(["sh", str(here / "tuf.sh"), "filter"], capture_output=True, text=True, timeout=60, env=env,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(B.read_task_spec(here / "tasks-main.txt"), {"tblite": ["t1"]})
        self.assertEqual(B.read_task_spec(here / "tasks-recheck.txt"), {"swerebench": ["swe-a"]})
        self.assertIn("pilot-oracle", (here / "tasks-main.txt").read_text())

    def test_prune_removes_only_what_harbor_left_behind(self):
        log = self.tmp / "docker.log"
        self.shim("docker", f"""echo "$*" >> {log}
case "$1 $2" in
  "ps -q") ;;
  "ps -a") printf '%s\\n' astronomy-commons__lsdb-1349__ecvqc4a__env-main-1 pi-agent-llama other_db_1 ;;
  "images --format") printf '%s\\n' security-incident-log-analysis__xeiq2xd__env-main:latest swerebench/sweb.eval.x86_64.a:latest debian:trixie myproject__env-main:latest ;;
  "system df") echo "Build Cache: 22.91GB" ;;
  "network ls") printf '%s\\n' bridge astronomy-commons__lsdb-1349__ecvqc4a__env_default pi-agent_default ;;
  "builder prune") echo "Total reclaimed space: 22.91GB" ;;
esac
""")
        r = self.tuf("prune", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Container Harbor bỏ lại (kèm network của chúng): 1 · image (swerebench/sweb.eval*, image dựng của Harbor): 2", r.stdout)
        self.assertIn("Chưa xóa", r.stdout)
        self.assertNotIn("rmi", log.read_text())
        r = self.tuf("prune", "--yes", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = log.read_text().splitlines()
        self.assertIn("rm -f astronomy-commons__lsdb-1349__ecvqc4a__env-main-1", calls)
        self.assertIn("rmi security-incident-log-analysis__xeiq2xd__env-main:latest swerebench/sweb.eval.x86_64.a:latest", calls)
        self.assertIn("builder prune -a -f", calls)
        self.assertIn("network rm astronomy-commons__lsdb-1349__ecvqc4a__env_default", calls)
        for keep in ("pi-agent-llama", "other_db_1", "debian:trixie", "myproject__env-main", "pi-agent_default", "bridge"):
            self.assertFalse(any(keep in c for c in calls if c.startswith(("rm ", "rmi ", "network rm"))), keep)

    def test_data_vi_gathers_the_synced_vietnamese_set_locks_and_vets_it(self):
        ag = self.rd / "agent-stack"
        src = HARBOR.parent / "vi-bench" / "code-phi-ship"
        import shutil
        shutil.copytree(src, ag / "vi-bench" / "code-phi-ship")
        shutil.copytree(src, ag / "vi-bench" / "code-xau")
        (ag / "vi-bench" / "code-xau" / "environment" / "docker-compose.yaml").write_text("services: {}\n")
        (ag / "vi-bench" / "_lib").mkdir()
        (ag / "vi-bench" / "selftest.py").write_text("# không phải bài\n")
        self.harbor("echo harbor download không được gọi >&2; exit 9\n")
        r = self.tuf("data", "vi", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(p.name for p in (self.rd / "datasets" / "vi").iterdir()), ["code-phi-ship"])  # bài có compose bị loại
        lock = json.loads((self.rd / "datasets" / "vi.lock.json").read_text())
        self.assertEqual(lock.get("ref"), "abc1234")
        self.assertTrue((self.rd / "datasets" / "vi.rejected.txt").is_file())
        # chạy lại sau khi bài đổi (commit mới): lock được ghi lại, không báo lệch mã băm
        (ag / "vi-bench" / "code-phi-ship" / "instruction.md").write_text("Đề đã sửa.\n")
        r = self.tuf("data", "vi", "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(json.loads((self.rd / "datasets" / "vi.lock.json").read_text())["sha256"], lock["sha256"])

    def test_status_filters_the_log_it_prints(self):
        (self.rd / "jobs" / "main").mkdir(parents=True)
        (self.rd / "jobs" / "main.log").write_text(f"bắt đầu\n\x1b[31mđỏ\x1b[0m khóa {self.TOKEN}\n\x1b]0;giả\x07xong\n")
        r = self.tuf("status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(self.TOKEN, r.stdout)
        self.assertNotIn("\x1b", r.stdout)
        self.assertIn("harbor: không thấy main.pid", r.stdout)
        self.assertIn("xong", r.stdout)


def shutil_rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


class SerialBuildEnvTests(TempDirTestCase):
    """serial_build_env.py import harbor: thay mô-đun harbor bằng bản giả rồi chạy thật trong asyncio."""

    def load(self):
        import asyncio
        import types
        state = {"now": 0, "max_build": 0, "max_all": 0, "calls": []}

        class FakeDocker:
            async def _run_docker_compose_command(self, command, check=True, timeout_sec=None):
                key = "build" if command[0] == "build" else "other"
                state["calls"].append(command[0])
                if key == "build":
                    state.setdefault("build_timeouts", []).append(timeout_sec)
                state["now"] += 1
                state["max_all"] = max(state["max_all"], state["now"])
                state.setdefault(key + "_now", 0)
                state[key + "_now"] += 1
                state["max_build"] = max(state["max_build"], state.get("build_now", 0))
                await asyncio.sleep(0.05)
                state[key + "_now"] -= 1
                state["now"] -= 1
                if command[0] == "build" and command[-1] == "boom":
                    raise RuntimeError("failed to solve")
                return (command, check, timeout_sec)

        mods = {}
        for name in ("harbor", "harbor.environments", "harbor.environments.docker", "harbor.environments.docker.docker"):
            mods[name] = types.ModuleType(name)
        mods["harbor.environments.docker.docker"].DockerEnvironment = FakeDocker
        spec = importlib.util.spec_from_file_location("serial_build_env_test", HARBOR / "serial_build_env.py")
        mod = importlib.util.module_from_spec(spec)
        with unittest.mock.patch.dict(sys.modules, mods):
            spec.loader.exec_module(mod)
        return mod, state

    def test_only_one_build_runs_at_a_time_while_other_compose_commands_overlap(self):
        import asyncio
        mod, state = self.load()
        envs = [mod.SerialBuildDockerEnvironment() for _ in range(3)]

        async def main():
            r = await asyncio.gather(*(e._run_docker_compose_command(["build"]) for e in envs),
                                     *(e._run_docker_compose_command(["up", "-d"], check=False) for e in envs))
            # lần dựng hỏng nhả khóa: lần dựng sau vẫn chạy được
            with self.assertRaises(RuntimeError):
                await envs[0]._run_docker_compose_command(["build", "boom"])
            await asyncio.wait_for(envs[1]._run_docker_compose_command(["build"]), 2)
            return r

        res = asyncio.run(main())
        self.assertEqual(state["max_build"], 1)
        self.assertEqual(state["build_timeouts"][:3], [1200, 1200, 1200])   # 2 × hạn dựng mặc định 600 của Harbor
        self.assertGreaterEqual(state["max_all"], 3)        # up -d của các lượt khác vẫn chạy song song
        self.assertEqual(res[3], (["up", "-d"], False, None))  # tham số đi nguyên vào lớp cha
        self.assertEqual(state["calls"].count("build"), 5)

    def test_a_build_gets_its_own_deadline_from_the_task_unless_the_caller_set_one(self):
        """Dựng treo phải nhả khóa: Harbor chỉ dừng `docker compose build` khi chính lệnh hết hạn, không khi lượt bị hủy."""
        import asyncio
        import types
        mod, state = self.load()
        env = mod.SerialBuildDockerEnvironment()
        env.task_env_config = types.SimpleNamespace(build_timeout_sec=1800.0)

        async def main():
            await env._run_docker_compose_command(["build"])
            await env._run_docker_compose_command(["build"], timeout_sec=60)
            await env._run_docker_compose_command(["build"], True, 30)
            return await env._run_docker_compose_command(["up"])

        self.assertEqual(asyncio.run(main()), (["up"], True, None))      # lệnh khác không bị gắn hạn
        self.assertEqual(state["build_timeouts"], [3600, 60, 30])

    def test_harbor_bench_points_the_job_at_this_class(self):
        mod, _ = self.load()
        path = B.SERIAL_ENV["import_path"]
        self.assertEqual(path.split(":")[0], "serial_build_env")
        self.assertTrue(hasattr(mod, path.split(":")[1]))
        self.assertIn('"$HERE/serial_build_env.py"', (HARBOR / "tuf.sh").read_text(encoding="utf-8"))   # sync đưa lên TUF


class AgentInstallTests(TempDirTestCase):
    """_Probed.install với ClaudeCode giả (agent_stack_agents.py import harbor): cài lại một lần đi thẳng, rồi báo lỗi hạ
    tầng. Ca 08/11/2026: apt-cacher-ng giữ InRelease ghép lẫn hai bản, 13/25 lượt đầu pilot hỏng ở apt BADSIG."""

    def load(self, outcomes):
        import types
        calls = []

        class FakeClaudeCode:
            async def exec_as_root(self, environment, command, env=None):
                calls.append(("root", command))

            async def exec_as_agent(self, environment, command, env=None):
                calls.append(("agent", command))

            async def install(self, environment):
                calls.append(("install", None))
                out = outcomes.pop(0)
                if isinstance(out, BaseException):
                    raise out

        mods = {n: types.ModuleType(n) for n in
                ("harbor", "harbor.agents", "harbor.agents.installed", "harbor.agents.installed.claude_code")}
        mods["harbor.agents.installed.claude_code"].ClaudeCode = FakeClaudeCode
        spec = importlib.util.spec_from_file_location("agent_stack_agents_test", HARBOR / "agent_stack_agents.py")
        mod = importlib.util.module_from_spec(spec)
        with unittest.mock.patch.dict(sys.modules, mods):
            spec.loader.exec_module(mod)
        mod.INSTALL_RETRY_WAIT = 0
        return mod, calls

    def run_install(self, outcomes):
        import asyncio
        mod, calls = self.load(outcomes)
        agent = mod.ClaudeCodePlain.__new__(mod.ClaudeCodePlain)
        try:
            asyncio.run(agent.install(object()))
            return mod, calls, None
        except BaseException as e:      # noqa: BLE001 - test cần cả CancelledError
            return mod, calls, e

    def kinds(self, mod, calls):
        return [k if k == "install" else ("go-direct" if c == mod.APT_GO_DIRECT else "root") for k, c in calls]

    def test_working_install_runs_once_and_keeps_the_cache(self):
        mod, calls, err = self.run_install([None])
        self.assertIsNone(err)
        self.assertEqual(self.kinds(mod, calls), ["root", "root", "install"])

    def test_failed_install_bypasses_the_cache_and_retries_once_directly(self):
        mod, calls, err = self.run_install([RuntimeError("Command failed (exit 100): apt-get update ... BADSIG"), None])
        self.assertIsNone(err)
        self.assertEqual(self.kinds(mod, calls), ["root", "root", "install", "go-direct", "install"])

    def test_two_failed_installs_raise_an_infra_error_that_harbor_retries(self):
        long = "x" * 5000
        mod, calls, err = self.run_install([RuntimeError("Command failed (exit 100): " + long + " BADSIG"),
                                            RuntimeError("timed out")])
        self.assertIsInstance(err, mod.AgentInstallError)
        self.assertIn(type(err).__name__, B.INFRA_RETRY)          # Harbor so đúng tên lớp
        self.assertIn("BADSIG", str(err))
        self.assertIn("timed out", str(err))
        self.assertLess(len(str(err)), 1500)                       # đầu ra apt dài bị cắt
        self.assertEqual(self.kinds(mod, calls), ["root", "root", "install", "go-direct", "install"])

    def test_setup_timeout_cancellation_is_not_swallowed_or_retried(self):
        import asyncio
        mod, calls, err = self.run_install([asyncio.CancelledError()])
        self.assertIsInstance(err, asyncio.CancelledError)
        self.assertEqual(self.kinds(mod, calls), ["root", "root", "install"])

    def test_go_direct_removes_the_proxy_and_partial_downloads_but_keeps_the_package_lists(self):
        mod, _ = self.load([])
        # hoàn tất dpkg dở trước khi gỡ proxy và cài lại
        self.assertLess(mod.APT_GO_DIRECT.index("dpkg --configure -a"), mod.APT_GO_DIRECT.index("rm -f"))
        root = self.tmp
        conf = root / "etc/apt/apt.conf.d"
        lists = root / "var/lib/apt/lists"
        (lists / "partial").mkdir(parents=True)
        conf.mkdir(parents=True)
        (conf / "99agent-stack-proxy").write_text('Acquire::http::Proxy "http://172.17.0.1:3142";\n')
        (conf / "99agent-stack-no-pipelining").write_text("x")
        (lists / "deb.debian.org_debian_dists_bookworm-updates_InRelease").write_text("hỏng")
        (lists / "partial" / "x_InRelease").write_text("dở")
        (lists / "lock").write_text("")
        cmd = (mod.APT_GO_DIRECT.replace("/etc/apt", str(root / "etc/apt")).replace("/var/lib/apt", str(root / "var/lib/apt"))
               .replace("dpkg ", "true "))                     # không chạy dpkg thật của máy test
        r = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((conf / "99agent-stack-proxy").exists())
        self.assertTrue((conf / "99agent-stack-no-pipelining").exists())
        # danh sách gói giữ lại: lần cài hai có thể không chạy apt-get update, agent vẫn phải cài được gói
        self.assertEqual(sorted(p.name for p in lists.iterdir()),
                         ["deb.debian.org_debian_dists_bookworm-updates_InRelease", "lock", "partial"])
        self.assertEqual(list((lists / "partial").iterdir()), [])
        r = subprocess.run(["sh", "-c", cmd.replace(str(root), str(root / "khong-co"))], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)                          # image không có apt: vẫn thoát 0


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

    def test_every_arm_turns_off_apt_pipelining_before_installing_claude_code(self):
        """Ca 06/11/2026: apt trong container chậm 49 kB/s và hỏng hash khi pipelining; tắt nó cho cả bốn cấu hình."""
        probed = self.classes["_Probed"]
        install = next(n for n in probed.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "install")
        calls = [n for n in ast.walk(install) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in
                 ("exec_as_root", "install")]
        # tắt trước, rồi mới cài; lần cài thứ hai (đi thẳng) chỉ khi lần đầu hỏng: AgentInstallTests chạy thật nhánh đó
        self.assertEqual([c.func.attr for c in calls], ["exec_as_root", "exec_as_root", "install", "exec_as_root", "install"])
        self.assertEqual(ast.unparse(calls[1].keywords[0].value), "APT_PREINSTALL")
        cmd = ast.literal_eval(next(k.value for k in calls[0].keywords if k.arg == "command"))
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "apt.conf.d"
            conf.mkdir()
            r = subprocess.run(["sh", "-c", cmd.replace("/etc/apt/apt.conf.d", str(conf))], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((conf / "99agent-stack-no-pipelining").read_text(), 'Acquire::http::Pipeline-Depth "0";\n')
            r = subprocess.run(["sh", "-c", cmd.replace("/etc/apt/apt.conf.d", str(Path(tmp) / "khong-co"))])
            self.assertEqual(r.returncode, 0)                                          # image không có apt: bỏ qua
        bases = {name: [b.id for b in c.bases] for name, c in self.classes.items()}
        self.assertEqual(bases["ClaudeCodePlain"], ["_Probed"])
        self.assertEqual(bases["ClaudeCodeAgentStack"], ["_Probed"])

    def test_apt_uses_the_host_cache_only_when_the_gateway_answers(self):
        """Ca 07/11/2026: tải từ deb.debian.org lúc chỉ 181 kB/s; dùng apt-cacher-ng qua gateway, không tới được thì
        đi thẳng."""
        import socket
        probed = self.classes["_Probed"]
        install = next(n for n in probed.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "install")
        call = next(n for n in ast.walk(install) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") ==
                    "exec_as_root")
        cmd = ast.literal_eval(next(k.value for k in call.keywords if k.arg == "command"))
        self.assertEqual(cmd.count("/proc/net/route"), 1)
        self.assertEqual(cmd.count("3142"), 2)                     # cổng thử và cổng ghi vào cấu hình
        for weak in ("AllowInsecure", "allow-unauthenticated", "AllowUnauthenticated", "Verify-Peer"):
            self.assertNotIn(weak, cmd + self.preinstall_script())  # không nới kiểm chữ ký gói
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(4)
            port = str(srv.getsockname()[1])
            route = Path(tmp) / "route"
            route.write_text("Iface\tDestination\tGateway \tFlags\n"
                             "eth0\t00000000\t0100007F\t0003\n"            # gateway 127.0.0.1, little-endian
                             "eth0\t000012AC\t00000000\t0001\n")
            conf = Path(tmp) / "apt.conf.d"
            conf.mkdir()

            def run(p):
                c = (cmd.replace("/etc/apt/apt.conf.d", str(conf)).replace("/proc/net/route", str(route))
                     .replace("3142", p))
                return subprocess.run(["sh", "-c", c], capture_output=True, text=True, timeout=30)

            r = run(port)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((conf / "99agent-stack-proxy").read_text(), f'Acquire::http::Proxy "http://127.0.0.1:{port}";\n')
            (conf / "99agent-stack-proxy").unlink()
            srv.close()                                                   # cổng đóng: apt đi thẳng
            r = run(port)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((conf / "99agent-stack-proxy").exists())
            self.assertTrue((conf / "99agent-stack-no-pipelining").exists())
            route.write_text("Iface\tDestination\tGateway \tFlags\n")      # không có tuyến mặc định
            r = run(port)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((conf / "99agent-stack-proxy").exists())
        self.assertIn("apt_proxy=", self.src)                             # mỗi lượt ghi lại có dùng bộ đệm không

    def preinstall_script(self):
        node = next(n for n in self.tree.body if isinstance(n, ast.Assign) and
                    getattr(n.targets[0], "id", "") == "APT_PREINSTALL")
        return ast.literal_eval(node.value)

    @staticmethod
    def isolated_bin(tmp, fakes):
        """PATH riêng: chỉ công cụ script cần và lệnh giả, để node hay curl có sẵn trên máy không đổi kết quả."""
        import shutil
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir()
        for tool in ("sleep", "find", "tail", "rm", "cat", "awk", "cut"):
            (bin_dir / tool).symlink_to(shutil.which(tool))
        for name, body in fakes.items():
            (bin_dir / name).write_text("#!/bin/sh\n" + body)
            (bin_dir / name).chmod(0o755)
        return bin_dir

    def run_preinstall(self, tmp, apt_body, present=()):
        """Chạy APT_PREINSTALL với apt-get và dpkg giả; trả về các lệnh apt-get đã gọi, stderr, thư mục cấu hình apt."""
        log = Path(tmp) / "apt.log"
        conf = Path(tmp) / "apt.conf.d"
        conf.mkdir()
        (conf / "99agent-stack-proxy").write_text('Acquire::http::Proxy "http://172.18.0.1:3142";\n')
        fakes = {"apt-get": f'echo "$*" >> {log}\n' + apt_body, "dpkg": "exit 0\n"}
        fakes.update({name: "exit 0\n" for name in present})
        bin_dir = self.isolated_bin(tmp, fakes)
        cmd = (self.preinstall_script().replace("wd_update=90", "wd_update=1").replace("wd_install=300", "wd_install=1")
               .replace("/var/lib/apt", f"{tmp}/lib-apt").replace("/var/cache/apt", f"{tmp}/cache-apt")
               .replace("/etc/apt/apt.conf.d", str(conf)).replace("/tmp/agent-stack-apt.log", f"{tmp}/out.log"))
        started = time.monotonic()
        r = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True, text=True, timeout=60,
                           env={"PATH": str(bin_dir)})
        self.assertEqual(r.returncode, 0, r.stderr)                       # luôn thoát 0: Harbor còn tự cài sau
        self.assertLess(time.monotonic() - started, 15)
        calls = log.read_text().splitlines() if log.exists() else []
        return calls, r.stderr, conf

    HANG_FIRST_UPDATE = ('if [ "$1" = update ] && [ ! -e "$0.da-treo" ]; then : > "$0.da-treo"; exec sleep 30; fi\n'
                         'exit 0\n')

    def test_preinstall_kills_a_hung_apt_update_then_retries_without_the_cache(self):
        """Ca 07/11/2026: apt-get update chờ mãi tệp InRelease 0 byte từ bộ đệm; hẹn giờ, bỏ bộ đệm, thử lại."""
        with tempfile.TemporaryDirectory() as tmp:
            calls, err, conf = self.run_preinstall(tmp, self.HANG_FIRST_UPDATE)
            self.assertFalse((conf / "99agent-stack-proxy").exists())      # lần 2 và bước cài của Harbor đi thẳng
        self.assertEqual(calls, ["update", "update", "install -y -o DPkg::Lock::Timeout=60 curl bash nodejs npm procps"])
        self.assertIn("apt lần 1", err)

    def test_preinstall_gives_up_after_two_hung_installs_and_still_exits_zero(self):
        body = 'if [ "$1" = install ]; then exec sleep 30; fi\nexit 0\n'
        with tempfile.TemporaryDirectory() as tmp:
            calls, err, _ = self.run_preinstall(tmp, body)
        self.assertEqual([c.split()[0] for c in calls], ["update", "install", "update", "install"])
        self.assertIn("apt lần 2", err)

    def test_preinstall_installs_only_missing_tools_and_keeps_the_cache_when_apt_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls, _, conf = self.run_preinstall(tmp, "exit 0\n", present=("node", "npm"))
            self.assertTrue((conf / "99agent-stack-proxy").exists())
        self.assertEqual(calls, ["update", "install -y -o DPkg::Lock::Timeout=60 curl bash procps"])
        with tempfile.TemporaryDirectory() as tmp:
            calls, _, _ = self.run_preinstall(tmp, "exit 0\n", present=("curl", "bash", "node", "npm", "pgrep"))
        self.assertEqual(calls, [])                                       # Harbor cũng bỏ qua: không cài lại

    def test_proxy_probe_gives_up_after_three_seconds_when_the_gateway_hangs(self):
        probed = self.classes["_Probed"]
        install = next(n for n in probed.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "install")
        call = next(n for n in ast.walk(install) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") ==
                    "exec_as_root")
        cmd = ast.literal_eval(next(k.value for k in call.keywords if k.arg == "command"))
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = self.isolated_bin(tmp, {"bash": "exec sleep 30\n"})   # kết nối treo, không ai trả lời
            route = Path(tmp) / "route"
            route.write_text("Iface\tDestination\tGateway \tFlags\neth0\t00000000\t0100007F\t0003\n")
            conf = Path(tmp) / "apt.conf.d"
            conf.mkdir()
            c = cmd.replace("/etc/apt/apt.conf.d", str(conf)).replace("/proc/net/route", str(route))
            started = time.monotonic()
            r = subprocess.run(["/bin/sh", "-c", c], capture_output=True, text=True, timeout=60,
                               env={"PATH": str(bin_dir)})
            elapsed = time.monotonic() - started
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((conf / "99agent-stack-proxy").exists())
            self.assertTrue((conf / "99agent-stack-no-pipelining").exists())
        self.assertGreaterEqual(elapsed, 2.5)                             # đúng là chờ hẹn giờ
        self.assertLess(elapsed, 10)

    def test_uses_only_harbor_api_verified_at_v0_25_0(self):
        for needle in ("exec_as_agent", "exec_as_root", "environment_logs_dir", "upload_dir", "build_cli_flags",
                       "from harbor.agents.installed.claude_code import ClaudeCode"):
            self.assertIn(needle, self.src)
        self.assertIn("agent-stack-env.txt", self.src)
        self.assertIn("python3", self.src)

    def test_env_file_keys_match_what_compare_reads(self):
        for key in ("variant=", "python3=", "payload_commit=", "user_claude_md=", "config_claude_md=", "plugin_dir=",
                    "hooks_json=", "agents_dir="):
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
