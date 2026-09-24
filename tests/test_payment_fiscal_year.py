# tests/test_payment_fiscal_year.py
"""入金管理の年度絞り込み（年度は4月〜翌3月）。

まとめて発行の書類は名簿の年度、単発発行の書類は発行日で年度を決める。
単発発行の集計用名簿は名前だけで使い回され、年度が最初の年のままのため。
"""
from datetime import date, datetime

import pytest

from app.database.models import Issuance, ProjectMember

_LINES = [{"item_template_id": None, "item_name": "年会費", "quantity": 1,
           "unit": "式", "unit_price": 10000, "tax_rate": 10}]


@pytest.mark.parametrize("d, fy", [
    (date(2026, 4, 1), 2026), (date(2027, 3, 31), 2026),
    (date(2026, 3, 31), 2025), (date(2026, 12, 1), 2026),
])
def test_fiscal_year_of(d, fy):
    from app.services.issuance_service import fiscal_year_of
    assert fiscal_year_of(d) == fy


def _counter(session, issued_at, doc_type="invoice"):
    from app.services.issuance_service import create_direct_issuance
    iss = create_direct_issuance(
        session, lines_data=_LINES, recipient_organization="窓口",
        recipient_name="", doc_type=doc_type, fiscal_year=issued_at.year,
        month=issued_at.month, staff_id=None, staff_name="",
        delivery_method="印刷", project_name="直接発行")
    iss.issued_at = issued_at
    session.commit()
    return iss


def _batch(session, project, name="○○商店", status="発行済み", cancelled=False):
    pm = ProjectMember(project_id=project.id, organization_name=name,
                       is_cancelled=cancelled)
    session.add(pm)
    session.flush()
    iss = Issuance(project_id=project.id, project_member_id=pm.id, doc_type="invoice",
                   doc_number=f"INV-{project.fiscal_year}-{pm.id}", status=status,
                   amount=10000, issued_at=datetime(2026, 5, 1),
                   recipient_organization=name)
    session.add(iss)
    session.commit()
    return iss


@pytest.fixture
def data(db_session):
    from app.services.project_service import create_project
    p2025 = create_project(db_session, "2025年度 視察研修", None, 2025, "list")
    p2026 = create_project(db_session, "2026年度 視察研修", None, 2026, "list")
    return {
        "b2025": _batch(db_session, p2025, "前年度商店"),
        "b2026": _batch(db_session, p2026, "今年度商店"),
        # 単発発行：2027年2月は2026年度、2026年3月は2025年度
        "c2026": _counter(db_session, datetime(2027, 2, 10)),
        "c2025": _counter(db_session, datetime(2026, 3, 10)),
        "p2025": p2025, "p2026": p2026,
    }


def _ids(rows):
    return sorted(i.id for i in rows)


def test_payment_issuances_filtered_by_fiscal_year(db_session, data):
    from app.services.issuance_service import get_payment_issuances
    got = get_payment_issuances(db_session, fiscal_year=2026)
    assert _ids(got) == _ids([data["b2026"], data["c2026"]])
    got = get_payment_issuances(db_session, fiscal_year=2025)
    assert _ids(got) == _ids([data["b2025"], data["c2025"]])
    assert len(get_payment_issuances(db_session, fiscal_year=None)) == 4


def test_payment_issuances_by_project(db_session, data):
    from app.services.issuance_service import get_payment_issuances
    got = get_payment_issuances(db_session, fiscal_year=2026,
                                project_id=data["p2026"].id)
    assert _ids(got) == _ids([data["b2026"]])


def test_count_unpaid_before_fiscal_year(db_session, data):
    from app.services.issuance_service import count_unpaid_invoices_before
    # 前年度以前の未入金：まとめて発行1件（前年度商店）＋単発発行1件（2026年3月）
    assert count_unpaid_invoices_before(db_session, 2026) == 2
    # 支払済み・キャンセル済みの人は数えない
    _batch(db_session, data["p2025"], "支払済み商店", status="支払済み")
    _batch(db_session, data["p2025"], "キャンセル商店", cancelled=True)
    assert count_unpaid_invoices_before(db_session, 2026) == 2
    assert count_unpaid_invoices_before(db_session, 2025) == 0


def test_payment_fiscal_years(db_session, data):
    from app.services.issuance_service import get_payment_fiscal_years
    from app.services.project_service import create_project
    assert get_payment_fiscal_years(db_session, today=date(2026, 9, 25)) == [2026, 2025]
    # 書類がまだない名簿の年度も選べる
    create_project(db_session, "2027年度 新年会", None, 2027, "list")
    assert get_payment_fiscal_years(db_session, today=date(2026, 9, 25)) == [2027, 2026, 2025]
