# app/ui/m365_mail_worker.py
from PyQt6.QtCore import QObject, pyqtSignal
import time

from app.services.m365_auth_service import M365AuthService
from app.services.m365_mail_service import M365MailService


class M365MailWorker(QObject):
    """認証→送信をバックグラウンドスレッドで実行する Worker。"""

    finished = pyqtSignal(dict)   # {"status": "accepted", "http_status_code": 202}
    failed   = pyqtSignal(str)    # エラーメッセージ

    def __init__(
        self,
        client_id:      str,
        tenant_id:      str,
        to_recipients:  list[str],
        subject:        str,
        body_html:      str,
        pdf_path:       str | None = None,
        cc_recipients:  list[str] | None = None,
        bcc_recipients: list[str] | None = None,
        sender_address: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._client_id      = client_id
        self._tenant_id      = tenant_id
        self._to             = to_recipients
        self._cc             = cc_recipients  or []
        self._bcc            = bcc_recipients or []
        self._subject        = subject
        self._body_html      = body_html
        self._pdf_path       = pdf_path
        if sender_address is None:
            from app.utils.app_config import get_m365_sender_address
            sender_address = get_m365_sender_address()
        self._sender_address = (sender_address or "").strip()

    def run(self) -> None:
        try:
            token = M365AuthService(
                self._client_id,
                self._tenant_id,
                include_shared=bool(self._sender_address),
            ).acquire_token()
            service = (
                M365MailService(token, sender_address=self._sender_address)
                if self._sender_address else M365MailService(token)
            )
            result = service.send_mail(
                to_recipients  = self._to,
                subject        = self._subject,
                body_html      = self._body_html,
                pdf_path       = self._pdf_path,
                cc_recipients  = self._cc  or None,
                bcc_recipients = self._bcc or None,
            )
            self.finished.emit(result)
        except Exception as ex:
            self.failed.emit(str(ex))


class M365ReminderBatchWorker(QObject):
    """督促メールを複数件まとめてM365で送信するワーカー。"""

    progress = pyqtSignal(int, int)        # (現在件数, 合計件数)
    done     = pyqtSignal(int, list)       # (送信成功数, エラー文字列リスト)

    def __init__(self, client_id: str, tenant_id: str,
                 items: list[dict], interval_seconds: float = 2.0,
                 sender_address: str | None = None,
                 parent=None):
        """items: [{"to": str, "subject": str, "body_html": str,
                    "pdf_path": str|None, "doc_number": str}, ...]"""
        super().__init__(parent)
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._items     = items
        self._interval_seconds = max(float(interval_seconds), 0.0)
        self._results: list[dict] = []
        self._cancel_requested = False
        if sender_address is None:
            from app.utils.app_config import get_m365_sender_address
            sender_address = get_m365_sender_address()
        self._sender_address = (sender_address or "").strip()

    @property
    def results(self) -> list[dict]:
        return list(self._results)

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        sent   = 0
        errors = []
        self._results = []
        try:
            token = M365AuthService(
                self._client_id,
                self._tenant_id,
                include_shared=bool(self._sender_address),
            ).acquire_token()
            svc = (
                M365MailService(token, sender_address=self._sender_address)
                if self._sender_address else M365MailService(token)
            )
        except Exception as ex:
            errors.append(f"M365認証エラー：{ex}")
            self.done.emit(0, errors)
            return

        consecutive_errors = 0
        for i, item in enumerate(self._items):
            if self._cancel_requested:
                errors.append("ユーザー操作により送信を中止しました。")
                break
            self.progress.emit(i, len(self._items))
            try:
                svc.send_mail(
                    to_recipients=[item["to"]],
                    subject=item["subject"],
                    body_html=item["body_html"],
                    pdf_path=item.get("pdf_path"),
                )
                sent += 1
                consecutive_errors = 0
                self._results.append({
                    "item": item, "success": True, "error": "",
                })
            except Exception as ex:
                error = str(ex)
                errors.append(f"{item['doc_number']}：{error}")
                self._results.append({
                    "item": item, "success": False, "error": error,
                })
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    errors.append("5件連続で送信に失敗したため、安全のため中断しました。")
                    break
            if i < len(self._items) - 1 and self._interval_seconds:
                time.sleep(self._interval_seconds)

        self.done.emit(sent, errors)
