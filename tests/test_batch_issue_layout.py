# tests/test_batch_issue_layout.py
"""まとめて発行（請求書・領収書を発行）の画面配置。

発行の設定は1つの枠にまとめ、普段は1行の要約で見せて「変更」で開く。
検索とExcelの操作は一覧の直上、プレビューと発行は下部の1行にまとめる。
"""
import pytest
from PyQt6.QtWidgets import QApplication, QCheckBox, QComboBox, QDateEdit, QPushButton


def _make(qtbot, doc_type="invoice", width=1000):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    w = IssuanceFromProjectWidget(doc_type)
    qtbot.addWidget(w)
    w.resize(width, 700)
    w.show()
    qtbot.waitExposed(w)
    return w


def _y(w, widget):
    return widget.mapTo(w, widget.rect().center()).y()


def _x(w, widget):
    return widget.mapTo(w, widget.rect().topLeft()).x()


def _button(w, text) -> QPushButton:
    return next(b for b in w.findChildren(QPushButton) if b.text() == text)


def _summary(w) -> str:
    """要約の表示文字列（折り返し位置を制御する WORD JOINER を除いたもの）。"""
    return w._settings_summary.text().replace("\u2060", "")


def test_settings_are_collapsed_to_summary(qtbot, memory_db):
    w = _make(qtbot)
    assert not w._settings_panel.isVisible()
    summary = _summary(w)
    # 発行方法と支払期日は発行時のダイアログで決めるので、要約には出さない
    assert "発行元：" in summary
    assert "個別PDF" in summary


def test_change_button_opens_all_settings(qtbot, memory_db):
    w = _make(qtbot)
    w._btn_settings_toggle.click()
    assert w._settings_panel.isVisible()
    for field in (w._issuer_combo, w._bank_combo,
                  w._seal_combo, w._pdf_output_combo, w._window_envelope_chk,
                  w._show_person_chk):
        assert w._settings_panel.isAncestorOf(field)
        assert field.isVisible()
    w._btn_settings_toggle.click()
    assert not w._settings_panel.isVisible()


def test_summary_follows_changes(qtbot, memory_db):
    w = _make(qtbot)
    w._pdf_output_combo.setCurrentIndex(w._pdf_output_combo.findData("merged"))
    w._window_envelope_chk.setChecked(True)
    summary = _summary(w)
    assert "一括PDF＋個別PDF" in summary
    assert "窓あき封筒" in summary


def test_search_and_excel_share_a_row_above_table(qtbot, memory_db):
    w = _make(qtbot)
    row_y = _y(w, w._search)
    assert abs(_y(w, w._btn_export_xlsx) - row_y) <= 2
    assert abs(_y(w, w._btn_import_xlsx) - row_y) <= 2
    assert row_y != _y(w, w._year_combo)            # 絞り込みとは別の行
    assert row_y < _y(w, w._table)


def test_preview_and_issue_share_bottom_row(qtbot, memory_db):
    w = _make(qtbot)
    preview = _button(w, "チェックした請求書をプレビュー")
    assert abs(_y(w, preview) - _y(w, w._btn_issue)) <= 2
    assert _x(w, preview) < _x(w, w._btn_issue)


def test_receipt_summary_has_no_invoice_options(qtbot, memory_db):
    """領収書には窓あき封筒などの請求書だけの設定がなく、発行日は発行時に聞く。"""
    w = _make(qtbot, doc_type="receipt")
    assert "発行日" not in _summary(w)
    assert not hasattr(w, "_window_envelope_chk")
    _button(w, "チェックした領収書をプレビュー")


@pytest.mark.parametrize("doc_type", ["invoice", "receipt"])
def test_fits_780px_with_settings_open(qtbot, memory_db, doc_type):
    """最小環境の幅780pxでも、設定を開いた状態で入力欄が右端からはみ出さない。"""
    w = _make(qtbot, doc_type=doc_type, width=780)
    w._btn_settings_toggle.click()
    QApplication.processEvents()
    for field in w.findChildren((QComboBox, QDateEdit, QCheckBox, QPushButton)):
        if not field.isVisible() or field is w._header_chk:
            continue
        right = field.mapTo(w, field.rect().topRight()).x()
        assert right < 780, f"{type(field).__name__} {getattr(field, 'text', lambda: '')()} が {right}px"


@pytest.mark.parametrize("width", [860, 780])
def test_summary_wraps_only_between_items(qtbot, memory_db, width):
    """要約の折り返しは「／」の区切りでだけ起き、項目の途中（「個別｜PDF」など）で切れない。"""
    from PyQt6.QtGui import QTextDocument
    w = _make(qtbot, width=width)
    label = w._settings_summary
    doc = QTextDocument()
    doc.setDefaultFont(label.font())
    doc.setPlainText(label.text())
    doc.setTextWidth(label.width())
    doc.documentLayout().documentSize()
    block = doc.begin()
    lay = block.layout()
    lines = [block.text()[lay.lineAt(i).textStart():
                          lay.lineAt(i).textStart() + lay.lineAt(i).textLength()]
             .replace("\u2060", "") for i in range(lay.lineCount())]
    items = label.text().replace("\u2060", "").split("／")
    for item in items:
        assert any(item in ln for ln in lines), f"「{item}」が途中で折り返された：{lines}"
