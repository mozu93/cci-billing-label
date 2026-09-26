# tests/test_payment_dialog_hides_empty_columns.py
"""入金管理：会員番号・メールなど任意項目が全行空欄なら列を隠す。"""
from datetime import datetime

from app.database.models import Issuance
from app.ui.payment_dialog import _COL_MEMBER, _COL_MAIL, _COL_DEST


def _widget(qtbot):
    from app.ui.payment_dialog import PaymentManagementWidget
    w = PaymentManagementWidget()
    qtbot.addWidget(w)
    return w


def _seed(fiscal_year=2026):
    from app.database.connection import get_session
    from app.services.project_service import create_project
    session = get_session()
    try:
        proj = create_project(session, "視察研修", None, fiscal_year, "list")
        session.add(Issuance(
            project_id=proj.id, doc_type="invoice", doc_number="INV-1",
            status="発行済み", amount=10000, issued_at=datetime(2026, 5, 1),
            recipient_organization="○○商店"))
        session.commit()
    finally:
        session.close()


def test_member_and_mail_columns_hidden_when_no_data(qtbot, memory_db):
    _seed()
    w = _widget(qtbot)
    w._year_combo.setCurrentIndex(w._year_combo.findData(2026))
    w._status_combo.setCurrentText("すべて")
    assert w._table.rowCount() == 1
    assert w._table.isColumnHidden(_COL_MEMBER)
    assert w._table.isColumnHidden(_COL_MAIL)
    assert not w._table.isColumnHidden(_COL_DEST)   # 宛先は常に表示
