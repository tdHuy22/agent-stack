import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cache import TTLCache


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class TestCache(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def test_basic(self):
        c = TTLCache(2, ttl=10, clock=self.clock)
        c.set("a", 1)
        self.assertEqual(c.get("a"), 1)
        self.assertEqual(c.get("zz", "x"), "x")

    def test_lru_eviction(self):
        c = TTLCache(2, clock=self.clock)
        c.set("a", 1); c.set("b", 2)
        c.get("a")
        c.set("c", 3)
        self.assertIsNone(c.get("b"))
        self.assertEqual(c.get("a"), 1)
        self.assertEqual(c.stats["evictions"], 1)

    def test_overwrite_resets_ttl(self):
        c = TTLCache(2, ttl=10, clock=self.clock)
        c.set("a", 1)
        self.clock.now = 8
        c.set("a", 2)
        self.clock.now = 15
        self.assertEqual(c.get("a"), 2)

    def test_expiry_at_deadline(self):
        c = TTLCache(2, ttl=10, clock=self.clock)
        c.set("a", 1)
        self.clock.now = 10
        self.assertIsNone(c.get("a"))


if __name__ == "__main__":
    unittest.main()
