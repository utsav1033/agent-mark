from users.api import fetch_usr


def display_name(user_id: int) -> str:
    user = fetch_usr(user_id)
    return user["name"] if user else "<unknown>"
