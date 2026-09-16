# app/utils/applog.py
"""診断用のログ出力。

業務の操作ログ（operation_log_service）とは別物で、そちらがDBに残す
「誰が何をしたか」に対して、こちらは「なぜ失敗したか」を残す。
pythonw / EXE 起動では stderr の出力先が無いため、ファイルに書き出す。
"""
import logging
import sys
from logging.handlers import RotatingFileHandler

from app.utils.app_config import CONFIG_DIR

LOG_FILE = CONFIG_DIR / "app.log"

_ROOT_NAME = "cci"
_configured = False

# 短すぎる値を伏せ字にすると無関係な文字列まで壊すため、下限を設ける。
_MIN_SECRET_LEN = 6
_MASK = "***"


def _secret_values() -> list[str]:
    """設定に保存されている秘密情報。ログに出さないための照合用。"""
    # 循環importを避けるため、関数内で読む。
    from app.utils.app_config import get_config
    try:
        config = get_config()
    except Exception:
        return []
    values = [config.get("password", "")]
    m365 = config.get("m365", {})
    if isinstance(m365, dict):
        values.append(m365.get("trace_client_secret", ""))
    return [v for v in values
            if isinstance(v, str) and len(v) >= _MIN_SECRET_LEN]


class RedactingFormatter(logging.Formatter):
    """例外メッセージに秘密情報が混ざっても、ファイルには残さない。

    ライブラリ側の例外(MSAL等)が何を含むか制御できないため、
    書き出す直前に既知の秘密情報を伏せ字にする。
    """

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for value in _secret_values():
            if value in text:
                text = text.replace(value, _MASK)
        return text


def _configure() -> None:
    logger = logging.getLogger(_ROOT_NAME)
    logger.setLevel(logging.INFO)
    # ルートロガーへ伝播させると pytest などの出力に混ざるため止める。
    logger.propagate = False
    try:
        CONFIG_DIR.mkdir(exist_ok=True)
        # delay=True で、実際に1件目を書くまでファイルを開かない。
        handler: logging.Handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=3,
            encoding="utf-8", delay=True,
        )
    except OSError:
        # ログファイルを作れない環境でもアプリは動かす。
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """モジュール名を渡して診断用ロガーを得る。"""
    global _configured
    if not _configured:
        _configure()
        _configured = True
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
