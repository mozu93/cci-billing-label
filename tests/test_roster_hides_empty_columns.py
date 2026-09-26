# tests/test_roster_hides_empty_columns.py
"""まとめて発行の名簿：フリガナなど任意項目が全行空欄なら列を隠す。"""
from app.ui.project_member_panel import ProjectMemberPanel


def _panel(qtbot, entries):
    from app.services.project_service import create_project, add_roster_entries
    from app.database.connection import get_session
    s = get_session()
    try:
        proj = create_project(s, name="2026 視察研修", category_id=None,
                              fiscal_year=2026, project_type="list")
        add_roster_entries(s, proj.id, entries)
        pid = proj.id
    finally:
        s.close()
    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    return panel


def test_kana_column_hidden_when_all_rows_empty(qtbot, memory_db):
    panel = _panel(qtbot, [
        {"organization_name": "○○商事", "organization_kana": ""},
        {"organization_name": "△△工業", "organization_kana": ""},
    ])
    assert panel._table.isColumnHidden(4)   # フリガナ


def test_kana_column_shown_when_any_row_has_value(qtbot, memory_db):
    panel = _panel(qtbot, [
        {"organization_name": "○○商事", "organization_kana": "マルマルショウジ"},
        {"organization_name": "△△工業", "organization_kana": ""},
    ])
    assert not panel._table.isColumnHidden(4)


def test_core_columns_stay_visible_even_when_empty(qtbot, memory_db):
    panel = _panel(qtbot, [{"organization_name": "○○商事"}])
    assert not panel._table.isColumnHidden(3)   # 事業所名は常に表示
