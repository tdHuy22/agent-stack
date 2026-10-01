import unittest
from text import slugify


class SlugifyTest(unittest.TestCase):
    def test_lowercase_and_spaces(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_collapse_and_strip(self):
        self.assertEqual(slugify("  --A  B--  "), "a-b")

    def test_symbols(self):
        self.assertEqual(slugify("C++ & Rust!"), "c-rust")


if __name__ == "__main__":
    unittest.main()
