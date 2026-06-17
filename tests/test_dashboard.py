# tests/test_dashboard.py
# ダッシュボードタブは廃止。同等機能（集計表・年度更新）は ProjectTab に移管。


def test_project_tab_has_rollover_button(qtbot, memory_db):
    """年度更新ボタンが ProjectTab に存在する。"""
    from PyQt6.QtWidgets import QPushButton
    from app.ui.project_tab import ProjectTab
    w = ProjectTab()
    qtbot.addWidget(w)
    texts = [b.text() for b in w.findChildren(QPushButton)]
    assert "年度更新" in texts


def test_project_tab_column_headers_include_progress(qtbot, memory_db):
    """ProjectTab の集計列（請求書発行済・領収書発行済・未発行）が存在する。"""
    from app.ui.project_tab import ProjectTab
    w = ProjectTab()
    qtbot.addWidget(w)
    headers = [w._table.horizontalHeaderItem(i).text()
               for i in range(w._table.columnCount())]
    assert "請求書発行済" in headers
    assert "領収書発行済" in headers
    assert "未発行" in headers
