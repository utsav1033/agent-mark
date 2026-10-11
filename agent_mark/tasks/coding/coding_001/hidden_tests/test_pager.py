import unittest

from pager import page_count, paginate


class TestPager(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(paginate(list(range(25)), 1), list(range(10)))

    def test_last_partial_page(self):
        self.assertEqual(paginate(list(range(25)), 3), [20, 21, 22, 23, 24])

    def test_past_end(self):
        self.assertEqual(paginate(list(range(25)), 4), [])

    def test_custom_page_size(self):
        self.assertEqual(paginate(list("abcdefg"), 2, per_page=3), ["d", "e", "f"])

    def test_page_count(self):
        self.assertEqual(page_count(25), 3)
        self.assertEqual(page_count(20), 2)
        self.assertEqual(page_count(1), 1)
        self.assertEqual(page_count(0), 0)
        self.assertEqual(page_count(7, per_page=3), 3)


if __name__ == "__main__":
    unittest.main()
