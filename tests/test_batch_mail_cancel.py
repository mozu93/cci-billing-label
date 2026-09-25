# tests/test_batch_mail_cancel.py
"""まとめて発行のメール送付：途中で残りをまとめて中止でき、送らなかった書類は準備中に戻す。

以前は1件ずつキャンセルするしかなく（66件なら66回）、キャンセルしても
送信確認の前に発行済みにしていたため、発行済みのまま残っていた。
"""
import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog, QMessageBox


class _FakeWorker(QObject):
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, *a, **k):
        super().__init__()

    def run(self):
        self.finished.emit({"status": "accepted"})


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
        {"organization_name": f"商店{i}", "email": f"s{i}@example.invalid"} for i in range(3)])
    for i, pm in enumerate(pms):
        s.add(Issuance(project_id=pid, project_member_id=pm.id, doc_type="invoice",
                       doc_number=f"INV-2026-{i + 1:04d}", status="発行済み", amount=10000,
                       recipient_organization=pm.organization_name))
    s.commit()
    s.close()

    monkeypatch.setattr(app_config, "get_m365_client_id", lambda: "client")
    monkeypatch.setattr(app_config, "get_m365_tenant_id", lambda: "tenant")
    monkeypatch.setattr(email_service, "prepare_issuance_email",
                        lambda sess, iss, to_addr=None: (to_addr, "件名", "<p>本文</p>", "x.pdf"))
    monkeypatch.setattr(email_service, "get_issuance_email_context", lambda sess, iss: {})
    monkeypatch.setattr(m365_mail_worker, "M365MailWorker", _FakeWorker)

    state = {"answers": [], "dialogs": 0, "questions": [], "infos": []}

    class _Dialog:
        def __init__(self, *a, **k):
            state["dialogs"] += 1
            self._accept = state["answers"].pop(0)

        def exec(self):
            return (QDialog.DialogCode.Accepted if self._accept
                    else QDialog.DialogCode.Rejected)

        def to_recipients(self): return ["x@example.invalid"]
        def cc_recipients(self): return []
        def bcc_recipients(self): return []
        def subject(self): return "件名"
        def body_html(self): return "<p>本文</p>"

    monkeypatch.setattr(mail_dialog, "InvoiceMailConfirmDialog", _Dialog)

    def fake_question(*a, **k):
        state["questions"].append(a[2])
        return QMessageBox.StandardButton.Yes    # 残りもすべてやめる
    monkeypatch.setattr(QMessageBox, "question", fake_question)
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: state["infos"].append(a[2]))

    w = IssuanceFromProjectWidget("invoice")
    qtbot.addWidget(w)
    return w, state


def _issued(was_issued=False):
    """_send_issue_emails に渡す (書類, セッション, 以前から発行済みか) の一覧。"""
    from app.database.connection import get_session
    from app.database.models import Issuance
    s = get_session()
    rows = s.query(Issuance).order_by(Issuance.doc_number).all()
    return s, [(iss, s, was_issued) for iss in rows]


def _statuses():
    from app.database.connection import get_session
    from app.database.models import Issuance
    s = get_session()
    try:
        return [i.status for i in s.query(Issuance).order_by(Issuance.doc_number)]
    finally:
        s.close()


def test_cancel_all_at_once_reverts_everything(env):
    w, state = env
    state["answers"] = [False]                  # 1件目でキャンセル
    s, items = _issued()
    reverted = w._send_issue_emails(items, [])
    s.close()
    assert state["dialogs"] == 1                # 残りの確認画面は出ない
    assert any("残り 2 件" in q for q in state["questions"])
    assert _statuses() == ["準備中"] * 3
    assert sorted(reverted) == ["INV-2026-0001", "INV-2026-0002", "INV-2026-0003"]


def test_sent_ones_stay_issued(env):
    w, state = env
    state["answers"] = [True, False]            # 1件目は送信、2件目でキャンセルして中止
    s, items = _issued()
    reverted = w._send_issue_emails(items, [])
    s.close()
    assert _statuses() == ["発行済み", "準備中", "準備中"]
    assert sorted(reverted) == ["INV-2026-0002", "INV-2026-0003"]
    assert any("送信しなかった 2 件" in m for m in state["infos"])


def test_previously_issued_are_not_reverted(env):
    """以前から発行済みだった書類（再送）は、キャンセルしても発行済みのまま。"""
    w, state = env
    state["answers"] = [False]
    s, items = _issued(was_issued=True)
    reverted = w._send_issue_emails(items, [])
    s.close()
    assert _statuses() == ["発行済み"] * 3
    assert reverted == []
