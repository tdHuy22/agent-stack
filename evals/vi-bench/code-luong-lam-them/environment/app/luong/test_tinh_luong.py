import unittest

from tinh_luong import tinh_tien_lam_them


class LamThemTest(unittest.TestCase):
    def test_ngay_thuong(self):
        # thứ Tư 06/03/2024, làm thêm 2 giờ; lương giờ 50.000đ, hệ số 150%
        self.assertEqual(tinh_tien_lam_them(10400000, [("06/03/2024", "18:00", "20:00")]), 150000)

    def test_khong_lam_them(self):
        self.assertEqual(tinh_tien_lam_them(10400000, []), 0)


if __name__ == "__main__":
    unittest.main()
