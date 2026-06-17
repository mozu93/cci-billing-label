# tests/test_report_service.py
from datetime import date
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.project_service import (
    create_project, add_template_to_project, add_roster_entries,
    get_project_members
)
from app.services.issuance_service import (
    create_issuance_for_member, mark_as_issued, record_payment
)
from app.services.report_service import (
    get_unpaid_report, get_payment_report, get_project_summary
)


def _setup(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
        {"organization_name": "△△産業", "representative_name": "鈴木"},
    ])
    pms = get_project_members(db_session, proj.id)
    iss1 = create_issuance_for_member(
        db_session, proj.id, pms[0].id,
        recipient_organization=pms[0].organization_name,
        recipient_name=pms[0].representative_name,
        doc_type="invoice", fiscal_year=2026, month=5
    )
    iss2 = create_issuance_for_member(
        db_session, proj.id, pms[1].id,
        recipient_organization=pms[1].organization_name,
        recipient_name=pms[1].representative_name,
        doc_type="invoice", fiscal_year=2026, month=5
    )
    mark_as_issued(db_session, iss1.id, None, "田中", "窓口手渡し")
    record_payment(db_session, iss1.id, date(2026, 5, 30), 10000, "現金", staff_name="田中")
    return proj, [iss1, iss2]


def test_get_unpaid_report(db_session):
    proj, issuances = _setup(db_session)
    rows = get_unpaid_report(db_session, fiscal_year=2026)
    assert len(rows) == 1
    assert rows[0]["organization_name"] == "△△産業"


def test_get_unpaid_report_includes_description(db_session):
    """未払い一覧に品目名（但し書き相当）が含まれる。"""
    proj, issuances = _setup(db_session)
    rows = get_unpaid_report(db_session, fiscal_year=2026)
    assert rows[0]["description"] == "青年部会費"


def test_get_payment_report(db_session):
    proj, issuances = _setup(db_session)
    rows = get_payment_report(db_session, fiscal_year=2026)
    assert len(rows) == 1
    assert rows[0]["amount"] == 10000


def test_get_payment_report_includes_description(db_session):
    """入金一覧に但し書き（発行明細の品目名）が含まれる。"""
    proj, issuances = _setup(db_session)
    rows = get_payment_report(db_session, fiscal_year=2026)
    assert rows[0]["description"] == "青年部会費"


def test_get_project_summary(db_session):
    proj, issuances = _setup(db_session)
    summary = get_project_summary(db_session, fiscal_year=2026)
    assert len(summary) == 1
    row = summary[0]
    assert row["total"] == 2
    assert row["invoice_issued"] == 1   # iss1 のみ発行済み（iss2 は準備中）
    assert row["receipt_issued"] == 0
    assert row["pending"] == 1
