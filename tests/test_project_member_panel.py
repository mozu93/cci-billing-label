# tests/test_project_member_panel.py
from PyQt6.QtWidgets import QPushButton


def _button_texts(w):
    return [b.text() for b in w.findChildren(QPushButton)]


def test_entry_dialog_returns_values(qtbot, memory_db):
    from app.ui.project_member_panel import RosterEntryDialog
    dlg = RosterEntryDialog()
    qtbot.addWidget(dlg)
    dlg._fields["organization_name"].setText("○○商事")
    dlg._fields["representative_name"].setText("田中")
    dlg._fields["email"].setText("t@example.com")
    v = dlg.values()
    assert v["organization_name"] == "○○商事"
    assert v["representative_name"] == "田中"
    assert v["email"] == "t@example.com"


def test_panel_has_add_and_copy_buttons(qtbot, memory_db):
    from app.ui.project_member_panel import ProjectMemberPanel
    from app.services.project_service import create_project
    from app.database.connection import get_session
    s = get_session()
    try:
        proj = create_project(s, name="2026 青年部", category_id=None,
                              fiscal_year=2026, project_type="list")
        pid = proj.id
    finally:
        s.close()
    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    texts = _button_texts(panel)
    assert "行を追加" in texts
    assert "他の名簿からコピー" in texts


def test_member_panel_has_registration_date_column(qtbot, memory_db):
    from app.ui.project_member_panel import ProjectMemberPanel
    from app.services.project_service import create_project, add_roster_entries
    from app.database.connection import get_session
    s = get_session()
    proj = create_project(s, name="2026 視察研修", category_id=None,
                          fiscal_year=2026, project_type="list")
    add_roster_entries(s, proj.id, [{"organization_name": "○○商事"}])
    pid = proj.id
    s.close()

    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    headers = [panel._table.horizontalHeaderItem(i).text()
               for i in range(panel._table.columnCount())]
    assert "登録日" in headers
    assert panel._table.isSortingEnabled()
