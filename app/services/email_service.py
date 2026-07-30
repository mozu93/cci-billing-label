# app/services/email_service.py
import html as _html
import os
import re
from uuid import uuid4
from app.utils.app_config import get_config, save_config


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

# テンプレート画面・送信確認画面で共通利用するタグ説明。
# キー文字列は既存テンプレートとの互換性のため変更しない。
PLACEHOLDER_DESCRIPTIONS = {
    "宛名": "請求先の表示名（事業所名と代表者名）",
    "事業所名": "請求先の事業所名",
    "代表者名": "請求先の代表者名",
    "会社名": "請求書を発行する自社・商工会議所名",
    "書類名": "請求書または領収書",
    "文書番号": "請求書番号または領収書番号",
    "金額": "請求金額または領収金額",
    "件名": "請求対象の案件名・業務名",
    "発行日": "請求書・領収書の発行日",
    "支払期限": "請求書に設定された支払期限",
}
PLACEHOLDER_KEYS = [
    "宛名", "事業所名", "代表者名", "会社名",
    "書類名", "文書番号", "金額", "件名", "発行日",
]


def render_email_template(text: str, context: dict[str, str]) -> str:
    for key, val in context.items():
        text = text.replace("{" + key + "}", val)
    return text


def _template_collection(kind: str, config: dict | None = None) -> dict:
    if kind not in _TEMPLATE_DEFAULTS:
        raise ValueError("メールテンプレート種別が不正です。")
    config = config if config is not None else get_config()
    saved = config.get("email_templates", {}).get(kind, {})
    default_subject, default_body = _TEMPLATE_DEFAULTS[kind]

    # v2.2以前の単一テンプレートは、標準テンプレート1件として扱う。
    if not isinstance(saved.get("items"), list):
        item = {
            "id": "standard",
            "name": "標準テンプレート",
            "subject": saved.get("subject") or default_subject,
            "body": saved.get("body") or default_body,
        }
        return {"default_id": item["id"], "items": [item]}

    items = []
    for raw in saved["items"]:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        items.append({
            "id": str(raw["id"]),
            "name": str(raw.get("name") or "名称未設定"),
            "subject": raw.get("subject") or default_subject,
            "body": raw.get("body") or default_body,
        })
    if not items:
        items = [{
            "id": "standard",
            "name": "標準テンプレート",
            "subject": default_subject,
            "body": default_body,
        }]
    default_id = saved.get("default_id")
    if default_id not in {item["id"] for item in items}:
        default_id = items[0]["id"]
    return {"default_id": default_id, "items": items}


def get_email_templates(kind: str) -> list[dict]:
    """指定書類のテンプレート一覧を、既定フラグ付きで返す。"""
    collection = _template_collection(kind)
    return [
        {**item, "is_default": item["id"] == collection["default_id"]}
        for item in collection["items"]
    ]


def get_email_template(
        kind: str, template_id: str | None = None) -> tuple[str, str]:
    """指定テンプレート（未指定なら既定）の件名と本文を返す。"""
    collection = _template_collection(kind)
    wanted = template_id or collection["default_id"]
    default_item = next(
        entry for entry in collection["items"]
        if entry["id"] == collection["default_id"])
    item = next(
        (entry for entry in collection["items"] if entry["id"] == wanted),
        default_item,
    )
    return item["subject"], item["body"]


def _write_template_collection(
        config: dict, kind: str, collection: dict) -> None:
    config.setdefault("email_templates", {})[kind] = {
        "default_id": collection["default_id"],
        "items": collection["items"],
    }


def save_email_template(
        kind: str,
        subject: str,
        body: str,
        template_id: str | None = None,
        name: str | None = None,
) -> str:
    """テンプレートを更新する。ID未指定時は既定テンプレートを更新する。"""
    config = get_config()
    collection = _template_collection(kind, config)
    wanted = template_id or collection["default_id"]
    item = next(
        (entry for entry in collection["items"] if entry["id"] == wanted),
        None,
    )
    if item is None:
        item = {
            "id": wanted or uuid4().hex,
            "name": name or "新しいテンプレート",
            "subject": subject,
            "body": body,
        }
        collection["items"].append(item)
    else:
        item["subject"] = subject
        item["body"] = body
        if name:
            item["name"] = name
    _write_template_collection(config, kind, collection)
    save_config(config)
    return item["id"]


def create_email_template(
        kind: str, name: str, subject: str, body: str) -> str:
    if not name.strip():
        raise ValueError("テンプレート名を入力してください。")
    config = get_config()
    collection = _template_collection(kind, config)
    template_id = uuid4().hex
    collection["items"].append({
        "id": template_id,
        "name": name.strip(),
        "subject": subject,
        "body": body,
    })
    _write_template_collection(config, kind, collection)
    save_config(config)
    return template_id


def rename_email_template(kind: str, template_id: str, name: str) -> None:
    if not name.strip():
        raise ValueError("テンプレート名を入力してください。")
    config = get_config()
    collection = _template_collection(kind, config)
    item = next(
        (entry for entry in collection["items"]
         if entry["id"] == template_id),
        None,
    )
    if item is None:
        raise ValueError("メールテンプレートが見つかりません。")
    item["name"] = name.strip()
    _write_template_collection(config, kind, collection)
    save_config(config)


def delete_email_template(kind: str, template_id: str) -> None:
    config = get_config()
    collection = _template_collection(kind, config)
    if template_id not in {item["id"] for item in collection["items"]}:
        raise ValueError("メールテンプレートが見つかりません。")
    if len(collection["items"]) <= 1:
        raise ValueError("最後のテンプレートは削除できません。")
    collection["items"] = [
        item for item in collection["items"] if item["id"] != template_id]
    if len(collection["items"]) == 0:
        raise ValueError("メールテンプレートが見つかりません。")
    if collection["default_id"] == template_id:
        collection["default_id"] = collection["items"][0]["id"]
    _write_template_collection(config, kind, collection)
    save_config(config)


def set_default_email_template(kind: str, template_id: str) -> None:
    config = get_config()
    collection = _template_collection(kind, config)
    if template_id not in {item["id"] for item in collection["items"]}:
        raise ValueError("メールテンプレートが見つかりません。")
    collection["default_id"] = template_id
    _write_template_collection(config, kind, collection)
    save_config(config)


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


def get_issuance_email_context(session, issuance) -> dict[str, str]:
    """発行データの差し込みタグ置換値を返す。"""
    from app.database.models import Project
    from app.utils.pdf_helpers import get_issuer_for_project

    project = (
        session.get(Project, issuance.project_id)
        if issuance.project_id else None
    )
    company, _bank, _seal = get_issuer_for_project(
        session, project, issuance=issuance)
    company_name = company.name if company else ""
    project_name = project.name if project else ""
    return build_issuance_context(issuance, company_name, project_name)


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
    from app.database.models import ProjectMember
    label = (issuance.recipient_organization or issuance.recipient_name
             or issuance.doc_number or "")
    if not to_addr:
        to_addr = (getattr(issuance, "recipient_email", "") or "").strip()
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
    context = get_issuance_email_context(session, issuance)
    subject_t, body_t = get_email_template(issuance.doc_type)
    subject = render_email_template(subject_t, context)
    body = render_email_template(body_t, context)
    import html as _html
    body_html = (
        "<div style='font-family:sans-serif; font-size:14px; line-height:1.8;'>"
        + _html.escape(body).replace("\n", "<br>")
        + "</div>"
    )
    return to_addr, subject, body_html, issuance.pdf_path


def prepare_reminder_email(session, issuance, due_date=None,
                           custom_subject: str | None = None,
                           custom_body: str | None = None,
                           ) -> tuple[str, str, str, str | None]:
    """督促メールの (宛先, 件名, 本文HTML, PDFパスまたはNone) を組み立てる。
    custom_subject / custom_body を渡すとテンプレート設定より優先して使用する。
    """
    from app.database.models import ProjectMember, Project
    from app.utils.pdf_helpers import get_issuer_for_project
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
    proj = (
        session.get(Project, issuance.project_id)
        if issuance.project_id else None
    )
    company, _bank, _seal = get_issuer_for_project(
        session, proj, issuance=issuance)
    company_name = company.name if company else ""
    project_name = proj.name if proj else ""
    extra = {"支払期限": due_date.strftime("%Y年%m月%d日") if due_date else ""}
    if custom_subject is not None and custom_body is not None:
        ctx = build_issuance_context(issuance, company_name, project_name)
        ctx.update(extra)
        subject = render_email_template(custom_subject, ctx)
        body    = render_email_template(custom_body,    ctx)
    else:
        subject, body = build_issuance_email(
            issuance, company_name, project_name,
            kind="reminder", extra_context=extra)
    body_html = (
        "<div style='font-family:sans-serif; font-size:14px; line-height:1.8;'>"
        + _html.escape(body).replace("\n", "<br>")
        + "</div>"
    )
    pdf = (issuance.pdf_path
           if issuance.pdf_path and os.path.exists(issuance.pdf_path)
           else None)
    return to_addr, subject, body_html, pdf
