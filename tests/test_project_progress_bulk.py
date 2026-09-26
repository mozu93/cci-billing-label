# tests/test_project_progress_bulk.py
"""名簿一覧・レポート画面のN+1解消：複数名簿の進捗をまとめて取得する。

get_project_progress_bulk / get_project_amount_summary_bulk は、名簿ごとに
1件ずつ問い合わせていたものをまとめて取得する。1件ずつ呼んだ結果と
一致することを確認する。
"""
from datetime import date

from app.services.issuance_service import create_direct_issuance, mark_as_issued, record_payment
from app.services.project_service import (
    create_project, add_roster_entries, get_project_progress,
    get_project_progress_bulk,
)
from app.services.report_service import (
    get_project_amount_summary, get_project_amount_summary_bulk,
)


def test_progress_bulk_matches_single_lookup_for_list_projects(db_session):
    p1 = create_project(db_session, "2026 青年部", None, 2026, "list")
    add_roster_entries(db_session, p1.id, [
        {"organization_name": "○○商事"}, {"organization_name": "△△産業"},
    ])
    p2 = create_project(db_session, "2026 視察研修", None, 2026, "list")
    add_roster_entries(db_session, p2.id, [{"organization_name": "□□工業"}])

    bulk = get_project_progress_bulk(db_session, [p1, p2])

    assert bulk[p1.id] == get_project_progress(db_session, p1.id)
    assert bulk[p2.id] == get_project_progress(db_session, p2.id)
    assert bulk[p1.id]["total"] == 2
    assert bulk[p2.id]["total"] == 1


def test_progress_bulk_falls_back_for_counter_projects(db_session):
    lines = [{"item_template_id": None, "item_name": "コピー代",
              "quantity": 1, "unit": "枚", "unit_price": 30, "tax_rate": 0}]
    iss = create_direct_issuance(
        db_session, lines_data=lines, recipient_organization="A商店",
        recipient_name="", doc_type="receipt", fiscal_year=2026, month=6,
        project_name="その他")
    from app.services.project_service import get_project_by_id
    proj = get_project_by_id(db_session, iss.project_id)

    bulk = get_project_progress_bulk(db_session, [proj])

    assert bulk[proj.id] == get_project_progress(db_session, proj.id)
    assert bulk[proj.id]["total"] == 1


def test_progress_bulk_counts_receipt_only_member_as_issued(db_session):
    """請求書を出さず領収書だけ発行した会員も issued に含まれる。"""
    proj = create_project(db_session, "2026 青年部", None, 2026, "list")
    add_roster_entries(db_session, proj.id, [{"organization_name": "○○商事"}])
    from app.services.project_service import get_project_members
    from app.services.issuance_service import create_issuance_for_member
    pm = get_project_members(db_session, proj.id)[0]
    rcp = create_issuance_for_member(
        db_session, proj.id, pm.id, "○○商事", "", "receipt", 2026, 6)
    mark_as_issued(db_session, rcp.id, None, "田中", "窓口手渡し")

    bulk = get_project_progress_bulk(db_session, [proj])
    assert bulk[proj.id]["issued"] == 1
    assert bulk[proj.id]["pending"] == 0


def test_amount_summary_bulk_matches_single_lookup(db_session):
    proj = create_project(db_session, "2026 青年部", None, 2026, "list")
    add_roster_entries(db_session, proj.id, [{"organization_name": "○○商事"}])
    from app.services.project_service import get_project_members
    from app.services.issuance_service import create_issuance_for_member
    pm = get_project_members(db_session, proj.id)[0]
    inv = create_issuance_for_member(
        db_session, proj.id, pm.id, "○○商事", "", "invoice", 2026, 6)
    mark_as_issued(db_session, inv.id, None, "田中", "窓口手渡し")
    record_payment(db_session, inv.id, date(2026, 6, 1),
                   int(inv.amount), "現金", staff_id=None, staff_name="田中")

    bulk = get_project_amount_summary_bulk(db_session, [proj.id])
    assert bulk[proj.id] == get_project_amount_summary(db_session, proj.id)
    assert bulk[proj.id]["paid_count"] == 1


def test_bulk_functions_return_empty_dict_for_no_projects(db_session):
    assert get_project_progress_bulk(db_session, []) == {}
    assert get_project_amount_summary_bulk(db_session, []) == {}
