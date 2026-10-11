from users import api


def exists(user_id: int) -> bool:
    return api.fetch_usr(user_id) is not None
