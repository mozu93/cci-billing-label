# tests/test_delete_confirmation.py
"""削除・無効化操作で確認ダイアログを挟むことのテスト。

QMessageBox.question をモンキーパッチで No / Yes に固定し、
キャンセル時はレコードが残り、承認時のみ削除されることを確認する。
"""
from PyQt6.QtWidgets import QMessageBox


def _patch_question(monkeypatch, answer):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answer)


def test_category_deactivate_requires_confirmation(qtbot, memory_db, monkeypatch):
    from app.database.connection import get_session
    from app.services.category_service import create_category, get_active_categories
    from app.ui.category_management import CategoryManagementWidget

    session = get_session()
    try:
        create_category(session, "青年部")
    finally:
        session.close()

    w = CategoryManagementWidget()
    qtbot.addWidget(w)
    w._list.setCurrentRow(0)

    # キャンセル → 残る
    _patch_question(monkeypatch, QMessageBox.StandardButton.No)
    w._deactivate()
    session = get_session()
    try:
        assert len(get_active_categories(session)) == 1
    finally:
        session.close()

    # 承認 → 無効化される
    _patch_question(monkeypatch, QMessageBox.StandardButton.Yes)
    w._deactivate()
    session = get_session()
    try:
        assert get_active_categories(session) == []
    finally:
        session.close()


def test_staff_deactivate_requires_confirmation(qtbot, memory_db, monkeypatch):
    from app.database.connection import get_session
    from app.services.staff_service import create_staff, get_all_staff
    from app.ui.staff_management import StaffManagementWidget

    session = get_session()
    try:
        create_staff(session, "山田太郎")
    finally:
        session.close()

    w = StaffManagementWidget()
    qtbot.addWidget(w)
    w._table.selectRow(0)

    # キャンセル → 有効のまま
    _patch_question(monkeypatch, QMessageBox.StandardButton.No)
    w._deactivate()
    session = get_session()
    try:
        assert get_all_staff(session)[0].is_active is True
    finally:
        session.close()

    # 承認 → 無効化される
    _patch_question(monkeypatch, QMessageBox.StandardButton.Yes)
    w._deactivate()
    session = get_session()
    try:
        assert get_all_staff(session)[0].is_active is False
    finally:
        session.close()
