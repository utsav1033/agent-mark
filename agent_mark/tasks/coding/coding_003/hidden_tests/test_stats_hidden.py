import unittest

from stats import mean, median


class TestStatsHidden(unittest.TestCase):
    def test_median_even(self):
        self.assertEqual(median([4, 1, 3, 2]), 2.5)
        self.assertEqual(median([10, 20]), 15)

    def test_median_odd(self):
        self.assertEqual(median([5]), 5)
        self.assertEqual(median([9, 1, 5, 3, 7]), 5)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            median([])
        with self.assertRaises(ValueError):
            mean([])


if __name__ == "__main__":
    unittest.main()
