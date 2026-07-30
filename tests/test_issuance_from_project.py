"""Tests for IssuanceFromProjectWidget (TDD)."""
from PyQt6.QtWidgets import QPushButton, QComboBox, QLabel


def _texts(w):
    return [b.text() for b in w.findChildren(QPushButton)]


def test_widget_uses_kenmei_label(qtbot, memory_db):
    """発行元の選択ラベルが用語統一で「件名：」になっている。"""
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    w = IssuanceFromProjectWidget()
    qtbot.addWidget(w)
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "件名：" in labels
    assert "名簿：" not in labels


def test_invoice_widget_has_correct_buttons(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    texts = _texts(w)
    assert "チェックした請求書を発行する" in texts
    assert "準備（採番）" not in texts


def test_receipt_widget_has_correct_buttons(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    w = IssuanceFromProjectWidget("receipt")
    qtbot.addWidget(w)
    texts = _texts(w)
    assert "チェックした領収書を発行する" in texts


def test_batch_output_mode_can_select_individual_pdf(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    assert w._pdf_output_combo.itemData(0) == "individual"
    assert w._pdf_output_combo.itemText(0) == "事業所ごとの個別PDF"
    assert w._pdf_output_combo.itemData(1) == "merged"


def test_widget_has_no_doctype_combo(qtbot, memory_db):
    """書類種別コンボは廃止され、タブで切り替える設計になっている。"""
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    w = IssuanceFromProjectWidget()
    qtbot.addWidget(w)
    combos = w.findChildren(QComboBox)
    for c in combos:
        datas = [c.itemData(i) for i in range(c.count())]
        assert "invoice" not in datas or "receipt" not in datas, \
            "書類種別コンボが残っている"


def _seed_two_members_with_issuances():
    """○○商事=請求書のみ発行済み / △△工業=請求書も領収書も発行済み。proj_id を返す。"""
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued
    s = get_session()
    cat = create_category(s, "青年部")
    tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(s, "2026 青年部会費", cat.id, 2026, "list")
    add_template_to_project(s, proj.id, tmpl.id)
    add_roster_entries(s, proj.id, [
        {"organization_name": "○○商事"},
        {"organization_name": "△△工業"},
    ])
    pms = get_project_members(s, proj.id)
    inv1 = create_issuance_for_member(s, proj.id, pms[0].id, "○○商事", "",
                                      "invoice", 2026, 5)
    mark_as_issued(s, inv1.id, None, "田中", "窓口手渡し")
    inv2 = create_issuance_for_member(s, proj.id, pms[1].id, "△△工業", "",
                                      "invoice", 2026, 5)
    mark_as_issued(s, inv2.id, None, "田中", "窓口手渡し")
    rcp2 = create_issuance_for_member(s, proj.id, pms[1].id, "△△工業", "",
                                      "receipt", 2026, 5)
    mark_as_issued(s, rcp2.id, None, "田中", "窓口手渡し")
    proj_id = proj.id
    s.close()
    return proj_id


def _select_project(w, proj_id):
    for i in range(w._proj_combo.count()):
        if w._proj_combo.itemData(i) == proj_id:
            w._proj_combo.setCurrentIndex(i)
            return


def test_excel_round_trip_updates_existing_issuance_lines(
        qtbot, memory_db, monkeypatch, tmp_path):
    import openpyxl
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    from app.database.connection import get_session
    from app.database.models import Issuance
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    import app.utils.app_config as app_config
    import app.utils.pdf_helpers as pdf_helpers

    session = get_session()
    category = create_category(session, "青年部")
    template = create_item_template(
        session, category.id, "参加費", 5000, "人", 10, "invoice", "")
    project = create_project(
        session, "2026 参加費", category.id, 2026, "list")
    add_template_to_project(session, project.id, template.id)
    add_roster_entries(
        session, project.id, [{"organization_name": "○○商事"}])
    member = get_project_members(session, project.id)[0]
    issuance = create_issuance_for_member(
        session, project.id, member.id, "○○商事", "",
        "invoice", 2026, 7,
    )
    project_id, issuance_id = project.id, issuance.id
    session.close()

    widget = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(widget)
    _select_project(widget, project_id)
    assert widget._table.rowCount() == 1

    xlsx_path = tmp_path / "単価数量入力.xlsx"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(xlsx_path), "Excel (*.xlsx)")))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    widget._export_excel()

    workbook = openpyxl.load_workbook(xlsx_path)
    sheet = workbook.active
    sheet["F2"] = 2500
    sheet["G2"] = 3
    workbook.save(xlsx_path)
    workbook.close()

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *args, **kwargs: (str(xlsx_path), "Excel (*.xlsx)")))
    widget._import_excel()

    assert widget._table.cellWidget(0, 5).value() == 2500
    assert widget._table.cellWidget(0, 6).value() == 3
    assert widget._table.item(0, 0).checkState().value == 2

    monkeypatch.setattr(app_config, "save_config", lambda _cfg: None)
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory",
        staticmethod(lambda *args, **kwargs: str(tmp_path)))
    monkeypatch.setattr(
        pdf_helpers, "generate_and_open",
        lambda *args, **kwargs: str(tmp_path / "invoice.pdf"))
    errors, _ = widget._do_issue_rows(widget._checked_rows())
    assert errors == []

    session = get_session()
    updated = session.get(Issuance, issuance_id)
    assert int(updated.amount) == 7500
    assert int(updated.lines[0].unit_price) == 2500
    assert int(updated.lines[0].quantity) == 3
    session.close()

    # 再編集後にPDF生成が失敗しても、確定済みの明細は変更しない。
    widget._table.cellWidget(0, 5).setValue(4000)
    widget._table.cellWidget(0, 6).setValue(4)

    def _fail_pdf(*args, **kwargs):
        raise RuntimeError("PDF error")

    monkeypatch.setattr(pdf_helpers, "generate_and_open", _fail_pdf)
    errors, _ = widget._do_issue_rows(widget._checked_rows())
    assert any("変更を取り消しました" in error for error in errors)

    session = get_session()
    restored = session.get(Issuance, issuance_id)
    assert int(restored.amount) == 7500
    assert int(restored.lines[0].unit_price) == 2500
    assert int(restored.lines[0].quantity) == 3
    session.close()


def test_two_columns_show_invoice_and_receipt_status(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget, COL_ORG
    proj_id = _seed_two_members_with_issuances()
    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    w._filter_combo.setCurrentIndex(1)  # すべて
    w._load_members()

    assert w._table.rowCount() == 2
    rows = {}
    for r in range(w._table.rowCount()):
        org = w._table.item(r, COL_ORG).text()
        rows[org] = (w._table.item(r, w._col_inv).text(),
                     w._table.item(r, w._col_rcp).text())
    # ○○商事：請求書発行済み・領収書未発行
    assert "発行済" in rows["○○商事"][0]
    assert "INV-" in rows["○○商事"][0]
    assert rows["○○商事"][1] == "未発行"
    # △△工業：請求書・領収書とも発行済み（古い方が消えない）
    assert "発行済" in rows["△△工業"][0]
    assert "INV-" in rows["△△工業"][0]
    assert "発行済" in rows["△△工業"][1]
    assert "RCP-" in rows["△△工業"][1]


def test_unissued_filter_per_doctype_invoice(qtbot, memory_db):
    """請求書タブの未発行フィルタ：請求書発行済みは非表示。"""
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    proj_id = _seed_two_members_with_issuances()
    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    w._filter_combo.setCurrentIndex(0)  # 未発行のみ
    w._load_members()
    # 両者とも請求書発行済みなので0件
    assert w._table.rowCount() == 0


def test_unissued_filter_per_doctype_receipt(qtbot, memory_db):
    """領収書タブの未発行フィルタ：領収書未発行の事業所のみ表示。"""
    from app.ui.issuance_from_project import IssuanceFromProjectWidget, COL_ORG
    proj_id = _seed_two_members_with_issuances()
    # ○○商事=請求書のみ発行済み/領収書未発行、△△工業=両方発行済み
    w = IssuanceFromProjectWidget("receipt")
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    w._filter_combo.setCurrentIndex(0)  # 未発行のみ
    w._load_members()
    orgs = [w._table.item(r, COL_ORG).text() for r in range(w._table.rowCount())]
    assert "○○商事" in orgs       # 領収書未発行
    assert "△△工業" not in orgs   # 領収書発行済み


def test_invoice_column_shows_voided_when_only_receipt(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued
    from app.ui.issuance_from_project import IssuanceFromProjectWidget, COL_ORG
    s = get_session()
    cat = create_category(s, "青年部")
    tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(s, "2026 青年部会費", cat.id, 2026, "list")
    add_template_to_project(s, proj.id, tmpl.id)
    add_roster_entries(s, proj.id, [
        {"organization_name": "○○商事"},
        {"organization_name": "△△工業"},
    ])
    pms = get_project_members(s, proj.id)
    # ○○商事：領収書のみ発行（請求書なし）→ 無効
    rcp = create_issuance_for_member(s, proj.id, pms[0].id, "○○商事", "",
                                     "receipt", 2026, 5)
    mark_as_issued(s, rcp.id, None, "田中", "窓口手渡し")
    # △△工業：請求書発行済み
    inv = create_issuance_for_member(s, proj.id, pms[1].id, "△△工業", "",
                                     "invoice", 2026, 5)
    mark_as_issued(s, inv.id, None, "田中", "窓口手渡し")
    proj_id = proj.id
    s.close()

    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    w._filter_combo.setCurrentIndex(1)  # すべて
    w._load_members()

    rows = {}
    for r in range(w._table.rowCount()):
        rows[w._table.item(r, COL_ORG).text()] = w._table.item(r, w._col_inv).text()
    assert rows["○○商事"] == "無効"          # 領収書のみ → 請求書は無効
    assert "発行済" in rows["△△工業"]        # 請求書発行済みは従来どおり


def test_unissued_filter_hides_voided_invoice(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued
    from app.ui.issuance_from_project import IssuanceFromProjectWidget, COL_ORG
    s = get_session()
    cat = create_category(s, "青年部")
    tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(s, "2026 青年部会費", cat.id, 2026, "list")
    add_template_to_project(s, proj.id, tmpl.id)
    add_roster_entries(s, proj.id, [
        {"organization_name": "○○商事"},   # 領収書のみ → 請求書無効
        {"organization_name": "××物産"},   # 何も発行なし → 純粋に未発行
    ])
    pms = get_project_members(s, proj.id)
    rcp = create_issuance_for_member(s, proj.id, pms[0].id, "○○商事", "",
                                     "receipt", 2026, 5)
    mark_as_issued(s, rcp.id, None, "田中", "窓口手渡し")
    proj_id = proj.id
    s.close()

    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    w._filter_combo.setCurrentIndex(0)  # 未発行のみ
    w._load_members()

    orgs = [w._table.item(r, COL_ORG).text() for r in range(w._table.rowCount())]
    assert "○○商事" not in orgs   # 無効は対応不要なので出ない
    assert "××物産" in orgs       # 純粋な未発行は出る


def test_issue_checked_skips_voided_invoice(qtbot, memory_db, monkeypatch):
    import app.utils.app_config as app_config
    monkeypatch.setattr(app_config, "save_config", lambda _cfg: None)
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued
    from app.ui.issuance_from_project import IssuanceFromProjectWidget, COL_CHK
    from app.database.models import Issuance
    from PyQt6.QtCore import Qt
    s = get_session()
    cat = create_category(s, "青年部")
    tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(s, "2026 青年部会費", cat.id, 2026, "list")
    add_template_to_project(s, proj.id, tmpl.id)
    add_roster_entries(s, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(s, proj.id)[0]
    rcp = create_issuance_for_member(s, proj.id, pm.id, "○○商事", "",
                                     "receipt", 2026, 5)
    mark_as_issued(s, rcp.id, None, "田中", "窓口手渡し")
    proj_id, pm_id = proj.id, pm.id
    s.close()

    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    w._filter_combo.setCurrentIndex(1)  # すべて表示で○○商事（無効）を出す
    w._load_members()
    assert w._table.rowCount() == 1
    # 行をチェックして請求書を発行
    w._table.item(0, COL_CHK).setCheckState(Qt.CheckState.Checked)
    w._issue_checked()

    # 無効なので請求書は作られない
    s = get_session()
    cnt = (s.query(Issuance)
           .filter_by(project_member_id=pm_id, doc_type="invoice")
           .count())
    s.close()
    assert cnt == 0
