import unittest

from scheduler import free_slots

DAY = (540, 1020)  # 09:00-17:00


class TestFreeSlots(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(free_slots([(600, 660)], *DAY), [(540, 600), (660, 1020)])

    def test_unsorted(self):
        self.assertEqual(free_slots([(900, 960), (600, 660)], *DAY),
                         [(540, 600), (660, 900), (960, 1020)])

    def test_overlapping(self):
        # (600,700) fully contains (620,650); a naive cursor would move backwards.
        self.assertEqual(free_slots([(600, 700), (620, 650)], *DAY), [(540, 600), (700, 1020)])

    def test_touching(self):
        self.assertEqual(free_slots([(600, 630), (630, 660)], *DAY), [(540, 600), (660, 1020)])

    def test_outside_day(self):
        self.assertEqual(free_slots([(480, 570), (1000, 1100)], *DAY), [(570, 1000)])
        self.assertEqual(free_slots([(0, 500), (1100, 1200)], *DAY), [(540, 1020)])

    def test_min_minutes(self):
        self.assertEqual(free_slots([(560, 600)], *DAY, min_minutes=30), [(600, 1020)])
        self.assertEqual(free_slots([(560, 600)], *DAY, min_minutes=15), [(540, 560), (600, 1020)])

    def test_fully_busy(self):
        self.assertEqual(free_slots([(500, 1100)], *DAY), [])


if __name__ == "__main__":
    unittest.main()
