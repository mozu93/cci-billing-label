# tests/test_project_member_panel.py
from PyQt6.QtWidgets import QPushButton


def _button_texts(w):
    return [b.text() for b in w.findChildren(QPushButton)]


def test_entry_dialog_returns_values(qtbot, memory_db):
    from app.ui.project_member_panel import RosterEntryDialog
    dlg = RosterEntryDialog()
    qtbot.addWidget(dlg)
    dlg._fields["organization_name"].setText("○○商事")
    dlg._fields["representative_name"].setText("田中")
    dlg._fields["email"].setText("t@example.com")
    v = dlg.values()
    assert v["organization_name"] == "○○商事"
    assert v["representative_name"] == "田中"
    assert v["email"] == "t@example.com"


def test_panel_has_add_and_copy_buttons(qtbot, memory_db):
    from app.ui.project_member_panel import ProjectMemberPanel
    from app.services.project_service import create_project
    from app.database.connection import get_session
    s = get_session()
    try:
        proj = create_project(s, name="2026 青年部", category_id=None,
                              fiscal_year=2026, project_type="list")
        pid = proj.id
    finally:
        s.close()
    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    texts = _button_texts(panel)
    assert "1件追加" in texts
    # 他の名簿からのコピーは分かりにくく使われていないため廃止
    assert "他名簿から追加" not in texts
    assert "他の名簿からコピー" not in texts


def test_member_panel_has_registration_date_column(qtbot, memory_db):
    from app.ui.project_member_panel import ProjectMemberPanel
    from app.services.project_service import create_project, add_roster_entries
    from app.database.connection import get_session
    s = get_session()
    proj = create_project(s, name="2026 視察研修", category_id=None,
                          fiscal_year=2026, project_type="list")
    add_roster_entries(s, proj.id, [{"organization_name": "○○商事"}])
    pid = proj.id
    s.close()

    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    headers = [panel._table.horizontalHeaderItem(i).text()
               for i in range(panel._table.columnCount())]
    assert "登録日" in headers
    assert "キャンセル" in headers
    assert "NO." in headers
    assert panel._table.isSortingEnabled()


def test_member_panel_filters_by_recipient_fields(qtbot, memory_db):
    """名簿検索は指定された4つの宛名項目を対象にする。"""
    from app.ui.project_member_panel import ProjectMemberPanel

    pid = _project_with_roster([
        {"organization_name": "青空商事", "organization_kana": "アオゾラショウジ",
         "representative_name": "田中 太郎", "representative_kana": "タナカタロウ"},
        {"organization_name": "緑産業", "representative_name": "佐藤 花子"},
    ])
    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)

    for query in ("青空", "アオゾラ", "太郎", "タナカ"):
        panel._search.setText(query)
        assert panel._table.rowCount() == 1
        assert "1 件を表示（全 2 件）" == panel._count_label.text()

    panel._search.clear()
    assert panel._table.rowCount() == 2


def test_cancelled_member_is_displayed_and_excluded_from_progress(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.project_service import (
        get_project_progress, set_project_members_cancelled,
    )
    from app.ui.project_member_panel import ProjectMemberPanel

    pid = _project_with_roster([{"organization_name": "○○商事"}])
    session = get_session()
    try:
        from app.services.project_service import get_project_members
        pm = get_project_members(session, pid)[0]
        set_project_members_cancelled(session, [pm.id], True)
        assert get_project_progress(session, pid)["total"] == 0
    finally:
        session.close()

    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    headers = [panel._table.horizontalHeaderItem(i).text()
               for i in range(panel._table.columnCount())]
    cancel_col = headers.index("キャンセル")
    assert panel._table.item(0, cancel_col).text() == "キャンセル"


# ── 追加取り込み ────────────────────────────────────────────────────────────

def _project_with_roster(entries=()):
    from app.database.connection import get_session
    from app.services.project_service import create_project, add_roster_entries
    session = get_session()
    try:
        proj = create_project(session, name="2026 新年互礼会", category_id=None,
                              fiscal_year=2026, project_type="list")
        if entries:
            add_roster_entries(session, proj.id, list(entries))
        return proj.id
    finally:
        session.close()


def test_panel_import_button_says_append(qtbot, memory_db):
    """一度確定した名簿にも追加できることがボタン名で分かる。"""
    from app.ui.project_member_panel import ProjectMemberPanel
    panel = ProjectMemberPanel(_project_with_roster())
    qtbot.addWidget(panel)
    # 見切れないよう短くしつつ、「追加」であることは名前で分かるようにする
    assert "Excel・貼付で追加" in _button_texts(panel)


def test_panel_emits_roster_changed_on_delete(qtbot, memory_db, monkeypatch):
    """名簿の増減は一覧側へ通知される。"""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox
    from app.ui.project_member_panel import ProjectMemberPanel

    pid = _project_with_roster([
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    panel._table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    with qtbot.waitSignal(panel.roster_changed, timeout=1000):
        panel._remove_checked()
    assert panel._table.rowCount() == 0


def test_project_tab_refreshes_row_after_roster_change(qtbot, memory_db):
    """名簿を追加すると、一覧の「全件」「未発行」がその場で更新される。"""
    from app.ui.project_tab import ProjectTab
    from app.database.connection import get_session
    from app.services.project_service import add_roster_entries

    pid = _project_with_roster([
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    tab = ProjectTab()
    qtbot.addWidget(tab)
    tab._load()
    tab._select_project(pid)
    row = tab._table.currentRow()
    assert tab._table.item(row, 2).text() == "1"

    session = get_session()
    try:
        add_roster_entries(session, pid, [
            {"organization_name": "△△産業", "representative_name": "佐藤"},
        ])
    finally:
        session.close()

    tab._refresh_project_row(pid)
    assert tab._table.item(row, 2).text() == "2"   # 全件
    assert tab._table.item(row, 5).text() == "2"   # 未発行


def test_panel_title_shows_project_name(qtbot, memory_db):
    """下のエリアが、どの件名の名簿かを見出しで示す。"""
    from PyQt6.QtWidgets import QLabel
    from app.ui.project_member_panel import ProjectMemberPanel
    panel = ProjectMemberPanel(_project_with_roster())
    qtbot.addWidget(panel)
    labels = [lb.text() for lb in panel.findChildren(QLabel)]
    assert any(t.startswith("名簿：") and len(t) > 3 for t in labels)


def test_panel_buttons_fit_780px_without_truncation(qtbot, memory_db):
    """ボタン名が見切れない（各ボタンが文字の幅以上あり、右端からはみ出さない）。"""
    from app.ui.project_member_panel import ProjectMemberPanel
    panel = ProjectMemberPanel(_project_with_roster())
    qtbot.addWidget(panel)
    panel.resize(780, 500)
    panel.show()
    qtbot.waitExposed(panel)
    for text in ("1件追加", "Excel・貼付で追加", "編集",
                 "参加キャンセル", "キャンセル解除", "削除"):
        b = next(x for x in panel.findChildren(QPushButton) if x.text() == text)
        assert b.width() >= b.sizeHint().width(), f"「{text}」が縮められている"
        assert b.mapTo(panel, b.rect().topRight()).x() < 780, f"「{text}」がはみ出した"
        assert b.toolTip(), f"「{text}」に説明がない"


def test_panel_title_shows_business_and_project_name(qtbot, memory_db):
    """見出しは「名簿：業務名　件名」。同じ件名の名簿を業務名で見分けられる。"""
    from PyQt6.QtWidgets import QLabel
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.project_service import create_project
    from app.ui.project_member_panel import ProjectMemberPanel
    s = get_session()
    cat = create_category(s, "不動産部会")
    with_cat = create_project(s, "視察研修会", cat.id, 2026, "list").id
    no_cat = create_project(s, "新年会", None, 2026, "list").id
    s.close()

    def _title(pid):
        panel = ProjectMemberPanel(pid)
        qtbot.addWidget(panel)
        return next(lb.text() for lb in panel.findChildren(QLabel)
                    if lb.text().startswith("名簿："))

    assert _title(with_cat) == "名簿：不動産部会　視察研修会"
    assert _title(no_cat) == "名簿：新年会"


def test_roster_excel_export_writes_displayed_rows(qtbot, memory_db, monkeypatch, tmp_path):
    """名簿の「Excel出力」は、表示中の行（検索で絞り込んだ行）を全項目で書き出す。"""
    import openpyxl
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    from app.database.connection import get_session
    from app.services.project_service import add_roster_entries, create_project
    from app.ui.project_member_panel import ProjectMemberPanel
    s = get_session()
    pid = create_project(s, "視察研修会", None, 2026, "list").id
    add_roster_entries(s, pid, [
        {"organization_name": "○○商店", "member_number": "0001", "email": "a@example.invalid"},
        {"organization_name": "△△工業", "member_number": "0002"},
    ])
    s.close()
    out = tmp_path / "roster.xlsx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    panel._search.setText("○○")          # 絞り込んだ状態で出力
    btn = next(b for b in panel.findChildren(QPushButton) if b.text() == "Excel出力")
    btn.click()

    ws = openpyxl.load_workbook(out).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][:4] == ("NO.", "会員番号", "事業所名", "フリガナ")
    assert "メール" in rows[0] and "キャンセル" in rows[0] and "登録日" in rows[0]
    assert len(rows) == 2                 # 見出し＋絞り込んだ1行
    assert rows[1][1] == "0001" and rows[1][2] == "○○商店"
    assert "a@example.invalid" in rows[1]
