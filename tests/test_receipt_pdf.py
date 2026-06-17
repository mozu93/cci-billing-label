# tests/test_receipt_pdf.py
import os, tempfile
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.project_service import create_project, add_template_to_project
from app.services.issuance_service import create_counter_issuance
from app.database.models import CompanySettings
from app.services.pdf.receipt_pdf import generate_receipt_pdf


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
    finally:
        if os.path.exists(path):
            os.unlink(path)
