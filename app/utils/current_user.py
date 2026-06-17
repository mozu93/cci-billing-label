# app/utils/current_user.py
_staff_id: int | None = None
_staff_name: str = ""
_is_admin: bool = False


def set_current(staff_id: int, staff_name: str, is_admin: bool = False) -> None:
    global _staff_id, _staff_name, _is_admin
    _staff_id = staff_id
    _staff_name = staff_name
    _is_admin = is_admin


def get_id() -> int | None:
    return _staff_id


def get_name() -> str:
    return _staff_name


def is_admin() -> bool:
    return _is_admin


def clear() -> None:
    global _staff_id, _staff_name, _is_admin
    _staff_id = None
    _staff_name = ""
    _is_admin = False


def is_logged_in() -> bool:
    return _staff_id is not None
