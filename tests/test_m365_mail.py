import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


# ── バリデーションテスト ────────────────────────────────────────────────

def _tmp_pdf(size: int = 100) -> str:
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.write(fd, b"%PDF" + b"x" * (size - 4))
    os.close(fd)
    return path


def test_validate_ok(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF" + b"x" * 100)
    from app.utils.mail_validator import validate_invoice_mail
    validate_invoice_mail(["a@example.com"], "件名", "<p>本文</p>", pdf)


def test_validate_no_recipient(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="宛先"):
        validate_invoice_mail([], "件名", "<p>本文</p>", pdf)


def test_validate_bad_email(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="形式"):
        validate_invoice_mail(["notanemail"], "件名", "<p>本文</p>", pdf)


def test_validate_empty_subject(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="件名"):
        validate_invoice_mail(["a@example.com"], "  ", "<p>本文</p>", pdf)


def test_validate_empty_body(tmp_path):
    pdf = str(tmp_path / "test.pdf")
    (tmp_path / "test.pdf").write_bytes(b"%PDF")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="本文"):
        validate_invoice_mail(["a@example.com"], "件名", "   ", pdf)


def test_validate_pdf_not_found():
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="存在しません"):
        validate_invoice_mail(["a@example.com"], "件名", "<p>x</p>", "/no/such/file.pdf")


def test_validate_not_pdf(tmp_path):
    f = tmp_path / "test.txt"
    f.write_bytes(b"hello")
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="PDF"):
        validate_invoice_mail(["a@example.com"], "件名", "<p>x</p>", str(f))


def test_validate_pdf_too_large(tmp_path):
    pdf = tmp_path / "big.pdf"
    pdf.write_bytes(b"%PDF" + b"x" * (3 * 1024 * 1024))
    from app.utils.mail_validator import validate_invoice_mail, MailValidationError
    with pytest.raises(MailValidationError, match="3MB"):
        validate_invoice_mail(["a@example.com"], "件名", "<p>x</p>", str(pdf))


# ── M365MailService テスト（requests.post をモック）──────────────────────

def test_send_mail_202_success(tmp_path):
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    mock_resp = MagicMock()
    mock_resp.status_code = 202

    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")

    with patch("app.services.m365_mail_service.requests.post", return_value=mock_resp):
        result = svc.send_mail(["a@example.com"], "件名", "<p>本文</p>", str(pdf))

    assert result["status"] == "accepted"
    assert result["http_status_code"] == 202


@pytest.mark.parametrize("status_code", [400, 401, 403, 429, 500])
def test_send_mail_non_202_raises(tmp_path, status_code):
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = "error"

    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")

    with patch("app.services.m365_mail_service.requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match=str(status_code)):
            svc.send_mail(["a@example.com"], "件名", "<p>本文</p>", str(pdf))


def test_send_mail_network_error(tmp_path):
    import requests as req_lib
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")

    with patch("app.services.m365_mail_service.requests.post",
               side_effect=req_lib.ConnectionError("接続失敗")):
        with pytest.raises(RuntimeError, match="接続に失敗"):
            svc.send_mail(["a@example.com"], "件名", "<p>本文</p>", str(pdf))


def test_send_mail_pdf_not_found():
    from app.services.m365_mail_service import M365MailService
    svc = M365MailService("dummy_token")
    with pytest.raises(FileNotFoundError):
        svc.send_mail(["a@example.com"], "件名", "<p>本文</p>", "/no/such/file.pdf")
