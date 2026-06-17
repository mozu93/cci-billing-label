# tests/test_project_service.py
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.project_service import (
    create_project, get_projects, close_project,
    add_template_to_project, add_roster_entries,
    get_project_members, get_project_progress, remove_member_from_project,
    copy_roster_from_project, get_project_by_id,
)


def test_create_project(db_session):
    cat = create_category(db_session, "青年部")
    proj = create_project(db_session, name="2026年度 青年部会費",
                          category_id=cat.id, fiscal_year=2026,
                          project_type="list")
    assert proj.id is not None
    assert proj.status == "active"
    assert proj.fiscal_year == 2026


def test_get_project_progress_counter(db_session):
    """会員名簿を持たないフリー発行プロジェクトは発行単位で集計する。"""
    from app.services.issuance_service import create_direct_issuance
    lines = [{"item_template_id": None, "item_name": "コピー代",
              "quantity": 1, "unit": "枚", "unit_price": 30, "tax_rate": 0}]
    r = create_direct_issuance(
        db_session, lines_data=lines, recipient_organization="A商店",
        recipient_name="", doc_type="receipt", fiscal_year=2026, month=6,
        project_name="その他")
    create_direct_issuance(
        db_session, lines_data=lines, recipient_organization="B商店",
        recipient_name="", doc_type="invoice", fiscal_year=2026, month=6,
        project_name="その他")
    prog = get_project_progress(db_session, r.project_id)
    assert prog["total"] == 2     # 発行2件
    assert prog["issued"] == 2    # 領収書(支払済み)＋請求書(発行済み)
    assert prog["paid"] == 1      # 領収書のみ入金済み
    assert prog["pending"] == 0


def test_create_project_is_active(db_session):
    from app.services.project_service import create_project
    p = create_project(db_session, name="2026 青年部", category_id=None,
                       fiscal_year=2026, project_type="list")
    assert p.status == "active"


def test_reopen_project(db_session):
    from app.services.project_service import create_project, close_project, reopen_project, get_project_by_id
    p = create_project(db_session, name="x", category_id=None, fiscal_year=2026, project_type="list")
    close_project(db_session, p.id)
    assert get_project_by_id(db_session, p.id).status == "closed"
    reopen_project(db_session, p.id)
    assert get_project_by_id(db_session, p.id).status == "active"


def test_get_projects_by_year(db_session):
    cat = create_category(db_session, "青年部")
    create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    create_project(db_session, "2025年度 青年部会費", cat.id, 2025, "list")
    result = get_projects(db_session, fiscal_year=2026)
    assert len(result) == 1
    assert result[0].fiscal_year == 2026


def test_add_template_to_project(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費", 10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    from app.database.models import ProjectTemplate
    pts = db_session.query(ProjectTemplate).filter_by(project_id=proj.id).all()
    assert len(pts) == 1
    assert pts[0].item_template_id == tmpl.id


def _mk_project(session, name="2026 青年部"):
    return create_project(session, name=name, category_id=None,
                          fiscal_year=2026, project_type="list")


def test_add_roster_entries_and_get(db_session):
    proj = _mk_project(db_session)
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
        {"organization_name": "△△産業", "representative_name": "鈴木",
         "email": "suzuki@example.com"},
    ])
    pms = get_project_members(db_session, proj.id)
    assert [p.organization_name for p in pms] == ["○○商事", "△△産業"]
    assert pms[1].email == "suzuki@example.com"
    assert pms[0].sort_order == 0 and pms[1].sort_order == 1


def test_copy_roster_from_project_snapshot(db_session):
    src = _mk_project(db_session, "2025 青年部")
    add_roster_entries(db_session, src.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    dst = _mk_project(db_session, "2026 青年部")
    copy_roster_from_project(db_session, src.id, dst.id)
    dst_pms = get_project_members(db_session, dst.id)
    assert len(dst_pms) == 1
    assert dst_pms[0].organization_name == "○○商事"
    dst_pms[0].organization_name = "改名"
    db_session.commit()
    src_pms = get_project_members(db_session, src.id)
    assert src_pms[0].organization_name == "○○商事"


def test_get_project_progress(db_session):
    proj = _mk_project(db_session)
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
        {"organization_name": "△△産業", "representative_name": "鈴木"},
    ])
    progress = get_project_progress(db_session, proj.id)
    assert progress["total"] == 2
    assert progress["issued"] == 0
    assert progress["paid"] == 0
    assert progress["pending"] == 2


def test_roster_member_has_created_at(db_session):
    """名簿エントリに登録日時(created_at)が自動で入る。"""
    from app.services.project_service import create_project, add_roster_entries, get_project_members
    from datetime import datetime
    proj = create_project(db_session, name="2026 視察研修", category_id=None,
                          fiscal_year=2026, project_type="list")
    add_roster_entries(db_session, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(db_session, proj.id)[0]
    assert isinstance(pm.created_at, datetime)


def test_get_project_members_newest_first(db_session):
    """newest_first=True で登録日の新しい順に並ぶ。"""
    from datetime import datetime
    from app.services.project_service import create_project, get_project_members
    from app.database.models import ProjectMember
    proj = create_project(db_session, name="2026 視察研修", category_id=None,
                          fiscal_year=2026, project_type="list")
    old = ProjectMember(project_id=proj.id, organization_name="先に登録",
                        sort_order=0, created_at=datetime(2026, 6, 1, 9, 0, 0))
    new = ProjectMember(project_id=proj.id, organization_name="後で登録",
                        sort_order=1, created_at=datetime(2026, 6, 3, 9, 0, 0))
    db_session.add_all([old, new])
    db_session.commit()
    members = get_project_members(db_session, proj.id, newest_first=True)
    assert members[0].organization_name == "後で登録"
    assert members[1].organization_name == "先に登録"


def test_create_project_with_issuer(db_session):
    from app.database.models import CompanySettings, BankAccount
    from app.services.category_service import create_category

    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()
    bank = BankAccount(company_id=cs.id, label="口座", bank_name="○○銀行", is_default=True)
    db_session.add(bank)
    db_session.commit()

    cat = create_category(db_session, "青年部")
    proj = create_project(db_session, name="テストPJ",
                          category_id=cat.id, fiscal_year=2026,
                          project_type="list",
                          company_settings_id=cs.id,
                          bank_account_id=bank.id)
    assert proj.company_settings_id == cs.id
    assert proj.bank_account_id == bank.id
    assert proj.seal_image_id is None
