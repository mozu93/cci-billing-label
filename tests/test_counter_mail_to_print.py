# tests/test_counter_mail_to_print.py
"""単発発行：メールで送らなかったとき、同じ番号のまま印刷に切り替えられる。"""
import pytest
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox


class _RejectingMailDialog:
    """送信確認画面でキャンセルした状態を再現する。"""
    def __init__(self, *a, **k):
        pass

    def exec(self):
        return QDialog.DialogCode.Rejected


@pytest.fixture
def widget(qtbot, memory_db, monkeypatch):
    import app.services.email_service as email_service
    import app.ui.invoice_mail_confirm_dialog as mail_dialog
    import app.utils.app_config as app_config
    import app.utils.pdf_helpers as pdf_helpers
    from app.database.connection import get_session
    from app.database.models import CompanySettings
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    s.add(CompanySettings(name="発行元", is_default=True))
    s.commit()
    s.close()
    monkeypatch.setattr(app_config, "get_config", lambda: {})
    monkeypatch.setattr(app_config, "save_config", lambda cfg: None)
    monkeypatch.setattr(app_config, "get_m365_client_id", lambda: "client")
    monkeypatch.setattr(app_config, "get_m365_tenant_id", lambda: "tenant")
    monkeypatch.setattr(email_service, "prepare_issuance_email",
                        lambda s, iss, to_addr=None: (to_addr, "件名", "<p>本文</p>", "C:/mail.pdf"))
    monkeypatch.setattr(email_service, "get_issuance_email_context", lambda s, iss: {})
    monkeypatch.setattr(mail_dialog, "InvoiceMailConfirmDialog", _RejectingMailDialog)

    pdf_calls = []

    def fake_generate(iss, session, **kwargs):
        pdf_calls.append(kwargs)
        return kwargs.get("save_path") or "C:/mail.pdf"
    monkeypatch.setattr(pdf_helpers, "generate_and_open", fake_generate)
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: ("C:/print/INV.pdf", ""))
    msgs = {"question": [], "answer": QMessageBox.StandardButton.Yes}
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: None)

    def fake_question(*a, **k):
        msgs["question"].append(a[2])
        return msgs["answer"]
    monkeypatch.setattr(QMessageBox, "question", fake_question)

    w = IssuanceCounterWidget(doc_type="invoice")
    qtbot.addWidget(w)
    w._reload_master()
    w._delivery.setCurrentText("メール送付")
    w._org_name.setText("○○商店")
    w._email.setText("shop@example.invalid")
    row = w._rows[0]
    row.tmpl_combo.setEditText("年会費")
    row.price_edit.setText("10000")
    w.msgs, w.pdf_calls = msgs, pdf_calls
    return w


def _issuances():
    from app.database.connection import get_session
    from app.database.models import Issuance
    s = get_session()
    try:
        return [(i.doc_number, i.delivery_method) for i in s.query(Issuance).all()]
    finally:
        s.close()


def test_cancelled_mail_can_be_switched_to_print(widget):
    widget._issue()
    assert any("印刷に切り替え" in q for q in widget.msgs["question"])
    rows = _issuances()
    assert len(rows) == 1                      # 2枚目は作らない（番号は同じ）
    assert rows[0][1] == "印刷"
    print_calls = [c for c in widget.pdf_calls if c.get("save_path")]
    assert print_calls and print_calls[0]["save_path"] == "C:/print/INV.pdf"


def test_declining_switch_cancels_issuance(widget):
    """メールも送らず印刷もしなければ、何も出力されていないので発行を取り消す。"""
    widget.msgs["answer"] = QMessageBox.StandardButton.No
    widget._issue()
    assert _issuances() == []
    assert not [c for c in widget.pdf_calls if c.get("save_path")]
    assert widget._issued_label.text() == ""


def test_switch_then_save_cancelled_cancels_issuance(widget, monkeypatch):
    """印刷に切り替えても保存先を選ばなければ、やはり取り消す。"""
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    widget._issue()
    assert _issuances() == []


def test_missing_mail_settings_offers_print(widget, monkeypatch):
    import app.ui.invoice_mail_confirm_dialog as mail_dialog
    import app.utils.app_config as app_config

    class _Accepting(_RejectingMailDialog):
        def exec(self):
            return QDialog.DialogCode.Accepted
        def to_recipients(self): return ["shop@example.invalid"]
        def cc_recipients(self): return []
        def bcc_recipients(self): return []
        def subject(self): return "件名"
        def body_html(self): return "<p>本文</p>"
    monkeypatch.setattr(mail_dialog, "InvoiceMailConfirmDialog", _Accepting)
    monkeypatch.setattr(app_config, "get_m365_client_id", lambda: "")
    widget._issue()
    assert any("印刷に切り替え" in q for q in widget.msgs["question"])
    assert _issuances()[0][1] == "印刷"
