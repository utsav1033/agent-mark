"""Text helpers for the blog engine."""


def slugify(title: str, max_length: int = 50) -> str:
    """Convert a post title into a URL slug.

    Rules:
    - lowercase
    - ASCII only: accented Latin letters are transliterated (e.g. "é" -> "e"),
      any other non-ASCII character is dropped
    - every run of characters that are not ASCII letters or digits becomes a
      single hyphen
    - no leading or trailing hyphens
    - at most max_length characters, and truncation must not leave a trailing
      hyphen
    - an input with no usable characters returns ""
    """
    raise NotImplementedError
