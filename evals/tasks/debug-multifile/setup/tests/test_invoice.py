import unittest

from billing.invoice import build_invoice
from billing.money import fmt


class InvoiceTest(unittest.TestCase):
    def test_simple(self):
        inv = build_invoice([("pen", 2, "1.50")])
        self.assertEqual((inv["subtotal"], inv["tax"], inv["total"]), (300, 30, 330))

    def test_mixed_cart(self):
        inv = build_invoice([("pen", 2, "1.50"), ("ink", 1, "19.99")])
        self.assertEqual(inv["subtotal"], 2299)
        self.assertEqual(inv["tax"], 230)
        self.assertEqual(inv["total"], 2529)

    def test_fmt(self):
        self.assertEqual(fmt(2529), "25.29")
        self.assertEqual(fmt(5), "0.05")


if __name__ == "__main__":
    unittest.main()
