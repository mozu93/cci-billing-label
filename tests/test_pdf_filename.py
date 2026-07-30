from datetime import datetime


class _Issuance:
    roster_no = "12"
    recipient_organization = "〇〇/商事"
    recipient_name = "山田太郎"
    issued_at = datetime(2026, 7, 30, 10, 15)
    doc_number = "INV-202607-0001"
    amount = 11000


def test_build_pdf_filename_uses_selected_fields():
    from app.utils.pdf_helpers import build_pdf_filename
    name = build_pdf_filename(
        _Issuance(),
        fields=["organization", "issued_date", "doc_number", "amount"],
    )
    assert name == (
        "〇〇_商事_20260730_INV-202607-0001_請求金額11,000円.pdf")


def test_build_pdf_filename_keeps_current_default():
    from app.utils.pdf_helpers import build_pdf_filename
    assert build_pdf_filename(
        _Issuance(), fields=["doc_number"]
    ) == "INV-202607-0001.pdf"


def test_build_pdf_filename_can_include_roster_no():
    from app.utils.pdf_helpers import build_pdf_filename
    assert build_pdf_filename(
        _Issuance(), fields=["roster_no", "organization"]
    ) == "NO.12_〇〇_商事.pdf"


def test_available_pdf_path_avoids_overwrite(tmp_path):
    from app.utils.pdf_helpers import available_pdf_path
    (tmp_path / "請求書.pdf").write_bytes(b"existing")
    assert available_pdf_path(
        str(tmp_path), "請求書.pdf"
    ).endswith("請求書_2.pdf")
