# app/services/pdf/batch_pdf.py
import os
from datetime import date
from app.services.pdf.invoice_pdf import generate_invoice_pdf
from app.services.pdf.receipt_pdf import generate_receipt_pdf
from app.services.project_service import get_project_members
from app.services.issuance_service import create_issuance_for_member, mark_as_issued
from app.database.models import Issuance, CompanySettings, BankAccount


def generate_batch_pdf(session, project_id: int, company: CompanySettings,
                        output_dir: str,
                        bank_account: BankAccount | None = None,
                        doc_type: str = "invoice") -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    pms = get_project_members(session, project_id)
    today = date.today()
    generated = []
    new_issuance_ids = []

    for pm in pms:
        iss = (session.query(Issuance)
               .filter_by(project_member_id=pm.id, doc_type=doc_type)
               .order_by(Issuance.created_at.desc())
               .first())
        is_new = False
        if iss is None:
            if not pm.organization_name and not pm.representative_name:
                continue
            # 請求書発行時、領収書が既にある＝請求書は無効。スキップ
            if doc_type == "invoice":
                has_receipt = (session.query(Issuance)
                               .filter_by(project_member_id=pm.id,
                                          doc_type="receipt")
                               .first() is not None)
                if has_receipt:
                    continue
            iss = create_issuance_for_member(
                session, project_id=project_id,
                project_member_id=pm.id,
                recipient_organization=pm.organization_name,
                recipient_name=pm.representative_name,
                doc_type=doc_type,
                fiscal_year=today.year, month=today.month,
            )
            is_new = True
        path = os.path.join(output_dir, f"{iss.doc_number}.pdf")
        if doc_type == "invoice":
            generate_invoice_pdf(iss, company, path, bank_account)
        else:
            generate_receipt_pdf(iss, company, path)
        iss.pdf_path = path
        session.commit()
        if is_new:
            new_issuance_ids.append(iss.id)
        generated.append(path)

    for iss_id in new_issuance_ids:
        mark_as_issued(session, iss_id, staff_id=None, staff_name="")

    return generated
