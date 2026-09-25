# tests/test_project_service.py
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.project_service import (
    create_project, get_projects,
    add_template_to_project, add_roster_entries,
    get_project_members, get_project_progress, remove_member_from_project,
    save_member_item_setting, get_member_item_settings,
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


def test_get_member_emails(db_session):
    """名簿会員IDからメールアドレスを引く。未登録・空欄は空文字で返す。"""
    from app.services.project_service import get_member_emails

    proj = create_project(db_session, "2026 視察研修", None, 2026, "list")
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事", "email": " a@example.com "},
        {"organization_name": "△△産業"},
    ])
    pms = get_project_members(db_session, proj.id)
    emails = get_member_emails(db_session, [pm.id for pm in pms])
    assert emails[pms[0].id] == "a@example.com"   # 前後の空白は落とす
    assert emails[pms[1].id] == ""
    assert get_member_emails(db_session, []) == {}


def test_clear_project_templates(db_session):
    """名簿の保存時、発行項目を入れ替えるために一括削除する。他の名簿は消さない。"""
    from app.services.project_service import (
        clear_project_templates, get_project_templates,
    )
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    keep = create_project(db_session, "2026年度 検定", cat.id, 2026, "list")
    target = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, keep.id, tmpl.id)
    add_template_to_project(db_session, target.id, tmpl.id)

    clear_project_templates(db_session, target.id)

    assert get_project_templates(db_session, target.id) == []
    assert len(get_project_templates(db_session, keep.id)) == 1


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


def test_member_item_setting_upsert_preserves_other_value(db_session):
    proj = _mk_project(db_session)
    add_roster_entries(db_session, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(db_session, proj.id)[0]
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "会費", 5000, "式", 0, "invoice", "")

    save_member_item_setting(db_session, pm.id, tmpl.id, quantity=3)
    save_member_item_setting(db_session, pm.id, tmpl.id, unit_price=2500)

    saved = get_member_item_settings(db_session, [pm.id])[(pm.id, tmpl.id)]
    assert int(saved.quantity) == 3
    assert int(saved.unit_price) == 2500


def test_remove_member_removes_member_item_settings(db_session):
    proj = _mk_project(db_session)
    add_roster_entries(db_session, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(db_session, proj.id)[0]
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "会費", 5000, "式", 0, "invoice", "")
    save_member_item_setting(db_session, pm.id, tmpl.id, quantity=2)

    remove_member_from_project(db_session, pm.id)

    assert get_member_item_settings(db_session, [pm.id]) == {}


# ── 名簿行の取得・更新 ─────────────────────────────────────────

def _one_member(db_session):
    cat = create_category(db_session, "青年部")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    return get_project_members(db_session, proj.id)[0]


def test_get_project_member(db_session):
    from app.services.project_service import get_project_member

    pm = _one_member(db_session)
    assert get_project_member(db_session, pm.id).organization_name == "○○商事"


def test_get_project_member_returns_none_when_missing(db_session):
    from app.services.project_service import get_project_member

    assert get_project_member(db_session, 9999) is None


def test_update_project_member_fields(db_session):
    from app.services.project_service import (
        get_project_member, update_project_member_fields)

    pm = _one_member(db_session)
    update_project_member_fields(db_session, pm.id, {
        "organization_name": "△△産業",
        "phone": "059-000-0000",
    })
    updated = get_project_member(db_session, pm.id)
    assert updated.organization_name == "△△産業"
    assert updated.phone == "059-000-0000"


def test_update_project_member_rejects_unknown_field(db_session):
    """画面の列定義から項目名が渡るため、想定外の更新を防ぐ。"""
    import pytest
    from app.services.project_service import update_project_member_fields

    pm = _one_member(db_session)
    with pytest.raises(ValueError, match="更新できない項目"):
        update_project_member_fields(db_session, pm.id, {"is_cancelled": True})


def test_update_project_member_rejects_id_overwrite(db_session):
    import pytest
    from app.services.project_service import update_project_member_fields

    pm = _one_member(db_session)
    with pytest.raises(ValueError):
        update_project_member_fields(db_session, pm.id, {"id": 12345})


def test_update_project_member_returns_none_when_missing(db_session):
    from app.services.project_service import update_project_member_fields

    assert update_project_member_fields(
        db_session, 9999, {"phone": "0"}) is None


def test_editable_member_fields_cover_dialog_keys(db_session):
    """編集ダイアログが扱う項目は、すべて更新許可リストに入っている。"""
    from app.services.project_service import EDITABLE_MEMBER_FIELDS

    pm = _one_member(db_session)
    for field in EDITABLE_MEMBER_FIELDS:
        assert hasattr(pm, field), field


def test_invoice_issued_counts_members_with_receipt_too(db_session):
    """請求書発行済は、同じ会員に領収書も出ていても数える。

    以前は「請求書のみ（領収書未発行）」の人数を返していたため、
    請求書と領収書の両方を発行すると 0 件と表示されていた。
    """
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import add_template_to_project
    from app.services.issuance_service import (
        create_issuance_for_member, mark_as_issued,
    )
    cat = create_category(db_session, "不動産部会")
    tmpl = create_item_template(db_session, cat.id, "視察参加費",
                                10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026 視察研修", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    pm = get_project_members(db_session, proj.id)[0]
    for doc_type in ("invoice", "receipt"):
        iss = create_issuance_for_member(
            db_session, proj.id, pm.id,
            recipient_organization=pm.organization_name,
            recipient_name=pm.representative_name,
            doc_type=doc_type, fiscal_year=2026, month=5)
        mark_as_issued(db_session, iss.id, None, "田中", "窓口手渡し")

    progress = get_project_progress(db_session, proj.id)
    assert progress["total"] == 1
    assert progress["invoice_issued"] == 1
    assert progress["receipt_issued"] == 1
    assert progress["pending"] == 0


def _roster_with_issuance(db_session):
    from app.database.models import Issuance
    p = create_project(db_session, "視察研修会", None, 2026, "list")
    issued, plain = add_roster_entries(db_session, p.id, [
        {"organization_name": "発行済み商店"}, {"organization_name": "未発行商店"}])
    db_session.add(Issuance(project_id=p.id, project_member_id=issued.id,
                            doc_type="invoice", doc_number="INV-2026-0001",
                            status="発行済み", amount=10000))
    db_session.commit()
    return issued.id, plain.id


def test_member_with_issuance_cannot_be_removed(db_session):
    """発行済みの書類がある名簿行は削除しない（書類が存在しない行を指したままになるため）。"""
    import pytest
    from app.database.models import ProjectMember
    issued_id, _ = _roster_with_issuance(db_session)
    with pytest.raises(ValueError):
        remove_member_from_project(db_session, issued_id)
    assert db_session.get(ProjectMember, issued_id) is not None


def test_members_with_issuances(db_session):
    from app.services.project_service import members_with_issuances
    issued_id, plain_id = _roster_with_issuance(db_session)
    assert members_with_issuances(db_session, [issued_id, plain_id]) == [issued_id]
    remove_member_from_project(db_session, plain_id)   # 発行のない行は削除できる
