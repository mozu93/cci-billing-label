from unittest.mock import MagicMock


def test_display_text_newline_replaced():
    from app.ui.label_issuance_tab import _MultilineDelegate
    delegate = _MultilineDelegate()
    assert delegate.displayText("株式会社テスト\n営業部", None) == "株式会社テスト ｜ 営業部"


def test_display_text_no_newline_unchanged():
    from app.ui.label_issuance_tab import _MultilineDelegate
    delegate = _MultilineDelegate()
    assert delegate.displayText("株式会社テスト", None) == "株式会社テスト"


def test_display_text_none_becomes_empty():
    from app.ui.label_issuance_tab import _MultilineDelegate
    delegate = _MultilineDelegate()
    assert delegate.displayText(None, None) == ""


def test_display_text_multiple_newlines():
    from app.ui.label_issuance_tab import _MultilineDelegate
    delegate = _MultilineDelegate()
    assert delegate.displayText("A\nB\nC", None) == "A ｜ B ｜ C"
