"""User lookup API."""

import warnings

_DB = {1: {"id": 1, "name": "Ada"}, 2: {"id": 2, "name": "Linus"}}


def fetch_user(user_id: int) -> dict | None:
    """Return the user record for user_id, or None if missing."""
    return _DB.get(user_id)


def fetch_usr(user_id: int) -> dict | None:
    """Deprecated alias for fetch_user."""
    warnings.warn("fetch_usr is deprecated; use fetch_user", DeprecationWarning, stacklevel=2)
    return fetch_user(user_id)
