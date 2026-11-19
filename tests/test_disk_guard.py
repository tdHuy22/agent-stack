"""Việc G mục 3 (19/11/2026): lệnh xóa ổ đĩa (`diskutil erase*`, `newfs*`, `mkfs*`, `dd of=/dev/disk*`) bị chặn hẳn ở
hook PreToolUse, kể cả khi viết khác (`sudo`, `sh -c`, đường dẫn đầy đủ, chữ hoa thường) hay khi người dùng vừa nhắn
đồng ý (TM-148, TM-149); lệnh chỉ đọc ổ đĩa vẫn qua. Bước cài `deny` của install.py ghi luật `permissions.deny` tương
ứng, có xem trước và hoàn tác (TM-150)."""
import json
import os
import subprocess
import sys

from tests._util import REPO, TempDirTestCase
from tests.test_guard import GuardBase

INSTALL = REPO / "tools" / "install.py"

BLOCKED = [
    "diskutil eraseDisk APFS Trong disk2",
    "diskutil eraseVolume APFS Trong /Volumes/USB",
    "diskutil secureErase 0 disk2",
    "diskutil zeroDisk disk2",
    "diskutil randomDisk disk2",
    "diskutil partitionDisk disk2 GPT APFS Trong 0",
    "diskutil reformat /Volumes/USB",
    "diskutil apfs deleteContainer disk3",
    "diskutil ap deleteContainer disk3",
    "diskutil apfs deleteVolume disk3s1",
    "diskutil apfs eraseVolume disk3s1 -name X",
    "newfs_apfs /dev/disk2s1",
    "newfs_hfs -v X /dev/rdisk2s1",
    "/sbin/newfs_msdos -F 32 /dev/disk2s1",
    "newfs /dev/disk2s1",
    "mkfs /dev/sdb1",
    "mkfs.ext4 /dev/sdb1",
    "mkfs.vfat -F 32 /dev/disk2s1",
    "dd if=/dev/zero of=/dev/disk2 bs=1m",
    "dd if=ubuntu.img of=/dev/rdisk4 bs=4m",
    "dd bs=1m of=/dev/disk2s1 if=/dev/urandom",
    'dd if=/dev/zero of="/dev/rdisk2"',
    "dd if=/dev/zero of=/dev/../dev/disk2",
]

EVASIONS = [
    "sudo diskutil eraseDisk APFS X disk2",
    "sudo -u root diskutil zeroDisk disk2",
    'sh -c "diskutil eraseDisk APFS X disk2"',
    "bash -lc 'sudo dd if=/dev/zero of=/dev/rdisk2'",
    "/usr/sbin/diskutil eraseDisk APFS X disk2",
    "diskutil ERASEDISK APFS X disk2",
    "diskutil erasedisk APFS X disk2",
    "diskutil APFS DELETECONTAINER disk3",
    "DiskUtil SecureErase 0 disk2",
    "/sbin/NEWFS_APFS /dev/disk2s1",
    "MKFS.EXT4 /dev/sdb1",
    "/bin/DD if=/dev/zero of=/dev/disk2",
    "env FOO=1 diskutil eraseVolume APFS X disk2s1",
    "time dd if=/dev/zero of=/dev/disk2",
    "ls && diskutil eraseDisk APFS X disk2",
    "echo ok; eval 'diskutil zeroDisk disk2'",
    "nohup newfs_apfs /dev/disk2s1 &",
    "/usr/bin/env diskutil eraseDisk APFS X disk2",
    "sudo /usr/bin/env dd if=/dev/zero of=/dev/disk2",
    "echo disk2 | xargs diskutil eraseDisk APFS X",
    "xargs -n 1 -I {} diskutil zeroDisk {} < list.txt",
    "xargs -i diskutil zeroDisk {} < list.txt",
    "find /dev -name disk2 -exec diskutil zeroDisk {} \\;",
    "find /dev -name 'disk2*' -execdir newfs_apfs {} +",
    "cat /dev/zero > /dev/disk2",
    "pv ubuntu.img >/dev/rdisk2",
    "head -c 1000000 /dev/urandom 1>> /dev/disk2s1",
    # review opus·xhigh 19/11: shell sau lệnh bọc viết bằng đường dẫn, xargs, find; shlex lỗi; `//dev`; gdd
    '/usr/bin/sudo sh -c "diskutil eraseDisk APFS X disk2"',
    "/usr/bin/env bash -c 'diskutil zeroDisk disk2'",
    "xargs -I{} sh -c 'diskutil eraseDisk APFS X {}'",
    "find /dev -name disk2 -exec sh -c 'newfs_apfs \"$1\"' _ {} \\;",
    "BASH -c 'diskutil zeroDisk disk2'",
    "/bin/SH -c 'mkfs.ext4 /dev/sdb1'",
    "ksh -c 'diskutil zeroDisk disk2'",
    "su root -c 'diskutil zeroDisk disk2'",
    "env -S 'diskutil zeroDisk disk2'",
    "diskutil eraseDisk APFS $'X\\'Y' disk2",
    "dd if=/dev/zero of=//dev/disk2",
    "cat /dev/zero > //dev/rdisk2",
    "gdd if=/dev/zero of=/dev/disk2",
    "caffeinate diskutil zeroDisk disk2",
    # review sonnet·xhigh 19/11: `#` giữa từ, biến trong of=, lệnh con, ống vào shell, `-c --`, `sudo -s`
    "ls # xem\ndiskutil eraseDisk APFS X disk2",
    "echo a#b; sudo dd if=/dev/zero of=/dev/rdisk2",
    "DISK=/dev/rdisk2; sudo dd if=ubuntu.img of=\"$DISK\" bs=4m",
    "dd if=/dev/zero of=$(echo /dev/disk2)",
    "cat img > \"$DEV\"  # DEV=/dev/disk2",
    'x="$(sudo diskutil eraseDisk APFS X disk2)"',
    "y=`diskutil zeroDisk disk2`",
    "echo 'diskutil eraseDisk APFS X disk2' | sh",
    "printf 'mkfs.ext4 /dev/sdb1\\n' | sudo bash",
    "bash -c -- 'diskutil zeroDisk disk2'",
    "sudo -s 'diskutil zeroDisk disk2'",
    "bash -c \"bash -c \\\"bash -c 'diskutil zeroDisk disk2'\\\"\"",
]

ALLOWED = [
    "diskutil list",
    "diskutil info disk2",
    "diskutil apfs list",
    "diskutil eject disk2",
    "dd if=/dev/disk2 of=backup.img bs=1m",
    "dd if=/dev/zero of=test.bin bs=1m count=1",
    "dd if=/dev/zero of=/dev/null count=1",
    "echo diskutil eraseDisk APFS X disk2",
    'git commit -m "chặn diskutil eraseDisk, mkfs, dd of=/dev/disk2"',
    "grep -n newfs_apfs notes.txt",
    "man mkfs",
    "ls > /dev/null",
    "echo x 2>/dev/null",
    "find . -name '*.py' -exec grep -n mkfs {} \\;",
    "printf 'diskutil eraseDisk' | xargs echo",
    "git ls-files | xargs grep -n mkfs",
    "xargs -0 grep -ln newfs_apfs < files.txt",
    # backtick markdown trong heredoc có nháy hay chuỗi nháy đơn: shell không chạy (lỗi gặp thật 19/11)
    "python3 - <<'EOF'\nprint('chặn `diskutil erase*`, `newfs*`')\nEOF",
    "echo 'x `diskutil zeroDisk disk2` y'",
]


class DiskEraseGuard(GuardBase):
    def assert_hard_denied(self, cmd, sid="disk"):
        result = self.bash(cmd, sid)
        self.assertIsNotNone(result, f"`{cmd}` không bị chặn")
        decision, reason = result
        self.assertEqual(decision, "deny", cmd)
        self.assertIn("xóa ổ đĩa", reason, cmd)
        self.assertIn("chặn hẳn", reason, cmd)
        # Không phải cổng "chặn lần đầu": lời nhắc không mời Claude hỏi lại người dùng để chạy lệnh.
        self.assertNotIn("hỏi họ có muốn chạy đúng lệnh này", reason, cmd)

    def test_each_disk_erase_command_is_hard_denied(self):
        self.start("Làm tiếp việc của project", "disk")
        for cmd in BLOCKED:
            with self.subTest(cmd=cmd):
                self.assert_hard_denied(cmd)

    def test_evasions_are_still_denied(self):
        self.start("Làm tiếp việc của project", "disk")
        for cmd in EVASIONS:
            with self.subTest(cmd=cmd):
                self.assert_hard_denied(cmd)

    def test_user_consent_does_not_unlock(self):
        for prompt, cmd in (("Đồng ý, xóa ổ disk2 đi: diskutil eraseDisk APFS X disk2", "diskutil eraseDisk APFS X disk2"),
                            ("Chạy dd if=/dev/zero of=/dev/disk2 đi", "dd if=/dev/zero of=/dev/disk2"),
                            ("mkfs.ext4 /dev/sdb1", "mkfs.ext4 /dev/sdb1")):
            with self.subTest(cmd=cmd):
                self.start(prompt, "consent")
                self.assert_hard_denied(cmd, "consent")
                self.assert_hard_denied(cmd, "consent")  # lần hai cũng chặn, không có "lần đầu rồi cho qua"

    def test_read_only_disk_commands_pass(self):
        self.start("Làm tiếp việc của project", "disk")
        for cmd in ALLOWED:
            with self.subTest(cmd=cmd):
                result = self.bash(cmd, "disk")
                self.assertTrue(result is None or "xóa ổ đĩa" not in result[1], f"`{cmd}` bị chặn nhầm: {result}")

    def test_monitor_tool_is_checked_too(self):
        result = self.guard("Monitor", {"command": "diskutil zeroDisk disk2", "description": "x"})
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "deny")
        self.assertIsNone(self.guard("Monitor", {"command": "tail -f log", "description": "x"}))

    def test_docstring_lists_hard_block(self):
        text = (REPO / "plugin" / "hooks" / "pretool_guard.py").read_text(encoding="utf-8")
        doc = text.split('"""')[1]
        for needle in ("`diskutil erase*`", "`newfs*`", "`mkfs*`", "`dd` có `of=/dev/disk*`", "chặn hẳn"):
            self.assertIn(needle, doc)


class DenyInstallStep(TempDirTestCase):
    """Bước `deny` của install.py: xem trước in luật, --apply ghi vào permissions.deny (giữ luật cũ), --rollback trả lại."""

    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        (self.home / ".claude").mkdir(parents=True)
        self.settings = self.home / ".claude" / "settings.json"
        self.original = {"model": "sonnet", "permissions": {"deny": ["Bash(rm -rf /)"], "allow": ["Bash(ls)"]}}
        self.settings.write_text(json.dumps(self.original))
        self.stack = self.tmp / "stack"
        self.stack.mkdir()

    def run_install(self, *args, expect=0):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        env.update(HOME=str(self.home), AGENT_STACK_HOME=str(self.stack),
                   AGENT_STACK_CLAUDE_BIN=str(self.tmp / "khong-co-claude"))
        out = subprocess.run([sys.executable, str(INSTALL), *args], capture_output=True, text=True, env=env, timeout=60)
        if expect is not None:
            self.assertEqual(out.returncode, expect, out.stdout + out.stderr)
        return out.stdout + out.stderr

    def test_deny_is_a_default_step(self):
        sys.path.insert(0, str(REPO / "tools"))
        try:
            import install
        finally:
            sys.path.pop(0)
        self.assertIn("deny", install.STEPS)
        self.assertIn("deny", install.__doc__)

    def test_preview_lists_rules_and_changes_nothing(self):
        out = self.run_install("--only", "deny")
        self.assertIn("XEM TRƯỚC", out)
        for rule in ("Bash(diskutil erase*)", "Bash(newfs*)", "Bash(mkfs*)", "Bash(dd *of=/dev/disk*)",
                     "Bash(dd *of=/dev/rdisk*)", "Bash(sudo diskutil erase*)"):
            self.assertIn(rule, out)
        self.assertEqual(json.loads(self.settings.read_text()), self.original)

    def test_apply_adds_rules_keeps_old_ones_and_rollback_restores(self):
        self.run_install("--apply", "--only", "deny")
        data = json.loads(self.settings.read_text())
        deny = data["permissions"]["deny"]
        self.assertEqual(deny[0], "Bash(rm -rf /)")
        self.assertIn("Bash(diskutil erase*)", deny)
        self.assertIn("Bash(dd *of=/dev/rdisk*)", deny)
        self.assertEqual(len(deny), len(set(deny)))
        self.assertEqual(data["permissions"]["allow"], ["Bash(ls)"])
        self.assertEqual(data["model"], "sonnet")
        again = self.run_install("--apply", "--only", "deny")  # chạy lại không thêm trùng
        self.assertEqual(json.loads(self.settings.read_text())["permissions"]["deny"], deny)
        self.assertIn("= đã có", again)
        out = self.run_install("--rollback", "--apply", expect=None)
        self.assertEqual(json.loads(self.settings.read_text()), self.original, out)

    def test_null_deny_list_is_treated_as_empty(self):
        for value in ({"permissions": {"deny": None}}, {"permissions": None}):
            with self.subTest(value=value):
                self.settings.write_text(json.dumps(value))
                self.run_install("--apply", "--only", "deny")
                self.assertIn("Bash(newfs*)", json.loads(self.settings.read_text())["permissions"]["deny"])

    def test_settings_without_permissions_gets_deny_list(self):
        self.settings.write_text(json.dumps({"model": "opus"}))
        self.run_install("--apply", "--only", "deny")
        data = json.loads(self.settings.read_text())
        self.assertIn("Bash(mkfs*)", data["permissions"]["deny"])
        self.assertEqual(data["model"], "opus")
