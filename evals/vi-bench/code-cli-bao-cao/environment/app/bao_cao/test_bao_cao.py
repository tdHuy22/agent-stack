import contextlib
import io
import os
import unittest

import bao_cao

MAU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mau.csv")


class BaoCaoTest(unittest.TestCase):
    def chay(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ma = bao_cao.main(argv)
        return ma, out.getvalue()

    def test_dinh_dang_tien(self):
        self.assertEqual(bao_cao.dinh_dang_tien(1234567), "1.234.567")

    def test_tong_hop(self):
        self.assertEqual(bao_cao.tong_hop(bao_cao.doc_giao_dich(MAU)), {"Cà phê": 180000, "Trà đào": 38000})

    def test_bao_cao_ca_file(self):
        ma, out = self.chay([MAU])
        self.assertEqual(ma, 0)
        self.assertEqual(out, "Cà phê: 180.000\nTrà đào: 38.000\nTổng: 218.000\n")


if __name__ == "__main__":
    unittest.main()
