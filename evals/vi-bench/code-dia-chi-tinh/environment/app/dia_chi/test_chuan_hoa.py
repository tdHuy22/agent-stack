import unittest

from chuan_hoa import chuan_hoa_tinh


class ChuanHoaTest(unittest.TestCase):
    def test_viet_tat(self):
        self.assertEqual(chuan_hoa_tinh("12 Lê Lợi, HN"), "12 Lê Lợi, Hà Nội")

    def test_da_chuan(self):
        self.assertEqual(chuan_hoa_tinh("5 Trần Phú, Đà Nẵng"), "5 Trần Phú, Đà Nẵng")


if __name__ == "__main__":
    unittest.main()
