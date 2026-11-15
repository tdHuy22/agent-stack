"""install.sh nâng công cụ cargo-source khi commit ghim đổi (TM-121, TM-122): dựng lại đúng bản ghim, sao lưu bản cũ,
`--rollback` lần nâng trả lại bản cũ; bản không do install.sh dựng hay bản đã bị thay thì không đụng."""
import json
import os
import unittest

from tests._util import git
from tests.test_install import InstallTests

NAME = "cong-cu-rust-nang"


def load_tests(_loader, _tests, _pattern):
    """Chỉ chạy test của file này: lớp kế thừa InstallTests để dùng lại HOME giả, không chạy lại test của lớp cha."""
    return unittest.TestSuite(CargoUpgrade(n) for n in sorted(vars(CargoUpgrade)) if n.startswith("test_"))


class CargoUpgrade(InstallTests):
    def setUp(self):
        super().setUp()
        self.src = self.tmp / "nguon-rust"
        (self.src / "crates" / "cli").mkdir(parents=True)
        git(self.src, "init", "-q")
        self.commits = [self.commit_version("ban-1"), self.commit_version("ban-2")]
        self.root = self.home / ".cargo"
        self.bin = self.root / "bin" / NAME
        self.cargo_log = self.tmp / "cargo.log"
        cargo = self.tmp / "fake-cargo"
        # cargo giả: `install` chép main.rs của bản đã archive thành binary trong <gốc>/bin, `uninstall` xóa nó
        cargo.write_text("#!/bin/sh\n"
                         f"echo \"$@\" >> {self.cargo_log}\n"
                         "root=\"${CARGO_INSTALL_ROOT:-$CARGO_HOME}\"\n"
                         f"if [ \"$1\" = install ]; then mkdir -p \"$root/bin\" && cp \"$5/main.rs\" \"$root/bin/{NAME}\""
                         f" && chmod +x \"$root/bin/{NAME}\"; fi\n"
                         "if [ \"$1\" = uninstall ]; then rm -f \"$root/bin/$2\"; fi\n")
        cargo.chmod(0o755)
        self.env = {"AGENT_STACK_CARGO_BIN": str(cargo), "AGENT_STACK_BREW_BIN": str(self.tmp / "khong-co-brew"),
                    "CARGO_HOME": str(self.root), "CARGO_INSTALL_ROOT": str(self.root),
                    "PATH": f"{self.root / 'bin'}{os.pathsep}{os.environ['PATH']}"}
        self.catalog["items"] = [{"key": "cargo:nang", "kind": "cargo-source", "scope": "user",
                                  "install": {"name": "cargo:nang"}}]
        self.pin(0)

    def commit_version(self, text):
        (self.src / "crates" / "cli" / "main.rs").write_text(text + "\n")
        git(self.src, "add", "-A")
        git(self.src, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", text)
        return git(self.src, "rev-parse", "HEAD").strip()

    def pin(self, i):
        self.lock["entries"] = {"cargo:nang": {
            "kind": "cargo-source", "repo": str(self.src), "commit": self.commits[i], "crate_path": "crates/cli",
            "bin": NAME, "verdict": "REVIEW", "human_review": {"status": "approved"}}}
        self.save()

    def tools(self, *args, expect=0):
        return self.run_install(*args, "--only", "tools", extra_env=self.env, expect=expect)

    def installs(self):
        if not self.cargo_log.exists():
            return []
        return [line for line in self.cargo_log.read_text().splitlines() if line.startswith("install ")]

    def logs(self):
        """Nhật ký cài còn hiệu lực, cũ nhất trước."""
        folder = self.stack / "state" / "install-logs"
        live = [p for p in folder.glob("*.json")
                if not p.name.endswith(".rolled-back.json") and p.name != "last-rollback.json"]
        return sorted(live, key=lambda p: json.loads(p.read_text())["created"])

    def test_pin_change_rebuilds_then_rollback_restores_old_binary(self):
        """Tiêu chí 1, 3: ghim đổi thì dựng lại đúng bản ghim, xem trước nói rõ nâng từ đâu lên đâu; đúng ghim thì
        không dựng lại; gỡ lần nâng trả lại đúng binary cũ (không gỡ hẳn); gỡ hết thì không còn binary."""
        c1, c2 = self.commits
        self.tools("--apply")
        self.assertEqual(self.bin.read_text(), "ban-1\n")
        self.assertIn(f"đúng commit ghim {c1[:12]}", self.tools("--apply"))
        self.assertEqual(len(self.installs()), 1, "đúng commit ghim thì không dựng lại")
        self.pin(1)
        out = self.tools()
        self.assertIn(f"nâng {NAME} từ {c1[:12]} lên {c2[:12]}", out)
        self.assertEqual(self.bin.read_text(), "ban-1\n", "xem trước không đổi gì")
        self.assertEqual(len(self.installs()), 1)
        self.tools("--apply")
        self.assertEqual(self.bin.read_text(), "ban-2\n")
        self.assertEqual(len(self.installs()), 2)
        self.assertNotIn("--force", self.installs()[-1], "không dùng --force: cargo tự từ chối đè binary của gói khác")
        self.assertIn(f"đúng commit ghim {c2[:12]}", self.tools("--apply"))
        manifest = (self.stack / "INSTALLED.md").read_text(encoding="utf-8")
        self.assertIn(f"{c1[:12]} → {c2[:12]}", manifest)
        self.run_install("--rollback", str(self.logs()[-1]), "--apply", extra_env=self.env)
        self.assertEqual(self.bin.read_text(), "ban-1\n", "gỡ lần nâng trả bản cũ, không gỡ hẳn")
        self.pin(0)
        self.assertIn(f"đúng commit ghim {c1[:12]}", self.tools())
        self.run_install("--rollback", "--apply", extra_env=self.env)
        self.assertFalse(self.bin.exists())

    def test_binary_not_built_by_install_sh_is_left_alone(self):
        """Tiêu chí 2: bản bạn tự cài (không có trong nhật ký) thì không dựng đè, chỉ in hướng dẫn."""
        self.bin.parent.mkdir(parents=True)
        self.bin.write_text("tu-cai\n")
        self.bin.chmod(0o755)
        out = self.tools("--apply")
        self.assertIn("không phải bản install.sh dựng", out)
        self.assertEqual(self.bin.read_text(), "tu-cai\n")
        self.assertEqual(self.installs(), [])

    def test_other_binary_first_on_path_is_left_alone(self):
        """TM-121: install.sh đã dựng ở gốc cargo, nhưng PATH gặp một binary cùng tên ở thư mục khác trước: không nâng."""
        self.tools("--apply")
        other = self.tmp / "khac"
        other.mkdir()
        (other / NAME).write_text("khac\n")
        (other / NAME).chmod(0o755)
        self.env["PATH"] = f"{other}{os.pathsep}{self.env['PATH']}"
        self.pin(1)
        self.assertIn("không phải bản install.sh dựng", self.tools("--apply"))
        self.assertEqual(self.bin.read_text(), "ban-1\n")
        self.assertEqual((other / NAME).read_text(), "khac\n")
        self.assertEqual(len(self.installs()), 1)

    def test_binary_replaced_after_build_is_not_upgraded(self):
        """TM-121: binary đổi sau lần install.sh dựng (mã băm không khớp nhật ký) thì bỏ qua và báo, không dựng đè."""
        self.tools("--apply")
        self.bin.write_text("thay-tay\n")
        self.pin(1)
        out = self.tools("--apply", expect=2)
        self.assertIn("đã bị thay sau lần install.sh dựng", out)
        self.assertEqual(self.bin.read_text(), "thay-tay\n")
        self.assertEqual(len(self.installs()), 1)

    def test_rollback_of_upgrade_leaves_a_binary_changed_after_it(self):
        """TM-122: binary đổi sau lần nâng thì gỡ lần nâng báo lỗi, không chép bản cũ đè lên."""
        self.tools("--apply")
        self.pin(1)
        self.tools("--apply")
        self.bin.write_text("thay-sau-khi-nang\n")
        out = self.run_install("--rollback", str(self.logs()[-1]), "--apply", extra_env=self.env, expect=1)
        self.assertIn("đã bị thay sau khi nâng", out)
        self.assertEqual(self.bin.read_text(), "thay-sau-khi-nang\n")

    def test_log_written_before_upgrade_support_still_counts(self):
        """Nhật ký cũ chỉ có lệnh `cargo install ... --path <repo>@<12 ký tự>/<crate>`, không có mã băm: vẫn nhận ra
        install.sh đã dựng và nâng được (máy thật đang ở trạng thái này: archctl dựng từ a82879b ngày 14/11)."""
        c1, c2 = self.commits
        self.tools("--apply")
        log = self.logs()[-1]
        data = json.loads(log.read_text())
        for action in data["actions"]:
            for key in ("bin", "commit", "sha256"):
                action.pop(key, None)
        log.write_text(json.dumps(data))
        self.pin(1)
        self.assertIn(f"nâng {NAME} từ {c1[:12]} lên {c2[:12]}", self.tools("--apply"))
        self.assertEqual(self.bin.read_text(), "ban-2\n")

    def test_rollback_all_keeps_binary_replaced_after_upgrade(self):
        """TM-122 (review 15/11): gỡ hết sau khi binary bị thay thì cả lần nâng lẫn lần cài gốc đều không đụng:
        lần cài gốc có mã băm nên không chạy `cargo uninstall` xóa bản của người khác."""
        self.tools("--apply")
        self.pin(1)
        self.tools("--apply")
        self.bin.write_text("ban-dev\n")
        out = self.run_install("--rollback", "--apply", extra_env=self.env, expect=1)
        self.assertIn("đã bị thay sau khi nâng", out)
        self.assertIn("khác bản lần cài này dựng", out)
        self.assertEqual(self.bin.read_text(), "ban-dev\n")
        self.assertNotIn("uninstall", self.cargo_log.read_text())

    def test_binary_in_cargo_root_off_path_is_still_checked(self):
        """TM-121 (review 15/11): gốc cargo không nằm trong PATH mà đã có binary bạn tự cài: không dựng đè."""
        self.bin.parent.mkdir(parents=True)
        self.bin.write_text("tu-cai\n")
        self.bin.chmod(0o755)
        self.env["PATH"] = os.environ["PATH"]
        out = self.tools("--apply")
        self.assertIn("không phải bản install.sh dựng", out)
        self.assertEqual(self.bin.read_text(), "tu-cai\n")
        self.assertEqual(self.installs(), [])

    def test_symlink_in_cargo_root_is_left_alone(self):
        """TM-121 (review 15/11): binary ở gốc cargo là symlink tới bản khác thì không nâng (cargo sẽ thay symlink bằng
        file thường), kể cả với nhật ký cũ không có mã băm."""
        self.tools("--apply")
        log = self.logs()[-1]
        data = json.loads(log.read_text())
        for action in data["actions"]:
            action.pop("sha256", None)
        log.write_text(json.dumps(data))
        dev = self.tmp / "ban-dev"
        dev.write_text("ban-dev\n")
        dev.chmod(0o755)
        self.bin.unlink()
        self.bin.symlink_to(dev)
        self.pin(1)
        self.assertIn("không phải bản install.sh dựng", self.tools("--apply"))
        self.assertTrue(self.bin.is_symlink())
        self.assertEqual(dev.read_text(), "ban-dev\n")
        self.assertEqual(len(self.installs()), 1)

    def test_chain_of_upgrades_rolls_back_one_step_at_a_time(self):
        """Nâng hai lần liên tiếp (1 → 2 → 3) rồi gỡ từng lần: mỗi lần gỡ trả đúng bản liền trước."""
        self.commits.append(self.commit_version("ban-3"))
        for i in range(3):
            self.pin(i)
            self.tools("--apply")
        self.assertEqual(self.bin.read_text(), "ban-3\n")
        self.assertEqual(len(self.logs()), 3)
        self.run_install("--rollback", str(self.logs()[-1]), "--apply", extra_env=self.env)
        self.assertEqual(self.bin.read_text(), "ban-2\n")
        self.run_install("--rollback", str(self.logs()[-1]), "--apply", extra_env=self.env)
        self.assertEqual(self.bin.read_text(), "ban-1\n")
        self.run_install("--rollback", "--apply", extra_env=self.env)
        self.assertFalse(self.bin.exists())

    def test_failed_upgrade_build_keeps_old_binary_and_writes_no_log(self):
        """Dựng bản mới lỗi: bản cũ còn nguyên, lần chạy báo lỗi (mã 1), không ghi nhật ký nâng."""
        self.tools("--apply")
        (self.tmp / "fake-cargo").write_text(f"#!/bin/sh\necho \"$@\" >> {self.cargo_log}\nexit 101\n")
        self.pin(1)
        out = self.tools("--apply", expect=1)
        self.assertIn("cargo install", out)
        self.assertEqual(self.bin.read_text(), "ban-1\n")
        self.assertEqual(len(self.logs()), 1)


if __name__ == "__main__":
    unittest.main()
