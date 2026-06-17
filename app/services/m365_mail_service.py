# app/services/m365_mail_service.py
import base64
import json
from pathlib import Path

import requests

_GRAPH_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
_TIMEOUT = 30


class M365MailService:
    """Microsoft Graph API /me/sendMail を使ってメールを送信する。"""

    def __init__(self, access_token: str):
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def send_mail(
        self,
        to_recipients: list[str],
        subject: str,
        body_html: str,
        pdf_path: str,
        cc_recipients:  list[str] | None = None,
        bcc_recipients: list[str] | None = None,
    ) -> dict:
        """PDF を添付してメール送信要求を送る。成功時は {"status": "accepted", ...} を返す。"""
        pdf = Path(pdf_path)
        if not pdf.exists():
            raise FileNotFoundError(f"PDFファイルが見つかりません: {pdf_path}")
        if pdf.suffix.lower() != ".pdf":
            raise ValueError("添付ファイルはPDFである必要があります。")

        pdf_b64 = base64.b64encode(pdf.read_bytes()).decode("utf-8")

        def _addr_list(addrs):
            return [{"emailAddress": {"address": a}} for a in addrs]

        message: dict = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": _addr_list(to_recipients),
            "attachments": [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": pdf.name,
                    "contentType": "application/pdf",
                    "contentBytes": pdf_b64,
                }
            ],
        }
        if cc_recipients:
            message["ccRecipients"] = _addr_list(cc_recipients)
        if bcc_recipients:
            message["bccRecipients"] = _addr_list(bcc_recipients)

        payload = {"message": message, "saveToSentItems": True}

        try:
            resp = requests.post(
                _GRAPH_SEND_MAIL_URL,
                headers=self._headers,
                data=json.dumps(payload),
                timeout=_TIMEOUT,
            )
        except requests.RequestException as ex:
            raise RuntimeError(f"Microsoft Graph への接続に失敗しました: {ex}") from ex

        if resp.status_code != 202:
            raise RuntimeError(
                f"メール送信要求に失敗しました。"
                f" status={resp.status_code} body={resp.text[:300]}"
            )

        return {"status": "accepted", "http_status_code": resp.status_code}
