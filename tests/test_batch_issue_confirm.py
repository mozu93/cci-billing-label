# tests/test_batch_issue_confirm.py
"""まとめて発行：「発行する」で発行方法と支払期日（領収書は発行日）を確認するダイアログ。

以前は発行の設定にある発行方法のまま、いきなりメールの送信画面になり、
支払期日も入力し忘れやすかった。
"""
from datetime import date

import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QDialog


def test_dialog_defaults_and_values(qtbot):
    from app.ui.batch_issue_confirm_dialog import BatchIssueConfirmDialog
    dlg = BatchIssueConfirmDialog(None, count=66, doc_type="invoice",
                                  delivery="メール送付", doc_date=date(2026, 10, 31))
    qtbot.addWidget(dlg)
    assert "66 件" in dlg._message.text()
    assert dlg.delivery() == "メール送付"
    assert dlg.doc_date() == date(2026, 10, 31)
    assert dlg._date_label.text() == "支払期日："
    dlg._print_radio.setChecked(True)
    dlg._date_edit.setDate(QDate(2026, 11, 30))
    assert dlg.delivery() == "印刷"
    assert dlg.doc_date() == date(2026, 11, 30)


def test_receipt_asks_issue_date(qtbot):
    from app.ui.batch_issue_confirm_dialog import BatchIssueConfirmDialog
    dlg = BatchIssueConfirmDialog(None, count=3, doc_type="receipt",
                                  delivery="印刷", doc_date=date(2026, 9, 25))
    qtbot.addWidget(dlg)
    assert dlg._date_label.text() == "発行日："
    assert "領収書" in dlg.windowTitle()


# ── 発行画面との連携 ─────────────────────────────────────────────

@pytest.fixture
def widget(qtbot, memory_db, monkeypatch):
    import app.utils.app_config as app_config
    from app.database.connection import get_session
    from app.services.project_service import add_roster_entries, create_project
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    monkeypatch.setattr(app_config, "get_config", lambda: {})
    monkeypatch.setattr(app_config, "save_config", lambda c: None)
    s = get_session()
    proj = create_project(s, "視察研修会", None, 2026, "list")
    proj.due_date = date(2026, 12, 25)          # この名簿で前回使った支払期日
    s.commit()
    add_roster_entries(s, proj.id, [{"organization_name": "○○商店"}])
    s.close()
    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    w._proj_combo.setCurrentIndex(w._proj_combo.findText("視察研修会"))
    calls = []
    monkeypatch.setattr(w, "_do_issue_rows", lambda targets: calls.append(
        (w._delivery_combo.currentText(), w._due_date.date().toPyDate())) or ([], []))
    monkeypatch.setattr(w, "_checked_rows", lambda: [(0, 1)])
    return w, calls


def _fake_dialog(monkeypatch, accept, delivery="印刷", doc_date=date(2026, 11, 30)):
    import app.ui.batch_issue_confirm_dialog as mod
    seen = {}

    class _Dlg:
        def __init__(self, parent, count, doc_type, delivery, doc_date):
            seen.update(count=count, delivery=delivery, doc_date=doc_date)

        def exec(self):
            return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

        def delivery(self_):
            return delivery_value

        def doc_date(self_):
            return date_value

    delivery_value, date_value = delivery, doc_date
    monkeypatch.setattr(mod, "BatchIssueConfirmDialog", _Dlg)
    return seen


def test_issue_uses_values_from_dialog(widget, monkeypatch):
    w, calls = widget
    seen = _fake_dialog(monkeypatch, accept=True, delivery="印刷",
                        doc_date=date(2026, 11, 30))
    w._issue_checked()
    assert seen["doc_date"] == date(2026, 12, 25)   # 名簿で前回使った支払期日が初期値
    assert seen["count"] == 1
    assert calls == [("印刷", date(2026, 11, 30))]


def test_cancel_does_nothing(widget, monkeypatch):
    w, calls = widget
    _fake_dialog(monkeypatch, accept=False)
    w._issue_checked()
    assert calls == []


def test_delivery_and_due_date_are_not_in_settings(widget):
    """発行方法と支払期日は発行時に決めるので、発行の設定には置かない。"""
    w, _ = widget
    assert not w._settings_panel.isAncestorOf(w._delivery_combo)
    assert not w._settings_panel.isAncestorOf(w._due_date)
    summary = w._settings_summary.text().replace("\u2060", "")
    assert "支払期日" not in summary
    assert "メール送付" not in summary and not summary.startswith("印刷")


def test_preview_uses_projects_last_due_date(widget):
    """名簿を選ぶと、その名簿で前回使った支払期日がプレビューにも使われる。"""
    w, _ = widget
    assert w._due_date.date().toPyDate() == date(2026, 12, 25)
