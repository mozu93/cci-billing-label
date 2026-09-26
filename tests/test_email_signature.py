# tests/test_email_signature.py
"""メール署名：config.json とは別のファイルに保存し、端末間コピーの対象にならない。"""
import app.utils.app_config as app_config


def test_signature_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(app_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "SIGNATURE_FILE", tmp_path / "email_signature.txt")

    assert app_config.get_email_signature() == ""
    app_config.save_email_signature("南工会議所 水谷\nTEL 000-000-0000")
    assert app_config.get_email_signature() == "南工会議所 水谷\nTEL 000-000-0000"


def test_signature_is_separate_file_from_config_json(tmp_path, monkeypatch):
    """config.json を他端末へコピーしても、署名ファイルは付いていかない。"""
    monkeypatch.setattr(app_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_config, "SIGNATURE_FILE", tmp_path / "email_signature.txt")

    app_config.save_email_signature("ローカル署名")

    assert not app_config.CONFIG_FILE.exists() or "ローカル署名" not in \
        app_config.CONFIG_FILE.read_text(encoding="utf-8")
    assert app_config.SIGNATURE_FILE.exists()
    assert app_config.SIGNATURE_FILE != app_config.CONFIG_FILE
