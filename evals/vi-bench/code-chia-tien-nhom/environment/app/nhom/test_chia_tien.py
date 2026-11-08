import unittest

from chia_tien import chia_tien


class ChiaTienTest(unittest.TestCase):
    def test_mot_nguoi_tra_het(self):
        ds = chia_tien([("An", 300000)], ["An", "Bình", "Chi"])
        self.assertEqual(ds, [("Bình", "An", 100000), ("Chi", "An", 100000)])

    def test_khong_ai_tra(self):
        self.assertEqual(chia_tien([], ["An", "Bình"]), [])


if __name__ == "__main__":
    unittest.main()
