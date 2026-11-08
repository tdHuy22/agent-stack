import os
import tempfile
import unittest
from decimal import Decimal

from doc_csv import tong_doanh_thu_theo_thang


class DocCsvTest(unittest.TestCase):
    def ghi(self, noi_dung):
        fd, duong_dan = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(os.remove, duong_dan)
        with open(duong_dan, "w", encoding="utf-8", newline="") as f:
            f.write(noi_dung)
        return duong_dan

    def test_hai_thang(self):
        p = self.ghi("Ngày;Khách hàng;Doanh thu\n05/03/2024;An;1000000\n20/03/2024;Bình;500000\n01/04/2024;An;250000\n")
        self.assertEqual(tong_doanh_thu_theo_thang(p), {"2024-03": Decimal("1500000"), "2024-04": Decimal("250000")})

    def test_so_thap_phan(self):
        p = self.ghi("Ngày;Doanh thu\n05/03/2024;1000,5\n")
        self.assertEqual(tong_doanh_thu_theo_thang(p), {"2024-03": Decimal("1000.5")})


if __name__ == "__main__":
    unittest.main()
