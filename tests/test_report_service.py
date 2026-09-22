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


def test_project_amount_summary(db_session):
    """ダッシュボード用の金額集計。請求書のみを対象にする。"""
    from app.services.report_service import get_project_amount_summary

    proj, issuances = _setup(db_session)
    summary = get_project_amount_summary(db_session, proj.id)
    # 請求書2件 × 10,000円、うち1件が入金済み。
    assert summary["total"] == 20000
    assert summary["paid"] == 10000
    assert summary["unpaid"] == 10000
    assert summary["paid_count"] == 1


def test_project_amount_summary_excludes_receipts(db_session):
    """領収書は二重計上しない。"""
    from app.services.issuance_service import create_issuance_for_member
    from app.services.project_service import get_project_members
    from app.services.report_service import get_project_amount_summary

    proj, issuances = _setup(db_session)
    pms = get_project_members(db_session, proj.id)
    create_issuance_for_member(
        db_session, proj.id, pms[0].id,
        recipient_organization=pms[0].organization_name,
        recipient_name=pms[0].representative_name,
        doc_type="receipt", fiscal_year=2026, month=5,
    )
    summary = get_project_amount_summary(db_session, proj.id)
    assert summary["total"] == 20000


def test_project_amount_summary_of_empty_project(db_session):
    from app.services.project_service import create_project
    from app.services.category_service import create_category
    from app.services.report_service import get_project_amount_summary

    cat = create_category(db_session, "空カテゴリ")
    proj = create_project(db_session, "空の名簿", cat.id, 2026, "list")
    assert get_project_amount_summary(db_session, proj.id) == {
        "total": 0, "paid": 0, "unpaid": 0, "paid_count": 0}


def test_amount_summary_does_not_double_count_receipts(db_session):
    """請求書と領収書の両方がある会員を、二重に計上しない。

    名簿一覧の「総額」が全種別合算で、実際の請求額より大きく出ていた。
    """
    from app.services.issuance_service import create_issuance_for_member
    from app.services.project_service import get_project_members
    from app.services.report_service import get_project_amount_summary

    proj, issuances = _setup(db_session)
    pms = get_project_members(db_session, proj.id)
    create_issuance_for_member(
        db_session, proj.id, pms[0].id,
        recipient_organization=pms[0].organization_name,
        recipient_name=pms[0].representative_name,
        doc_type="receipt", fiscal_year=2026, month=5,
    )
    # 請求書2件 × 10,000円。領収書10,000円は加算しない。
    assert get_project_amount_summary(db_session, proj.id)["total"] == 20000


def test_amount_summary_counts_payments(db_session):
    from app.services.report_service import get_project_amount_summary

    proj, issuances = _setup(db_session)
    assert get_project_amount_summary(db_session, proj.id)["paid_count"] == 1


def test_get_project_summary_counts_invoices_only(db_session):
    """集計レポートの金額は請求書のみを対象にする。

    領収書も合算すると、同じ会員の請求書と領収書が重複して計上され、
    請求総額が実際より大きくなる。
    """
    from app.services.issuance_service import create_issuance_for_member

    proj, issuances = _setup(db_session)
    pms = get_project_members(db_session, proj.id)
    create_issuance_for_member(
        db_session, proj.id, pms[0].id,
        recipient_organization=pms[0].organization_name,
        recipient_name=pms[0].representative_name,
        doc_type="receipt", fiscal_year=2026, month=5)

    row = get_project_summary(db_session, fiscal_year=2026)[0]
    # 請求書2件 × 10,000円。領収書10,000円は加算しない。
    assert row["total_amount"] == 20000
    assert row["paid_amount"] == 10000
