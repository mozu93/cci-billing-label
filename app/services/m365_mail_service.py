# app/services/m365_mail_service.py
import base64
import time
from pathlib import Path

import requests
from app.utils.mail_validator import validate_email_address, validate_mail

_GRAPH_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
_TIMEOUT = 30
_MAX_ATTEMPTS = 4


class M365MailService:
    """Microsoft Graph API /me/sendMail を使ってメールを送信する。"""

    def __init__(self, access_token: str, sender_address: str = ""):
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        self._sender_address = (sender_address or "").strip()
        if self._sender_address:
            self._sender_address = validate_email_address(
                self._sender_address, "代理送信元")

    def send_mail(
        self,
        to_recipients: list[str],
        subject: str,
        body_html: str,
        pdf_path: str | None = None,
        cc_recipients:  list[str] | None = None,
        bcc_recipients: list[str] | None = None,
    ) -> dict:
        """メール送信要求を送る。pdf_path を指定した場合のみPDFを添付する。"""
        if pdf_path is not None and not Path(pdf_path).is_file():
            raise FileNotFoundError(f"PDFファイルが見つかりません: {pdf_path}")
        validate_mail(
            to_recipients=to_recipients,
            subject=subject,
            body_html=body_html,
            pdf_path=pdf_path,
            cc_recipients=cc_recipients,
            bcc_recipients=bcc_recipients,
        )

        def _addr_list(addrs):
            return [
                {"emailAddress": {"address": a.strip()}}
                for a in addrs
            ]

        message: dict = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": _addr_list(to_recipients),
        }
        if self._sender_address:
            message["from"] = {
                "emailAddress": {"address": self._sender_address}
            }

        if pdf_path is not None:
            pdf = Path(pdf_path)
            if not pdf.exists():
                raise FileNotFoundError(f"PDFファイルが見つかりません: {pdf_path}")
            if pdf.suffix.lower() != ".pdf":
                raise ValueError("添付ファイルはPDFである必要があります。")
            pdf_b64 = base64.b64encode(pdf.read_bytes()).decode("utf-8")
            message["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": pdf.name,
                    "contentType": "application/pdf",
                    "contentBytes": pdf_b64,
                }
            ]
        if cc_recipients:
            message["ccRecipients"] = _addr_list(cc_recipients)
        if bcc_recipients:
            message["bccRecipients"] = _addr_list(bcc_recipients)

        payload = {"message": message, "saveToSentItems": True}
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = requests.post(
                    _GRAPH_SEND_MAIL_URL,
                    headers=self._headers,
                    json=payload,
                    timeout=_TIMEOUT,
                )
            except requests.RequestException as ex:
                raise RuntimeError(
                    f"Microsoft Graph への接続に失敗しました: {ex}") from ex
            if resp.status_code in (200, 202):
                return {
                    "status": "accepted",
                    "http_status_code": resp.status_code,
                }
            if resp.status_code == 429 and attempt < _MAX_ATTEMPTS - 1:
                try:
                    delay = min(max(int(resp.headers.get("Retry-After", "5")), 0), 60)
                except (TypeError, ValueError):
                    delay = 5
                time.sleep(delay)
                continue
            detail = ""
            if resp.status_code == 403 and self._sender_address:
                detail = (
                    " 代理送信元メールボックスに対する「差出人として送信」"
                    "または「代理人として送信」権限と、"
                    "Mail.Send.Shared 権限を確認してください。"
                )
            raise RuntimeError(
                f"メール送信要求に失敗しました。"
                f" status={resp.status_code} body={resp.text[:300]}{detail}"
            )
        raise RuntimeError("メール送信要求の再試行回数を超えました。")
