import os
import tempfile

from pypdf import PdfReader


def test_label_layouts_populated():
    from app.services.pdf.label_pdf import LABEL_LAYOUTS
    assert "a_one_28185" in LABEL_LAYOUTS
    assert "a_one_28187" in LABEL_LAYOUTS
    assert "a_one_51002" in LABEL_LAYOUTS
    assert "a4_4split" not in LABEL_LAYOUTS


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


# ── 屋号なし個人事業主（事業所名＝代表者名）の判定 ──────────────────────

def test_is_individual_proprietor_when_names_match():
    from app.services.pdf.label_pdf import _is_individual_proprietor
    assert _is_individual_proprietor("四日市太郎", "四日市太郎") is True


def test_is_individual_proprietor_ignores_whitespace_differences():
    from app.services.pdf.label_pdf import _is_individual_proprietor
    assert _is_individual_proprietor("四日市　太郎", "四日市太郎") is True


def test_is_individual_proprietor_false_when_names_differ():
    from app.services.pdf.label_pdf import _is_individual_proprietor
    assert _is_individual_proprietor("テスト商事", "田中太郎") is False


def test_is_individual_proprietor_false_when_company_empty():
    from app.services.pdf.label_pdf import _is_individual_proprietor
    assert _is_individual_proprietor("", "田中太郎") is False


# ── 個人事業主の宛名ラベル：事業所名の重複表示を避ける ──────────────────

class _SoleProprietorEntry:
    company_name    = "四日市太郎"
    postal_code     = "123-4567"
    address1        = "東京都千代田区1-2-3"
    address2        = ""
    title           = ""
    person_name     = "四日市太郎"
    barcode_address = ""
    entry_mode      = "inherit"


def test_normal_mode_shows_name_once_for_sole_proprietor():
    """事業所名＝代表者名のとき、「宛名（氏名あり）」では氏名を1回だけ表示する。"""
    from app.services.pdf.label_pdf import generate_label_pdf
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "test_label.pdf")
        generate_label_pdf([_SoleProprietorEntry()], out, batch_mode="normal")
        text = PdfReader(out).pages[0].extract_text()
        assert text.count("四日市太郎") == 1
        assert "様" in text
        assert "御中" not in text


def test_no_person_mode_uses_sama_for_sole_proprietor():
    """事業所名＝代表者名のとき、「宛名（氏名なし）」でも「御中」ではなく「様」にする。"""
    from app.services.pdf.label_pdf import generate_label_pdf
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "test_label.pdf")
        generate_label_pdf([_SoleProprietorEntry()], out, batch_mode="no_person")
        text = PdfReader(out).pages[0].extract_text()
        assert "様" in text
        assert "御中" not in text


def test_nametag_mode_shows_name_once_for_sole_proprietor():
    """事業所名＝代表者名のとき、「名札」では氏名を1回だけ表示する。"""
    from app.services.pdf.label_pdf import generate_label_pdf
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "test_label.pdf")
        generate_label_pdf([_SoleProprietorEntry()], out, batch_mode="nametag")
        text = PdfReader(out).pages[0].extract_text()
        assert text.count("四日市太郎") == 1
