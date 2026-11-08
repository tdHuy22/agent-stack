import unittest

from tinh_hoa_don import tinh_hoa_don


class HoaDonTest(unittest.TestCase):
    def test_mot_dong_thuc_pham(self):
        dong = [{"ten": "Gạo", "nhom": "Thực phẩm", "don_gia": 20000, "so_luong": 5}]
        self.assertEqual(tinh_hoa_don(dong), {"tien_hang": 100000, "vat": 8000, "tong": 108000})

    def test_hoa_don_rong(self):
        self.assertEqual(tinh_hoa_don([]), {"tien_hang": 0, "vat": 0, "tong": 0})


if __name__ == "__main__":
    unittest.main()
