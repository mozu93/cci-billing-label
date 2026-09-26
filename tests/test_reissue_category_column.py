# tests/test_reissue_category_column.py
"""修正・再発行の一覧：業務名と件名を分けて表示する。

単発発行（project_type="counter"）は Project.name に業務名が入っており、
件名に相当するものが無い。以前は「件名」列にこの業務名がそのまま出ていた。
"""
from datetime import datetime

from app.database.models import Issuance
from app.ui.reissue_tab import COL_CAT, COL_PROJ, _DIRECT_ISSUANCE_LABEL


def _category(session, name):
    from app.database.models import Category
    cat = Category(name=name, sort_order=0, is_active=True)
    session.add(cat)
    session.flush()
    return cat.id


def _project(session, name, category_id, fiscal_year):
    from app.services.project_service import create_project
    return create_project(session, name, category_id, fiscal_year, "list")


def _direct_issuance(session, project_name):
    from app.services.issuance_service import create_direct_issuance
    lines = [{"item_template_id": None, "item_name": "年会費", "quantity": 1,
              "unit": "式", "unit_price": 10000, "tax_rate": 10}]
    return create_direct_issuance(
        session, lines_data=lines, recipient_organization="窓口",
        recipient_name="", doc_type="invoice", fiscal_year=2026, month=4,
        staff_id=None, staff_name="", delivery_method="印刷",
        project_name=project_name)


def _widget(qtbot):
    from app.ui.reissue_tab import ReissueWidget
    w = ReissueWidget()
    qtbot.addWidget(w)
    return w


def test_regular_project_shows_category_and_subject(qtbot, memory_db):
    from app.database.connection import get_session
    session = get_session()
    try:
        cat_id = _category(session, "視察研修")
        proj = _project(session, "フラワーアレンジメント講習会", cat_id, 2026)
        session.add(Issuance(
            project_id=proj.id, doc_type="invoice", doc_number="INV-1",
            status="発行済み", amount=10000, issued_at=datetime(2026, 5, 1),
            recipient_organization="○○商店"))
        session.commit()
    finally:
        session.close()

    w = _widget(qtbot)
    w._year_combo.setCurrentIndex(w._year_combo.findData(2026))
    assert w._table.rowCount() == 1
    assert w._table.item(0, COL_CAT).text() == "視察研修"
    assert w._table.item(0, COL_PROJ).text() == "フラワーアレンジメント講習会"


def test_direct_issuance_shows_business_name_and_marker(qtbot, memory_db):
    from app.database.connection import get_session
    session = get_session()
    try:
        _direct_issuance(session, "四日市を美しくする会")
    finally:
        session.close()

    w = _widget(qtbot)
    w._year_combo.setCurrentIndex(w._year_combo.findData(2026))
    assert w._table.rowCount() == 1
    assert w._table.item(0, COL_CAT).text() == "四日市を美しくする会"
    assert w._table.item(0, COL_PROJ).text() == _DIRECT_ISSUANCE_LABEL
