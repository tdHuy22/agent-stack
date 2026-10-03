import unittest
from datetime import datetime

from cron import next_run


class CronTest(unittest.TestCase):
    def test_every_quarter_hour(self):
        self.assertEqual(next_run("*/15 * * * *", datetime(2026, 3, 10, 10, 7, 30)), datetime(2026, 3, 10, 10, 15))

    def test_weekday_morning(self):
        # 02/10/2026 là thứ Sáu
        self.assertEqual(next_run("0 9 * * 1-5", datetime(2026, 10, 2, 9, 0)), datetime(2026, 10, 5, 9, 0))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            next_run("60 * * * *", datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
