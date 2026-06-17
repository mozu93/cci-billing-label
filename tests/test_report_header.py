# tests/test_report_header.py
def test_reissue_tab_uses_kenmei_header(qtbot, memory_db):
    from app.ui.reissue_tab import ReissueWidget
    w = ReissueWidget()
    qtbot.addWidget(w)
    headers = [w._table.horizontalHeaderItem(i).text()
               for i in range(w._table.columnCount())]
    assert "件名" in headers
    assert "名簿名" not in headers
