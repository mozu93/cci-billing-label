# tests/test_payment_direct_issuance_due_date.py
"""単発発行の支払期限：入金管理に表示できるよう Issuance に保存する。

以前は画面入力の支払期限がPDF印字にしか使われずDBに保存されなかったため、
入金管理の「支払期限」列が単発発行の行だけ空欄になっていた。
"""
from datetime import date

from app.ui.payment_dialog import _COL_DUE


def _widget(qtbot):
    from app.ui.payment_dialog import PaymentManagementWidget
    w = PaymentManagementWidget()
    qtbot.addWidget(w)
    return w


def test_create_direct_issuance_saves_due_date(db_session):
    from app.services.issuance_service import create_direct_issuance
    lines = [{"item_template_id": None, "item_name": "年会費", "quantity": 1,
              "unit": "式", "unit_price": 10000, "tax_rate": 10}]
    iss = create_direct_issuance(
        db_session, lines_data=lines, recipient_organization="窓口",
        recipient_name="", doc_type="invoice", fiscal_year=2026, month=4,
        staff_id=None, staff_name="", delivery_method="印刷",
        project_name="四日市を美しくする会", due_date=date(2026, 5, 31))

    assert iss.due_date == date(2026, 5, 31)


def test_update_direct_issuance_saves_due_date(db_session):
    from app.services.issuance_service import (
        create_direct_issuance, update_direct_issuance)
    lines = [{"item_template_id": None, "item_name": "年会費", "quantity": 1,
              "unit": "式", "unit_price": 10000, "tax_rate": 10}]
    iss = create_direct_issuance(
        db_session, lines_data=lines, recipient_organization="窓口",
        recipient_name="", doc_type="invoice", fiscal_year=2026, month=4,
        staff_id=None, staff_name="", delivery_method="印刷",
        project_name="四日市を美しくする会", due_date=date(2026, 5, 31))

    update_direct_issuance(
        db_session, issuance_id=iss.id, lines_data=lines,
        recipient_organization="窓口", recipient_name="",
        delivery_method="印刷", due_date=date(2026, 6, 30))

    assert iss.due_date == date(2026, 6, 30)


def test_payment_dialog_shows_direct_issuance_due_date(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.issuance_service import create_direct_issuance
    session = get_session()
    try:
        lines = [{"item_template_id": None, "item_name": "年会費", "quantity": 1,
                  "unit": "式", "unit_price": 10000, "tax_rate": 10}]
        create_direct_issuance(
            session, lines_data=lines, recipient_organization="窓口",
            recipient_name="", doc_type="invoice", fiscal_year=2026, month=4,
            staff_id=None, staff_name="", delivery_method="印刷",
            project_name="四日市を美しくする会", due_date=date(2026, 5, 31))
    finally:
        session.close()

    w = _widget(qtbot)
    w._year_combo.setCurrentIndex(w._year_combo.findData(2026))
    w._status_combo.setCurrentText("すべて")
    assert w._table.rowCount() == 1
    assert w._table.item(0, _COL_DUE).text() == "2026/05/31"


def test_no_doctype_dropdown_and_receipts_excluded(qtbot, memory_db):
    """領収書は発行と同時に支払済みになるため、入金管理は請求書のみを扱う。"""
    from app.database.connection import get_session
    from app.services.issuance_service import create_direct_issuance
    session = get_session()
    try:
        lines = [{"item_template_id": None, "item_name": "年会費", "quantity": 1,
                  "unit": "式", "unit_price": 10000, "tax_rate": 10}]
        create_direct_issuance(
            session, lines_data=lines, recipient_organization="窓口",
            recipient_name="", doc_type="receipt", fiscal_year=2026, month=4,
            staff_id=None, staff_name="", delivery_method="印刷",
            project_name="四日市を美しくする会")
    finally:
        session.close()

    w = _widget(qtbot)
    assert not hasattr(w, "_doctype_combo")
    w._year_combo.setCurrentIndex(w._year_combo.findData(2026))
    w._status_combo.setCurrentText("すべて")
    assert w._table.rowCount() == 0
