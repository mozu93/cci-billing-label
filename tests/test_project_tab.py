# tests/test_project_tab.py
from PyQt6.QtWidgets import QPushButton


def _texts(w):
    return [b.text() for b in w.findChildren(QPushButton)]


def test_project_tab_buttons_simplified(qtbot, memory_db):
    from app.ui.project_tab import ProjectTab
    w = ProjectTab()
    qtbot.addWidget(w)
    texts = _texts(w)
    # 完了・年度更新は廃止（名簿は毎年新しく作る。年度で絞り込めば足りる）
    assert "完了" not in texts
    assert "完了を戻す" not in texts
    assert "年度更新" not in texts
    assert not hasattr(w, "_status_combo")
    assert "受付開始（active）" not in texts
    assert "一括PDF生成" not in texts
    assert "アーカイブ" not in texts
    assert "＋ 名簿・請求内容を作成" in texts


def test_project_tab_explains_empty_state(qtbot, memory_db):
    from app.ui.project_tab import ProjectTab
    w = ProjectTab()
    qtbot.addWidget(w)
    assert w._empty_label.isVisibleTo(w)
    assert "この年度の名簿・請求内容はありません" in w._empty_label.text()


def test_project_tab_lists_closed_projects(qtbot, memory_db):
    """旧版で「完了」にした名簿も、年度の一覧に表示される。"""
    from datetime import date
    from app.database.connection import get_session
    from app.services.project_service import create_project
    from app.ui.project_tab import ProjectTab
    s = get_session()
    p = create_project(s, "完了にした名簿", None, date.today().year, "list")
    p.status = "closed"
    s.commit()
    s.close()
    w = ProjectTab()
    qtbot.addWidget(w)
    names = [w._table.item(r, 1).text() for r in range(w._table.rowCount())]
    assert names == ["完了にした名簿"]


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


class _Feb2027:
    """date.today() を 2027年2月10日（2026年度）に固定する。"""
    @staticmethod
    def today():
        from datetime import date
        return date(2027, 2, 10)


def test_default_year_is_fiscal_year_starting_april(qtbot, memory_db, monkeypatch):
    """年度は4月始まり。2027年2月は2026年度を初期表示する（入金管理とそろえる）。"""
    import app.ui.project_tab as project_tab
    monkeypatch.setattr(project_tab, "date", _Feb2027)
    w = project_tab.ProjectTab()
    qtbot.addWidget(w)
    assert w._year_combo.currentData() == 2026
    years = [w._year_combo.itemData(i) for i in range(w._year_combo.count())]
    assert years[:2] == [2027, 2026]   # 翌年度も選べる


def test_new_project_default_year_is_fiscal_year(qtbot, memory_db, monkeypatch):
    """新しく作る名簿・請求内容の年度も4月始まり（作った名簿が一覧に出るように）。"""
    import app.ui.project_form as project_form
    monkeypatch.setattr(project_form, "date", _Feb2027)
    dlg = project_form.ProjectFormDialog()
    qtbot.addWidget(dlg)
    assert dlg._fiscal_year.value() == 2026


def test_export_buttons_share_the_year_row(qtbot, memory_db):
    """CSV出力・Excel出力は年度の行にまとめ、1行にする（幅780pxでも収まる）。"""
    from PyQt6.QtWidgets import QPushButton
    from app.ui.project_tab import ProjectTab
    w = ProjectTab()
    qtbot.addWidget(w)
    w.resize(780, 500)
    w.show()
    qtbot.waitExposed(w)
    buttons = {b.text(): b for b in w.findChildren(QPushButton)}
    row_y = w._year_combo.mapTo(w, w._year_combo.rect().center()).y()
    for text in ("＋ 名簿・請求内容を作成", "編集", "CSV出力", "Excel出力"):
        b = buttons[text]
        assert abs(b.mapTo(w, b.rect().center()).y() - row_y) <= 2, text
        assert b.mapTo(w, b.rect().topRight()).x() < 780, text
