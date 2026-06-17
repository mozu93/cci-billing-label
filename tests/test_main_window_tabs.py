# tests/test_main_window_tabs.py
from PyQt6.QtWidgets import QTabWidget


def _get_tabs(window) -> QTabWidget:
    # centralWidget is now a QWidget container (holds UpdateBanner + QTabWidget)
    return window.centralWidget().findChild(QTabWidget)


def _tab_titles(tabwidget: QTabWidget) -> list[str]:
    return [tabwidget.tabText(i) for i in range(tabwidget.count())]


def test_top_level_tabs_order(qtbot, memory_db):
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    tabs = _get_tabs(window)
    assert isinstance(tabs, QTabWidget)
    assert _tab_titles(tabs) == [
        "単発発行", "まとめて発行", "修正・再発行", "設定",
    ]


def test_default_tab_is_counter(qtbot, memory_db):
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    tabs = _get_tabs(window)
    assert tabs.currentIndex() == 0
    assert tabs.tabText(tabs.currentIndex()) == "単発発行"
