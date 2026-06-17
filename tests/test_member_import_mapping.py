# tests/test_member_import_mapping.py
"""会員マスタ取り込みの列マッピング（位置固定ではなく列を選んで対応づけ）のテスト。"""
from app.utils.excel_utils import (
    parse_tsv_text_raw, column_count, default_positional_mapping,
    guess_mapping_from_header, build_member_rows,
)


def test_parse_tsv_text_raw_keeps_cells():
    raw = parse_tsv_text_raw("A-001\t○○商事\t田中\n\nB-002\t△△産業")
    assert raw == [["A-001", "○○商事", "田中"], ["B-002", "△△産業"]]


def test_column_count():
    assert column_count([["a", "b", "c"], ["x"]]) == 3
    assert column_count([]) == 0


def test_default_positional_mapping():
    m = default_positional_mapping(3)
    assert m["member_number"] == 0
    assert m["organization_name"] == 1
    assert m["organization_kana"] == 2
    assert m["representative_name"] is None  # 列が足りない


def test_guess_mapping_from_header_by_label():
    header = ["代表者名", "事業所名", "会員番号"]
    m = guess_mapping_from_header(header)
    assert m["representative_name"] == 0
    assert m["organization_name"] == 1
    assert m["member_number"] == 2
    assert m["phone"] is None


def test_build_member_rows_with_reordered_mapping():
    # 列順：事業所名 / 会員番号 / 代表者名
    raw = [["○○商事", "A-001", "田中太郎"]]
    mapping = {
        "organization_name": 0,
        "member_number": 1,
        "representative_name": 2,
    }
    rows = build_member_rows(raw, mapping)
    assert len(rows) == 1
    assert rows[0]["organization_name"] == "○○商事"
    assert rows[0]["member_number"] == "A-001"
    assert rows[0]["representative_name"] == "田中太郎"
    assert rows[0]["phone"] == ""  # 未割り当ては空


def test_build_member_rows_skips_header_and_required():
    raw = [
        ["事業所名", "会員番号"],   # 見出し
        ["○○商事", "A-001"],
        ["", ""],                  # 必須なし → 除外
    ]
    mapping = {"organization_name": 0, "member_number": 1}
    rows = build_member_rows(raw, mapping, has_header=True)
    assert len(rows) == 1
    assert rows[0]["organization_name"] == "○○商事"


