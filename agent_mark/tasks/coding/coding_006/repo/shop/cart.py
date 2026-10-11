"""Shopping cart."""

from shop.pricing import apply_discount


class Cart:
    def __init__(self) -> None:
        self.lines: list[tuple[str, float, int]] = []
        self.discount_code: str | None = None

    def add(self, sku: str, unit_price: float, qty: int = 1) -> None:
        self.lines.append((sku, unit_price, qty))

    def subtotal(self) -> float:
        raw = sum(price * qty for _, price, qty in self.lines)
        return apply_discount(raw, self.discount_code)

    def total(self) -> float:
        """Amount charged to the customer."""
        return apply_discount(self.subtotal(), self.discount_code)
