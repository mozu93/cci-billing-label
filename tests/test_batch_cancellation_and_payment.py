"""まとめて発行の入金額・参加キャンセルの回帰テスト。"""


def _seed_invoice(memory_db, *, cancelled=False):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members, set_project_members_cancelled,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued

    session = get_session()
    try:
        category = create_category(session, "青年部")
        template = create_item_template(session, category.id, "参加費", 5000, "人", 10,
                                        "invoice", "")
        project = create_project(session, "2026 参加費", category.id, 2026, "list")
        add_template_to_project(session, project.id, template.id)
        add_roster_entries(session, project.id, [{"organization_name": "○○商事"}])
        member = get_project_members(session, project.id)[0]
        invoice = create_issuance_for_member(session, project.id, member.id, "○○商事", "",
                                              "invoice", 2026, 5)
        mark_as_issued(session, invoice.id, None, "田中")
        if cancelled:
            set_project_members_cancelled(session, [member.id], True)
        return project.id, invoice.id
    finally:
        session.close()


def test_batch_project_paid_amount_uses_recorded_payment(qtbot, memory_db):
    from datetime import date
    from app.database.connection import get_session
    from app.services.issuance_service import record_payment
    from app.ui.project_tab import ProjectTab

    _project_id, invoice_id = _seed_invoice(memory_db)
    session = get_session()
    try:
        record_payment(session, invoice_id, date(2026, 5, 30), 1200, "振込")
    finally:
        session.close()

    tab = ProjectTab()
    qtbot.addWidget(tab)
    tab._year_combo.setCurrentIndex(tab._year_combo.findData(2026))
    assert tab._table.rowCount() == 1
    assert tab._table.item(0, 7).text() == "1"
    assert tab._table.item(0, 8).text() == "¥1,200"


def test_cancelled_member_is_hidden_from_payment_management(qtbot, memory_db):
    from app.ui.payment_dialog import PaymentManagementWidget

    project_id, _invoice_id = _seed_invoice(memory_db, cancelled=True)
    widget = PaymentManagementWidget()
    qtbot.addWidget(widget)
    for i in range(widget._proj_combo.count()):
        if widget._proj_combo.itemData(i) == project_id:
            widget._proj_combo.setCurrentIndex(i)
            break
    widget._load()
    assert widget._table.rowCount() == 0
