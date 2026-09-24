# tests/test_dashboard.py
# ダッシュボードタブは廃止。集計表は ProjectTab に移管（年度更新は廃止）。


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
    assert "入金件数" in headers
