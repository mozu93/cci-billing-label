# tests/test_counter_layout_redesign.py
"""単発発行の画面配置：宛先に関わる入力は宛先欄に集め、支払期日は合計の横に置く。"""
import pytest
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QGroupBox, QLineEdit, QPushButton,
)

_FIELD_TYPES = (QLineEdit, QComboBox, QCheckBox, QDateEdit, QPushButton)


def _make(qtbot, doc_type="invoice", width=1120, height=728):
    from app.ui.issuance_counter import IssuanceCounterWidget
    w = IssuanceCounterWidget(doc_type=doc_type)
    qtbot.addWidget(w)
    w.resize(width, height)
    w.show()
    QApplication.processEvents()
    return w


def _group(w, title) -> QGroupBox:
    return next(g for g in w.findChildren(QGroupBox) if g.title() == title)


def test_address_and_print_options_are_in_destination_group(qtbot, memory_db):
    w = _make(qtbot)
    dest, opts = _group(w, "宛先"), _group(w, "発行設定")
    for field in (w._postal_code_edit, w._address1_edit, w._address2_edit,
                  w._window_envelope_chk, w._show_person_chk,
                  w._dept_edit, w._rep_name_edit):
        assert dest.isAncestorOf(field)
        assert not opts.isAncestorOf(field)


def test_dept_and_name_are_visible_without_opening_details(qtbot, memory_db):
    w = _make(qtbot)
    assert not w._detail_widget.isVisible()
    assert w._dept_edit.isVisible()
    assert w._rep_name_edit.isVisible()
    assert w._show_person_chk.isVisible()


def test_address_is_always_visible_but_editable_only_in_window_mode(qtbot, memory_db):
    w = _make(qtbot)
    w._window_envelope_chk.setChecked(False)
    w._address1_edit.setText("三重県四日市市")
    assert w._address1_edit.isVisible()
    assert w._address1_edit.text() == "三重県四日市市"
    for f in (w._postal_code_edit, w._address1_edit, w._address2_edit):
        assert not f.isEnabled()

    w._window_envelope_chk.setChecked(True)
    for f in (w._postal_code_edit, w._address1_edit, w._address2_edit):
        assert f.isEnabled()


def test_due_date_sits_next_to_total(qtbot, memory_db):
    w = _make(qtbot)
    assert not _group(w, "発行設定").isAncestorOf(w._due_date)
    assert w._summary_bar.isAncestorOf(w._due_date)
    assert w._summary_bar.isAncestorOf(w._total_label)
    # 支払期日は合計より左
    assert (w._due_date.mapTo(w._summary_bar, w._due_date.rect().topLeft()).x()
            < w._total_label.mapTo(w._summary_bar, w._total_label.rect().topLeft()).x())


def test_due_date_and_total_are_not_hidden_by_scrolling(qtbot, memory_db):
    """最小環境の高さ（728px）でも、スクロールせずに支払期日と合計が見える。"""
    from PyQt6.QtWidgets import QScrollArea
    w = _make(qtbot, height=728)
    outer = next(s for s in w.findChildren(QScrollArea) if s.parent() is w)
    assert not outer.isAncestorOf(w._summary_bar)
    bottom = w._summary_bar.mapTo(w, w._summary_bar.rect().bottomLeft()).y()
    assert w._due_date.isVisible() and bottom <= w.height()


def test_receipt_has_total_bar_without_due_date(qtbot, memory_db):
    w = _make(qtbot, doc_type="receipt")
    assert w._summary_bar.isAncestorOf(w._total_label)
    assert not hasattr(w, "_due_date")


def test_member_with_only_name_does_not_open_details(qtbot, memory_db):
    """氏名・所属は常に見えるので、それだけでは詳細欄を開かない。"""
    from types import SimpleNamespace
    w = _make(qtbot)
    m = SimpleNamespace(
        member_number="0001", organization_name="○○商店", organization_kana="",
        department="代表取締役", representative_name="山田太郎", representative_kana="",
        phone="", email="", postal_code="", address="", address2="")
    w._fill_from_member(m)
    assert not w._detail_widget.isVisible()
    assert w._rep_name_edit.text() == "山田太郎"


@pytest.mark.parametrize("doc_type", ["invoice", "receipt"])
@pytest.mark.parametrize("width", [1000, 850, 780, 700])
def test_top_groups_fit_within_width(qtbot, memory_db, doc_type, width):
    """狭い幅でも宛先・発行設定の入力欄が欄からはみ出さない。

    画面全体の右端は下の「発行項目」の最小幅（約776px）で決まるため、ここでは
    上部2欄の中身だけを検証する。"""
    w = _make(qtbot, doc_type=doc_type, width=width)
    for title in ("宛先", "発行設定"):
        g = _group(w, title)
        for child in g.findChildren(_FIELD_TYPES):
            if not child.isVisible():
                continue
            x = child.mapTo(g, child.rect().topLeft()).x()
            assert x >= 0 and x + child.width() <= g.width(), (
                f"{title} 内の {type(child).__name__} がはみ出した")
