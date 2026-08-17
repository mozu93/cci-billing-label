# tests/test_batch_issuance_tab.py
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QComboBox, QTabWidget


def _tab_titles(tabwidget: QTabWidget) -> list[str]:
    return [tabwidget.tabText(i) for i in range(tabwidget.count())]


def test_batch_issuance_subtabs(qtbot, memory_db):
    from app.ui.batch_issuance_tab import BatchIssuanceTab
    w = BatchIssuanceTab()
    qtbot.addWidget(w)
    inner = w.findChild(QTabWidget)
    assert inner is not None
    assert _tab_titles(inner) == [
        "名簿・請求内容", "請求書を発行", "領収書を発行", "入金管理"
    ]


def test_batch_issuance_tab_no_legacy_tab(qtbot, memory_db):
    from app.ui.batch_issuance_tab import BatchIssuanceTab
    w = BatchIssuanceTab()
    qtbot.addWidget(w)
    inner = w.findChild(QTabWidget)
    titles = [inner.tabText(i) for i in range(inner.count())]
    assert "登録データから発行" not in titles
    assert "名簿登録" not in titles


def test_closed_combo_ignores_mouse_wheel(qtbot, memory_db):
    from app.ui.batch_issuance_tab import BatchIssuanceTab
    tab = BatchIssuanceTab()
    qtbot.addWidget(tab)
    combo = tab.findChild(QComboBox)
    assert combo is not None
    assert tab._combo_wheel_guard.eventFilter(
        combo, QEvent(QEvent.Type.Wheel)) is True
