# app/services/email_service.py
import smtplib
import ssl
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from app.utils.app_config import get_config


def get_smtp_config() -> dict:
    return get_config().get("smtp", {})


def _build_message(smtp_config: dict, to_addr: str, subject: str,
                   body: str, pdf_path: str | None = None,
                   is_test: bool = False) -> MIMEMultipart:
    msg = MIMEMultipart()
    from_addr = smtp_config.get("from_addr", "")
    from_name = smtp_config.get("from_name", "")
    msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    msg["To"] = to_addr
    msg["Subject"] = Header(
        f"【テスト】{subject}" if is_test else subject, "utf-8"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(pdf_path))
        part["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(pdf_path)}"'
        )
        msg.attach(part)
    return msg


def send_email(to_addr: str, subject: str, body: str,
               pdf_path: str | None = None) -> None:
    config = get_smtp_config()
    msg = _build_message(config, to_addr, subject, body, pdf_path)
    _send(config, to_addr, msg)


def send_test_email(subject: str, body: str,
                    pdf_path: str | None = None) -> None:
    config = get_smtp_config()
    test_addr = config.get("test_addr", "")
    if not test_addr:
        raise ValueError("テスト送信先メールアドレスが設定されていません。")
    msg = _build_message(config, test_addr, subject, body, pdf_path, is_test=True)
    _send(config, test_addr, msg)


def _connect(config: dict) -> smtplib.SMTP:
    host = config.get("host", "")
    port = int(config.get("port", 587))
    user = config.get("user", "")
    password = config.get("password", "")
    use_tls = config.get("use_tls", True)

    if not host:
        raise ValueError("SMTPサーバーが設定されていません。")

    if port == 465:
        # SSL直結（SMTPS）
        s = smtplib.SMTP_SSL(host, port, timeout=15,
                             context=ssl.create_default_context())
    else:
        s = smtplib.SMTP(host, port, timeout=15)
        if use_tls:
            s.ehlo()
            s.starttls(context=ssl.create_default_context())
    if user:
        s.login(user, password)
    return s


def _send(config: dict, to_addr: str, msg: MIMEMultipart) -> None:
    s = _connect(config)
    try:
        s.sendmail(msg["From"], [to_addr], msg.as_string())
    finally:
        try:
            s.quit()
        except Exception:
            pass


class SmtpSession:
    """複数通を1つのSMTP接続で送るためのラッパー（with文で使用）。"""

    def __enter__(self):
        self._config = get_smtp_config()
        self._smtp = _connect(self._config)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._smtp.quit()
        except Exception:
            pass
        return False

    def send(self, to_addr: str, subject: str, body: str,
             pdf_path: str | None = None) -> None:
        msg = _build_message(self._config, to_addr, subject, body, pdf_path)
        self._smtp.sendmail(msg["From"], [to_addr], msg.as_string())


_ADDR_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email_addr(addr: str) -> str:
    """メールアドレスの形式を簡易チェックし、前後の空白を除いて返す。"""
    a = (addr or "").strip()
    if not _ADDR_RE.match(a):
        raise ValueError(
            f"メールアドレスの形式が正しくありません：{a or '（空欄）'}")
    return a


# ── 差し込みテンプレート ──────────────────────────────────────

DEFAULT_SUBJECT = "【{会社名}】{書類名}をお送りします"
DEFAULT_BODY = (
    "{宛名} 様\n\n"
    "お世話になっております。{会社名}でございます。\n\n"
    "{書類名}（{文書番号}）を添付にてお送りいたします。\n"
    "金額：{金額}（税込）\n\n"
    "ご確認のほどよろしくお願いいたします。\n\n"
    "{会社名}"
)

DEFAULT_REMINDER_SUBJECT = "【{会社名}】{書類名}（{文書番号}）お支払いのご確認"
DEFAULT_REMINDER_BODY = (
    "{宛名} 様\n\n"
    "お世話になっております。{会社名}でございます。\n\n"
    "{発行日}付でお送りした{書類名}（{文書番号}）につきまして、\n"
    "支払期限（{支払期限}）を過ぎてもご入金の確認ができておりません。\n"
    "金額：{金額}（税込）\n\n"
    "行き違いでご入金済みの場合は、何卒ご容赦ください。\n"
    "ご確認のほどよろしくお願いいたします。\n\n"
    "{会社名}"
)

_TEMPLATE_DEFAULTS = {
    "invoice": (DEFAULT_SUBJECT, DEFAULT_BODY),
    "receipt": (DEFAULT_SUBJECT, DEFAULT_BODY),
    "reminder": (DEFAULT_REMINDER_SUBJECT, DEFAULT_REMINDER_BODY),
}

# メール設定画面のヘルプ表示にも使う
PLACEHOLDER_KEYS = [
    "宛名", "事業所名", "代表者名", "会社名",
    "書類名", "文書番号", "金額", "件名", "発行日",
]


def render_email_template(text: str, context: dict[str, str]) -> str:
    for key, val in context.items():
        text = text.replace("{" + key + "}", val)
    return text


def get_email_template(kind: str) -> tuple[str, str]:
    """kind: invoice / receipt / reminder のテンプレート（件名, 本文）を返す。"""
    d_subject, d_body = _TEMPLATE_DEFAULTS.get(
        kind, (DEFAULT_SUBJECT, DEFAULT_BODY))
    tmpl = get_config().get("email_templates", {}).get(kind, {})
    return (tmpl.get("subject") or d_subject,
            tmpl.get("body") or d_body)


def build_issuance_context(issuance, company_name: str,
                           project_name: str = "") -> dict[str, str]:
    doc_label = "請求書" if issuance.doc_type == "invoice" else "領収書"
    org = issuance.recipient_organization or ""
    rep = issuance.recipient_name or ""
    addressee = "　".join(x for x in (org, rep) if x)
    issued = (issuance.issued_at.strftime("%Y年%m月%d日")
              if issuance.issued_at else "")
    return {
        "宛名": addressee,
        "事業所名": org,
        "代表者名": rep,
        "会社名": company_name,
        "書類名": doc_label,
        "文書番号": issuance.doc_number or "",
        "金額": f"¥{int(issuance.amount or 0):,}",
        "件名": project_name,
        "発行日": issued,
    }


def build_issuance_email(issuance, company_name: str,
                         project_name: str = "",
                         kind: str | None = None,
                         extra_context: dict[str, str] | None = None
                         ) -> tuple[str, str]:
    subject_t, body_t = get_email_template(kind or issuance.doc_type)
    ctx = build_issuance_context(issuance, company_name, project_name)
    if extra_context:
        ctx.update(extra_context)
    return (render_email_template(subject_t, ctx),
            render_email_template(body_t, ctx))


def prepare_issuance_email(session, issuance,
                           to_addr: str | None = None
                           ) -> tuple[str, str, str, str]:
    """Issuance から (宛先, 件名, 本文, PDFパス) を検証込みで組み立てる。

    to_addr 未指定時は ProjectMember.email を宛先に使う。
    """
    from app.database.models import CompanySettings, ProjectMember, Project
    label = (issuance.recipient_organization or issuance.recipient_name
             or issuance.doc_number or "")
    if not to_addr and issuance.project_member_id:
        pm = session.get(ProjectMember, issuance.project_member_id)
        to_addr = (pm.email or "").strip() if pm else ""
    if not to_addr:
        raise ValueError(f"{label}：メールアドレスが登録されていません。")
    try:
        to_addr = validate_email_addr(to_addr)
    except ValueError as e:
        raise ValueError(f"{label}：{e}")
    if not issuance.pdf_path or not os.path.exists(issuance.pdf_path):
        raise ValueError(f"{label}：添付するPDFファイルが見つかりません。")
    company = session.query(CompanySettings).first()
    company_name = company.name if company else ""
    project_name = ""
    if issuance.project_id:
        proj = session.get(Project, issuance.project_id)
        project_name = proj.name if proj else ""
    subject, body = build_issuance_email(issuance, company_name, project_name)
    return to_addr, subject, body, issuance.pdf_path


def send_reminder_email(session, issuance, due_date=None,
                        smtp: SmtpSession | None = None) -> str:
    """支払期限超過の督促メールを送る（請求書PDFがあれば再添付）。送信先を返す。"""
    from app.database.models import CompanySettings, ProjectMember, Project
    label = (issuance.recipient_organization or issuance.recipient_name
             or issuance.doc_number or "")
    to_addr = ""
    if issuance.project_member_id:
        pm = session.get(ProjectMember, issuance.project_member_id)
        to_addr = (pm.email or "").strip() if pm else ""
    if not to_addr:
        raise ValueError(f"{label}：メールアドレスが登録されていません。")
    try:
        to_addr = validate_email_addr(to_addr)
    except ValueError as e:
        raise ValueError(f"{label}：{e}")
    company = session.query(CompanySettings).first()
    company_name = company.name if company else ""
    project_name = ""
    if issuance.project_id:
        proj = session.get(Project, issuance.project_id)
        project_name = proj.name if proj else ""
    extra = {"支払期限": due_date.strftime("%Y年%m月%d日") if due_date else ""}
    subject, body = build_issuance_email(
        issuance, company_name, project_name,
        kind="reminder", extra_context=extra)
    pdf = (issuance.pdf_path
           if issuance.pdf_path and os.path.exists(issuance.pdf_path)
           else None)
    if smtp is not None:
        smtp.send(to_addr, subject, body, pdf)
    else:
        send_email(to_addr, subject, body, pdf_path=pdf)
    return to_addr


def send_issuance_email(session, issuance, to_addr: str | None = None,
                        smtp: SmtpSession | None = None) -> str:
    """発行済み Issuance の PDF を添付してメール送信し、送信先を返す。

    smtp に SmtpSession を渡すと既存接続を使い回す（一括送信用）。
    """
    to_addr, subject, body, pdf_path = prepare_issuance_email(
        session, issuance, to_addr)
    if smtp is not None:
        smtp.send(to_addr, subject, body, pdf_path)
    else:
        send_email(to_addr, subject, body, pdf_path=pdf_path)
    return to_addr
