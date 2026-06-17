# tests/test_counter_issuance_tab.py
from PyQt6.QtWidgets import QTabWidget


def _tab_titles(tabwidget: QTabWidget) -> list[str]:
    return [tabwidget.tabText(i) for i in range(tabwidget.count())]


def test_counter_issuance_subtabs(qtbot, memory_db):
    from app.ui.counter_issuance_tab import CounterIssuanceTab
    w = CounterIssuanceTab()
    qtbot.addWidget(w)
    inner = w.findChild(QTabWidget)
    assert inner is not None
    assert _tab_titles(inner) == ["請求書", "領収書"]


def _seed_duplicate_named_templates():
    """同名「視察研修会参加費」を別業務で2件登録し、(t1, t2) を返す。"""
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    s = get_session()
    c1 = create_category(s, "不動産部会")
    c2 = create_category(s, "建設部会")
    t1 = create_item_template(s, c1.id, "視察研修会参加費", 5000, "人", 0, "receipt", "")
    t2 = create_item_template(s, c2.id, "視察研修会参加費", 6000, "人", 0, "receipt", "")
    ids = (t1.id, t2.id)
    s.close()
    return ids


def test_freeissue_item_combo_shows_category_when_unfiltered(qtbot, memory_db):
    """業務名未選択時は、同名項目に業務名を併記して見分けられる。"""
    _seed_duplicate_named_templates()
    from app.ui.issuance_counter import IssuanceCounterWidget
    w = IssuanceCounterWidget()
    qtbot.addWidget(w)
    w._reload_master()
    row = w._rows[0]
    labels = [row.tmpl_combo.itemText(i) for i in range(row.tmpl_combo.count())]
    assert any("視察研修会参加費（不動産部会）" in t for t in labels)
    assert any("視察研修会参加費（建設部会）" in t for t in labels)


def test_freeissue_groups_by_item_category(qtbot, memory_db):
    """業務名を選ばず項目だけ選んでも、項目の業務名に集計される。"""
    _t1_id, t2_id = _seed_duplicate_named_templates()
    from app.ui.issuance_counter import IssuanceCounterWidget
    w = IssuanceCounterWidget()
    qtbot.addWidget(w)
    w._reload_master()
    row = w._rows[0]
    idx = next(i for i in range(row.tmpl_combo.count())
               if row.tmpl_combo.itemData(i) == t2_id)
    row.tmpl_combo.setCurrentIndex(idx)
    # 業務名コンボは未選択（None）のまま
    assert row.cat_combo.currentData() is None
    assert w._derive_project_name() == "建設部会"


def test_issue_invoice_warns_when_no_company_settings(qtbot, memory_db, monkeypatch):
    """会社情報が未登録のまま発行すると、PDFが無言で生成されないのを防ぐため警告して発行を中止する。"""
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.database.models import Issuance
    import app.ui.issuance_counter as ic

    s = get_session()
    cat = create_category(s, "不動産部会")
    create_item_template(s, cat.id, "視察研修会参加費", 5000, "人", 0, "invoice", "")
    s.close()

    warnings = []
    monkeypatch.setattr(ic.QMessageBox, "warning", lambda *a, **k: warnings.append(a))
    monkeypatch.setattr(ic.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(ic.QMessageBox, "critical", lambda *a, **k: None)
    # 会社情報チェックより先にファイル保存ダイアログ（実モーダル）に到達したら
    # テストがブロックするので、安全側として空応答にしておく。
    from PyQt6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    w = ic.IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    w._reload_master()
    w._org_name.setText("テスト株式会社")
    row = w._rows[0]
    idx = next(i for i in range(row.tmpl_combo.count())
               if row.tmpl_combo.itemData(i) is not None)
    row.tmpl_combo.setCurrentIndex(idx)

    w._issue()

    assert len(warnings) == 1
    s = get_session()
    assert s.query(Issuance).count() == 0  # 会社情報未登録なら発行記録も作られない
    s.close()


def test_issuer_combo_changing_resets_bank_and_seal(qtbot, memory_db):
    """発行元コンボを変更すると、銀行口座・印鑑コンボがその発行元のデフォルトにリセットされる。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings, BankAccount, SealImage
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    cs1 = CompanySettings(name="発行元A", is_default=True)
    cs2 = CompanySettings(name="発行元B", is_default=False)
    s.add_all([cs1, cs2])
    s.commit()
    bank2 = BankAccount(company_id=cs2.id, label="B口座", bank_name="△△銀行", is_default=True)
    seal2 = SealImage(company_id=cs2.id, label="B印鑑", path="/tmp/b.png", is_default=True)
    s.add_all([bank2, seal2])
    s.commit()
    cs2_id, bank2_id, seal2_id = cs2.id, bank2.id, seal2.id
    s.close()

    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)

    idx = next(i for i in range(w._issuer_combo.count())
               if w._issuer_combo.itemData(i) == cs2_id)
    w._issuer_combo.setCurrentIndex(idx)

    assert w._bank_combo.currentData() == bank2_id
    assert w._seal_combo.currentData() == seal2_id


def test_show_person_checkbox_defaults_to_true_when_unset(qtbot, memory_db, monkeypatch):
    """recipient_person_last が未設定の場合はチェック済み（既存挙動）になる。

    app_config はホームディレクトリの実ファイルを読み書きするため、開発機に残った
    過去の設定値に依存しないよう get_config をその場でモックする。
    """
    import app.utils.app_config as cfg_mod
    monkeypatch.setattr(cfg_mod, "get_config", lambda: {})
    from app.ui.issuance_counter import IssuanceCounterWidget
    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    assert w._show_person_chk.isChecked() is True


def test_payment_dialog_collect_only_mode(qtbot, memory_db):
    """auto_record=False では record_payment を呼ばず値だけ返す。"""
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import (
        create_issuance_for_member, mark_as_issued,
    )
    from app.ui.payment_dialog import PaymentDialog
    from app.database.models import Payment

    s = get_session()
    cat = create_category(s, "青年部")
    tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(s, "2026 青年部", cat.id, 2026, "list")
    add_template_to_project(s, proj.id, tmpl.id)
    add_roster_entries(s, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(s, proj.id)[0]
    inv = create_issuance_for_member(s, proj.id, pm.id, "○○商事", "",
                                     "invoice", 2026, 5)
    mark_as_issued(s, inv.id, None, "田中", "窓口手渡し")
    inv_id = inv.id
    s.close()

    dlg = PaymentDialog(inv_id, auto_record=False)
    qtbot.addWidget(dlg)
    v = dlg.values()
    assert set(v.keys()) == {"payment_date", "amount", "payment_method", "notes"}
    from datetime import date as _date
    assert isinstance(v["payment_date"], _date)
    assert v["amount"] == 5000

    dlg._save()  # accept のみ。record_payment は呼ばれない
    s = get_session()
    assert s.query(Payment).filter_by(issuance_id=inv_id).count() == 0
    s.close()


def test_issue_invoice_persists_selected_issuer_and_display_setting(qtbot, memory_db, monkeypatch):
    """単発発行（請求書）で選んだ発行元・宛名表示設定が Issuance に保存される。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings, Issuance
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    import app.ui.issuance_counter as ic
    from PyQt6.QtWidgets import QFileDialog

    # app_config は実ファイル（~/.cci-billing/config.json）を読み書きするため、
    # テストで開発機の実ファイルを汚さないようインメモリの辞書に差し替える。
    import app.utils.app_config as cfg_mod
    _fake_cfg: dict = {}
    monkeypatch.setattr(cfg_mod, "get_config", lambda: _fake_cfg)
    monkeypatch.setattr(cfg_mod, "save_config", lambda c: _fake_cfg.update(c))

    s = get_session()
    cs1 = CompanySettings(name="発行元A", is_default=True)
    cs2 = CompanySettings(name="発行元B", is_default=False)
    s.add_all([cs1, cs2])
    s.commit()
    cat = create_category(s, "不動産部会")
    create_item_template(s, cat.id, "視察研修会参加費", 5000, "人", 0, "invoice", "")
    cs2_id = cs2.id
    s.close()

    monkeypatch.setattr(ic.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    w = ic.IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    w._reload_master()
    w._org_name.setText("テスト株式会社")
    row = w._rows[0]
    idx = next(i for i in range(row.tmpl_combo.count()) if row.tmpl_combo.itemData(i) is not None)
    row.tmpl_combo.setCurrentIndex(idx)

    issuer_idx = next(i for i in range(w._issuer_combo.count())
                      if w._issuer_combo.itemData(i) == cs2_id)
    w._issuer_combo.setCurrentIndex(issuer_idx)
    w._show_person_chk.setChecked(False)

    w._issue()

    s = get_session()
    iss = s.query(Issuance).order_by(Issuance.id.desc()).first()
    assert iss.company_settings_id == cs2_id
    assert iss.show_recipient_person is False
    s.close()
    assert _fake_cfg["recipient_person_last"] is False  # 次回デフォルト用に記憶される


def test_edit_issuance_restores_issuer_and_display_setting(qtbot, memory_db):
    """内容修正で開くと、保存済みの発行元・宛名表示設定が復元される。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings
    from app.services.issuance_service import create_direct_issuance
    import app.ui.issuance_counter as ic

    s = get_session()
    cs1 = CompanySettings(name="発行元A", is_default=True)
    cs2 = CompanySettings(name="発行元B", is_default=False)
    s.add_all([cs1, cs2])
    s.commit()
    lines = [{"item_template_id": None, "item_name": "会費",
              "quantity": 1, "unit": "式", "unit_price": 5000, "tax_rate": 0}]
    iss = create_direct_issuance(
        s, lines_data=lines,
        recipient_organization="○○商事", recipient_name="",
        doc_type="invoice", fiscal_year=2026, month=6,
        company_settings_id=cs2.id, show_recipient_person=False,
    )
    iss_id, cs2_id = iss.id, cs2.id
    s.close()

    w = ic.IssuanceCounterWidget("invoice", edit_issuance_id=iss_id)
    qtbot.addWidget(w)
    w._reload_master()
    w._load_edit_data()

    assert w._issuer_combo.currentData() == cs2_id
    assert w._show_person_chk.isChecked() is False

