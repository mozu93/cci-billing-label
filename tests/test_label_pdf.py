import pytest
import os
import tempfile


def test_label_layouts_populated():
    from app.services.pdf.label_pdf import LABEL_LAYOUTS
    assert "a_one_28185" in LABEL_LAYOUTS
    assert "a_one_28187" in LABEL_LAYOUTS
    assert "a_one_51002" in LABEL_LAYOUTS
    assert "a4_4split"   in LABEL_LAYOUTS


def test_font_options_not_empty():
    from app.services.pdf.label_pdf import FONT_OPTIONS
    assert len(FONT_OPTIONS) > 0


def test_default_keys_exist():
    from app.services.pdf.label_pdf import (
        DEFAULT_LAYOUT_KEY, DEFAULT_FONT_KEY, LABEL_LAYOUTS, FONT_OPTIONS
    )
    assert DEFAULT_LAYOUT_KEY in LABEL_LAYOUTS
    assert DEFAULT_FONT_KEY in FONT_OPTIONS


class _DummyEntry:
    company_name    = "テスト商事"
    postal_code     = "123-4567"
    address1        = "東京都千代田区1-2-3"
    address2        = ""
    title           = "部長"
    person_name     = "田中太郎"
    barcode_address = ""
    entry_mode      = "inherit"


def test_generate_label_pdf_creates_file():
    from app.services.pdf.label_pdf import generate_label_pdf
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "test_label.pdf")
        generate_label_pdf([_DummyEntry()], out, batch_mode="normal")
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0
