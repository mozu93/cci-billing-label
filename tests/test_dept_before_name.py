# tests/test_dept_before_name.py
"""所属・役職は、どの画面でも氏名（代表者名）の左に置く（宛名の並び「所属・役職　氏名」と同じ）。"""


def _project_with_member():
    from app.database.connection import get_session
    from app.services.project_service import add_roster_entries, create_project
    s = get_session()
    pid = create_project(s, "視察研修会", None, 2026, "list").id
    add_roster_entries(s, pid, [{"organization_name": "○○商店", "representative_name": "山田",
                                 "department": "代表取締役"}])
    s.close()
    return pid


def _headers(table):
    return [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]


def test_batch_issue_table(qtbot, memory_db):
    from app.ui.issuance_from_project import COL_DEPT, COL_REP, IssuanceFromProjectWidget
    pid = _project_with_member()
    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    w._proj_combo.setCurrentIndex(w._proj_combo.findData(pid))
    assert COL_DEPT == COL_REP - 1
    assert w._table.item(0, COL_DEPT).text() == "代表取締役"
    assert w._table.item(0, COL_REP).text() == "山田"


def test_roster_table_and_entry_dialog(qtbot, memory_db):
    from app.ui.project_member_panel import ProjectMemberPanel, RosterEntryDialog
    panel = ProjectMemberPanel(_project_with_member())
    qtbot.addWidget(panel)
    headers = _headers(panel._table)
    dept, name = headers.index("所属・役職名"), headers.index("氏名")
    assert dept == name - 1
    assert panel._table.item(0, dept).text() == "代表取締役"
    assert panel._table.item(0, name).text() == "山田"

    keys = [k for k, _ in RosterEntryDialog.FIELDS]
    assert keys.index("department") == keys.index("representative_name") - 1


def test_label_table(qtbot, memory_db):
    from app.ui.label_issuance_tab import COL_DEPT, COL_REP, _HEADERS
    assert COL_DEPT == COL_REP - 1
    assert _HEADERS[COL_DEPT] == "役職・所属" and _HEADERS[COL_REP] == "代表者名"


def test_member_master_dialog(qtbot, memory_db):
    from app.ui.member_import_widget import _MemberDialog
    keys = [k for k, _ in _MemberDialog._FIELDS]
    assert keys.index("department") == keys.index("representative_name") - 1
