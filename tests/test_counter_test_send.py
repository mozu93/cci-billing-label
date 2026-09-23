# tests/test_counter_test_send.py
"""単発発行：番号を使わずに、自分宛てに請求書メールを試し送信する。"""
import os

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog, QInputDialog, QMessageBox


class _FakeWorker(QObject):
    """M365MailWorker の代わり。送信内容を記録して成功を返す。"""
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)
    sent: list = []

    def __init__(self, client_id, tenant_id, to_recipients, subject, body_html,
                 pdf_path=None, cc_recipients=None, bcc_recipients=None, **kwargs):
        super().__init__()
        self.args = dict(to=to_recipients, subject=subject, body=body_html,
                         pdf=pdf_path, cc=cc_recipients, bcc=bcc_recipients)

    def run(self):
        _FakeWorker.sent.append(self.args)
        self.finished.emit({"status": "accepted"})


@pytest.fixture
def widget(qtbot, memory_db, monkeypatch, tmp_path):
    import app.services.email_service as email_service
    import app.ui.m365_mail_worker as m365_mail_worker
    import app.utils.app_config as app_config
    import app.utils.pdf_helpers as pdf_helpers
    from app.database.connection import get_session
    from app.database.models import CompanySettings
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    s.add(CompanySettings(name="四日市商工会議所", is_default=True))
    s.commit()
    s.close()
    monkeypatch.setattr(app_config, "get_config", lambda: {})
    monkeypatch.setattr(app_config, "save_config", lambda cfg: None)
    monkeypatch.setattr(app_config, "get_m365_client_id", lambda: "client")
    monkeypatch.setattr(app_config, "get_m365_tenant_id", lambda: "tenant")
    monkeypatch.setattr(app_config, "get_m365_test_recipient", lambda: "me@example.invalid")
    monkeypatch.setattr(pdf_helpers, "get_preview_dir", lambda: tmp_path / "preview")
    monkeypatch.setattr(email_service, "get_email_template",
                        lambda kind, template_id=None: ("{書類名}送付のご案内", "{宛名} 様"))
    _FakeWorker.sent = []
    monkeypatch.setattr(m365_mail_worker, "M365MailWorker", _FakeWorker)
    msgs = {"information": [], "question": []}
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: msgs["information"].append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(a[2]))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail(a[2]))

    w = IssuanceCounterWidget(doc_type="invoice")
    qtbot.addWidget(w)
    w._reload_master()
    w._delivery.setCurrentText("メール送付")
    w._org_name.setText("○○商店")
    w._email.setText("shop@example.invalid")
    row = w._rows[0]
    row.tmpl_combo.setEditText("年会費")
    row.price_edit.setText("10000")
    w.msgs = msgs
    return w


def _issuances():
    from app.database.connection import get_session
    from app.database.models import Issuance
    s = get_session()
    try:
        return s.query(Issuance).all()
    finally:
        s.close()


def test_test_send_button_only_for_mail(widget):
    widget._delivery.setCurrentText("印刷")
    assert widget._btn_test_send.isHidden()
    widget._delivery.setCurrentText("メール送付")
    assert not widget._btn_test_send.isHidden()


def test_test_send_sends_sample_to_one_address_without_saving(widget, monkeypatch):
    asked = {}

    def fake_get_text(parent, title, label, *a, text="", **k):
        asked["default"] = text
        return "tester@example.invalid", True
    monkeypatch.setattr(QInputDialog, "getText", fake_get_text)

    widget._test_send()

    assert asked["default"] == "me@example.invalid"   # 設定の受信先が初期値
    sent = _FakeWorker.sent[0]
    assert sent["to"] == ["tester@example.invalid"]  # お客様のアドレスには送らない
    assert not sent["cc"] and not sent["bcc"]
    assert sent["subject"] == "【テスト】請求書送付のご案内"
    assert "これはテスト送信です" in sent["body"]
    assert os.path.exists(sent["pdf"]) and "preview" in sent["pdf"]
    assert _issuances() == []                          # 発行・採番・送信記録なし
    assert any("テストメールを送信しました" in m for m in widget.msgs["information"])


def test_test_send_cancelled_sends_nothing(widget, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    widget._test_send()
    assert _FakeWorker.sent == []


def test_real_mail_send_still_records_sent_mail(widget, monkeypatch):
    """送信処理を共通化した後も、本番の送信は記録される（回帰防止）。"""
    import app.ui.invoice_mail_confirm_dialog as mail_dialog

    class _Accepting:
        def __init__(self, *a, **k):
            pass
        def exec(self): return QDialog.DialogCode.Accepted
        def to_recipients(self): return ["shop@example.invalid"]
        def cc_recipients(self): return ["boss@example.invalid"]
        def bcc_recipients(self): return []
        def subject(self): return "請求書送付のご案内"
        def body_html(self): return "<p>本文</p>"
    monkeypatch.setattr(mail_dialog, "InvoiceMailConfirmDialog", _Accepting)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: pytest.fail("送信成功時に印刷切り替えを聞いた"))

    widget._issue()

    rows = _issuances()
    assert len(rows) == 1
    assert rows[0].mail_sent_at is not None
    assert rows[0].mail_subject == "請求書送付のご案内"
    assert _FakeWorker.sent[0]["cc"] == ["boss@example.invalid"]
