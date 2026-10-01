import unittest
from users import change_email, create_user


class UsersTest(unittest.TestCase):
    def test_create_normalizes(self):
        self.assertEqual(create_user("  An@Example.com ", "An")["email"], "an@example.com")

    def test_change_rejects(self):
        with self.assertRaises(ValueError):
            change_email({"email": "a@b.co"}, "không-phải-email")


if __name__ == "__main__":
    unittest.main()
