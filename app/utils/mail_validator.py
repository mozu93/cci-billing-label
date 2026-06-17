# app/utils/mail_validator.py
import re
from pathlib import Path

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_PDF_BYTES = 3 * 1024 * 1024  # 3 MB


class MailValidationError(ValueError):
    pass


def _check_email_list(addrs: list[str], field: str) -> None:
    for a in addrs:
        if not _EMAIL_RE.match(a):
            raise MailValidationError(f"{field}のメールアドレス形式が不正です: {a}")


def validate_invoice_mail(
    to_recipients:  list[str],
    subject:        str,
    body_html:      str,
    pdf_path:       str,
    cc_recipients:  list[str] | None = None,
    bcc_recipients: list[str] | None = None,
) -> None:
    if not to_recipients:
        raise MailValidationError("宛先を1件以上指定してください。")

    _check_email_list(to_recipients, "宛先")
    if cc_recipients:
        _check_email_list(cc_recipients, "CC")
    if bcc_recipients:
        _check_email_list(bcc_recipients, "BCC")

    if not subject.strip():
        raise MailValidationError("件名を入力してください。")
    if not body_html.strip():
        raise MailValidationError("本文を入力してください。")

    pdf = Path(pdf_path)
    if not pdf.exists():
        raise MailValidationError(f"PDFファイルが存在しません: {pdf_path}")
    if pdf.suffix.lower() != ".pdf":
        raise MailValidationError("添付ファイルはPDFである必要があります。")

    if pdf.stat().st_size >= _MAX_PDF_BYTES:
        # TODO: 3MB以上のPDFは Microsoft Graph large attachment upload session で対応する
        raise MailValidationError(
            "PDFファイルが3MB以上です。現在の実装では3MB未満のPDFのみ送信できます。"
        )
