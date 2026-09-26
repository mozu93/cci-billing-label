# tests/test_payment_category_column.py
"""入金管理の一覧：業務名と件名の列で、どの業務のどの件名かわかるようにする。"""
from datetime import datetime

from app.database.models import Issuance
from app.ui.payment_dialog import _COL_CAT, _COL_PROJ, _DIRECT_ISSUANCE_LABEL


def _category(session, name):
    from app.database.models import Category
    cat = Category(name=name, sort_order=0, is_active=True)
    session.add(cat)
    session.flush()
    return cat.id


def _widget(qtbot):
    from app.ui.payment_dialog import PaymentManagementWidget
    w = PaymentManagementWidget()
    qtbot.addWidget(w)
    return w


def test_regular_project_shows_category_and_subject(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.project_service import create_project
    session = get_session()
    try:
        cat_id = _category(session, "視察研修")
        proj = create_project(
            session, "フラワーアレンジメント講習会", cat_id, 2026, "list")
        session.add(Issuance(
            project_id=proj.id, doc_type="invoice", doc_number="INV-1",
            status="発行済み", amount=10000, issued_at=datetime(2026, 5, 1),
            recipient_organization="○○商店"))
        session.commit()
    finally:
        session.close()

    w = _widget(qtbot)
    w._year_combo.setCurrentIndex(w._year_combo.findData(2026))
    w._status_combo.setCurrentText("すべて")
    assert w._table.rowCount() == 1
    assert w._table.item(0, _COL_CAT).text() == "視察研修"
    assert w._table.item(0, _COL_PROJ).text() == "フラワーアレンジメント講習会"


def test_direct_issuance_shows_business_name_and_marker(qtbot, memory_db):
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
            project_name="四日市を美しくする会")
    finally:
        session.close()

    w = _widget(qtbot)
    w._year_combo.setCurrentIndex(w._year_combo.findData(2026))
    w._status_combo.setCurrentText("すべて")
    assert w._table.rowCount() == 1
    assert w._table.item(0, _COL_CAT).text() == "四日市を美しくする会"
    assert w._table.item(0, _COL_PROJ).text() == _DIRECT_ISSUANCE_LABEL
