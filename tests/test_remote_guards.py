"""Test thêm sau review F2b (20/11/2026) cho các chốt chặn của TM-164, TM-165 chưa có test chạm nhánh từ chối:
dấu vân tay đổi hay không tính được lúc đóng gói, máy xa thấy cây chạy không khớp commit tạm, JSON mutation thiếu số
đếm, hạn trong của mutation trên máy xa. Dùng lại phần dựng của `tests/test_remote.py` (ssh giả, repo tạm)."""
from __future__ import annotations

import json
from unittest import mock

from tests import test_remote as TR


class PackingGuards(TR.RemoteBase):
    def run_here(self):
        return self.remote.run_remote(self.repo, self.repo, ["python3", "-c", "print('chay')"], "tuf", 60)

    def test_control_run_works(self):
        """Đối chứng: cùng repo và cấu hình, lần chạy bình thường đạt."""
        res = self.run_here()
        self.assertEqual(res.code, 0, res)
        self.assertIsNone(res.error)

    def test_tree_changing_while_packing_is_refused(self):
        """spec:f2b-chay-xa#S5 — dấu vân tay sau khi đóng gói khác lúc trước: từ chối, không gọi ssh."""
        real = self.remote.fingerprints
        calls = []

        def drifting(root):
            calls.append(root)
            fp = real(root)
            return fp if len(calls) == 1 else ("khac", "khac")

        with mock.patch.object(self.remote, "fingerprints", side_effect=drifting), \
                self.assertRaises(self.remote.Refused) as ctx:
            self.run_here()
        self.assertIn("đổi trong lúc đóng gói", str(ctx.exception))
        self.assertEqual(self.ssh_calls(), [])

    def test_unknown_fingerprint_is_refused(self):
        """TM-164 — không tính được dấu vân tay (git lỗi, quá giờ): từ chối thay vì ghi biên nhận không có dấu."""
        with mock.patch.object(self.remote, "fingerprints", return_value=(None, None)), \
                self.assertRaises(self.remote.Refused) as ctx:
            self.run_here()
        self.assertIn("dấu vân tay", str(ctx.exception))
        self.assertEqual(self.ssh_calls(), [])


class RemoteTreeCheck(TR.RemoteBase):
    def tampered(self, inject):
        """Chuỗi lệnh máy xa bị chèn `inject` ngay trước bước kiểm cây (giả máy xa có file lạ hay file bị sửa)."""
        real = self.remote.run_script

        def wrapped(*args, **kw):
            script = real(*args, **kw)
            self.assertIn("git diff --quiet", script)
            return script.replace("git diff --quiet", f"{inject} && git diff --quiet", 1)

        return mock.patch.object(self.remote, "run_script", side_effect=wrapped)

    def test_stray_file_on_remote_stops_the_run(self):
        """TM-164 — thư mục chạy có file không thuộc commit tạm: lệnh không chạy, mã 255 kèm lỗi."""
        marker = self.tmp / "ran-marker"
        with self.tampered("touch stray.txt"):
            res = self.remote.run_remote(self.repo, self.repo, ["python3", "-c", f"open({str(marker)!r},'w')"],
                                         "tuf", 60)
        self.assertEqual(res.code, 255, res)
        self.assertTrue(res.error)
        self.assertIn("không khớp", res.output + res.error)
        self.assertFalse(marker.exists(), "lệnh không được chạy khi cây không khớp")

    def test_modified_tracked_file_on_remote_stops_the_run(self):
        """TM-164 — file đang theo dõi bị sửa trên máy xa trước khi chạy: mã 255."""
        with self.tampered("echo lech >> keep.txt"):
            res = self.remote.run_remote(self.repo, self.repo, ["python3", "-c", "print(1)"], "tuf", 60)
        self.assertEqual(res.code, 255, res)
        self.assertIn("không khớp", res.output + res.error)


class MutationJsonCounts(TR.MutationBase):
    def test_missing_or_inconsistent_counts_are_not_a_result(self):
        """spec:f2b-chay-xa#S10 — JSON `ran`/`partial` thiếu `total`, `killed`, hay số cộng lại quá `total`: chưa chạy."""
        self.control_mut()
        bad = [{"status": "ran"}, {"status": "ran", "total": 3}, {"status": "partial", "killed": 1, "reason": "x"},
               {**TR.GOOD_JSON, "total": True}, {**TR.GOOD_JSON, "total": 2},
               {**TR.GOOD_JSON, "total": 3, "killed": 2, "timeout": 2}]
        for data in bad:
            with self.subTest(data=data):
                with self.patched(self.fake_result(output=json.dumps(data))):
                    code, lines = self.mut("--host", "tuf", "--cmd", TR.MUT_CMD)
                self.assertNotRan(code, lines, json.dumps(data))


class MutationInnerTimeout(TR.MutationBase):
    def test_remote_mutation_gets_a_shorter_limit_than_the_run(self):
        """S9 — `--timeout` là hạn chung: mutation.py trên máy xa nhận hạn nhỏ hơn hạn của lần chạy để kịp in kết quả."""
        for outer, inner in ((3600, 3540), (100, 90), (10, 9)):
            with self.subTest(outer=outer):
                with self.patched(self.good_result()) as run:
                    self.mut("--host", "tuf", "--cmd", TR.MUT_CMD, "--timeout", str(outer))
                args = run.call_args.args
                cmd, limit = args[2], args[4]
                self.assertEqual(limit, outer)
                self.assertEqual(float(cmd[cmd.index("--timeout") + 1]), inner)


class MoreBadRemoteResults(TR.MutationBase):
    def test_non_finite_numbers_missing_survived_and_multiline_errors(self):
        """spec:f2b-chay-xa#S10 — số không hữu hạn, thiếu `survived`, lỗi nhiều dòng: dòng cuối vẫn `Mutation: chưa chạy:`."""
        self.control_mut()
        texts = ['{"status": "ran", "total": 3, "killed": 3}',
                 '{"status": "partial", "reason": "x", "total": 4, "killed": 1, "survived": [], "untested": 3, '
                 '"estimate_seconds": Infinity, "seconds": NaN}']
        for text in texts:
            with self.subTest(text=text), self.patched(self.fake_result(output=text)):
                code, lines = self.mut("--host", "tuf", "--cmd", TR.MUT_CMD)
            self.assertNotRan(code, lines, text)
        trace = "Traceback (most recent call last):\n  File \"x.py\", line 1\nSyntaxError: invalid syntax\n"
        with self.patched(self.fake_result(code=1, output=trace)):
            code, lines = self.mut("--host", "tuf", "--cmd", TR.MUT_CMD)
        self.assertNotRan(code, lines, "lỗi nhiều dòng")


class SubmoduleRefused(TR.RemoteBase):
    def test_repo_with_a_submodule_is_refused(self):
        """S1 — repo có submodule (gitlink): máy xa sẽ chạy thiếu code, nên từ chối, không gọi ssh."""
        sub = self.tmp / "subrepo"
        sub.mkdir()
        (sub / "a.txt").write_text("a\n", encoding="utf-8")
        TR.git(sub, "init", "-q")
        TR.git(sub, "add", "-A")
        TR.git(sub, "commit", "-q", "-m", "s")
        head = TR.git(sub, "rev-parse", "HEAD").strip()
        TR.git(self.repo, "update-index", "--add", "--cacheinfo", f"160000,{head},lib")
        with self.assertRaises(self.remote.Refused) as ctx:
            self.remote.run_remote(self.repo, self.repo, ["python3", "-c", "print(1)"], "tuf", 60)
        self.assertIn("submodule", str(ctx.exception))
        self.assertEqual(self.ssh_calls(), [])


class ProgressIgnoresRemote(TR.RemoteBase):
    def test_failing_remote_receipt_is_not_a_blocking_task(self):
        """S3 — biên nhận xa trượt (máy khác hệ điều hành) không thành việc "Chạy lại và sửa kiểm tra" ở progress."""
        out = self.py("import sys; sys.exit(3)")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        import importlib.util
        spec = importlib.util.spec_from_file_location("plan_tree_remote",
                                                      TR.PLUGIN / "skills" / "progress" / "scripts" / "plan_tree.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tasks = module.failing_checks(self.repo)
        self.assertFalse([t for t in tasks if "@tuf" in t], tasks)
