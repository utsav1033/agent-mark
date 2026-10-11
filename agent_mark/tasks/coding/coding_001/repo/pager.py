"""Simple list pagination helpers."""


def paginate(items: list, page: int, per_page: int = 10) -> list:
    """Return the items shown on a 1-indexed page. Pages past the end are empty."""
    start = page * per_page
    return items[start:start + per_page]


def page_count(n_items: int, per_page: int = 10) -> int:
    """Number of pages needed to show n_items (0 items -> 0 pages)."""
    return n_items // per_page
