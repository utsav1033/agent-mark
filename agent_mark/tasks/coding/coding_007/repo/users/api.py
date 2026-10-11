"""User lookup API."""

_DB = {1: {"id": 1, "name": "Ada"}, 2: {"id": 2, "name": "Linus"}}


def fetch_usr(user_id: int) -> dict | None:
    """Return the user record for user_id, or None if missing."""
    return _DB.get(user_id)
