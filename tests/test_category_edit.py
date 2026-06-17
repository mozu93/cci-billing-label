# tests/test_category_edit.py
"""業務名（カテゴリ）の編集機能のテスト。"""
from PyQt6.QtWidgets import QPushButton


def _button_texts(widget) -> list[str]:
    return [b.text() for b in widget.findChildren(QPushButton)]


def test_update_category_changes_name_and_order(db_session):
    from app.services.category_service import (
        create_category, update_category, get_active_categories
    )
    cat = create_category(db_session, "青年部", sort_order=1)
    update_category(db_session, cat.id, name="青年部会", sort_order=5)
    result = get_active_categories(db_session)
    assert result[0].name == "青年部会"
    assert result[0].sort_order == 5


def test_edit_dialog_prefills_and_returns_values(qtbot, memory_db):
    from app.ui.category_management import CategoryEditDialog
    dlg = CategoryEditDialog(name="青年部", sort_order=3)
    qtbot.addWidget(dlg)
    assert dlg._name.text() == "青年部"
    assert dlg._order.value() == 3
    dlg._name.setText("青年部会")
    dlg._order.setValue(7)
    assert dlg.values() == ("青年部会", 7)


def test_category_widget_has_edit(qtbot, memory_db):
    from app.ui.category_management import CategoryManagementWidget
    w = CategoryManagementWidget()
    qtbot.addWidget(w)
    assert "編集" in _button_texts(w)
    assert hasattr(w, "_edit")
