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
        pdf_path:       str,
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
