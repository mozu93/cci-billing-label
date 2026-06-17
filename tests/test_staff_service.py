# tests/test_staff_service.py
import pytest
from app.services.staff_service import (
    create_staff, get_active_staff, deactivate_staff
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
