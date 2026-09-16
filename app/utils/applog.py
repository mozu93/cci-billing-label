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
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """モジュール名を渡して診断用ロガーを得る。"""
    global _configured
    if not _configured:
        _configure()
        _configured = True
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
