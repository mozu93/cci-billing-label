# tests/test_category_quick_add.py
"""フリー発行でその場で業務名（カテゴリ）を登録する近道のテスト。"""
from PyQt6.QtWidgets import QPushButton


def _button_texts(widget) -> list[str]:
    return [b.text() for b in widget.findChildren(QPushButton)]


def test_counter_widget_has_category_quick_add(qtbot, memory_db):
    from app.ui.issuance_counter import IssuanceCounterWidget
    w = IssuanceCounterWidget()
    qtbot.addWidget(w)
    assert "＋ 新規業務名登録" in _button_texts(w)
    assert hasattr(w, "_add_category_master")


def test_reload_master_picks_up_new_category(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.ui.issuance_counter import IssuanceCounterWidget

    w = IssuanceCounterWidget()
    qtbot.addWidget(w)
    w._reload_master()
    assert w._categories == []

    session = get_session()
    try:
        create_category(session, "青年部")
    finally:
        session.close()

    w._reload_master()
    assert any(c.name == "青年部" for c in w._categories)


def test_category_edit_dialog_custom_title(qtbot, memory_db):
    from app.ui.category_management import CategoryEditDialog
    dlg = CategoryEditDialog(title="業務名の登録")
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "業務名の登録"
