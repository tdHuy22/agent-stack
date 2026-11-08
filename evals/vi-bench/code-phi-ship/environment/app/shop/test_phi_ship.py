import unittest

from phi_ship import tinh_phi_ship


class PhiShipTest(unittest.TestCase):
    def test_tinh_khac(self):
        self.assertEqual(tinh_phi_ship(100, "Đà Nẵng"), 35000)

    def test_ha_noi(self):
        self.assertEqual(tinh_phi_ship(120000, "Hà Nội"), 20000)


if __name__ == "__main__":
    unittest.main()
