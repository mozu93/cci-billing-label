# tests/test_wheel_guard.py
"""閉じたプルダウン・数値欄・日付欄は、マウスホイールで値が変わらない（誤入力防止）。"""
import pytest
from PyQt6.QtCore import QDate, QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QDateEdit, QSpinBox


def _wheel(widget, steps: int = -1):
    """ホイールを1目盛り回したときと同じイベントを送る（アプリのイベントフィルタを通る）。"""
    pos = QPointF(widget.rect().center())
    ev = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())),
                     QPoint(0, 0), QPoint(0, 120 * steps),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def _widgets(qtbot):
    combo = QComboBox()
    combo.addItems(["印刷", "メール送付", "その他"])
    spin = QSpinBox()
    spin.setRange(0, 100)
    spin.setValue(5)
    date = QDateEdit(QDate(2026, 10, 31))
    for w in (combo, spin, date):
        qtbot.addWidget(w)
        w.show()
        qtbot.waitExposed(w)
    return combo, spin, date


@pytest.fixture
def guard():
    from app.ui.wheel_guard import install_wheel_guard
    app = QApplication.instance()
    g = install_wheel_guard(app)
    yield g
    app.removeEventFilter(g)


def test_without_guard_wheel_changes_values(qtbot):
    """対照：ガードがなければホイールで値が変わる（テストの前提の確認）。"""
    combo, spin, date = _widgets(qtbot)
    _wheel(combo)
    _wheel(spin, +1)
    _wheel(date, +1)
    assert combo.currentIndex() != 0
    assert spin.value() != 5
    assert date.date() != QDate(2026, 10, 31)


def test_wheel_does_not_change_values(qtbot, guard):
    combo, spin, date = _widgets(qtbot)
    _wheel(combo)
    _wheel(spin, +1)
    _wheel(date, +1)
    assert combo.currentIndex() == 0
    assert spin.value() == 5
    assert date.date() == QDate(2026, 10, 31)


def test_open_dropdown_list_can_still_scroll(qtbot, guard):
    combo, _spin, _date = _widgets(qtbot)
    combo.showPopup()
    qtbot.waitUntil(combo.view().isVisible)
    assert guard.eventFilter(combo, QEvent(QEvent.Type.Wheel)) is False
    combo.hidePopup()


def test_other_events_pass_through(qtbot, guard):
    combo, spin, _date = _widgets(qtbot)
    assert guard.eventFilter(combo, QEvent(QEvent.Type.MouseButtonPress)) is False
    assert guard.eventFilter(spin, QEvent(QEvent.Type.KeyPress)) is False
