# tests/test_issuance_service.py
from datetime import date
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.project_service import (
    create_project, add_template_to_project, add_roster_entries,
    get_project_members
)
from app.services.issuance_service import (
    get_next_doc_number, create_issuance_for_member,
    create_counter_issuance, mark_as_issued, record_payment,
    get_pending_issuances_for_project_member, get_project_issuances
)


def _setup(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事", "representative_name": "田中太郎"},
    ])
    pm = get_project_members(db_session, proj.id)[0]
    return proj, tmpl, pm


def test_get_next_doc_number(db_session):
    n1 = get_next_doc_number(db_session, "invoice", 2026, 5)
    n2 = get_next_doc_number(db_session, "invoice", 2026, 5)
    assert n1 == "INV-202605-0001"
    assert n2 == "INV-202605-0002"


def test_get_next_doc_number_receipt(db_session):
    n = get_next_doc_number(db_session, "receipt", 2026, 5)
    assert n == "RCP-202605-0001"


def test_get_next_doc_number_resumes_after_existing_data(db_session):
    from app.database.models import Issuance, Project

    project = Project(
        name="既存案件", fiscal_year=2026, project_type="counter")
    db_session.add(project)
    db_session.flush()
    db_session.add(Issuance(
        project_id=project.id,
        doc_type="invoice",
        doc_number="INV-202605-0042",
    ))
    db_session.commit()

    assert get_next_doc_number(
        db_session, "invoice", 2026, 5) == "INV-202605-0043"


def test_get_next_doc_number_catches_up_when_sequence_is_behind(db_session):
    from app.database.models import DocumentSequence, Issuance

    proj, _tmpl, _pm = _setup(db_session)
    db_session.add(DocumentSequence(
        doc_type="invoice", year_month="202605", last_value=10))
    db_session.add(Issuance(
        project_id=proj.id,
        doc_type="invoice",
        doc_number="INV-202605-0042",
        recipient_name="既存",
        amount=0,
    ))
    db_session.commit()

    assert get_next_doc_number(
        db_session, "invoice", 2026, 5) == "INV-202605-0043"


def test_document_number_reservation_is_rolled_back(db_session):
    first = get_next_doc_number(db_session, "invoice", 2026, 5)
    db_session.rollback()
    retried = get_next_doc_number(db_session, "invoice", 2026, 5)

    assert first == "INV-202605-0001"
    assert retried == "INV-202605-0001"


def test_duplicate_document_number_is_rejected(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app.database.models import Issuance, Project

    project = Project(
        name="重複確認", fiscal_year=2026, project_type="counter")
    db_session.add(project)
    db_session.flush()
    db_session.add_all([
        Issuance(
            project_id=project.id,
            doc_type="invoice",
            doc_number="INV-202605-0001",
        ),
        Issuance(
            project_id=project.id,
            doc_type="invoice",
            doc_number="INV-202605-0001",
        ),
    ])

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_document_number_is_unique_during_concurrent_issue(tmp_path):
    import threading
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base, Issuance, Project

    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent.db'}",
        connect_args={"timeout": 10},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    setup_session = session_factory()
    project = Project(
        name="同時発行", fiscal_year=2026, project_type="counter")
    setup_session.add(project)
    setup_session.commit()
    project_id = project.id
    setup_session.close()

    barrier = threading.Barrier(2)
    numbers = []
    errors = []

    def _issue():
        session = session_factory()
        try:
            barrier.wait()
            number = get_next_doc_number(
                session, "invoice", 2026, 5)
            session.add(Issuance(
                project_id=project_id,
                doc_type="invoice",
                doc_number=number,
            ))
            session.commit()
            numbers.append(number)
        except Exception as exc:
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=_issue) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert errors == []
    assert sorted(numbers) == [
        "INV-202605-0001",
        "INV-202605-0002",
    ]


def test_create_issuance_for_member(db_session):
    proj, tmpl, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, project_id=proj.id, project_member_id=pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5
    )
    assert issuance.id is not None
    assert issuance.status == "準備中"
    assert issuance.doc_number.startswith("INV-")
    assert len(issuance.lines) == 1
    assert int(issuance.lines[0].unit_price) == 10000


def test_update_issuance_lines_from_project_applies_excel_values(db_session):
    from app.services.issuance_service import update_issuance_lines_from_project

    proj, tmpl, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, project_id=proj.id, project_member_id=pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5,
    )

    updated = update_issuance_lines_from_project(
        db_session,
        issuance.id,
        quantities={tmpl.id: 3},
        unit_prices={tmpl.id: 2500},
    )

    assert int(updated.amount) == 7500
    assert len(updated.lines) == 1
    assert int(updated.lines[0].quantity) == 3
    assert int(updated.lines[0].unit_price) == 2500
    assert int(updated.lines[0].line_total) == 7500


def test_project_issuance_accepts_zero_unit_price(db_session):
    from app.services.issuance_service import update_issuance_lines_from_project

    proj, tmpl, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, project_id=proj.id, project_member_id=pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5,
    )

    updated = update_issuance_lines_from_project(
        db_session,
        issuance.id,
        quantities={tmpl.id: 1},
        unit_prices={tmpl.id: 0},
    )

    assert int(updated.amount) == 0
    assert int(updated.lines[0].unit_price) == 0


def test_paid_issuance_rejects_project_line_update(db_session):
    from app.services.issuance_service import update_issuance_lines_from_project

    proj, tmpl, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, project_id=proj.id, project_member_id=pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5,
    )
    issuance.status = "支払済み"
    db_session.commit()

    import pytest
    with pytest.raises(ValueError, match="支払済み"):
        update_issuance_lines_from_project(
            db_session,
            issuance.id,
            quantities={tmpl.id: 3},
            unit_prices={tmpl.id: 2500},
        )


def test_project_line_update_can_be_rolled_back_before_pdf_success(db_session):
    from app.services.issuance_service import update_issuance_lines_from_project

    proj, tmpl, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, project_id=proj.id, project_member_id=pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5,
    )
    issuance_id = issuance.id

    update_issuance_lines_from_project(
        db_session,
        issuance_id,
        quantities={tmpl.id: 3},
        unit_prices={tmpl.id: 2500},
        commit=False,
    )
    assert int(db_session.get(type(issuance), issuance_id).amount) == 7500

    db_session.rollback()
    restored = db_session.get(type(issuance), issuance_id)
    assert int(restored.amount) == 10000
    assert int(restored.lines[0].quantity) == 1


def test_mark_as_issued(db_session):
    proj, tmpl, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, proj.id, pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5
    )
    mark_as_issued(db_session, issuance.id, staff_id=None,
                   staff_name="田中", delivery_method="窓口手渡し")
    db_session.refresh(issuance)
    assert issuance.status == "発行済み"
    assert issuance.staff_name == "田中"


def test_record_payment(db_session):
    proj, tmpl, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, proj.id, pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5
    )
    mark_as_issued(db_session, issuance.id, None, "田中", "窓口手渡し")
    record_payment(db_session, issuance.id,
                   payment_date=date(2026, 5, 30),
                   amount=10000, payment_method="現金",
                   staff_name="田中")
    db_session.refresh(issuance)
    assert issuance.status == "支払済み"


def test_get_pending_for_project_member(db_session):
    proj, tmpl, pm = _setup(db_session)
    create_issuance_for_member(
        db_session, proj.id, pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5
    )
    pending = get_pending_issuances_for_project_member(db_session, pm.id)
    assert len(pending) == 1
    assert pending[0].status == "準備中"


def test_pending_for_project_member(db_session):
    from app.services.project_service import (
        create_project, add_roster_entries, get_project_members, add_template_to_project
    )
    from app.services.item_template_service import create_item_template
    from app.services.category_service import create_category
    from app.services.issuance_service import (
        create_issuance_for_member, get_pending_issuances_for_project_member,
    )
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "会費", 1000, "式", 0, "invoice", "")
    proj = create_project(db_session, name="2026 青年部", category_id=cat.id,
                          fiscal_year=2026, project_type="list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    add_roster_entries(db_session, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(db_session, proj.id)[0]
    create_issuance_for_member(db_session, proj.id, pm.id, "○○商事", "", "invoice", 2026, 4)
    pending = get_pending_issuances_for_project_member(db_session, pm.id)
    assert len(pending) == 1


def test_create_direct_issuance_receipt_records_payment(db_session):
    """フリー発行の領収書は入金（Payment）を記録し支払済みにする。"""
    from app.services.issuance_service import create_direct_issuance
    from app.database.models import Payment
    lines = [{"item_template_id": None, "item_name": "証明手数料",
              "quantity": 2, "unit": "通", "unit_price": 30, "tax_rate": 0}]
    iss = create_direct_issuance(
        db_session, lines_data=lines,
        recipient_organization="", recipient_name="山田",
        doc_type="receipt", fiscal_year=2026, month=6,
        staff_name="田中", delivery_method="窓口手渡し",
        project_name="その他",
    )
    assert iss.status == "支払済み"
    payments = db_session.query(Payment).filter_by(issuance_id=iss.id).all()
    assert len(payments) == 1
    assert int(payments[0].amount) == 60
    assert payments[0].staff_name == "田中"
    assert payments[0].payment_date == date(2026, 6, 2) or payments[0].payment_date is not None


def test_create_direct_issuance_invoice_no_payment(db_session):
    """フリー発行の請求書は未入金なので Payment を作らず発行済みのまま。"""
    from app.services.issuance_service import create_direct_issuance
    from app.database.models import Payment
    lines = [{"item_template_id": None, "item_name": "会費",
              "quantity": 1, "unit": "式", "unit_price": 5000, "tax_rate": 0}]
    iss = create_direct_issuance(
        db_session, lines_data=lines,
        recipient_organization="○○商事", recipient_name="",
        doc_type="invoice", fiscal_year=2026, month=6,
    )
    assert iss.status == "発行済み"
    assert db_session.query(Payment).filter_by(issuance_id=iss.id).count() == 0


def test_create_counter_issuance(db_session):
    cat = create_category(db_session, "検定")
    tmpl = create_item_template(db_session, cat.id, "珠算検定受験料",
                                3000, "人", 0, "receipt", "珠算検定受験料として")
    proj = create_project(db_session, "珠算検定", cat.id, 2026, "counter")
    add_template_to_project(db_session, proj.id, tmpl.id)
    issuance = create_counter_issuance(
        db_session, project_id=proj.id,
        recipient_organization="△△そろばん教室",
        recipient_name="",
        doc_type="receipt", quantity=3,
        fiscal_year=2026, month=5
    )
    assert issuance.id is not None
    assert issuance.status == "発行済み"
    assert int(issuance.lines[0].quantity) == 3
    assert int(issuance.amount) == 9000


def test_issue_receipt_for_invoice(db_session):
    from app.services.issuance_service import (
        create_issuance_for_member, mark_as_issued, issue_receipt_for_invoice,
    )
    from app.database.models import Payment, Issuance
    from datetime import date
    proj, tmpl, pm = _setup(db_session)
    invoice = create_issuance_for_member(
        db_session, proj.id, pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5,
    )
    mark_as_issued(db_session, invoice.id, None, "田中", "窓口手渡し")

    receipt = issue_receipt_for_invoice(
        db_session, invoice_id=invoice.id,
        payment_date=date(2026, 5, 30),
        payment_method="現金", notes="窓口入金",
        staff_id=None, staff_name="田中",
    )

    # 領収書は元請求書の明細・金額・宛名を引き継ぐ
    assert receipt.doc_type == "receipt"
    assert receipt.doc_number.startswith("RCP-")
    assert receipt.status == "支払済み"
    assert int(receipt.amount) == int(invoice.amount)
    assert receipt.recipient_organization == invoice.recipient_organization
    assert len(receipt.lines) == len(invoice.lines)
    assert int(receipt.lines[0].unit_price) == int(invoice.lines[0].unit_price)
    assert receipt.id != invoice.id

    # 元請求書は支払済みになり、Payment が1件記録される
    db_session.refresh(invoice)
    assert invoice.status == "支払済み"
    payments = db_session.query(Payment).filter_by(issuance_id=invoice.id).all()
    assert len(payments) == 1
    assert int(payments[0].amount) == int(invoice.amount)
    assert payments[0].payment_method == "現金"
    assert payments[0].notes == "窓口入金"


def test_issue_receipt_for_invoice_rejects_paid(db_session):
    import pytest
    from app.services.issuance_service import (
        create_issuance_for_member, mark_as_issued, issue_receipt_for_invoice,
    )
    from datetime import date
    proj, tmpl, pm = _setup(db_session)
    invoice = create_issuance_for_member(
        db_session, proj.id, pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5,
    )
    mark_as_issued(db_session, invoice.id, None, "田中", "窓口手渡し")
    issue_receipt_for_invoice(db_session, invoice_id=invoice.id,
                              payment_date=date(2026, 5, 30), staff_name="田中")
    # 2回目は拒否される
    with pytest.raises(ValueError):
        issue_receipt_for_invoice(db_session, invoice_id=invoice.id,
                                  payment_date=date(2026, 5, 30), staff_name="田中")


def test_search_unpaid_invoices(db_session):
    from app.services.issuance_service import (
        create_issuance_for_member, mark_as_issued, record_payment,
        search_unpaid_invoices,
    )
    from datetime import date
    proj, tmpl, pm = _setup(db_session)

    inv = create_issuance_for_member(
        db_session, proj.id, pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5,
    )
    mark_as_issued(db_session, inv.id, None, "田中", "窓口手渡し")

    # 発行済み・未入金なのでヒットする
    hits = search_unpaid_invoices(db_session, "○○商事")
    assert len(hits) == 1
    assert hits[0].id == inv.id

    # マッチしない検索語では出ない
    assert search_unpaid_invoices(db_session, "存在しない名前") == []

    # フリガナでもヒットする
    pm.organization_kana = "マルマルショウジ"
    db_session.commit()
    kana_hits = search_unpaid_invoices(db_session, "マルマルショウジ")
    assert len(kana_hits) == 1
    assert kana_hits[0].id == inv.id

    # 支払済みになると一覧から外れる
    record_payment(db_session, inv.id, payment_date=date(2026, 5, 30),
                   amount=int(inv.amount), payment_method="現金", staff_name="田中")
    assert search_unpaid_invoices(db_session, "○○商事") == []


def test_create_direct_issuance_stores_issuer_and_display_settings(db_session):
    """単発発行で発行元・口座・印鑑・宛名表示・メールアドレスを保存する。"""
    from app.services.issuance_service import create_direct_issuance
    from app.database.models import CompanySettings, BankAccount, SealImage

    cs = CompanySettings(name="テスト発行元")
    db_session.add(cs)
    db_session.commit()
    bank = BankAccount(company_id=cs.id, label="口座", bank_name="○○銀行")
    seal = SealImage(company_id=cs.id, label="印鑑", path="/tmp/seal.png")
    db_session.add_all([bank, seal])
    db_session.commit()

    lines = [{"item_template_id": None, "item_name": "会費",
              "quantity": 1, "unit": "式", "unit_price": 5000, "tax_rate": 0}]
    iss = create_direct_issuance(
        db_session, lines_data=lines,
        recipient_organization="○○商事", recipient_name="",
        doc_type="invoice", fiscal_year=2026, month=6,
        company_settings_id=cs.id, bank_account_id=bank.id,
        seal_image_id=seal.id, show_recipient_person=False,
        recipient_email="billing@example.com",
    )
    assert iss.company_settings_id == cs.id
    assert iss.bank_account_id == bank.id
    assert iss.seal_image_id == seal.id
    assert iss.show_recipient_person is False
    assert iss.recipient_email == "billing@example.com"


def test_update_direct_issuance_updates_issuer_and_display_settings(db_session):
    """内容修正で発行元・宛名表示・メールアドレスを変更できる。"""
    from app.services.issuance_service import create_direct_issuance, update_direct_issuance
    from app.database.models import CompanySettings

    cs1 = CompanySettings(name="発行元A")
    cs2 = CompanySettings(name="発行元B")
    db_session.add_all([cs1, cs2])
    db_session.commit()

    lines = [{"item_template_id": None, "item_name": "会費",
              "quantity": 1, "unit": "式", "unit_price": 5000, "tax_rate": 0}]
    iss = create_direct_issuance(
        db_session, lines_data=lines,
        recipient_organization="○○商事", recipient_name="",
        doc_type="invoice", fiscal_year=2026, month=6,
        company_settings_id=cs1.id, show_recipient_person=True,
    )

    updated = update_direct_issuance(
        db_session, issuance_id=iss.id, lines_data=lines,
        recipient_organization="○○商事", recipient_name="",
        delivery_method="窓口手渡し",
        company_settings_id=cs2.id, show_recipient_person=False,
        recipient_email="updated@example.com",
    )
    assert updated.company_settings_id == cs2.id
    assert updated.show_recipient_person is False
    assert updated.recipient_email == "updated@example.com"
