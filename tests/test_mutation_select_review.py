"""Siết theo review 18/11 (sonnet·xhigh) của spec `mutation-chon-test`: test phụ thuộc thứ tự không được biến đột biến
sống thành bị bắt; id test không nạp lại được theo tên thì không được ghi "theo dòng". Chạy mutmut thật như
`tests/test_mutation_select.py` (bỏ qua khi máy thiếu mutmut hay `ps`); chỉ chạy lúc cuối.
"""
import unittest

from tests.test_mutation_select import SUT_NEW, SUT_OLD, TESTS_HEAD, TESTS_MAIN, TOOL_NEW, SelBase

ORD_OLD = 'STATE = {"ready": False}\n\n\ndef f(x):\n    return x\n'
ORD_NEW = 'STATE = {"ready": False}\n\n\ndef f(x):\n    a = x + 1\n    unused = x + 100\n    return a * 3\n'
ORD_TESTS = TESTS_HEAD.replace("from sut import f, g", "from sut import STATE, f") + '''
class T(unittest.TestCase):
    def test_a_setup(self):
        note("a")
        STATE["ready"] = True

    def test_b(self):
        note("b")
        self.assertTrue(STATE["ready"])
        self.assertEqual(f(1), 6)
'''
ODD_ID_TESTS = TESTS_MAIN.replace('''class T(unittest.TestCase):
''', '''class T(unittest.TestCase):
    def id(self):
        return "khong.nap.duoc." + self._testMethodName

''')


class ReviewFindings(SelBase):
    def test_order_dependent_test_does_not_turn_survivors_into_kills(self):
        # spec:mutation-chon-test#S2 (review: test_b chỉ đạt khi test_a_setup chạy trước; chạy riêng test_b thì trượt
        # trên cả code gốc, nên đột biến sống `unused` không được tính là bị bắt)
        self.build({"sut.py": ORD_OLD, "tests/test_x.py": ORD_TESTS}, {"sut.py": ORD_NEW})
        sel, _ = self.ran()
        full, _ = self.ran("--no-select")
        self.assertTrue(full["survived"], f"fixture phải có đột biến sống: {full}")
        self.assertSameOutcome(sel, full)

    def test_unloadable_test_ids_turn_selection_off(self):
        # spec:mutation-chon-test#S3
        # spec:mutation-chon-test#S4 (review: mọi dòng bị bỏ khỏi bảng thì không được ghi "theo dòng")
        self.build({"sut.py": SUT_OLD, "tool.py": TOOL_NEW, "tests/test_x.py": ODD_ID_TESTS}, {"sut.py": SUT_NEW})
        sel, _ = self.ran()
        self.assertOff(sel)
        self.assertNotEqual(sel["selection"], "tắt: --no-select")
        full, _ = self.ran("--no-select")
        self.assertSameOutcome(sel, full)


if __name__ == "__main__":
    unittest.main()
