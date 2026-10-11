"""Discount rules."""

DISCOUNT_CODES = {"SAVE10": 0.10, "HALFOFF": 0.50}


def apply_discount(amount: float, code: str | None) -> float:
    """Return amount after applying a discount code (unknown codes are ignored)."""
    if not code:
        return amount
    rate = DISCOUNT_CODES.get(code.upper(), 0.0)
    return round(amount * (1 - rate), 2)
