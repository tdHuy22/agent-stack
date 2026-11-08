import unittest

from thue import tinh_thue_tncn


class ThueTest(unittest.TestCase):
    def test_luong_thap_khong_dong_thue(self):
        self.assertEqual(tinh_thue_tncn(8000000), 0)

    def test_luong_trung_binh(self):
        self.assertEqual(tinh_thue_tncn(15000000), 121250)


if __name__ == "__main__":
    unittest.main()
