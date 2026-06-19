# app/services/staff_service.py
import hashlib
import secrets
from sqlalchemy.orm import Session
from app.database.models import Staff

_MAX_ADMINS = 2


def _hash_password(raw: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}:{h.hex()}"


def _check_password(raw: str, stored: str) -> bool:
    try:
        salt, hashed = stored.split(":", 1)
        h = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return h.hex() == hashed
    except Exception:
        return False


def create_staff(session: Session, name: str,
                 supervisor_id: int | None = None) -> Staff:
    staff = Staff(name=name, supervisor_id=supervisor_id)
    session.add(staff)
    session.commit()
    session.refresh(staff)
    return staff


def get_staff(session: Session, staff_id: int) -> Staff | None:
    return session.get(Staff, staff_id)


def get_active_staff(session: Session) -> list[Staff]:
    return session.query(Staff).filter_by(is_active=True).order_by(Staff.name).all()


def get_all_staff(session: Session) -> list[Staff]:
    return session.query(Staff).order_by(Staff.name).all()


def deactivate_staff(session: Session, staff_id: int) -> None:
    staff = session.get(Staff, staff_id)
    if staff:
        staff.is_active = False
        session.commit()


def reactivate_staff(session: Session, staff_id: int) -> None:
    staff = session.get(Staff, staff_id)
    if staff:
        staff.is_active = True
        session.commit()


def update_staff_name(session: Session, staff_id: int, name: str) -> Staff:
    staff = session.get(Staff, staff_id)
    staff.name = name
    session.commit()
    return staff


def update_staff(session: Session, staff_id: int, name: str,
                 supervisor_id: int | None = None) -> Staff:
    staff = session.get(Staff, staff_id)
    staff.name = name
    staff.supervisor_id = supervisor_id
    session.commit()
    return staff


# ── パスワード管理 ────────────────────────────────────────

def set_password(session: Session, staff_id: int, raw_password: str) -> None:
    """パスワードをハッシュ化して保存する。"""
    staff = session.get(Staff, staff_id)
    if staff:
        staff.password_hash = _hash_password(raw_password)
        session.commit()


def verify_password(session: Session, staff_id: int, raw_password: str) -> bool:
    """パスワードを照合する。"""
    staff = session.get(Staff, staff_id)
    if not staff or not staff.password_hash:
        return False
    return _check_password(raw_password, staff.password_hash)


def reset_password(session: Session, staff_id: int) -> None:
    """パスワードをリセット（NULL）する。次回ログイン時に再設定を求める。"""
    staff = session.get(Staff, staff_id)
    if staff:
        staff.password_hash = None
        session.commit()


# ── 管理者管理 ────────────────────────────────────────────

def count_admins(session: Session) -> int:
    return session.query(Staff).filter_by(is_admin=True, is_active=True).count()


def has_any_admin(session: Session) -> bool:
    return count_admins(session) > 0


def set_admin(session: Session, staff_id: int, is_admin: bool) -> None:
    """管理者フラグを設定する。管理者は最大2名まで。"""
    if is_admin and count_admins(session) >= _MAX_ADMINS:
        raise ValueError(f"管理者は最大{_MAX_ADMINS}名まで設定できます。")
    staff = session.get(Staff, staff_id)
    if staff:
        staff.is_admin = is_admin
        session.commit()
