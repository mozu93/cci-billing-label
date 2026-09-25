# tests/test_batch_mail_cancel.py
"""まとめて発行のメール送付：確認は1回だけで、あとは一括送信する。

以前は1件ずつ送信確認画面と最終確認が出て、66件なら132回のクリックが必要だった。
1件目を見本に確認画面を1回だけ出し、そこで直した件名・本文のテンプレートを
各書類に差し込んで一括送信する。中止・失敗・宛先なしで送らなかった分は準備中に戻す。
"""
import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog, QMessageBox


class _FakeBatchWorker(QObject):
    """M365ReminderBatchWorker の代わり。stop_after 件で中止した扱いにできる。"""
    progress = pyqtSignal(int, int)
    done = pyqtSignal(int, list)
    created: list = []
    stop_after = None

    def __init__(self, client_id, tenant_id, items, *a, **k):
        super().__init__()
        self._items = items
        self._results = []
        _FakeBatchWorker.created.append(self)

    @property
    def results(self):
        return list(self._results)

    def cancel(self):
        pass

    def run(self):
        n = len(self._items) if self.stop_after is None else self.stop_after
        for item in self._items[:n]:
            self._results.append({"item": item, "success": True, "error": ""})
        self.done.emit(n, [])


@pytest.fixture
def env(qtbot, memory_db, monkeypatch):
    import app.services.email_service as email_service
    import app.ui.invoice_mail_confirm_dialog as mail_dialog
    import app.ui.m365_mail_worker as m365_mail_worker
    import app.utils.app_config as app_config
    from app.database.connection import get_session
    from app.database.models import Issuance
    from app.services.project_service import add_roster_entries, create_project
    from app.ui.issuance_from_project import IssuanceFromProjectWidget

    s = get_session()
    pid = create_project(s, "視察研修会", None, 2026, "list").id
    pms = add_roster_entries(s, pid, [
        {"organization_name": "商店0", "email": "s0@example.invalid"},
        {"organization_name": "商店1", "email": "s1@example.invalid"},
        {"organization_name": "商店2", "email": ""},              # 宛先なし
    ])
    for i, pm in enumerate(pms):
        s.add(Issuance(project_id=pid, project_member_id=pm.id, doc_type="invoice",
                       doc_number=f"INV-2026-{i + 1:04d}", status="発行済み", amount=10000,
                       recipient_organization=pm.organization_name))
    s.commit()
    s.close()

    monkeypatch.setattr(app_config, "get_m365_client_id", lambda: "client")
    monkeypatch.setattr(app_config, "get_m365_tenant_id", lambda: "tenant")

    def fake_prepare(sess, iss, to_addr=None):
        if not to_addr:
            raise ValueError(f"{iss.recipient_organization}：メールアドレスが登録されていません。")
        return to_addr, "件名", "<p>本文</p>", "x.pdf"
    monkeypatch.setattr(email_service, "prepare_issuance_email", fake_prepare)
    monkeypatch.setattr(email_service, "get_issuance_email_context",
                        lambda sess, iss: {"事業所名": iss.recipient_organization,
                                           "文書番号": iss.doc_number})
    _FakeBatchWorker.created = []
    _FakeBatchWorker.stop_after = None
    monkeypatch.setattr(m365_mail_worker, "M365ReminderBatchWorker", _FakeBatchWorker)

    state = {"accept": True, "dialogs": [], "confirm": QMessageBox.StandardButton.Yes,
             "questions": [], "infos": []}

    class _Dialog:
        def __init__(self, *a, **k):
            state["dialogs"].append(k)

        def exec(self):
            return QDialog.DialogCode.Accepted if state["accept"] else QDialog.DialogCode.Rejected

        def template_subject(self): return "{文書番号} のご案内"
        def template_body(self): return "{事業所名} 様"
        def cc_recipients(self): return ["cc@example.invalid"]
        def bcc_recipients(self): return []

    monkeypatch.setattr(mail_dialog, "InvoiceMailConfirmDialog", _Dialog)

    def fake_question(*a, **k):
        state["questions"].append(a[2])
        return state["confirm"]
    monkeypatch.setattr(QMessageBox, "question", fake_question)
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: state["infos"].append(a[2]))

    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    return w, state


def _send(w, was_issued=False):
    from app.database.connection import get_session
    from app.database.models import Issuance
    s = get_session()
    items = [(iss, s, was_issued)
             for iss in s.query(Issuance).order_by(Issuance.doc_number).all()]
    errors = []
    reverted = w._send_issue_emails(items, errors)
    s.close()
    return reverted, errors


def _rows():
    from app.database.connection import get_session
    from app.database.models import Issuance
    s = get_session()
    try:
        return [(i.status, i.mail_sent_at is not None)
                for i in s.query(Issuance).order_by(Issuance.doc_number)]
    finally:
        s.close()


def test_confirm_once_then_send_all_with_rendered_mails(env):
    w, state = env
    reverted, errors = _send(w)
    assert len(state["dialogs"]) == 1                 # 確認画面は1回だけ
    assert state["dialogs"][0].get("bulk_count") == 2  # 送れるのは2件（宛先なし1件）
    assert any("2 件" in q and "1 件" in q for q in state["questions"])
    items = _FakeBatchWorker.created[0]._items
    assert [i["to"] for i in items] == ["s0@example.invalid", "s1@example.invalid"]
    # テンプレートを書類ごとに差し込む
    assert [i["subject"] for i in items] == ["INV-2026-0001 のご案内", "INV-2026-0002 のご案内"]
    assert "商店1 様" in items[1]["body_html"]
    assert items[0]["cc"] == ["cc@example.invalid"]
    # 送れた2件は送信記録あり、宛先なしは準備中に戻る
    assert _rows() == [("発行済み", True), ("発行済み", True), ("準備中", False)]
    assert reverted == ["INV-2026-0003"]
    assert any("メールアドレス" in e for e in errors)


def test_cancel_in_confirm_reverts_all(env):
    w, state = env
    state["accept"] = False
    reverted, _ = _send(w)
    assert _FakeBatchWorker.created == []
    assert _rows() == [("準備中", False)] * 3
    assert len(reverted) == 3


def test_no_at_final_confirm_reverts_all(env):
    w, state = env
    state["confirm"] = QMessageBox.StandardButton.No
    _send(w)
    assert _FakeBatchWorker.created == []
    assert _rows() == [("準備中", False)] * 3


def test_stopped_midway_reverts_unsent(env):
    w, state = env
    _FakeBatchWorker.stop_after = 1                 # 1件送ったところで中止
    reverted, _ = _send(w)
    assert _rows() == [("発行済み", True), ("準備中", False), ("準備中", False)]
    assert sorted(reverted) == ["INV-2026-0002", "INV-2026-0003"]


def test_previously_issued_are_not_reverted(env):
    w, state = env
    state["accept"] = False
    reverted, _ = _send(w, was_issued=True)
    assert _rows() == [("発行済み", False)] * 3
    assert reverted == []


def test_confirm_dialog_bulk_mode(qtbot, monkeypatch):
    """一括送信では宛先を直せず、画面の中の1件用の最終確認は出さない。"""
    from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: pytest.fail("1件用の最終確認が出た"))
    dlg = InvoiceMailConfirmDialog(
        None, to_recipients=["s0@example.invalid"], subject="件名",
        body_html="<p>本文</p>", invoice_no="INV-2026-0001", bulk_count=66)
    qtbot.addWidget(dlg)
    assert "66 件" in dlg.windowTitle()
    assert dlg._to_edit.isReadOnly()
    dlg._accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
