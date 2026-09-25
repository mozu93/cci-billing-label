# tests/test_mail_test_mode.py
"""テスト送信モード：アプリが送るすべてのメールを、テスト送信先だけに送る。

開発中に本物のお客様へ送ってしまわないため。送信の一番下（M365MailService.send_mail）
で宛先を差し替えるので、どの画面から送っても効く。
"""
import pytest

# このファイルではテスト送信モードの設定を本来どおり読む（conftest の強制オフを外す）
pytestmark = pytest.mark.real_mail_test_mode


@pytest.fixture
def cfg(monkeypatch):
    import app.utils.app_config as app_config
    store = {"m365": {"test_recipient": "dev@example.invalid"}}
    monkeypatch.setattr(app_config, "get_config", lambda: store)
    monkeypatch.setattr(app_config, "save_config", lambda c: store.update(c))
    return store


def test_test_mode_setting_roundtrip(cfg):
    from app.utils.app_config import get_m365_test_mode, set_m365_test_mode
    assert get_m365_test_mode() is False
    set_m365_test_mode(True)
    assert get_m365_test_mode() is True
    assert cfg["m365"]["test_recipient"] == "dev@example.invalid"   # 他の設定は消えない


def test_off_keeps_recipients(cfg):
    from app.services.m365_mail_service import apply_mail_test_mode
    got = apply_mail_test_mode(["shop@example.invalid"], "件名", "<p>本文</p>",
                               ["boss@example.invalid"], None)
    assert got == (["shop@example.invalid"], "件名", "<p>本文</p>",
                   ["boss@example.invalid"], None)


def test_on_redirects_everything_to_test_recipient(cfg):
    from app.services.m365_mail_service import apply_mail_test_mode
    from app.utils.app_config import set_m365_test_mode
    set_m365_test_mode(True)
    to, subject, body, cc, bcc = apply_mail_test_mode(
        ["shop@example.invalid"], "請求書送付", "<p>本文</p>",
        ["boss@example.invalid"], ["audit@example.invalid"])
    assert to == ["dev@example.invalid"]
    assert cc is None and bcc is None
    assert subject == "【テスト送信モード】請求書送付"
    # 本来の宛先が本文の先頭で分かる
    assert body.index("shop@example.invalid") < body.index("<p>本文</p>")
    assert "boss@example.invalid" in body and "audit@example.invalid" in body


def test_on_without_test_recipient_refuses_to_send(cfg):
    from app.services.m365_mail_service import apply_mail_test_mode
    from app.utils.app_config import set_m365_test_mode
    cfg["m365"]["test_recipient"] = ""
    set_m365_test_mode(True)
    with pytest.raises(ValueError):
        apply_mail_test_mode(["shop@example.invalid"], "件名", "<p>本文</p>", None, None)


def test_send_mail_posts_to_test_recipient(cfg, monkeypatch):
    """実際に Graph へ送る内容（payload）が、テスト送信先だけになっている。"""
    import app.services.m365_mail_service as svc
    from app.utils.app_config import set_m365_test_mode
    set_m365_test_mode(True)
    posted = {}

    class _Resp:
        status_code = 202
        headers = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        posted.update(json)
        return _Resp()
    monkeypatch.setattr(svc.requests, "post", fake_post)

    svc.M365MailService("token").send_mail(
        ["shop@example.invalid"], "請求書送付", "<p>本文</p>",
        cc_recipients=["boss@example.invalid"])
    msg = posted["message"]
    assert [r["emailAddress"]["address"] for r in msg["toRecipients"]] == ["dev@example.invalid"]
    assert "ccRecipients" not in msg and "bccRecipients" not in msg
    assert msg["subject"].startswith("【テスト送信モード】")


def test_settings_checkbox_turns_mode_on_and_off(qtbot, memory_db, cfg, monkeypatch):
    from app.ui.email_settings import EmailSettingsWidget
    from app.utils.app_config import get_m365_test_mode
    w = EmailSettingsWidget()
    qtbot.addWidget(w)
    assert w._test_mode_chk.isChecked() is False
    w._test_mode_chk.setChecked(True)
    assert get_m365_test_mode() is True
    w._test_mode_chk.setChecked(False)
    assert get_m365_test_mode() is False


def test_settings_checkbox_requires_test_recipient(qtbot, memory_db, cfg, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from app.ui.email_settings import EmailSettingsWidget
    from app.utils.app_config import get_m365_test_mode
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    w = EmailSettingsWidget()
    qtbot.addWidget(w)
    w._test_recipient.setText("")
    w._test_mode_chk.setChecked(True)
    assert get_m365_test_mode() is False
    assert not w._test_mode_chk.isChecked()
    assert warned


def test_status_bar_shows_test_mode(qtbot, memory_db, cfg):
    """オンの間は画面下に赤字で表示し、切り忘れを防ぐ。"""
    from app.ui.main_window import MainWindow
    from app.utils.app_config import set_m365_test_mode
    w = MainWindow()
    qtbot.addWidget(w)
    assert w._test_mode_label.isHidden()
    set_m365_test_mode(True)
    w._refresh_test_mode_label()
    assert not w._test_mode_label.isHidden()
    assert "dev@example.invalid" in w._test_mode_label.text()
