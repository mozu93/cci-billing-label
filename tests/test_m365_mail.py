import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


def test_invoice_mail_confirm_dialog_returns_edited_values(qtbot):
    from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog

    dlg = InvoiceMailConfirmDialog(
        to_recipients=["old@example.com"],
        subject="変更前",
        body_html="<p>変更前本文</p>",
    )
    qtbot.addWidget(dlg)

    dlg._to_edit.setText("new@example.com; second@example.com")
    dlg._cc_edit.setText("cc@example.com")
    dlg._bcc_edit.setText("bcc@example.com")
    dlg._subject_edit.setText("変更後")
    dlg._body_edit.setPlainText("変更後本文")

    assert dlg.to_recipients() == ["new@example.com", "second@example.com"]
    assert dlg.cc_recipients() == ["cc@example.com"]
    assert dlg.bcc_recipients() == ["bcc@example.com"]
    assert dlg.subject() == "変更後"
    assert "変更後本文" in dlg.body_html()


def test_invoice_mail_confirm_dialog_saves_edited_template_with_tags(
        qtbot, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from app.services import email_service
    from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog

    config = {}
    monkeypatch.setattr(email_service, "get_config", lambda: config)
    monkeypatch.setattr(
        email_service, "save_config",
        lambda value: config.update(value),
    )
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    dlg = InvoiceMailConfirmDialog(
        subject="【CCI商工会議所】請求書をお送りします",
        body_html="<p>株式会社テスト 様</p><p>文面を変更しました。</p>",
        template_kind="invoice",
        template_context={
            "会社名": "CCI商工会議所",
            "宛名": "株式会社テスト",
        },
    )
    qtbot.addWidget(dlg)
    dlg._subject_edit.setText("【{会社名}】請求書をお送りします")
    dlg._body_edit.setPlainText("{宛名} 様\n\n文面を変更しました。")
    dlg._save_template()

    saved = config["email_templates"]["invoice"]["items"][0]
    assert saved["subject"] == "【{会社名}】請求書をお送りします"
    assert "{宛名} 様" in saved["body"]
    assert "文面を変更しました。" in saved["body"]


def test_invoice_mail_confirm_dialog_shows_rendered_preview_and_confirms_send(
        qtbot, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog

    questions = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: (
            questions.append(args[2]) or QMessageBox.StandardButton.Yes),
    )
    dlg = InvoiceMailConfirmDialog(
        to_recipients=["billing@example.com"],
        template_kind="invoice",
        template_context={
            "会社名": "CCI商工会議所",
            "宛名": "株式会社テスト",
            "書類名": "請求書",
        },
    )
    qtbot.addWidget(dlg)
    dlg._subject_edit.setText("【{会社名}】{書類名}")
    dlg._body_edit.setPlainText("{宛名} 様")

    assert dlg.template_subject() == "【{会社名}】{書類名}"
    assert dlg.subject() == "【CCI商工会議所】請求書"
    assert dlg._preview_subject.text() == "【CCI商工会議所】請求書"
    assert "株式会社テスト 様" in dlg._preview_body.toPlainText()

    dlg._accept()

    assert dlg.result() == dlg.DialogCode.Accepted
    assert any("メールを送信しますか" in message for message in questions)


def test_invoice_mail_confirm_dialog_can_select_saved_template(
        qtbot, monkeypatch):
    from app.services import email_service
    from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog

    monkeypatch.setattr(email_service, "get_config", lambda: {
        "email_templates": {
            "invoice": {
                "default_id": "formal",
                "items": [
                    {
                        "id": "short",
                        "name": "短い案内",
                        "subject": "{書類名}送付",
                        "body": "{宛名} 様\n添付をご確認ください。",
                    },
                    {
                        "id": "formal",
                        "name": "正式案内",
                        "subject": "【{会社名}】{書類名}送付のご案内",
                        "body": "{宛名} 様\n平素よりお世話になっております。",
                    },
                ],
            }
        }
    })
    dlg = InvoiceMailConfirmDialog(
        template_kind="invoice",
        template_context={
            "宛名": "株式会社テスト",
            "会社名": "CCI商工会議所",
            "書類名": "請求書",
        },
    )
    qtbot.addWidget(dlg)

    assert dlg._template_choice.count() == 2
    assert dlg._template_choice.currentData()["id"] == "formal"
    dlg._template_choice.setCurrentIndex(0)
    assert dlg.template_subject() == "{書類名}送付"
    assert dlg.subject() == "請求書送付"
    assert "添付をご確認ください。" in dlg._preview_body.toPlainText()


def test_email_template_service_manages_multiple_templates(monkeypatch):
    from app.services import email_service

    config = {}
    monkeypatch.setattr(email_service, "get_config", lambda: config)
    monkeypatch.setattr(email_service, "save_config", lambda value: None)
    monkeypatch.setattr(
        email_service, "uuid4",
        lambda: type("FixedUuid", (), {"hex": "second"})(),
    )

    template_id = email_service.create_email_template(
        "invoice", "簡潔版", "件名2", "本文2")
    assert template_id == "second"
    assert [item["name"] for item in email_service.get_email_templates(
        "invoice")] == ["標準テンプレート", "簡潔版"]

    email_service.set_default_email_template("invoice", template_id)
    assert email_service.get_email_template("invoice") == ("件名2", "本文2")
    email_service.rename_email_template("invoice", template_id, "短文版")
    assert email_service.get_email_templates("invoice")[1]["name"] == "短文版"
    email_service.delete_email_template("invoice", template_id)
    assert len(email_service.get_email_templates("invoice")) == 1


# ── バリデーションテスト ────────────────────────────────────────────────

def _tmp_pdf(size: int = 100) -> str:
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.write(fd, b"%PDF" + b"x" * (size - 4))
    os.close(fd)
    return path


def test_validate_ok(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF" + b"x" * 100)
    from app.utils.mail_validator import validate_invoice_mail
    validate_invoice_mail(["a@example.com"], "件名", "<p>本文</p>", pdf)


def test_validate_no_recipient(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="宛先"):
        validate_invoice_mail([], "件名", "<p>本文</p>", pdf)


def test_validate_bad_email(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="形式"):
        validate_invoice_mail(["notanemail"], "件名", "<p>本文</p>", pdf)


def test_validate_empty_subject(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="件名"):
        validate_invoice_mail(["a@example.com"], "  ", "<p>本文</p>", pdf)


def test_validate_empty_body(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="本文"):
        validate_invoice_mail(["a@example.com"], "件名", "   ", pdf)


def test_validate_pdf_not_found():
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="存在しません"):
        validate_invoice_mail(["a@example.com"], "件名", "<p>x</p>", "/no/such/file.pdf")


def test_validate_not_pdf(tmp_path):
    f = tmp_path / "test.txt"
    f.write_bytes(b"hello")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="PDF"):
        validate_invoice_mail(["a@example.com"], "件名", "<p>x</p>", str(f))


def test_validate_pdf_too_large(tmp_path):
    pdf = tmp_path / "big.pdf"
    pdf.write_bytes(b"%PDF" + b"x" * int(2.5 * 1024 * 1024))
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="2.5MB"):
        validate_invoice_mail(["a@example.com"], "件名", "<p>x</p>", str(pdf))


def test_issuance_email_context_uses_issuance_company(db_session):
    from app.database.models import CompanySettings, Issuance, Project
    from app.services.email_service import get_issuance_email_context

    first = CompanySettings(name="先頭発行元", is_default=True)
    selected = CompanySettings(name="選択発行元")
    db_session.add_all([first, selected])
    db_session.flush()
    project = Project(
        name="対象案件", fiscal_year=2026, project_type="list",
        company_settings_id=first.id)
    db_session.add(project)
    db_session.flush()
    issuance = Issuance(
        project_id=project.id,
        doc_type="invoice",
        doc_number="INV-202607-0001",
        company_settings_id=selected.id,
    )
    db_session.add(issuance)
    db_session.commit()

    context = get_issuance_email_context(db_session, issuance)

    assert context["会社名"] == "選択発行元"
    assert context["件名"] == "対象案件"


def test_reminder_email_uses_project_company(db_session, tmp_path, monkeypatch):
    from app.database.models import (
        CompanySettings, Issuance, Project, ProjectMember)
    from app.services import email_service

    first = CompanySettings(name="先頭発行元", is_default=True)
    selected = CompanySettings(name="案件発行元")
    db_session.add_all([first, selected])
    db_session.flush()
    project = Project(
        name="対象案件", fiscal_year=2026, project_type="list",
        company_settings_id=selected.id)
    db_session.add(project)
    db_session.flush()
    member = ProjectMember(
        project_id=project.id, organization_name="請求先",
        email="customer@example.com")
    db_session.add(member)
    db_session.flush()
    issuance = Issuance(
        project_id=project.id,
        project_member_id=member.id,
        doc_type="invoice",
        doc_number="INV-202607-0001",
        amount=1000,
    )
    db_session.add(issuance)
    db_session.commit()
    monkeypatch.setattr(
        email_service,
        "get_email_template",
        lambda _kind: ("{会社名}", "{会社名}からのご案内"),
    )

    _to, subject, body_html, _pdf = email_service.prepare_reminder_email(
        db_session, issuance)

    assert subject == "案件発行元"
    assert "案件発行元からのご案内" in body_html


# ── M365MailService テスト（requests.post をモック）──────────────────────

def test_send_mail_202_success(tmp_path):
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    mock_resp = MagicMock()
    mock_resp.status_code = 202

    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")

    with patch("app.services.m365_mail_service.requests.post", return_value=mock_resp):
        result = svc.send_mail(["a@example.com"], "件名", "<p>本文</p>", str(pdf))

    assert result["status"] == "accepted"
    assert result["http_status_code"] == 202


def test_send_mail_200_success_without_attachment():
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")

    with patch("app.services.m365_mail_service.requests.post",
               return_value=mock_resp) as post:
        result = svc.send_mail([" a@example.com "], "件名", "<p>本文</p>")

    assert result["http_status_code"] == 200
    payload = post.call_args.kwargs["json"]
    assert payload["message"]["toRecipients"][0]["emailAddress"]["address"] == (
        "a@example.com")


def test_send_mail_retries_429_using_retry_after(tmp_path):
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    throttled = MagicMock(status_code=429, text="throttled")
    throttled.headers = {"Retry-After": "1"}
    accepted = MagicMock(status_code=202, text="")

    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")

    with patch("app.services.m365_mail_service.requests.post",
               side_effect=[throttled, accepted]) as post, \
            patch("app.services.m365_mail_service.time.sleep") as sleep:
        result = svc.send_mail(
            ["a@example.com"], "件名", "<p>本文</p>", str(pdf))

    assert result["http_status_code"] == 202
    assert post.call_count == 2
    sleep.assert_called_once_with(1)


def test_send_mail_validates_recipient_before_graph_call():
    from app.services.m365_mail_service import M365MailService
    from app.utils.mail_validator import MailValidationError
    svc = M365MailService("dummy_token")

    with patch("app.services.m365_mail_service.requests.post") as post:
        with pytest.raises(MailValidationError, match="形式"):
            svc.send_mail(["bad,address@example.com"], "件名", "<p>本文</p>")
    post.assert_not_called()


@pytest.mark.parametrize("status_code", [400, 401, 403, 429, 500])
def test_send_mail_non_202_raises(tmp_path, status_code):
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = "error"
    mock_resp.headers = {"Retry-After": "0"}

    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")

    with patch("app.services.m365_mail_service.requests.post",
               return_value=mock_resp), \
            patch("app.services.m365_mail_service.time.sleep"):
        with pytest.raises(RuntimeError, match=str(status_code)):
            svc.send_mail(["a@example.com"], "件名", "<p>本文</p>", str(pdf))


def test_send_mail_network_error(tmp_path):
    import requests as req_lib
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")

    with patch("app.services.m365_mail_service.requests.post",
               side_effect=req_lib.ConnectionError("接続失敗")):
        with pytest.raises(RuntimeError, match="接続に失敗"):
            svc.send_mail(["a@example.com"], "件名", "<p>本文</p>", str(pdf))


def test_send_mail_pdf_not_found():
    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")
    with pytest.raises(FileNotFoundError):
        svc.send_mail(["a@example.com"], "件名", "<p>本文</p>", "/no/such/file.pdf")


def test_auth_service_uses_configured_account():
    from app.services.m365_auth_service import M365AuthService

    account_a = {"username": "a@example.com"}
    account_b = {"username": "b@example.com"}
    app = MagicMock()
    app.get_accounts.return_value = [account_a, account_b]
    app.acquire_token_silent.return_value = {
        "access_token": "token",
        "id_token_claims": {"preferred_username": "b@example.com"},
    }
    service = M365AuthService.__new__(M365AuthService)
    service._app = app
    service._account_username = "B@example.com"
    service._scopes = ["https://graph.microsoft.com/Mail.Send"]

    token, username = service.acquire_token_with_account()

    assert (token, username) == ("token", "b@example.com")
    app.acquire_token_silent.assert_called_once_with(
        ["https://graph.microsoft.com/Mail.Send"],
        account=account_b,
    )


def test_auth_service_requests_shared_scope_only_when_enabled():
    from app.services.m365_auth_service import M365AuthService

    app = MagicMock()
    account = {"username": "sender@example.com"}
    app.get_accounts.return_value = [account]
    app.acquire_token_silent.return_value = {"access_token": "token"}
    service = M365AuthService.__new__(M365AuthService)
    service._app = app
    service._account_username = "sender@example.com"
    service._scopes = [
        "https://graph.microsoft.com/Mail.Send",
        "https://graph.microsoft.com/Mail.Send.Shared",
    ]

    service.acquire_token_with_account()

    app.acquire_token_silent.assert_called_once_with(
        service._scopes, account=account)


def test_auth_service_rejects_ambiguous_cached_accounts():
    from app.services.m365_auth_service import M365AuthService

    app = MagicMock()
    app.get_accounts.return_value = [
        {"username": "a@example.com"},
        {"username": "b@example.com"},
    ]
    service = M365AuthService.__new__(M365AuthService)
    service._app = app
    service._account_username = ""

    with pytest.raises(RuntimeError, match="送信に使用する"):
        service.acquire_token_with_account()
    app.acquire_token_interactive.assert_not_called()


def test_auth_service_removes_plaintext_cache_without_backup(tmp_path, monkeypatch):
    from app.services import m365_auth_service as auth_module

    cache = tmp_path / "m365_token_cache.bin"
    cache.write_text('{"AccessToken": {}}', encoding="utf-8")
    monkeypatch.setattr(auth_module, "_CACHE_FILE", cache)

    auth_module.M365AuthService._remove_legacy_plaintext_cache()

    assert not cache.exists()
    assert not list(tmp_path.glob("*.legacy*.json"))


def test_m365_config_update_preserves_selected_account(monkeypatch):
    from app.utils import app_config

    config = {
        "m365": {
            "client_id": "old-client",
            "tenant_id": "old-tenant",
            "account_username": "sender@example.com",
            "sender_address": "shared@example.com",
            "test_recipient": "test@example.com",
        }
    }
    saved = []
    monkeypatch.setattr(app_config, "get_config", lambda: config)
    monkeypatch.setattr(app_config, "save_config", lambda value: saved.append(value))

    app_config.save_m365_config("new-client", "new-tenant")

    assert saved[0]["m365"] == {
        "client_id": "new-client",
        "tenant_id": "new-tenant",
        "account_username": "sender@example.com",
        "sender_address": "shared@example.com",
        "test_recipient": "test@example.com",
    }


def test_m365_config_saves_proxy_sender(monkeypatch):
    from app.utils import app_config

    saved = []
    monkeypatch.setattr(app_config, "get_config", lambda: {})
    monkeypatch.setattr(app_config, "save_config", lambda value: saved.append(value))

    app_config.save_m365_config(
        "client", "tenant", "user@example.com", "shared@example.com")

    assert saved[0]["m365"]["sender_address"] == "shared@example.com"


def test_m365_config_saves_test_recipient(monkeypatch):
    from app.utils import app_config

    saved = []
    monkeypatch.setattr(app_config, "get_config", lambda: {})
    monkeypatch.setattr(app_config, "save_config", lambda value: saved.append(value))

    app_config.save_m365_config(
        "client", "tenant", "user@example.com", "", "test@example.com")

    assert saved[0]["m365"]["test_recipient"] == "test@example.com"


def test_send_mail_as_proxy_uses_me_endpoint_and_from():
    mock_resp = MagicMock(status_code=202, text="")
    from app.services.m365_mail_service import M365MailService

    svc = M365MailService("token", sender_address="shared+sales@example.com")
    with patch("app.services.m365_mail_service.requests.post",
               return_value=mock_resp) as post:
        svc.send_mail(["customer@example.com"], "件名", "<p>本文</p>")

    assert post.call_args.args[0].endswith("/me/sendMail")
    assert post.call_args.kwargs["json"]["message"]["from"] == {
        "emailAddress": {"address": "shared+sales@example.com"}
    }


def test_proxy_sender_rejects_invalid_address_before_graph_call():
    from app.services.m365_mail_service import M365MailService
    from app.utils.mail_validator import MailValidationError

    with pytest.raises(MailValidationError, match="代理送信元"):
        M365MailService("token", sender_address="invalid,address@example.com")


def test_proxy_sender_403_explains_required_permissions():
    mock_resp = MagicMock(status_code=403, text="Forbidden")
    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("token", sender_address="shared@example.com")

    with patch("app.services.m365_mail_service.requests.post",
               return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Mail.Send.Shared"):
            svc.send_mail(["customer@example.com"], "件名", "<p>本文</p>")


def test_email_settings_has_account_sign_in_and_sign_out(
        qtbot, monkeypatch):
    from PyQt6.QtWidgets import QPushButton
    from app.ui import email_settings

    monkeypatch.setattr(email_settings, "get_m365_client_id", lambda: "")
    monkeypatch.setattr(email_settings, "get_m365_tenant_id", lambda: "")
    monkeypatch.setattr(email_settings, "get_m365_account_username", lambda: "")
    monkeypatch.setattr(email_settings, "get_m365_sender_address", lambda: "")
    monkeypatch.setattr(email_settings, "get_m365_test_recipient", lambda: "")
    widget = email_settings.EmailSettingsWidget()
    qtbot.addWidget(widget)

    button_texts = {
        button.text() for button in widget.findChildren(QPushButton)
    }
    assert "サインイン／確認" in button_texts
    assert "サインアウト" in button_texts
    assert "テストメール送信" in button_texts
    assert "このテンプレートを保存" not in button_texts


def test_email_settings_restores_test_recipient(qtbot, monkeypatch):
    from app.ui import email_settings

    monkeypatch.setattr(email_settings, "get_m365_client_id", lambda: "")
    monkeypatch.setattr(email_settings, "get_m365_tenant_id", lambda: "")
    monkeypatch.setattr(email_settings, "get_m365_account_username", lambda: "")
    monkeypatch.setattr(email_settings, "get_m365_sender_address", lambda: "")
    monkeypatch.setattr(
        email_settings, "get_m365_test_recipient",
        lambda: "test@example.com")

    widget = email_settings.EmailSettingsWidget()
    qtbot.addWidget(widget)

    assert widget._test_recipient.text() == "test@example.com"


def test_email_template_inserts_tag_into_last_focused_editor(
        qtbot, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTableWidgetItem
    from app.ui import email_settings
    from app.services import email_service

    monkeypatch.setattr(email_service, "get_config", lambda: {})
    widget = email_settings.EmailTemplateWidget()
    qtbot.addWidget(widget)

    widget._tmpl_subject.setText("ご案内")
    widget._tmpl_subject.setCursorPosition(2)
    widget._last_template_editor = widget._tmpl_subject
    addressee_item = QTableWidgetItem("請求先の表示名")
    addressee_item.setData(Qt.ItemDataRole.UserRole, "{宛名}")
    widget._insert_tag(addressee_item)
    assert widget._tmpl_subject.text() == "ご案{宛名}内"

    widget._tmpl_body.setPlainText("本文")
    cursor = widget._tmpl_body.textCursor()
    cursor.setPosition(1)
    widget._tmpl_body.setTextCursor(cursor)
    widget._last_template_editor = widget._tmpl_body
    amount_item = QTableWidgetItem("請求金額")
    amount_item.setData(Qt.ItemDataRole.UserRole, "{金額}")
    widget._insert_tag(amount_item)
    assert widget._tmpl_body.toPlainText() == "本{金額}文"


def test_email_template_saves_only_current_template(qtbot, monkeypatch):
    from app.ui import email_settings
    from app.services import email_service

    saved = []
    config = {}
    monkeypatch.setattr(email_service, "get_config", lambda: config)
    monkeypatch.setattr(
        email_service, "save_config", lambda value: saved.append(value.copy()))
    monkeypatch.setattr(email_settings.QMessageBox, "information", lambda *args: None)
    widget = email_settings.EmailTemplateWidget()
    qtbot.addWidget(widget)

    widget._tmpl_subject.setText("保存する件名")
    widget._tmpl_body.setPlainText("保存する本文")
    widget._save_current_template()

    stored = saved[-1]["email_templates"]["invoice"]
    assert stored["default_id"] == "standard"
    assert stored["items"][0] == {
        "id": "standard",
        "name": "標準テンプレート",
        "subject": "保存する件名",
        "body": "保存する本文",
    }


def test_email_template_reminder_adds_due_date_tag(qtbot, monkeypatch):
    from app.ui import email_settings
    from app.services import email_service

    monkeypatch.setattr(email_service, "get_config", lambda: {})
    widget = email_settings.EmailTemplateWidget()
    qtbot.addWidget(widget)

    widget._tmpl_type.setCurrentIndex(2)

    assert "{支払期限}" in [
        widget._tag_table.item(row, 0).text()
        for row in range(widget._tag_table.rowCount())
    ]


def test_email_template_explains_ambiguous_tags(qtbot, monkeypatch):
    from app.ui import email_settings
    from app.services import email_service

    monkeypatch.setattr(email_service, "get_config", lambda: {})
    widget = email_settings.EmailTemplateWidget()
    qtbot.addWidget(widget)

    descriptions = {
        widget._tag_table.item(row, 0).text():
        widget._tag_table.item(row, 1).text()
        for row in range(widget._tag_table.rowCount())
    }
    assert descriptions["{宛名}"] == "請求先の表示名（事業所名と代表者名）"
    assert descriptions["{会社名}"] == "請求書を発行する自社・商工会議所名"


def test_email_template_widget_can_create_and_select_multiple_templates(
        qtbot, monkeypatch):
    from app.services import email_service
    from app.ui import email_settings

    config = {}
    monkeypatch.setattr(email_service, "get_config", lambda: config)
    monkeypatch.setattr(email_service, "save_config", lambda value: None)
    monkeypatch.setattr(
        email_service, "uuid4",
        lambda: type("FixedUuid", (), {"hex": "new-template"})(),
    )
    monkeypatch.setattr(
        email_settings.QInputDialog, "getText",
        lambda *args, **kwargs: ("会費請求用", True),
    )
    widget = email_settings.EmailTemplateWidget()
    qtbot.addWidget(widget)

    widget._new_template()

    assert widget._template_choice.count() == 2
    assert widget._template_choice.currentData()["id"] == "new-template"
    assert widget._template_choice.currentData()["name"] == "会費請求用"


def test_email_template_widget_uses_two_columns_and_scrollable_body(
        qtbot, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QSplitter
    from app.services import email_service
    from app.ui import email_settings

    monkeypatch.setattr(email_service, "get_config", lambda: {})
    widget = email_settings.EmailTemplateWidget()
    qtbot.addWidget(widget)
    widget.resize(900, 610)
    widget.show()
    widget._tmpl_body.setPlainText("\n".join(
        f"本文 {index}" for index in range(100)))
    qtbot.wait(10)

    splitter = widget.findChild(QSplitter)
    assert splitter is not None
    assert splitter.orientation() == Qt.Orientation.Horizontal
    assert widget._tmpl_body.height() >= 390
    assert widget._tmpl_body.verticalScrollBar().maximum() > 0


def test_email_template_actions_wrap_to_two_rows(qtbot, monkeypatch):
    from PyQt6.QtWidgets import QPushButton
    from app.services import email_service
    from app.ui import email_settings

    monkeypatch.setattr(email_service, "get_config", lambda: {})
    widget = email_settings.EmailTemplateWidget()
    qtbot.addWidget(widget)
    widget.resize(900, 610)
    widget.show()
    qtbot.wait(10)

    buttons = {
        button.text(): button
        for button in widget.findChildren(QPushButton)
    }
    first_row = [buttons["新規作成"], buttons["名前変更"]]
    second_row = [buttons["削除"], buttons["既定に設定"]]
    assert first_row[0].y() == first_row[1].y()
    assert second_row[0].y() == second_row[1].y()
    assert second_row[0].y() > first_row[0].y()
    assert all(
        not left.geometry().intersects(right.geometry())
        for index, left in enumerate(first_row + second_row)
        for right in (first_row + second_row)[index + 1:]
    )


def test_reminder_preview_can_select_template(qtbot):
    from app.ui.payment_dialog import _ReminderPreviewDialog

    templates = [
        {
            "id": "standard", "name": "標準", "is_default": True,
            "subject": "標準件名", "body": "標準本文",
        },
        {
            "id": "strong", "name": "再督促", "is_default": False,
            "subject": "再督促件名", "body": "再督促本文",
        },
    ]
    dialog = _ReminderPreviewDialog(2, templates)
    qtbot.addWidget(dialog)
    dialog._template_choice.setCurrentIndex(1)

    assert dialog.subject() == "再督促件名"
    assert dialog.body() == "再督促本文"


def test_reminder_batch_stops_after_five_consecutive_errors(monkeypatch):
    from app.ui import m365_mail_worker as worker_module

    auth = MagicMock()
    auth.acquire_token.return_value = "token"
    monkeypatch.setattr(
        worker_module, "M365AuthService", lambda *args, **kwargs: auth)
    mail = MagicMock()
    mail.send_mail.side_effect = RuntimeError("send failed")
    monkeypatch.setattr(worker_module, "M365MailService", lambda _token: mail)
    items = [
        {
            "to": f"user{i}@example.com",
            "subject": "件名",
            "body_html": "本文",
            "doc_number": f"INV-{i}",
        }
        for i in range(8)
    ]
    worker = worker_module.M365ReminderBatchWorker(
        "client", "tenant", items, interval_seconds=0, sender_address="")
    results = []
    worker.done.connect(lambda sent, errors: results.append((sent, errors)))

    worker.run()

    assert mail.send_mail.call_count == 5
    assert results[0][0] == 0
    assert any("5件連続" in error for error in results[0][1])
    assert len(worker.results) == 5
    assert all(not result["success"] for result in worker.results)


def test_reminder_batch_records_each_item_result(monkeypatch):
    from app.ui import m365_mail_worker as worker_module

    auth = MagicMock()
    auth.acquire_token.return_value = "token"
    monkeypatch.setattr(
        worker_module, "M365AuthService", lambda *args, **kwargs: auth)
    mail = MagicMock()
    mail.send_mail.side_effect = [RuntimeError("first failed"), {"status": "accepted"}]
    monkeypatch.setattr(worker_module, "M365MailService", lambda _token: mail)
    items = [
        {
            "to": "first@example.com", "subject": "件名", "body_html": "本文",
            "doc_number": "INV-1", "iss_id": 1,
        },
        {
            "to": "second@example.com", "subject": "件名", "body_html": "本文",
            "doc_number": "INV-2", "iss_id": 2,
        },
    ]
    worker = worker_module.M365ReminderBatchWorker(
        "client", "tenant", items, interval_seconds=0, sender_address="")

    worker.run()

    assert [result["success"] for result in worker.results] == [False, True]
    assert worker.results[0]["item"]["iss_id"] == 1
    assert worker.results[1]["item"]["iss_id"] == 2


def test_reminder_batch_can_be_cancelled_before_next_item(monkeypatch):
    from app.ui import m365_mail_worker as worker_module

    auth = MagicMock()
    auth.acquire_token.return_value = "token"
    monkeypatch.setattr(
        worker_module, "M365AuthService", lambda *args, **kwargs: auth)
    mail = MagicMock()
    monkeypatch.setattr(worker_module, "M365MailService", lambda _token: mail)
    worker = worker_module.M365ReminderBatchWorker(
        "client", "tenant",
        [{"to": "a@example.com", "subject": "件名", "body_html": "本文",
          "doc_number": "INV-1"}],
        interval_seconds=0, sender_address="",
    )
    results = []
    worker.done.connect(lambda sent, errors: results.append((sent, errors)))
    worker.cancel()

    worker.run()

    mail.send_mail.assert_not_called()
    assert results[0][0] == 0
    assert any("中止" in error for error in results[0][1])
