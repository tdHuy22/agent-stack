import unittest
from datetime import date

from cua_hang import don_hang, giam_gia

HOM_NAY = date(2026, 11, 10)


class TestGiamGia(unittest.TestCase):
    def test_giam_phan_tram(self):
        self.assertEqual(giam_gia.ap_dung_ma(200_000, "GIAM10", HOM_NAY), 20_000)

    def test_ma_sai(self):
        self.assertEqual(giam_gia.ap_dung_ma(200_000, "KHONGCO", HOM_NAY), 0)

    def test_ma_het_han(self):
        self.assertFalse(giam_gia.ma_con_han("LAN1", HOM_NAY))
        self.assertEqual(giam_gia.ap_dung_ma(500_000, "LAN1", HOM_NAY), 0)

    def test_giam_khong_vuot_tien_hang(self):
        self.assertEqual(giam_gia.ap_dung_ma(80_000, "LAN1", date(2026, 10, 1)), 80_000)

    def test_phi_ship_khong_tinh_giam(self):
        self.assertEqual(don_hang.tinh_tong(100_000, 25_000, "GIAM10", HOM_NAY), 115_000)


if __name__ == "__main__":
    unittest.main()
