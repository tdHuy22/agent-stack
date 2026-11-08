import unittest

from lich_tra_no import lap_lich_tra_no


class LichTraNoTest(unittest.TestCase):
    def test_vay_chia_het(self):
        lich = lap_lich_tra_no(12000000, 12, 4)
        self.assertEqual(len(lich), 4)
        self.assertEqual(lich[0], {"ky": 1, "goc": 3000000, "lai": 120000, "tong": 3120000, "du_no_cuoi": 9000000})
        self.assertEqual(lich[3]["du_no_cuoi"], 0)


if __name__ == "__main__":
    unittest.main()
