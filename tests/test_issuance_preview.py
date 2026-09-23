# tests/test_issuance_preview.py
"""単発発行のプレビュー：DB に記録せず、採番もせずに「見本」入りの PDF を作る。"""
import os

import pytest
from pypdf import PdfReader

from app.database.models import CompanySettings, Issuance

_LINES = [
    {"item_template_id": None, "item_name": "年会費", "quantity": 1,
     "unit": "式", "unit_price": 10000, "tax_rate": 10},
    {"item_template_id": None, "item_name": "視察研修会参加費", "quantity": 2,
     "unit": "人", "unit_price": 5000, "tax_rate": 10},
]


def test_build_preview_issuance_is_not_saved(db_session):
    from app.services.issuance_service import build_preview_issuance
    iss = build_preview_issuance(
        _LINES, doc_type="invoice", recipient_organization="○○商店",
        recipient_name="山田太郎")
    assert iss.doc_number == "（プレビュー）"
    assert iss.amount == 20000
    assert [l.item_name for l in iss.lines] == ["年会費", "視察研修会参加費"]
    assert [l.line_total for l in iss.lines] == [10000, 10000]
    assert iss not in db_session
    assert db_session.query(Issuance).count() == 0


def test_switch_to_print_keeps_doc_number(db_session):
    from app.services.issuance_service import create_direct_issuance, switch_to_print
    iss = create_direct_issuance(
        db_session, lines_data=_LINES, recipient_organization="○○商店",
        recipient_name="", doc_type="invoice", fiscal_year=2026, month=9,
        staff_id=None, staff_name="", delivery_method="メール送付",
        project_name="直接発行")
    number = iss.doc_number
    switch_to_print(db_session, iss)
    db_session.expire_all()
    got = db_session.get(Issuance, iss.id)
    assert got.delivery_method == "印刷"
    assert got.doc_number == number
    assert db_session.query(Issuance).count() == 1


@pytest.mark.parametrize("doc_type", ["invoice", "receipt"])
def test_cancel_unoutput_issuance_removes_records_and_logs(db_session, doc_type):
    """出力されなかった発行は、明細・入金記録ごと取り消し、「発行取消」のログを残す。"""
    from app.database.models import IssuanceLine, OperationLog, Payment
    from app.services.issuance_service import (
        cancel_unoutput_issuance, create_direct_issuance)

    def _create():
        return create_direct_issuance(
            db_session, lines_data=_LINES, recipient_organization="○○商店",
            recipient_name="", doc_type=doc_type, fiscal_year=2026, month=9,
            staff_id=None, staff_name="", delivery_method="印刷",
            project_name="直接発行")

    iss = _create()
    number = iss.doc_number
    cancel_unoutput_issuance(db_session, iss)

    assert db_session.query(Issuance).count() == 0
    assert db_session.query(IssuanceLine).count() == 0
    assert db_session.query(Payment).count() == 0      # 領収書の入金記録も消す
    logs = [l.detail for l in db_session.query(OperationLog).filter_by(action="発行取消")]
    assert len(logs) == 1 and number in logs[0]
    # 番号は戻さない（他の端末と重ならないよう欠番にする）
    assert _create().doc_number != number


@pytest.fixture
def preview_dir(tmp_path, monkeypatch):
    import app.utils.pdf_helpers as ph
    d = tmp_path / "preview"
    monkeypatch.setattr(ph, "get_preview_dir", lambda: d)
    return d


@pytest.mark.parametrize("doc_type", ["invoice", "receipt"])
def test_preview_pdf_has_watermark_and_saves_nothing(db_session, preview_dir, doc_type):
    from sqlalchemy import text
    from app.services.issuance_service import build_preview_issuance
    from app.utils.pdf_helpers import generate_preview_pdf
    db_session.add(CompanySettings(name="発行元", is_default=True))
    db_session.commit()

    iss = build_preview_issuance(_LINES, doc_type=doc_type,
                                 recipient_organization="○○商店")
    path = generate_preview_pdf(db_session, iss, subject="直接発行")

    assert path and path.startswith(str(preview_dir))
    text_all = "".join(p.extract_text() or "" for p in PdfReader(path).pages)
    assert "見本" in text_all
    assert "プレビュー" in text_all
    # 発行記録も採番も増えていない
    assert db_session.query(Issuance).count() == 0
    seq = db_session.execute(text("SELECT COUNT(*) FROM document_sequences")).scalar()
    assert seq == 0


def test_old_previews_are_removed(db_session, preview_dir):
    from app.services.issuance_service import build_preview_issuance
    from app.utils.pdf_helpers import generate_preview_pdf
    db_session.add(CompanySettings(name="発行元", is_default=True))
    db_session.commit()
    iss = build_preview_issuance(_LINES, doc_type="invoice",
                                 recipient_organization="○○商店")
    first = generate_preview_pdf(db_session, iss)
    second = generate_preview_pdf(db_session, iss)
    assert first != second
    assert [p.name for p in preview_dir.glob("*.pdf")] == [os.path.basename(second)]
