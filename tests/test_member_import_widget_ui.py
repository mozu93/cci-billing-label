# tests/test_member_import_widget_ui.py
"""会員マスタ画面：事業所名の列幅変更と、CSV列マッピングの設定状況表示のテスト。"""
import pytest
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QHeaderView, QMessageBox

from app.ui.member_import_widget import (
    MemberImportWidget, MemberMappingDialog, COL_ORG,
)

WJ = "\u2060"  # WORD JOINER（状況欄で改行を禁止するために文字間へ挟んでいる）


def _status_text(dlg) -> str:
    return dlg._status_label.text().replace(WJ, "")


# ── 会員一覧：事業所名の列幅 ──────────────────────────────────────

def test_org_column_is_resizable_by_user(qtbot, memory_db):
    w = MemberImportWidget()
    qtbot.addWidget(w)
    hdr = w._table.horizontalHeader()
    assert hdr.sectionResizeMode(COL_ORG) == QHeaderView.ResizeMode.Interactive

    hdr.resizeSection(COL_ORG, 333)
    assert hdr.sectionSize(COL_ORG) == 333


def test_only_one_column_stretches(qtbot, memory_db):
    w = MemberImportWidget()
    qtbot.addWidget(w)
    hdr = w._table.horizontalHeader()
    stretch = [c for c in range(hdr.count())
               if hdr.sectionResizeMode(c) == QHeaderView.ResizeMode.Stretch]
    assert stretch == []
    assert hdr.stretchLastSection()


# ── CSV列マッピング：設定状況 ─────────────────────────────────────

def _make_dialog(qtbot, tmp_path, header_line: str, data_line: str):
    p = tmp_path / "members.csv"
    p.write_text(header_line + "\n" + data_line + "\n", encoding="utf-8-sig")
    dlg = MemberMappingDialog(str(p))
    qtbot.addWidget(dlg)
    return dlg


def _select(dlg, csv_header: str, field: str):
    combo = dlg._combos[csv_header]
    combo.setCurrentIndex(combo.findData(field))


def test_status_shows_assigned_and_unassigned_fields(qtbot, tmp_path):
    # ヘッダーは自動検出されない名前にして、手で設定する状況を再現する
    dlg = _make_dialog(qtbot, tmp_path, "列A,列B,列C", "0012,○○商店,マルマルショウテン")
    assert "✖事業所名" in _status_text(dlg)

    _select(dlg, "列B", "organization_name")

    text = _status_text(dlg)
    assert "✔事業所名<" in text
    assert "列B" not in text   # CSV列名は行の色分けで分かるので、状況欄には出さない
    assert "✖会員番号" in text


@pytest.mark.parametrize("width", [300, 500, 680])
def test_status_items_do_not_wrap_in_the_middle(qtbot, tmp_path, width):
    """狭い幅でも「氏／名フリガナ」のように項目名の途中で改行されない。"""
    dlg = _make_dialog(qtbot, tmp_path, "列A", "x")
    doc = QTextDocument()
    doc.setDefaultFont(dlg._status_label.font())
    doc.setHtml(dlg._status_label.text())
    doc.setTextWidth(width)
    doc.documentLayout().documentSize()  # レイアウトを確定させる

    block = doc.begin()
    layout = block.layout()
    lines = []
    for i in range(layout.lineCount()):
        ln = layout.lineAt(i)
        lines.append(block.text()[ln.textStart():ln.textStart() + ln.textLength()]
                     .replace(WJ, ""))
    assert len(lines) >= 2   # 実際に折り返しが起きる幅で検証している
    for label in dlg._field_labels.values():
        assert any(label in ln for ln in lines), f"{label} が途中で折り返された"


def test_assigned_rows_are_highlighted(qtbot, tmp_path):
    dlg = _make_dialog(qtbot, tmp_path, "列A,列B", "0012,○○商店")
    _select(dlg, "列B", "organization_name")

    row_b = dlg._headers.index("列B")
    row_a = dlg._headers.index("列A")
    assert dlg._row_state(row_b) == "assigned"
    assert dlg._row_state(row_a) == "none"

    _select(dlg, "列B", "")
    assert dlg._row_state(row_b) == "none"


def test_duplicate_assignment_is_warned_and_blocks_import(qtbot, tmp_path, monkeypatch):
    dlg = _make_dialog(qtbot, tmp_path, "列A,列B", "○○商店,△△商店")
    _select(dlg, "列A", "organization_name")
    _select(dlg, "列B", "organization_name")

    assert "⚠事業所名（2列）" in _status_text(dlg)
    assert dlg._row_state(0) == "duplicate"
    assert dlg._row_state(1) == "duplicate"

    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: warned.append(a))
    dlg.accept()
    assert warned
    assert dlg.result() != dlg.DialogCode.Accepted

    _select(dlg, "列B", "")
    assert dlg._row_state(0) == "assigned"
