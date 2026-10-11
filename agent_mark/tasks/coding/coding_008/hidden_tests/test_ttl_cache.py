import unittest

from ttl_cache import TTLCache


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TestTTLCache(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()

    def make(self, capacity=2, ttl=10):
        return TTLCache(capacity, ttl, clock=self.clock)

    def test_validation(self):
        with self.assertRaises(ValueError):
            TTLCache(0, 1)
        with self.assertRaises(ValueError):
            TTLCache(1, 0)

    def test_basic_get_set(self):
        c = self.make()
        c.set("a", 1)
        self.assertEqual(c.get("a"), 1)
        self.assertEqual(c.get("zz", "dflt"), "dflt")

    def test_expiry(self):
        c = self.make()
        c.set("a", 1)
        self.clock.t += 9.9
        self.assertEqual(c.get("a"), 1)
        self.clock.t += 0.2
        self.assertIsNone(c.get("a"))
        self.assertEqual(len(c), 0)

    def test_overwrite_resets_ttl(self):
        c = self.make()
        c.set("a", 1)
        self.clock.t += 8
        c.set("a", 2)
        self.clock.t += 8
        self.assertEqual(c.get("a"), 2)

    def test_lru_eviction(self):
        c = self.make(capacity=2)
        c.set("a", 1)
        c.set("b", 2)
        c.get("a")          # a is now most recent
        c.set("c", 3)       # evicts b
        self.assertIn("a", c)
        self.assertNotIn("b", c)
        self.assertIn("c", c)

    def test_contains_does_not_touch_recency(self):
        c = self.make(capacity=2)
        c.set("a", 1)
        c.set("b", 2)
        self.assertIn("a", c)  # must not refresh a
        c.set("c", 3)          # evicts a (still LRU)
        self.assertNotIn("a", c)
        self.assertIn("b", c)

    def test_expired_purged_before_lru_eviction(self):
        c = TTLCache(2, 10, clock=self.clock)
        c.set("old", 0)
        self.clock.t += 5
        c.set("fresh", 1)
        c.get("old")           # old is MRU but will expire first
        self.clock.t += 6      # old expired, fresh still valid
        c.set("new", 2)
        self.assertIn("fresh", c)
        self.assertIn("new", c)
        self.assertEqual(len(c), 2)

    def test_len_counts_live_only(self):
        c = self.make(capacity=5, ttl=10)
        c.set("a", 1)
        self.clock.t += 5
        c.set("b", 2)
        self.clock.t += 6
        self.assertEqual(len(c), 1)


if __name__ == "__main__":
    unittest.main()
