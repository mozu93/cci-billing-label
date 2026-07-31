# tests/test_invoice_pdf.py
import os, tempfile
from pypdf import PdfReader
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
        text = PdfReader(result).pages[0].extract_text()
        assert "単位（円）" in text
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_bank_block_shows_account_name_kana():
    from app.services.pdf.invoice_pdf import _build_bank_block
    from app.database.models import BankAccount
    from reportlab.lib.units import mm
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
    assert "フリガナ：ﾖｯｶｲﾁｼｮｳｺｳｶｲｷﾞｼｮ" in texts
    assert not any("口座名義（フリガナ）" in text for text in texts)
    assert all(
        cell.style.leading == 11.5
        for row in table._cellvalues
        for cell in row
        if hasattr(cell, "style")
    )
    cell_styles = [style for row in table._cellStyles for style in row]
    assert all(style.topPadding == 0.375 * mm for style in cell_styles)
    assert all(style.bottomPadding == 0.375 * mm for style in cell_styles)


def test_account_name_kana_converts_voiced_marks_and_space_to_halfwidth():
    from app.services.pdf.invoice_pdf import _to_halfwidth_kana

    assert _to_halfwidth_kana("カブシキガイシャ　テスト") == (
        "ｶﾌﾞｼｷｶﾞｲｼｬ ﾃｽﾄ"
    )


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


def test_tax_rows_remove_space_before_tax_label_and_exclude_total():
    from types import SimpleNamespace
    from app.services.pdf.invoice_pdf import _build_tax_rows

    issuance = SimpleNamespace(lines=[
        SimpleNamespace(tax_rate=10, line_total=1100),
        SimpleNamespace(tax_rate=8, line_total=1080),
    ])
    table = _build_tax_rows(issuance, "税込", 2180)[0]
    labels = [row[0].text for row in table._cellvalues]

    assert "10%税額" in labels
    assert "8%税額" in labels
    assert all("合計" not in label and "合　計" not in label for label in labels)


def test_total_row_is_independent_from_tax_rows():
    from app.services.pdf.invoice_pdf import C_BORDER, _build_total_row

    table = _build_total_row("税込", 2180)

    assert table._cellvalues[0][0].text == "合計（税込）"
    assert table._cellvalues[0][1].text == "2,180 -"
    amount_ratio = 0.155 / (0.08 + 0.14 + 0.155)
    assert abs(table._argW[1] / sum(table._argW) - amount_ratio) < 1e-9
    grid = next(cmd for cmd in table._linecmds if cmd[0] == "GRID")
    assert grid[1:5] == ((0, 0), (-1, -1), 0.3, C_BORDER)


def test_total_row_starts_at_unit_column():
    from app.services.pdf.invoice_pdf import (
        _build_right_column_block, _build_total_row,
    )

    width = 500
    total_width_ratio = 0.08 + 0.14 + 0.155
    total = _build_total_row(
        "税込", 2180, total_W=width * total_width_ratio,
    )
    block = _build_right_column_block(
        [total], width, right_width_ratio=total_width_ratio,
    )

    assert block._argW == [
        width * (1 - total_width_ratio),
        width * total_width_ratio,
    ]
    assert block._cellStyles[0][1].leftPadding == 0
    assert block._cellStyles[0][1].rightPadding == 0
