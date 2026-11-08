import os
import unittest

from ngay_lam_viec import dem_ngay_lam_viec

FILE_LE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ngay_le_mau.txt")


class DemNgayTest(unittest.TestCase):
    def test_mot_tuan_khong_le(self):
        # 05/02/2024 là thứ Hai, 09/02/2024 là thứ Sáu
        self.assertEqual(dem_ngay_lam_viec("05/02/2024", "09/02/2024", FILE_LE), 5)

    def test_tuan_co_le(self):
        # 15/04/2024 là thứ Hai, 19/04/2024 là thứ Sáu, 18/04 là lễ
        self.assertEqual(dem_ngay_lam_viec("15/04/2024", "19/04/2024", FILE_LE), 4)


if __name__ == "__main__":
    unittest.main()
