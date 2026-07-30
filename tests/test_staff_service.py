# tests/test_staff_service.py
import pytest
from app.services.staff_service import (
    create_staff, get_active_staff, deactivate_staff,
    set_password, verify_password,
)


def test_create_staff(db_session):
    staff = create_staff(db_session, "田中 太郎")
    assert staff.id is not None
    assert staff.name == "田中 太郎"
    assert staff.is_active is True


def test_get_active_staff(db_session):
    create_staff(db_session, "田中 太郎")
    create_staff(db_session, "鈴木 花子")
    result = get_active_staff(db_session)
    assert len(result) == 2


def test_deactivate_staff(db_session):
    staff = create_staff(db_session, "田中 太郎")
    deactivate_staff(db_session, staff.id)
    result = get_active_staff(db_session)
    assert len(result) == 0


def test_duplicate_name_raises(db_session):
    create_staff(db_session, "田中 太郎")
    with pytest.raises(Exception):
        create_staff(db_session, "田中 太郎")


def test_password_requires_at_least_eight_characters(db_session):
    staff = create_staff(db_session, "安全確認")

    with pytest.raises(ValueError, match="8文字以上"):
        set_password(db_session, staff.id, "short")


def test_password_hash_can_be_verified(db_session):
    staff = create_staff(db_session, "認証確認")
    set_password(db_session, staff.id, "secure-pass")

    assert verify_password(db_session, staff.id, "secure-pass") is True
    assert verify_password(db_session, staff.id, "wrong-pass") is False


def test_admin_account_is_not_auto_logged_in(qtbot, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from app.ui import login_dialog

    config = {"auto_login_staff_id": 7}
    session = MagicMock()
    saved = []
    monkeypatch.setattr(login_dialog, "get_config", lambda: config)
    monkeypatch.setattr(
        login_dialog, "save_config",
        lambda value: saved.append(value.copy()))
    monkeypatch.setattr(login_dialog, "get_session", lambda: session)
    monkeypatch.setattr(
        login_dialog, "get_staff",
        lambda _session, _staff_id: SimpleNamespace(
            id=7, name="管理者", is_admin=True, is_active=True))
    set_current = MagicMock()
    monkeypatch.setattr(
        login_dialog.current_user, "set_current", set_current)

    dialog = login_dialog.LoginDialog(skip_auto_login=True)
    qtbot.addWidget(dialog)
    dialog._try_auto_login()

    set_current.assert_not_called()
    assert saved[-1].get("auto_login_staff_id") is None
