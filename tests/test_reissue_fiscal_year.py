# tests/test_reissue_fiscal_year.py
"""修正・再発行の年度（4月〜翌3月）。

まとめて発行の書類は名簿の年度、単発発行の書類は発行日で年度を決める。
以前は名簿の年度だけで絞り込んでいたため、単発発行の書類（毎年使い回す
集計用名簿にひも付く）は、最初に集計用名簿を作った年度にしか出なかった。
"""
from datetime import datetime

from app.database.models import Issuance

_LINES = [{"item_template_id": None, "item_name": "年会費", "quantity": 1,
           "unit": "式", "unit_price": 10000, "tax_rate": 10}]


def _counter(session, issued_at):
    from app.services.issuance_service import create_direct_issuance
    iss = create_direct_issuance(
        session, lines_data=_LINES, recipient_organization="窓口",
        recipient_name="", doc_type="invoice", fiscal_year=issued_at.year,
        month=issued_at.month, staff_id=None, staff_name="",
        delivery_method="印刷", project_name="直接発行")
    iss.issued_at = issued_at
    session.commit()
    return iss.id


def _batch(session, fiscal_year):
    from app.services.project_service import create_project
    p = create_project(session, f"{fiscal_year}年度 視察研修", None, fiscal_year, "list")
    iss = Issuance(project_id=p.id, doc_type="invoice", doc_number=f"INV-B{fiscal_year}",
                   status="発行済み", amount=10000, issued_at=datetime(2026, 5, 1),
                   recipient_organization="○○商店")
    session.add(iss)
    session.commit()
    return iss.id


def test_counter_documents_found_by_issued_date(db_session):
    from app.services.issuance_service import search_reissuable_issuances
    # 集計用名簿は 2025年4月の発行で作られ、年度は2025のまま使い回される
    first = _counter(db_session, datetime(2025, 4, 10))    # 2025年度
    later = _counter(db_session, datetime(2027, 2, 10))    # 2026年度
    batch = _batch(db_session, 2026)

    ids_2026 = sorted(i.id for i, _ in search_reissuable_issuances(db_session, fiscal_year=2026))
    assert ids_2026 == sorted([later, batch])
    ids_2025 = [i.id for i, _ in search_reissuable_issuances(db_session, fiscal_year=2025)]
    assert ids_2025 == [first]
    assert len(search_reissuable_issuances(db_session)) == 3


class _Feb2027:
    @staticmethod
    def today():
        from datetime import date
        return date(2027, 2, 10)


def test_default_year_is_fiscal_year_starting_april(qtbot, memory_db, monkeypatch):
    """2027年2月に開くと2026年度を初期表示する（他の画面とそろえる）。"""
    import app.ui.reissue_tab as reissue_tab
    monkeypatch.setattr(reissue_tab, "date", _Feb2027)
    w = reissue_tab.ReissueWidget()
    qtbot.addWidget(w)
    assert w._year_combo.currentData() == 2026
    assert w._year_combo.itemData(1) == 2027   # 「すべて」の次に翌年度
