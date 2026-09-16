# -*- coding: utf-8 -*-
"""診断ログの基本動作を確認する。"""
import logging
from logging.handlers import RotatingFileHandler

from app.utils import applog


def test_logger_is_namespaced():
    log = applog.get_logger("app.ui.sample")
    assert log.name == "cci.app.ui.sample"


def test_root_logger_does_not_propagate():
    applog.get_logger("app.ui.sample")
    assert logging.getLogger("cci").propagate is False


def test_handler_is_configured_once():
    """get_logger を何度呼んでもハンドラは増えない。

    pytest が caplog 用のハンドラを足すため、総数ではなく増分で確認する。
    """
    applog.get_logger("a")
    before = len(logging.getLogger("cci").handlers)
    applog.get_logger("b")
    applog.get_logger("c")
    assert len(logging.getLogger("cci").handlers) == before


def test_log_file_is_opened_lazily():
    """ログファイルは1件目を書くまで開かない（delay=True）。

    stream の状態は他テストが先に書いたかに左右されるため、
    ハンドラの設定そのものを確認する。
    """
    applog.get_logger("app.ui.sample")
    ours = [h for h in logging.getLogger("cci").handlers
            if isinstance(h, RotatingFileHandler)]
    assert len(ours) == 1
    assert ours[0].delay is True
    assert ours[0].baseFilename == str(applog.LOG_FILE)


def test_warning_is_written(tmp_path, monkeypatch):
    """例外を握り潰した箇所のメッセージとトレースバックが残る。"""
    log_file = tmp_path / "app.log"
    logger = logging.getLogger("cci.test_write")
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        try:
            raise ValueError("印影が壊れています")
        except ValueError:
            logger.warning("請求書の印影描画に失敗", exc_info=True)
    finally:
        handler.close()
        logger.removeHandler(handler)

    text = log_file.read_text(encoding="utf-8")
    assert "WARNING 請求書の印影描画に失敗" in text
    assert "ValueError: 印影が壊れています" in text
    assert "Traceback" in text


def test_secrets_are_redacted(tmp_path, monkeypatch):
    """設定に入っている秘密情報は、ログファイルに残さない。"""
    from app.utils import app_config
    monkeypatch.setattr(app_config, "get_config", lambda: {
        "password": "sup3r-s3cret-db-pw",
        "m365": {"trace_client_secret": "m365-client-secret-value"},
    })

    log_file = tmp_path / "app.log"
    logger = logging.getLogger("cci.test_redact")
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(applog.RedactingFormatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        try:
            raise RuntimeError(
                "auth failed: secret=m365-client-secret-value "
                "dsn=postgresql://u:sup3r-s3cret-db-pw@host/db")
        except RuntimeError:
            logger.warning("M365のキャッシュ済みアカウント取得に失敗", exc_info=True)
    finally:
        handler.close()
        logger.removeHandler(handler)

    text = log_file.read_text(encoding="utf-8")
    assert "sup3r-s3cret-db-pw" not in text
    assert "m365-client-secret-value" not in text
    assert text.count("***") >= 2
    # 伏せ字にしても、何が失敗したかは分かる状態で残す。
    assert "M365のキャッシュ済みアカウント取得に失敗" in text
    assert "RuntimeError" in text


def test_short_values_are_not_redacted(tmp_path, monkeypatch):
    """短い値まで伏せ字にすると無関係な文字列を壊すため、対象外とする。"""
    from app.utils import app_config
    monkeypatch.setattr(app_config, "get_config", lambda: {"password": "abc"})

    log_file = tmp_path / "app.log"
    logger = logging.getLogger("cci.test_short")
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(applog.RedactingFormatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        logger.warning("abcdef で始まる処理に失敗")
    finally:
        handler.close()
        logger.removeHandler(handler)

    assert "abcdef" in log_file.read_text(encoding="utf-8")
