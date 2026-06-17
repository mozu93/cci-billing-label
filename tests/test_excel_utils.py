# tests/test_excel_utils.py
from app.utils.excel_utils import parse_tsv_text, MEMBER_COLUMNS


def test_parse_tsv_basic():
    tsv = "A-001\t○○商事\tマルマルショウジ\t田中 太郎\tタナカ タロウ\t123-4567\t東京都\t03-1234-5678\ttest@example.com"
    rows = parse_tsv_text(tsv)
    assert len(rows) == 1
    assert rows[0]["member_number"] == "A-001"
    assert rows[0]["organization_name"] == "○○商事"
    assert rows[0]["representative_name"] == "田中 太郎"


def test_parse_tsv_multiple_rows():
    tsv = "A-001\t○○商事\t\t\t\t\t\t\t\nA-002\t△△産業\t\t\t\t\t\t\t"
    rows = parse_tsv_text(tsv)
    assert len(rows) == 2


def test_parse_tsv_skips_empty_rows():
    tsv = "A-001\t○○商事\t\t\t\t\t\t\t\n\n\n"
    rows = parse_tsv_text(tsv)
    assert len(rows) == 1


def test_required_field_validation():
    tsv = "A-001\t\t\t\t\t\t\t\t"
    rows = parse_tsv_text(tsv)
    assert len(rows) == 0
