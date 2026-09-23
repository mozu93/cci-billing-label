# tests/test_tax_rounding.py
"""消費税額の端数処理は、請求書・領収書とも「税率ごとに切り捨て」でそろえる。

以前は領収書だけ税抜額を先に切り捨てて差し引いていたため、税額が実質
切り上げになり、同じ金額でも請求書（909円）と領収書（910円）で食い違っていた。
"""
import pytest
from pypdf import PdfReader

from app.database.models import CompanySettings
from app.services.issuance_service import build_preview_issuance

_LINES = [
    # 10%: 10,000 × 10/110 = 909.09… → 909
    {"item_template_id": None, "item_name": "年会費", "quantity": 1,
     "unit": "式", "unit_price": 10000, "tax_rate": 10},
    # 8%: 1,000 × 8/108 = 74.07… → 74
    {"item_template_id": None, "item_name": "弁当代", "quantity": 1,
     "unit": "個", "unit_price": 1000, "tax_rate": 8},
]


def _text(path) -> str:
    return "".join(p.extract_text() or "" for p in PdfReader(path).pages)


@pytest.mark.parametrize("doc_type", ["invoice", "receipt"])
def test_included_tax_is_rounded_down(tmp_path, doc_type):
    from app.services.pdf.invoice_pdf import generate_invoice_pdf
    from app.services.pdf.receipt_pdf import generate_receipt_pdf
    company = CompanySettings(name="発行元")
    iss = build_preview_issuance(_LINES, doc_type=doc_type,
                                 recipient_organization="○○商店")
    path = str(tmp_path / f"{doc_type}.pdf")
    if doc_type == "invoice":
        generate_invoice_pdf(iss, company, path, None)
    else:
        generate_receipt_pdf(iss, company, path)
    text = _text(path).replace(",", "")
    assert "909" in text and "910" not in text
    assert "74" in text and "75円" not in text and " 75\n" not in text
