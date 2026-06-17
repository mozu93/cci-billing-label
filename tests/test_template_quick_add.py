# tests/test_template_quick_add.py
"""発行作業中にその場で請求項目テンプレートを追加する近道機能のテスト。"""
from PyQt6.QtWidgets import QPushButton


def _button_texts(widget) -> list[str]:
    return [b.text() for b in widget.findChildren(QPushButton)]


def test_dialog_preselects_default_category(qtbot, memory_db):
    """default_category_id を渡すと、その カテゴリが初期選択される。"""
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.ui.item_template_management import ItemTemplateDialog

    session = get_session()
    try:
        create_category(session, "青年部")
        cat2 = create_category(session, "検定")
        cat2_id = cat2.id
    finally:
        session.close()

    dlg = ItemTemplateDialog(default_category_id=cat2_id)
    qtbot.addWidget(dlg)
    assert dlg._category.currentData() == cat2_id


def test_counter_widget_has_quick_add_button(qtbot, memory_db):
    """窓口発行（フリー発行）に新規テンプレートの近道ボタンとハンドラがある。"""
    from app.ui.issuance_counter import IssuanceCounterWidget

    w = IssuanceCounterWidget()
    qtbot.addWidget(w)
    assert "＋ 新規テンプレート…" in _button_texts(w)
    assert hasattr(w, "_add_template_master")


def test_counter_reload_master_picks_up_new_template(qtbot, memory_db):
    """テンプレート追加後の再読込で、新しいテンプレートが選択肢に反映される。"""
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.ui.issuance_counter import IssuanceCounterWidget

    w = IssuanceCounterWidget()
    qtbot.addWidget(w)
    w._reload_master()
    assert w._templates == []

    session = get_session()
    try:
        cat = create_category(session, "青年部")
        create_item_template(session, cat.id, "青年部会費", 10000, "式", 0, "invoice", "")
    finally:
        session.close()

    w._reload_master()
    assert any(t.name == "青年部会費" for t in w._templates)


def test_project_form_has_quick_add_button(qtbot, memory_db):
    """まとめて発行の事業登録フォームに新規テンプレートの近道ボタンがある。"""
    from app.ui.project_form import ProjectFormDialog

    dlg = ProjectFormDialog()
    qtbot.addWidget(dlg)
    assert "＋ 新規テンプレート…" in _button_texts(dlg)
    assert hasattr(dlg, "_add_template_master")
