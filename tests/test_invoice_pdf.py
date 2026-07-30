# tests/test_invoice_pdf.py
import os, tempfile
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.project_service import (
    create_project, add_template_to_project, add_roster_entries,
    get_project_members
)
from app.services.issuance_service import create_issuance_for_member
from app.database.models import CompanySettings
from app.services.pdf.invoice_pdf import generate_invoice_pdf


def _make_issuance(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事株式会社",
         "organization_kana": "マルマルショウジ",
         "representative_name": "田中 太郎"},
    ])
    pm = get_project_members(db_session, proj.id)[0]
    return create_issuance_for_member(
        db_session, proj.id, pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5
    )


def test_generate_invoice_pdf(db_session):
    issuance = _make_issuance(db_session)
    company = CompanySettings(
        name="○○商工会議所",
        postal_code="123-4567",
        address="東京都千代田区1-1-1",
        phone="03-1234-5678",
        invoice_reg_number="T1234567890123"
    )
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        result = generate_invoice_pdf(issuance, company, path)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 1000
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_bank_block_shows_account_name_kana():
    from app.services.pdf.invoice_pdf import _build_bank_block
    from app.database.models import BankAccount
    bank = BankAccount(
        bank_name="テスト銀行", bank_account_name="四日市商工会議所",
        bank_account_name_kana="ヨッカイチショウコウカイギショ",
    )
    table = _build_bank_block(bank, 500)
    texts = [
        cell.text
        for row in table._cellvalues
        for cell in row
        if hasattr(cell, "text")
    ]
    assert any("ヨッカイチショウコウカイギショ" in text for text in texts)


def test_issuer_block_is_indented_and_ordered():
    from app.services.pdf.invoice_pdf import (
        _build_company_block, ISSUER_NAME_INDENT_CHARS,
    )
    from app.database.models import CompanySettings, Issuance
    company = CompanySettings(
        name="四日市商工会議所",
        postal_code="510-8501",
        address="三重県四日市市諏訪町2番5号",
        phone="059-352-8191",
        fax="059-354-3737",
        invoice_reg_number="T1234567890123",
    )
    issuance = Issuance(doc_number="INV-202607-0001", doc_type="invoice")
    parts = _build_company_block(
        issuance, company, "2026年7月30日", seal_image=None, col_w=240)
    info = [p for p in parts if hasattr(p, "text")][2:]
    assert [p.text for p in info] == [
        "四日市商工会議所",
        "〒510-8501",
        "三重県四日市市諏訪町2番5号",
        "TEL：059-352-8191",
        "FAX：059-354-3737",
        "登録番号：T1234567890123",
    ]
    assert all(
        p.style.leftIndent == 11 * ISSUER_NAME_INDENT_CHARS for p in info)
    assert all(p.style.rightIndent == 0 for p in info)


def test_issuer_block_moves_left_and_reserves_seal_space(monkeypatch):
    from app.services.pdf import invoice_pdf
    from app.database.models import CompanySettings, Issuance

    monkeypatch.setattr(invoice_pdf, "_seal_source", lambda seal: object())
    company = CompanySettings(
        name="四日市商工会議所",
        address="三重県四日市市諏訪町2番5号",
    )
    issuance = Issuance(doc_number="INV-202607-0001", doc_type="invoice")

    parts = invoice_pdf._build_company_block(
        issuance, company, "2026年7月30日",
        seal_image=object(), col_w=240,
    )
    overlay = parts[-1]
    content = overlay._content._cellvalues[0][0]
    info = [p for p in content if hasattr(p, "text")]

    assert all(
        p.style.leftIndent == 11 * invoice_pdf.ISSUER_SEAL_INDENT_CHARS
        for p in info
    )
    assert all(
        p.style.rightIndent
        == invoice_pdf.ISSUER_SEAL_SIZE + invoice_pdf.ISSUER_SEAL_GAP
        - 11 * invoice_pdf.ISSUER_SEAL_INDENT_CHARS
        for p in info
    )
    assert info[0].style.fontSize == 11
    assert all(p.style.fontSize == 10 for p in info[1:])


def test_build_client_block_hides_person_when_disabled():
    from app.services.pdf.invoice_pdf import _build_client_block
    from app.database.models import Issuance

    iss = Issuance(
        doc_number="INV-003", doc_type="invoice",
        recipient_organization="○○商事株式会社",
        recipient_department="営業部",
        recipient_name="田中太郎",
    )
    parts = _build_client_block(iss, show_recipient_person=False)
    texts = [p.text for p in parts if hasattr(p, "text")]
    assert any("御中" in t for t in texts)
    assert not any("田中太郎" in t for t in texts)
    assert not any("営業部" in t for t in texts)


def test_build_client_block_shows_person_by_default():
    """show_recipient_person を指定しない場合は既存どおり氏名・役職を表示する（回帰防止）。"""
    from app.services.pdf.invoice_pdf import _build_client_block
    from app.database.models import Issuance

    iss = Issuance(
        doc_number="INV-004", doc_type="invoice",
        recipient_organization="○○商事株式会社",
        recipient_department="営業部",
        recipient_name="田中太郎",
    )
    parts = _build_client_block(iss)
    texts = [p.text for p in parts if hasattr(p, "text")]
    assert any("田中太郎" in t for t in texts)
    assert any("営業部" in t for t in texts)
