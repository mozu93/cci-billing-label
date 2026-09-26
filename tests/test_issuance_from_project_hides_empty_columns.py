# tests/test_issuance_from_project_hides_empty_columns.py
"""請求書・領収書を発行する名簿：フリガナ・所属など任意項目が空なら列を隠す。"""
from app.ui.issuance_from_project import COL_KANA, COL_DEPT, COL_NUM


def _project_with_members(kana_values):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
    )
    s = get_session()
    try:
        cat = create_category(s, "青年部")
        tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
        proj = create_project(s, "2026 青年部会費", cat.id, 2026, "list")
        add_template_to_project(s, proj.id, tmpl.id)
        add_roster_entries(s, proj.id, [
            {"organization_name": f"事業所{i}", "organization_kana": kana}
            for i, kana in enumerate(kana_values)
        ])
        return proj.id
    finally:
        s.close()


def _select_project(w, proj_id):
    for i in range(w._proj_combo.count()):
        if w._proj_combo.itemData(i) == proj_id:
            w._proj_combo.setCurrentIndex(i)
            return


def test_kana_column_hidden_when_roster_has_no_kana(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    proj_id = _project_with_members(["", ""])
    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    assert w._table.isColumnHidden(COL_KANA)


def test_kana_column_shown_when_roster_has_kana(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    proj_id = _project_with_members(["ジギョウショゼロ", ""])
    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    assert not w._table.isColumnHidden(COL_KANA)


def test_org_name_column_stays_visible_even_when_empty(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    from app.ui.issuance_from_project import COL_ORG
    proj_id = _project_with_members(["", ""])
    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    assert not w._table.isColumnHidden(COL_ORG)
