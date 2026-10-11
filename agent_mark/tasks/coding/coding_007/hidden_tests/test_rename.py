import pathlib
import unittest
import warnings

from users import admin, api, profile


class TestRename(unittest.TestCase):
    def test_new_name(self):
        self.assertEqual(api.fetch_user(1)["name"], "Ada")
        self.assertIsNone(api.fetch_user(99))

    def test_alias_warns_and_works(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertEqual(api.fetch_usr(2)["name"], "Linus")
        self.assertTrue(any(issubclass(w.category, DeprecationWarning) for w in caught))

    def test_call_sites_do_not_warn(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            self.assertEqual(profile.display_name(1), "Ada")
            self.assertEqual(profile.display_name(5), "<unknown>")
            self.assertTrue(admin.exists(2))

    def test_no_old_name_at_call_sites(self):
        for f in ("profile.py", "admin.py"):
            src = pathlib.Path("users", f).read_text(encoding="utf-8")
            self.assertNotIn("fetch_usr", src, f)


if __name__ == "__main__":
    unittest.main()
