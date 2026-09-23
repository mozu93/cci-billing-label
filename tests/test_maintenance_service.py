# tests/test_maintenance_service.py
"""業務データの削除。設定画面の3つの削除機能が使う。"""
from datetime import date

import pytest

from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.project_service import (
    create_project, add_template_to_project, add_roster_entries,
    get_project_members, get_projects,
)
from app.services.issuance_service import (
    create_issuance_for_member, mark_as_issued, record_payment,
)
from app.services.staff_service import create_staff, get_all_staff
from app.services.company_service import list_issuers, save_issuer
from app.database.models import Issuance, Payment, DocumentSequence


def _setup(db_session):
    """発行元・スタッフ・業務名・テンプレート・名簿・発行・入金を一通り作る。"""
    save_issuer(db_session, None, name="四日市商工会議所")
    create_staff(db_session, "水谷")
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    pm = get_project_members(db_session, proj.id)[0]
    iss = create_issuance_for_member(
        db_session, proj.id, pm.id, recipient_organization="○○商事",
        recipient_name="田中", doc_type="invoice", fiscal_year=2026, month=5)
    mark_as_issued(db_session, iss.id, None, "田中", "窓口手渡し")
    record_payment(db_session, iss.id, date(2026, 5, 30), 10000, "現金",
                   staff_name="田中")


def test_reset_document_numbers_keeps_projects(db_session):
    """発行番号リセットは発行書類と入金だけ消し、名簿は残す。"""
    from app.services.maintenance_service import reset_document_numbers

    _setup(db_session)
    reset_document_numbers(db_session)

    assert db_session.query(Issuance).count() == 0
    assert db_session.query(Payment).count() == 0
    assert len(get_projects(db_session)) == 1      # 名簿は残る
    assert len(get_all_staff(db_session)) == 1     # スタッフも残る


@pytest.mark.parametrize("func_name", [
    "reset_document_numbers",
    "initialize_business_data",
    "delete_all_except_issuers",
])
def test_all_deletions_reset_document_sequence(db_session, func_name):
    """どの削除でも採番表を消す。残すと次の発行で番号が飛ぶ。"""
    from app.services import maintenance_service

    _setup(db_session)
    assert db_session.query(DocumentSequence).count() > 0
    getattr(maintenance_service, func_name)(db_session)
    assert db_session.query(DocumentSequence).count() == 0


def test_initialize_business_data_keeps_masters(db_session):
    """業務データ初期化は名簿まで消すが、業務名・テンプレート・スタッフは残す。"""
    from app.services.maintenance_service import initialize_business_data
    from app.services.item_template_service import get_all_active_templates
    from app.services.category_service import get_active_categories

    _setup(db_session)
    initialize_business_data(db_session)

    assert db_session.query(Issuance).count() == 0
    assert get_projects(db_session) == []
    assert len(get_active_categories(db_session)) == 1
    assert len(get_all_active_templates(db_session)) == 1
    assert len(get_all_staff(db_session)) == 1


def test_delete_all_except_issuers_keeps_only_issuers(db_session):
    """全データ削除でも発行元情報は残す。"""
    from app.services.maintenance_service import delete_all_except_issuers
    from app.services.item_template_service import get_all_active_templates
    from app.services.category_service import get_active_categories

    _setup(db_session)
    delete_all_except_issuers(db_session)

    assert db_session.query(Issuance).count() == 0
    assert get_projects(db_session) == []
    assert get_active_categories(db_session) == []
    assert get_all_active_templates(db_session) == []
    assert get_all_staff(db_session) == []
    assert len(list_issuers(db_session)) == 1      # 発行元だけ残る
