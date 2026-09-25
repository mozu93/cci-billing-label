# tests/test_combo_popup.py
"""プルダウンの候補一覧が、すべての候補を切れずに表示し、入力欄の下に開く。

以前は Fusion の「現在の項目に重ねて開く」方式で、候補2件に必要な高さ54pxに
対して42pxしかなく2件目が切れ、入力欄の上にかぶさって開いていた。
"""
from PyQt6.QtWidgets import QApplication, QComboBox, QWidget, QVBoxLayout


def test_popup_shows_all_items_below_the_field(qtbot):
    from app.ui.theme import STYLESHEET
    app = QApplication.instance()
    old_style, old_sheet = app.style().name(), app.styleSheet()
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    try:
        host = QWidget()
        # 名簿・請求内容の作成画面と同じく、画面側でも入力欄のスタイルを重ねる
        host.setStyleSheet("QComboBox { border: 1px solid #b5b5b5; padding: 3px 4px; }")
        combo = QComboBox(host)
        combo.addItems(["不動産部会", "四日市を美しくする会"])
        QVBoxLayout(host).addWidget(combo)
        qtbot.addWidget(host)
        host.show()
        qtbot.waitExposed(host)

        combo.showPopup()
        view = combo.view()
        qtbot.waitUntil(view.isVisible)
        needed = sum(view.sizeHintForRow(i) for i in range(combo.count()))
        assert view.viewport().height() >= needed, "候補が切れている"
        assert view.sizeHintForRow(0) >= 24, "候補の行が詰まっていて読みにくい"
        popup_top = view.window().geometry().top()
        field_bottom = combo.mapToGlobal(combo.rect().bottomLeft()).y()
        assert popup_top >= field_bottom - 2, "入力欄の上にかぶさって開いている"
        combo.hidePopup()
    finally:
        app.setStyleSheet(old_sheet)
        app.setStyle(old_style)
