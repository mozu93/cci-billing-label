# tests/test_payment_column_order.py
"""入金管理の列順：宛先の次に業務名・件名。フリガナは非表示だが検索は効く。"""
from datetime import datetime

from app.database.models import Issuance, ProjectMember
from app.ui.payment_dialog import (
    _COL_CAT, _COL_DEST, _COL_KANA, _COL_PROJ,
)


def _widget(qtbot):
    from app.ui.payment_dialog import PaymentManagementWidget
    w = PaymentManagementWidget()
    qtbot.addWidget(w)
    return w


def _seed(session, org_kana):
    from app.services.project_service import create_project
    proj = create_project(session, "視察研修", None, 2026, "list")
    pm = ProjectMember(
        project_id=proj.id, member_number="1", organization_name="○○商店",
        organization_kana=org_kana)
    session.add(pm)
    session.flush()
    session.add(Issuance(
        project_id=proj.id, project_member_id=pm.id, doc_type="invoice",
        doc_number="INV-1", status="発行済み", amount=10000,
        issued_at=datetime(2026, 5, 1), recipient_organization="○○商店"))
    session.commit()


def test_business_name_and_subject_come_right_after_destination(qtbot, memory_db):
    assert _COL_CAT == _COL_DEST + 1
    assert _COL_PROJ == _COL_CAT + 1


def test_kana_column_is_hidden(qtbot, memory_db):
    w = _widget(qtbot)
    assert w._table.isColumnHidden(_COL_KANA)


def test_search_still_matches_kana_even_though_hidden(qtbot, memory_db):
    from app.database.connection import get_session
    session = get_session()
    try:
        _seed(session, "マルマルショウテン")
    finally:
        session.close()

    w = _widget(qtbot)
    w._year_combo.setCurrentIndex(w._year_combo.findData(2026))
    w._status_combo.setCurrentText("すべて")
    assert w._table.rowCount() == 1

    w._search.setText("マルマルショウテン")
    w._apply_search()
    assert not w._table.isRowHidden(0)

    w._search.setText("該当なし")
    w._apply_search()
    assert w._table.isRowHidden(0)
