import unittest

from shop.cart import Cart
from shop.pricing import apply_discount


class TestCart(unittest.TestCase):
    def test_ticket(self):
        c = Cart()
        c.add("mug", 25.0, 2)
        c.discount_code = "SAVE10"
        self.assertEqual(c.total(), 45.0)

    def test_subtotal_is_pre_discount(self):
        c = Cart()
        c.add("mug", 25.0, 2)
        c.discount_code = "HALFOFF"
        self.assertEqual(c.subtotal(), 50.0)
        self.assertEqual(c.total(), 25.0)

    def test_no_code(self):
        c = Cart()
        c.add("pen", 1.5, 3)
        self.assertEqual(c.total(), 4.5)

    def test_pricing_contract_unchanged(self):
        self.assertEqual(apply_discount(100.0, "save10"), 90.0)
        self.assertEqual(apply_discount(100.0, "BOGUS"), 100.0)
        self.assertEqual(apply_discount(100.0, None), 100.0)


if __name__ == "__main__":
    unittest.main()
