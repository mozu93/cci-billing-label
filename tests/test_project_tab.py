# tests/test_project_tab.py
from PyQt6.QtWidgets import QPushButton


def _texts(w):
    return [b.text() for b in w.findChildren(QPushButton)]


def test_project_tab_buttons_simplified(qtbot, memory_db):
    from app.ui.project_tab import ProjectTab
    w = ProjectTab()
    qtbot.addWidget(w)
    texts = _texts(w)
    assert "完了" in texts
    assert "受付開始（active）" not in texts
    assert "一括PDF生成" not in texts
    assert "アーカイブ" not in texts


def test_project_tab_shows_business_and_title_columns(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.project_service import create_project
    s = get_session()
    cat = create_category(s, "不動産部会")
    create_project(s, name="2026 視察研修会参加費", category_id=cat.id,
                   fiscal_year=2026, project_type="list")
    s.close()

    from app.ui.project_tab import ProjectTab
    w = ProjectTab()
    qtbot.addWidget(w)
    headers = [w._table.horizontalHeaderItem(i).text()
               for i in range(w._table.columnCount())]
    assert headers[0] == "業務名"
    assert headers[1] == "件名"

    cells = []
    for r in range(w._table.rowCount()):
        cells.append((w._table.item(r, 0).text(), w._table.item(r, 1).text()))
    assert ("不動産部会", "2026 視察研修会参加費") in cells


def test_project_tab_column_headers(qtbot, memory_db):
    """状態列が廃止され、請求書発行済・領収書発行済・未発行の列になっている。"""
    from app.ui.project_tab import ProjectTab
    w = ProjectTab()
    qtbot.addWidget(w)
    headers = [w._table.horizontalHeaderItem(i).text()
               for i in range(w._table.columnCount())]
    assert "状態" not in headers
    assert "発行済" not in headers
    assert "請求書発行済" in headers
    assert "領収書発行済" in headers
    assert "未発行" in headers
