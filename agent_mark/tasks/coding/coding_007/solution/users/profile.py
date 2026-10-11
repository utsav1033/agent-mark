from users.api import fetch_user


def display_name(user_id: int) -> str:
    user = fetch_user(user_id)
    return user["name"] if user else "<unknown>"
