"""Test cho evals/harbor/harbor_bench.py (sinh cấu hình job Harbor, so ghép cặp kết quả) và tuf.sh (phần không cần ssh)."""
import importlib.util
import json
import subprocess
import unittest

from tests._util import REPO, TempDirTestCase, run_script

HARBOR = REPO / "evals" / "harbor"
SCRIPT = HARBOR / "harbor_bench.py"
_spec = importlib.util.spec_from_file_location("harbor_bench", SCRIPT)
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

INIT_STACK = json.dumps({"type": "system", "subtype": "init", "plugins": [{"name": "agent-stack"}]})
INIT_PLAIN = json.dumps({"type": "system", "subtype": "init", "plugins": []})


class HarborBenchTests(TempDirTestCase):
    def trial(self, job, agent, task, reward=1.0, exception=None, cost=0.1, init=None, n=0):
        """Một lượt giả đúng cấu trúc result.json của Harbor 0.25."""
        d = self.tmp / job / f"{task}__{agent}{n}"
        res = {"task_name": task, "agent_info": {"name": agent},
               "verifier_result": None if reward is None else {"rewards": {"reward": reward}},
               "agent_result": {"n_input_tokens": 1000, "n_cache_tokens": 500, "n_output_tokens": 200,
                                "cost_usd": cost},
               "exception_info": {"exception_type": exception} if exception else None,
               "agent_execution": {"started_at": "2026-10-30T10:00:00Z", "finished_at": "2026-10-30T10:01:30Z"}}
        self.write(f"{job}/{d.name}/result.json", json.dumps(res))
        if init is not None:
            self.write(f"{job}/{d.name}/agent/claude-code.txt", '{"type":"other"}\n' + init + "\n")
        return d

    # ---------------------------------------------------------------- make-configs

    def test_configs_run_both_arms_in_one_job_and_oracle_on_the_same_tasks(self):
        tasks = self.write("tasks-x.txt", "# chú thích\nviec-a\n\nviec-b  # ghi chú cuối dòng\n")
        out = self.tmp / "cfg"
        r = run_script(SCRIPT, "make-configs", "--tasks", str(tasks), "--name", "x", "--attempts", "2",
                       "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        bench = json.loads((out / "x.json").read_text())
        oracle = json.loads((out / "x-oracle.json").read_text())
        self.assertEqual(bench["datasets"][0]["task_names"], ["viec-a", "viec-b"])
        self.assertEqual(oracle["datasets"], bench["datasets"])
        self.assertEqual((bench["job_name"], bench["n_attempts"], oracle["job_name"]), ("x", 2, "x-oracle"))
        self.assertEqual(oracle["agents"], [{"name": "oracle"}])
        plain, stack = bench["agents"]
        self.assertEqual(plain["import_path"], "agent_stack_agents:ClaudeCodePlain")
        self.assertEqual(stack["import_path"], "agent_stack_agents:ClaudeCodeAgentStack")
        # hai bản chỉ khác lớp agent và biến tắt việc nền của agent-stack
        for key in ("model_name", "kwargs"):
            self.assertEqual(plain[key], stack[key])
        self.assertEqual(plain["kwargs"]["version"], stack["kwargs"]["version"])
        self.assertEqual(set(stack["env"]) - set(plain["env"]), {"AGENT_STACK_NO_BACKGROUND"})
        # token không bao giờ nằm trong cấu hình
        self.assertNotIn("TOKEN", json.dumps(bench).upper().replace("MAX_TOKENS", ""))

    def test_task_file_must_be_non_empty_and_unique(self):
        for text in ("# chỉ có chú thích\n", "a\nb\na\n"):
            with self.subTest(text=text):
                tasks = self.write("t.txt", text)
                r = run_script(SCRIPT, "make-configs", "--tasks", str(tasks), "--name", "x", "--out",
                               str(self.tmp / "o"))
                self.assertNotEqual(r.returncode, 0)

    def test_pilot_task_list_is_twenty_unique_names(self):
        names = B.read_tasks(HARBOR / "tasks-pilot.txt")
        self.assertEqual(len(names), 20)

    # ---------------------------------------------------------------- compare

    def test_exact_mcnemar(self):
        self.assertEqual(B.exact_binomial_p(0, 0), 1.0)
        self.assertAlmostEqual(B.exact_binomial_p(0, 6), 0.03125)
        self.assertAlmostEqual(B.exact_binomial_p(6, 0), 0.03125)
        self.assertAlmostEqual(B.exact_binomial_p(2, 3), 1.0)
        self.assertAlmostEqual(B.exact_binomial_p(1, 9), 0.021484375)

    def test_pairs_by_task_and_counts_wins_and_losses(self):
        P, S = B.PLAIN, B.STACK
        for task, a, b in (("t1", 1, 1), ("t2", 1, 0), ("t3", 0, 1), ("t4", 0, 0), ("t5", 1, 0)):
            self.trial("job", P, task, reward=float(a), init=INIT_PLAIN)
            self.trial("job", S, task, reward=float(b), init=INIT_STACK)
        res = B.compare(B.load_trials([self.tmp / "job"]))
        self.assertEqual(res["pairs"], 5)
        self.assertEqual(res["worse"], ["t2", "t5"])
        self.assertEqual(res["better"], ["t3"])
        self.assertAlmostEqual(res["p_value"], B.exact_binomial_p(2, 1))
        self.assertAlmostEqual(res["a"]["pass_rate"], 0.6)
        self.assertAlmostEqual(res["b"]["pass_rate"], 0.4)
        self.assertEqual(res["b"]["loaded"], [True] * 5)
        self.assertEqual(res["a"]["loaded"], [False] * 5)
        self.assertEqual(res["a"]["seconds"]["median"], 90)
        text = B.report(res)
        self.assertIn("kém hơn ở 2 việc, tốt hơn ở 1 việc", text)
        self.assertIn("nạp plugin ở 5/5 lượt", text)
        self.assertNotIn("⚠️", text)

    def test_oracle_failures_and_ungraded_trials_drop_the_pair(self):
        P, S = B.PLAIN, B.STACK
        for task in ("ok", "bad-grader", "env-broken", "timeout"):
            self.trial("job", P, task, reward=1.0)
        self.trial("job", S, "ok", reward=1.0)
        self.trial("job", S, "bad-grader", reward=0.0)
        self.trial("job", S, "env-broken", reward=None, exception="EnvironmentStartTimeoutError")
        # hết giờ mà grader vẫn chấm: là kết quả thật của bản đó, giữ cặp
        self.trial("job", S, "timeout", reward=0.0, exception="AgentTimeoutError")
        for task, reward in (("ok", 1.0), ("bad-grader", 0.0), ("env-broken", 1.0), ("timeout", 1.0)):
            self.trial("oracle", "oracle", task, reward=reward)
        res = B.compare(B.load_trials([self.tmp / "job"]), B.load_trials([self.tmp / "oracle"]))
        self.assertEqual([r["task"] for r in res["rows"]], ["ok", "timeout"])
        why = dict(res["excluded"])
        self.assertEqual(why["bad-grader"], "lời giải mẫu không đạt")
        self.assertIn("EnvironmentStartTimeoutError", why["env-broken"])
        self.assertEqual(res["worse"], ["timeout"])
        self.assertEqual(res["b"]["n_exceptions"], 1)

    def test_infrastructure_errors_drop_the_pair_but_agent_failures_count(self):
        # Lỗi thấy khi review (30/10/2026): Harbor vẫn chấm sau lỗi hạn mức nên lượt có điểm 0; bản trơn chạy trước
        # trong mỗi việc, nên việc ở ranh giới hết hạn mức bị tính oan là agent-stack kém hơn.
        P, S = B.PLAIN, B.STACK
        cases = (("limit", "ApiUsageLimitError"), ("auth", "AgentAuthenticationError"),
                 ("ctx", "ContextWindowExceededError"), ("exit", "NonZeroAgentExitCodeError"))
        for task, exc in cases:
            self.trial("job", P, task, reward=1.0)
            self.trial("job", S, task, reward=0.0, exception=exc)
        res = B.compare(B.load_trials([self.tmp / "job"]))
        self.assertEqual([r["task"] for r in res["rows"]], ["ctx", "exit"])
        why = dict(res["excluded"])
        self.assertIn("ApiUsageLimitError", why["limit"])
        self.assertIn("AgentAuthenticationError", why["auth"])
        self.assertEqual(res["b"]["infra_dropped"], 2)
        self.assertEqual(res["b"]["trials"], 2)
        self.assertIn("Lượt bỏ vì hạ tầng", B.report(res))

    def test_export_copies_only_results_and_masks_tokens(self):
        token = "sk-ant-oat01-" + "Ab1" * 12
        d = self.trial("pilot", B.STACK, "t", init=INIT_STACK)
        log = d / "agent" / "claude-code.txt"
        log.write_text(log.read_text() + json.dumps({"type": "user", "content": f"CLAUDE_CODE_OAUTH_TOKEN={token}"}) + "\n")
        self.write(f"pilot/{d.name}/agent/sessions/khac.jsonl", token)  # file khác không được chép
        self.write(f"pilot/{d.name}/verifier/reward.txt", "1\n")
        out = self.tmp / "out"
        r = run_script(SCRIPT, "export", str(self.tmp / "pilot"), str(self.tmp / "khong-co"), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("che token trong 1 file", r.stdout)
        files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
        self.assertEqual(files, [f"pilot/{d.name}/agent/claude-code.txt", f"pilot/{d.name}/result.json",
                                 f"pilot/{d.name}/verifier/reward.txt"])
        for f in out.rglob("*"):
            if f.is_file():
                self.assertNotIn(token, f.read_text())
        # vẫn so được trên bản đã chép, và không ghi đè thư mục đã có
        self.assertEqual(B.load_trials([out / "pilot"])[0]["loaded"], True)
        self.assertEqual(run_script(SCRIPT, "export", str(self.tmp / "pilot"), "--out", str(out)).returncode, 1)

    def test_export_fails_when_the_job_has_no_finished_trial_yet(self):
        # Lỗi thấy khi review: fetch ngay sau run báo "Đã kéo về" dù chưa có gì, sau khi đã xoá bản cũ trên Mac.
        (self.tmp / "pilot" / "t__dang-chay").mkdir(parents=True)
        r = run_script(SCRIPT, "export", str(self.tmp / "pilot"), "--out", str(self.tmp / "out"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Chưa có kết quả", r.stderr)

    def test_task_missing_from_oracle_run_is_excluded(self):
        self.trial("job", B.PLAIN, "t", reward=1.0)
        self.trial("job", B.STACK, "t", reward=1.0)
        self.trial("oracle", "oracle", "khac", reward=1.0)
        res = B.compare(B.load_trials([self.tmp / "job"]), B.load_trials([self.tmp / "oracle"]))
        self.assertEqual(res["pairs"], 0)
        self.assertEqual(res["excluded"], [("t", "chưa chạy lời giải mẫu")])

    def test_several_attempts_compare_pass_rates_per_task(self):
        for n, (a, b) in enumerate(((1, 1), (1, 0), (0, 0))):
            self.trial("job", B.PLAIN, "t", reward=float(a), n=n)
            self.trial("job", B.STACK, "t", reward=float(b), n=n)
        res = B.compare(B.load_trials([self.tmp / "job"]))
        self.assertAlmostEqual(res["rows"][0]["a"], 2 / 3)
        self.assertAlmostEqual(res["rows"][0]["b"], 1 / 3)
        self.assertEqual(res["worse"], ["t"])

    def test_report_warns_when_the_plain_arm_saw_agent_stack(self):
        self.trial("job", B.PLAIN, "t", init=INIT_STACK)
        self.trial("job", B.STACK, "t", init=INIT_STACK)
        self.assertIn("Bản trơn thấy agent-stack ở 1 lượt", B.report(B.compare(B.load_trials([self.tmp / "job"]))))

    def test_cli_compare_and_empty_dir(self):
        self.trial("job", B.PLAIN, "t")
        self.trial("job", B.STACK, "t")
        r = run_script(SCRIPT, "compare", str(self.tmp / "job"), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["pairs"], 1)
        (self.tmp / "empty").mkdir()
        self.assertEqual(run_script(SCRIPT, "compare", str(self.tmp / "empty")).returncode, 1)


class TufScriptTests(unittest.TestCase):
    def run_sh(self, *args):
        return subprocess.run(["sh", str(HARBOR / "tuf.sh"), *args], capture_output=True, text=True, timeout=30,
                              env={"PATH": "/usr/bin:/bin", "HARBOR_HOST": "khong-ton-tai.invalid"})

    def test_syntax_and_usage(self):
        self.assertEqual(subprocess.run(["sh", "-n", str(HARBOR / "tuf.sh")]).returncode, 0)
        r = self.run_sh()
        self.assertEqual(r.returncode, 2)
        self.assertIn("tuf.sh sync", r.stdout)

    def test_background_job_is_grouped_so_ssh_returns_at_once(self):
        # Lỗi thấy khi review: `a && nohup x > log &` cho cả AND-list vào nền, subshell giữ stdout nên ssh chờ tới
        # khi job xong. Phần nền phải nằm trong { … & }.
        text = (HARBOR / "tuf.sh").read_text()
        start = text.index("start_job() {")
        body = text[start:text.index("\n}\n", start)]
        self.assertIn("&& { \\", body)
        self.assertIn("< /dev/null & }", body)
        self.assertIn("AGENT_STACK_PAYLOAD=", body)

    def test_rejects_unsafe_job_names_and_unknown_flags(self):
        for args in (("status", "a;rm -rf ~"), ("status", "../x"), ("run", "--yes")):
            with self.subTest(args=args):
                self.assertEqual(self.run_sh(*args).returncode, 2)


if __name__ == "__main__":
    unittest.main()
