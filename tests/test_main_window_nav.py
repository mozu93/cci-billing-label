# tests/test_main_window_nav.py
from PyQt6.QtWidgets import QStackedWidget, QWidget

from app.ui.nav_shell import (
    GLYPH_MONEY, NavItem, NavRail, PageShell,
    PANE_WIDTH_COMPACT, PANE_WIDTH_EXPANDED,
)

_EXPECTED = [
    "単発発行", "まとめて発行", "入金管理", "宛名ラベル発行",
    "修正・再発行", "登録・マスタ", "メールテンプレート", "設定",
]


def _nav(window) -> NavRail:
    return window.centralWidget().findChild(NavRail)


def _stack(window) -> QStackedWidget:
    return window.centralWidget().findChild(QStackedWidget)


def test_nav_item_order(qtbot, memory_db):
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    assert _nav(window).labels() == _EXPECTED


def test_default_page_is_counter(qtbot, memory_db):
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    stack = _stack(window)
    assert stack.currentIndex() == 0
    assert _nav(window).current_index() == 0
    assert stack.currentWidget().title() == "単発発行"


def test_every_nav_item_has_matching_page(qtbot, memory_db):
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    stack = _stack(window)
    assert stack.count() == len(_EXPECTED)
    for index, title in enumerate(_EXPECTED):
        page = stack.widget(index)
        assert isinstance(page, PageShell)
        assert page.title() == title


def test_nav_selection_switches_page(qtbot, memory_db):
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    nav, stack = _nav(window), _stack(window)

    for index, title in enumerate(_EXPECTED):
        nav.set_current_index(index)
        assert nav.current_index() == index
        assert stack.currentIndex() == index
        assert stack.currentWidget().title() == title


def test_non_default_pages_are_built_lazily(qtbot, memory_db, monkeypatch):
    """起動時は既定ページ（単発発行）だけを作り、他は選択されるまで作らない。

    表示していないタブの重い初期化（DB問い合わせ・外部ライブラリ初期化など）が
    起動時間に乗ってしまっていたため、選択されて初めて生成するようにする。
    """
    import app.ui.batch_issuance_tab as batch_mod
    build_count = []

    class _Spy(QWidget):
        def __init__(self):
            super().__init__()
            build_count.append(1)

    monkeypatch.setattr(batch_mod, "BatchIssuanceTab", _Spy)

    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    assert build_count == []

    nav = _nav(window)
    nav.set_current_index(1)  # まとめて発行
    assert build_count == [1]

    # 一度作ったページは選び直しても作り直さない
    nav.set_current_index(0)
    nav.set_current_index(1)
    assert build_count == [1]


def test_pane_collapses_to_icon_width(qtbot, memory_db):
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    nav = _nav(window)

    nav.set_compact(True)
    assert nav.is_compact()
    assert nav.width() == PANE_WIDTH_COMPACT

    nav.set_compact(False)
    assert not nav.is_compact()
    assert nav.width() == PANE_WIDTH_EXPANDED


def test_compact_pane_keeps_labels_as_tooltips(qtbot, memory_db):
    """折りたたみ時はラベルが隠れるため、項目名をツールチップで補う。"""
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    nav = _nav(window)

    nav.set_compact(True)
    assert [item.toolTip() for item in nav._items] == _EXPECTED

    nav.set_compact(False)
    assert all(item.toolTip() == "" for item in nav._items)


def test_payment_nav_uses_yen_glyph(qtbot):
    item = NavItem("入金管理", GLYPH_MONEY)
    qtbot.addWidget(item)
    assert GLYPH_MONEY == "￥"
    assert item._icon.property("textGlyph") is True
