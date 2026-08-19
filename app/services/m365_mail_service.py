# app/services/m365_mail_service.py
import base64
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
import msal
from app.utils.mail_validator import validate_email_address, validate_mail

_GRAPH_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
_TIMEOUT = 30
_MAX_ATTEMPTS = 4
_TRACE_SCOPE = ["https://graph.microsoft.com/.default"]


def get_delivery_trace(client_id: str, tenant_id: str, client_secret: str,
                       sender_address: str, recipient_address: str,
                       subject: str, sent_at: datetime | None) -> dict:
    """Exchange Onlineメッセージ追跡APIから配信状態を取得する。"""
    if not client_secret.strip():
        raise ValueError("配信状況確認用のクライアントシークレットを設定してください。")
    if not sent_at:
        return {"status": "unknown", "message": "送信日時がありません。"}
    app = msal.ConfidentialClientApplication(
        client_id, client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}")
    token_result = app.acquire_token_for_client(scopes=_TRACE_SCOPE)
    if not token_result or "access_token" not in token_result:
        detail = token_result.get("error_description", str(token_result)) if token_result else "不明なエラー"
        raise RuntimeError(f"配信状況確認の認証に失敗しました: {detail}")
    sent_utc = sent_at.replace(tzinfo=ZoneInfo("Asia/Tokyo")).astimezone(timezone.utc)
    esc = lambda value: value.replace("'", "''")
    query = (
        f"recipientAddress eq '{esc(recipient_address)}' and senderAddress eq '{esc(sender_address)}' "
        f"and receivedDateTime ge {(sent_utc - timedelta(hours=2)).isoformat().replace('+00:00', 'Z')} "
        f"and receivedDateTime le {(sent_utc + timedelta(days=3)).isoformat().replace('+00:00', 'Z')}"
    )
    headers = {"Authorization": f"Bearer {token_result['access_token']}"}
    response = requests.get(
        "https://graph.microsoft.com/v1.0/admin/exchange/tracing/messageTraces",
        headers=headers, params={"$filter": query, "$top": "50"}, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"メッセージ追跡APIに失敗しました（HTTP {response.status_code}）。")
    values = response.json().get("value", [])
    matches = [item for item in values if item.get("subject") == subject]
    candidates = matches or values
    if not candidates:
        return {"status": "pending", "message": "追跡情報がまだ反映されていません。"}
    trace = sorted(candidates, key=lambda item: item.get("receivedDateTime", ""), reverse=True)[0]
    status = str(trace.get("status", "unknown")).lower()
    message = {
        "delivered": "Microsoft 365で配信済みです。",
        "failed": "Microsoft 365で配信に失敗しました。",
        "pending": "Microsoft 365で処理中です。",
        "quarantined": "隔離されています。",
        "filteredasspam": "スパムとして処理されました。",
    }.get(status, f"Microsoft 365の状態: {status}")
    if status == "failed" and trace.get("id"):
        detail_url = (
            "https://graph.microsoft.com/v1.0/admin/exchange/tracing/"
            f"messageTraces/{quote(str(trace['id']), safe='')}"
            f"/getDetailsByRecipient(recipientAddress='{quote(recipient_address, safe='@._-')}')")
        detail_response = requests.get(detail_url, headers=headers, timeout=30)
        if detail_response.status_code == 200:
            descriptions = [item.get("description", "") for item in detail_response.json().get("value", [])]
            if descriptions:
                message += "\n" + descriptions[-1]
    return {"status": status, "message": message}


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
