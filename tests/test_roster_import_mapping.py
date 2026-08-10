# tests/test_roster_import_mapping.py
"""事業名簿向け取り込み（列マッピング）のテスト。"""
from app.utils.excel_utils import (
    parse_tsv_text_raw, column_count, default_positional_mapping,
    guess_mapping_from_header, build_member_rows,
)


# ── excel_utils の純粋関数テスト（member_import_mapping から移管） ──────────

def test_parse_tsv_text_raw_keeps_cells():
    raw = parse_tsv_text_raw("A-001\t○○商事\t田中\n\nB-002\t△△産業")
    assert raw == [["A-001", "○○商事", "田中"], ["B-002", "△△産業"]]


def test_column_count():
    assert column_count([["a", "b", "c"], ["x"]]) == 3
    assert column_count([]) == 0


def test_default_positional_mapping():
    m = default_positional_mapping(3)
    assert m["member_number"] == 0
    assert m["organization_name"] == 1
    assert m["organization_kana"] == 2
    assert m["representative_name"] is None  # 列が足りない


def test_guess_mapping_from_header_by_label():
    header = ["代表者名", "事業所名", "会員番号"]
    m = guess_mapping_from_header(header)
    assert m["representative_name"] == 0
    assert m["organization_name"] == 1
    assert m["member_number"] == 2
    assert m["phone"] is None


def test_build_member_rows_with_reordered_mapping():
    # 列順：事業所名 / 会員番号 / 代表者名
    raw = [["○○商事", "A-001", "田中太郎"]]
    mapping = {
        "organization_name": 0,
        "member_number": 1,
        "representative_name": 2,
    }
    rows = build_member_rows(raw, mapping)
    assert len(rows) == 1
    assert rows[0]["organization_name"] == "○○商事"
    assert rows[0]["member_number"] == "A-001"
    assert rows[0]["representative_name"] == "田中太郎"
    assert rows[0]["phone"] == ""  # 未割り当ては空


def test_build_member_rows_skips_header_and_required():
    raw = [
        ["事業所名", "会員番号"],   # 見出し
        ["○○商事", "A-001"],
        ["", ""],                  # 必須なし → 除外
    ]
    mapping = {"organization_name": 0, "member_number": 1}
    rows = build_member_rows(raw, mapping, has_header=True)
    assert len(rows) == 1
    assert rows[0]["organization_name"] == "○○商事"


# ── RosterImportDialog のテスト ──────────────────────────────────────────────

def test_roster_import_dialog_maps_rows(qtbot, memory_db):
    from app.ui.roster_import import RosterImportDialog
    dlg = RosterImportDialog(project_id=1)
    qtbot.addWidget(dlg)
    # 先頭列=NO.、2列目=会員番号、3列目=事業所名 の順でデータを渡す
    dlg._set_raw_rows([["1", "A-001", "○○商事", "田中"]])
    rows = dlg._mapped_rows()
    assert len(rows) == 1
    assert rows[0]["roster_no"] == "1"
    assert rows[0]["organization_name"] == "○○商事"
    assert rows[0]["member_number"] == "A-001"


def test_roster_import_includes_member_number(qtbot, memory_db):
    from app.ui.roster_import import RosterImportDialog
    from app.utils.excel_utils import ROSTER_COLUMNS
    dlg = RosterImportDialog(project_id=1)
    qtbot.addWidget(dlg)
    # 会員番号が取り込み対象に含まれる
    assert "member_number" in dlg._field_combos
    assert "member_number" in ROSTER_COLUMNS
    # 住所が住所１・住所２に分かれている
    assert "address" in ROSTER_COLUMNS
    assert "address2" in ROSTER_COLUMNS


def test_roster_import_includes_roster_no(qtbot, memory_db):
    from app.ui.roster_import import RosterImportDialog
    from app.utils.excel_utils import ROSTER_COLUMNS, FIELD_LABELS
    dlg = RosterImportDialog(project_id=1)
    qtbot.addWidget(dlg)
    assert ROSTER_COLUMNS[0] == "roster_no"
    assert FIELD_LABELS["roster_no"] == "NO."
    assert "roster_no" in dlg._field_combos


def test_roster_import_auto_detects_event_header(qtbot, memory_db):
    from app.ui.roster_import import RosterImportDialog
    dlg = RosterImportDialog(project_id=1)
    qtbot.addWidget(dlg)
    dlg._set_raw_rows([
        ["NO.", "事業所名", "参加者名①", "フリガナ①",
         "事業所所在地：郵便番号", "事業所所在地：市区町村番地",
         "事業所所在地：マンション・ビル名", "事業所電話番号"],
        ["1", "〇〇商事", "山田太郎", "ヤマダタロウ",
         "5100001", "四日市市〇〇町1-2", "〇〇ビル", "059-123-4567"],
    ])
    assert dlg._header_chk.isChecked()
    rows = dlg._mapped_rows()
    assert len(rows) == 1
    assert rows[0]["roster_no"] == "1"
    assert rows[0]["organization_name"] == "〇〇商事"
    assert rows[0]["representative_name"] == "山田太郎"
    assert rows[0]["postal_code"] == "5100001"
    assert rows[0]["address"] == "四日市市〇〇町1-2"


# ── 追加取り込み（既存名簿を残したまま追加する）──────────────────────────────

def _make_project_with_members(entries):
    """名簿つきプロジェクトを作成して project_id を返す。"""
    from app.database.connection import get_session
    from app.services.project_service import create_project, add_roster_entries
    session = get_session()
    try:
        proj = create_project(session, name="2026 新年互礼会", category_id=None,
                              fiscal_year=2026, project_type="list")
        if entries:
            add_roster_entries(session, proj.id, entries)
        return proj.id
    finally:
        session.close()


def test_import_appends_to_existing_roster(qtbot, memory_db):
    """確定済みの名簿に対し、既存行を消さずに追加できる。"""
    from app.ui.roster_import import RosterImportDialog
    from app.database.connection import get_session
    from app.services.project_service import get_project_members

    pid = _make_project_with_members([
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    dlg = RosterImportDialog(project_id=pid)
    qtbot.addWidget(dlg)
    assert dlg._existing_count == 1

    dlg._set_raw_rows([["2", "B-002", "△△産業", "", "佐藤"]])
    rows, skipped = dlg._rows_to_import()
    assert len(rows) == 1
    assert skipped == 0

    from app.services.project_service import add_roster_entries
    session = get_session()
    try:
        add_roster_entries(session, pid, rows)
        members = get_project_members(session, pid)
    finally:
        session.close()
    names = sorted(m.organization_name for m in members)
    assert names == ["△△産業", "○○商事"]


def test_import_skips_rows_already_in_roster(qtbot, memory_db):
    """会員番号・事業所名＋氏名が一致する行は重複としてスキップする。"""
    from app.ui.roster_import import RosterImportDialog

    pid = _make_project_with_members([
        {"member_number": "A-001", "organization_name": "○○商事",
         "representative_name": "田中"},
        {"organization_name": "□□工業", "representative_name": "鈴木"},
    ])
    dlg = RosterImportDialog(project_id=pid)
    qtbot.addWidget(dlg)
    assert dlg._dup_chk.isChecked()  # 既存があれば既定でスキップ

    dlg._set_raw_rows([
        ["1", "A-001", "○○商事", "", "田中"],   # 会員番号が一致 → 重複
        ["2", "", "□□工業", "", "鈴木"],        # 事業所名＋氏名が一致 → 重複
        ["3", "B-002", "△△産業", "", "佐藤"],   # 新規
    ])
    rows, skipped = dlg._rows_to_import()
    assert skipped == 2
    assert [r["organization_name"] for r in rows] == ["△△産業"]


def test_import_detects_duplicates_within_pasted_data(qtbot, memory_db):
    """貼り付けたデータの中で重複している行も1件だけ取り込む。"""
    from app.ui.roster_import import RosterImportDialog

    pid = _make_project_with_members([
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    dlg = RosterImportDialog(project_id=pid)
    qtbot.addWidget(dlg)
    dlg._set_raw_rows([
        ["1", "", "△△産業", "", "佐藤"],
        ["2", "", "△△産業", "", "佐藤"],
    ])
    rows, skipped = dlg._rows_to_import()
    assert len(rows) == 1
    assert skipped == 1


def test_import_can_keep_duplicates_when_unchecked(qtbot, memory_db):
    """重複チェックを外せば、同じ事業所でも追加できる（キャンセル分の再登録など）。"""
    from app.ui.roster_import import RosterImportDialog

    pid = _make_project_with_members([
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    dlg = RosterImportDialog(project_id=pid)
    qtbot.addWidget(dlg)
    dlg._dup_chk.setChecked(False)
    dlg._set_raw_rows([["1", "", "○○商事", "", "田中"]])
    rows, skipped = dlg._rows_to_import()
    assert len(rows) == 1
    assert skipped == 0


def test_empty_roster_keeps_import_defaults(qtbot, memory_db):
    """空の名簿では従来どおり全件が取り込み対象になる。"""
    from app.ui.roster_import import RosterImportDialog

    pid = _make_project_with_members([])
    dlg = RosterImportDialog(project_id=pid)
    qtbot.addWidget(dlg)
    assert dlg._existing_count == 0
    assert not dlg._dup_chk.isChecked()
    dlg._set_raw_rows([["1", "", "○○商事", "", "田中"]])
    rows, skipped = dlg._rows_to_import()
    assert len(rows) == 1
    assert skipped == 0


def test_preview_shows_state_column(qtbot, memory_db):
    """プレビュー先頭に「追加」「重複（スキップ）」を示す列がある。"""
    from app.ui.roster_import import RosterImportDialog

    pid = _make_project_with_members([
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    dlg = RosterImportDialog(project_id=pid)
    qtbot.addWidget(dlg)
    assert dlg._table.horizontalHeaderItem(0).text() == "取込"
    dlg._set_raw_rows([
        ["1", "", "○○商事", "", "田中"],
        ["2", "", "△△産業", "", "佐藤"],
    ])
    states = [dlg._table.item(r, 0).text() for r in range(dlg._table.rowCount())]
    assert states == ["重複（スキップ）", "追加"]
