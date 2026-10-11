import unittest

from text_utils import slugify


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_accents(self):
        self.assertEqual(slugify("  Café  Crème brûlée "), "cafe-creme-brulee")

    def test_collapse_separators(self):
        self.assertEqual(slugify("a---b___c   d"), "a-b-c-d")

    def test_non_latin_dropped(self):
        self.assertEqual(slugify("日本 test 2024"), "test-2024")

    def test_truncation_no_trailing_hyphen(self):
        self.assertEqual(slugify("abc def", max_length=4), "abc")
        self.assertEqual(len(slugify("word " * 40)), 49)

    def test_empty(self):
        self.assertEqual(slugify(""), "")
        self.assertEqual(slugify("!!! ???"), "")


if __name__ == "__main__":
    unittest.main()
