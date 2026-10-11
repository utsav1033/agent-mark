"""Text helpers for the blog engine."""

import re
import unicodedata


def slugify(title: str, max_length: int = 50) -> str:
    """Convert a post title into a URL slug (see tests for the exact rules)."""
    ascii_text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-")
