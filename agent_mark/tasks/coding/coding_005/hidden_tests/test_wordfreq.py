import contextlib
import io
import os
import tempfile
import unittest

import wordfreq

TEXT = "the cat and the hat. The bat and a cat! zebra"


def run(*args):
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(TEXT)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = wordfreq.main([*args, path])
    finally:
        os.remove(path)
    return code, out.getvalue().splitlines()


class TestWordFreq(unittest.TestCase):
    def test_default_unchanged(self):
        _, lines = run()
        self.assertEqual(lines, ["the 3", "and 2", "cat 2", "a 1", "bat 1", "hat 1", "zebra 1"])

    def test_top(self):
        _, lines = run("--top", "2")
        self.assertEqual(lines, ["the 3", "and 2"])

    def test_top_tie_break(self):
        _, lines = run("--top", "4")
        self.assertEqual(lines, ["the 3", "and 2", "cat 2", "a 1"])

    def test_top_larger_than_vocab(self):
        _, lines = run("--top", "100")
        self.assertEqual(len(lines), 7)

    def test_top_invalid(self):
        for bad in ("0", "-1"):
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                run("--top", bad)
            self.assertNotEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
