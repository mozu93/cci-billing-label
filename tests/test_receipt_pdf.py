# tests/test_receipt_pdf.py
import os
import tempfile
import pytest
from pypdf import PdfReader
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.project_service import create_project, add_template_to_project
from app.services.issuance_service import create_counter_issuance
from app.database.models import CompanySettings
from app.services.pdf.receipt_pdf import generate_receipt_pdf, generate_receipt_originals_pdf


def test_generate_receipt_pdf(db_session):
    cat = create_category(db_session, "検定")
    tmpl = create_item_template(db_session, cat.id, "珠算検定受験料",
                                3000, "人", 0, "receipt", "珠算検定受験料として")
    proj = create_project(db_session, "珠算検定", cat.id, 2026, "counter")
    add_template_to_project(db_session, proj.id, tmpl.id)
    issuance = create_counter_issuance(
        db_session, project_id=proj.id,
        recipient_organization="△△そろばん教室",
        recipient_name="", doc_type="receipt",
        quantity=3, fiscal_year=2026, month=5
    )
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
        result = generate_receipt_pdf(issuance, company, path)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 1000
        standard_page = PdfReader(result).pages[0]

        with tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False) as email_file:
            email_path = email_file.name
        generate_receipt_pdf(
            issuance, company, email_path, include_copy=False)
        email_page = PdfReader(email_path).pages[0]

        assert float(email_page.mediabox.width) == pytest.approx(
            float(standard_page.mediabox.width))
        assert float(email_page.mediabox.height) == pytest.approx(
            float(standard_page.mediabox.height) / 2)
    finally:
        if os.path.exists(path):
            os.unlink(path)
        if "email_path" in locals() and os.path.exists(email_path):
            os.unlink(email_path)


def _make_issuance(db_session, recipient_organization: str):
    cat = create_category(db_session, "検定")
    tmpl = create_item_template(db_session, cat.id, "珠算検定受験料",
                                3000, "人", 0, "receipt", "珠算検定受験料として")
    proj = create_project(db_session, "珠算検定", cat.id, 2026, "counter")
    add_template_to_project(db_session, proj.id, tmpl.id)
    return create_counter_issuance(
        db_session, project_id=proj.id,
        recipient_organization=recipient_organization,
        recipient_name="", doc_type="receipt",
        quantity=1, fiscal_year=2026, month=5
    )


def _company():
    return CompanySettings(
        name="○○商工会議所",
        postal_code="123-4567",
        address="東京都千代田区1-1-1",
        phone="03-1234-5678",
        invoice_reg_number="T1234567890123"
    )


def test_receipt_with_recipient_shows_sama_and_no_note(db_session):
    issuance = _make_issuance(db_session, "△△そろばん教室")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        generate_receipt_pdf(issuance, _company(), path)
        text = PdfReader(path).pages[0].extract_text()
        assert "様" in text
        assert "簡易インボイス" not in text
    finally:
        os.unlink(path)


def test_receipt_without_recipient_hides_sama_and_shows_note(db_session):
    """宛名が空のときは「様」を出さず、「※簡易インボイス」を注記する（下線は残す）。"""
    issuance = _make_issuance(db_session, "")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        generate_receipt_pdf(issuance, _company(), path)
        text = PdfReader(path).pages[0].extract_text()
        assert "様" not in text
        assert "※簡易インボイス" in text
    finally:
        os.unlink(path)


def test_generate_receipt_originals_pdf_packs_two_per_page(db_session):
    """控え不要のときは、原本のみを2件ずつ1ページ（A5）にまとめる。奇数件なら最後は1件のみ。"""
    issuances = [_make_issuance(db_session, "") for _ in range(3)]
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        generate_receipt_originals_pdf(issuances, _company(), path)
        pages = PdfReader(path).pages
        assert len(pages) == 2  # 3件 → 2件+1件の2ページ
        page1_text = pages[0].extract_text()
        page2_text = pages[1].extract_text()
        assert issuances[0].doc_number in page1_text
        assert issuances[1].doc_number in page1_text
        assert issuances[2].doc_number in page2_text
        assert "控え" not in page1_text
        assert "控え" not in page2_text
    finally:
        os.unlink(path)
