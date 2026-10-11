import unittest

from csvlite import parse_line


class TestParseLine(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_line("a,b,c"), ["a", "b", "c"])

    def test_empty_fields(self):
        self.assertEqual(parse_line("a,,c,"), ["a", "", "c", ""])
        self.assertEqual(parse_line(""), [""])

    def test_quoted_comma(self):
        self.assertEqual(parse_line('1,"Smith, John",NY'), ["1", "Smith, John", "NY"])

    def test_escaped_quote(self):
        self.assertEqual(parse_line('"He said ""hi""",x'), ['He said "hi"', "x"])

    def test_quoted_empty(self):
        self.assertEqual(parse_line('"",b'), ["", "b"])

    def test_only_quotes_inside(self):
        self.assertEqual(parse_line('""""'), ['"'])

    def test_unterminated(self):
        with self.assertRaises(ValueError):
            parse_line('a,"broken')


if __name__ == "__main__":
    unittest.main()
