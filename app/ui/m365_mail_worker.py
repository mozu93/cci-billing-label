# app/ui/m365_mail_worker.py
from PyQt6.QtCore import QObject, pyqtSignal

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

    def run(self) -> None:
        try:
            token = M365AuthService(self._client_id, self._tenant_id).acquire_token()
            result = M365MailService(token).send_mail(
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
                 items: list[dict], parent=None):
        """items: [{"to": str, "subject": str, "body_html": str,
                    "pdf_path": str|None, "doc_number": str}, ...]"""
        super().__init__(parent)
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._items     = items

    def run(self) -> None:
        sent   = 0
        errors = []
        try:
            token = M365AuthService(self._client_id, self._tenant_id).acquire_token()
            svc   = M365MailService(token)
        except Exception as ex:
            errors.append(f"M365認証エラー：{ex}")
            self.done.emit(0, errors)
            return

        for i, item in enumerate(self._items):
            self.progress.emit(i, len(self._items))
            try:
                svc.send_mail(
                    to_recipients=[item["to"]],
                    subject=item["subject"],
                    body_html=item["body_html"],
                    pdf_path=item.get("pdf_path"),
                )
                sent += 1
            except Exception as ex:
                errors.append(f"{item['doc_number']}：{ex}")

        self.done.emit(sent, errors)
