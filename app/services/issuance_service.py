# app/services/issuance_service.py
from datetime import datetime, date
from sqlalchemy.orm import Session
from app.database.models import (
    Issuance, IssuanceLine, Payment, ProjectTemplate, ProjectMember
)


def get_next_doc_number(session: Session, doc_type: str,
                         fiscal_year: int, month: int) -> str:
    prefix = "INV" if doc_type == "invoice" else "RCP"
    ym = f"{fiscal_year}{month:02d}"
    pattern = f"{prefix}-{ym}-%"
    last = (session.query(Issuance)
            .filter(Issuance.doc_number.like(pattern))
            .order_by(Issuance.doc_number.desc())
            .first())
    if last:
        seq = int(last.doc_number.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}-{ym}-{seq:04d}"


def _build_lines_from_project(session: Session, project_id: int,
                               quantities: dict[int, int] | None = None,
                               unit_prices: dict[int, int] | None = None,
                               default_quantity: int | None = None) -> tuple[list[dict], int]:
    """プロジェクトテンプレートから発行明細を生成する。

    quantities:  {item_template_id: 数量} — 品目ごとに数量を指定する場合。
                 未指定のキーは default_quantity（指定なければ品目の既定数量）を使う。
    unit_prices: {item_template_id: 単価} — 品目ごとに単価を上書きする場合。
                 None または未指定のキーはプロジェクト設定 or マスタ単価を使う。
    default_quantity: 明示的に指定された場合、品目側の既定数量より優先する
                 （窓口発行で「数量3で発行」のように一括上書きする場合に使う）。
    """
    pts = (session.query(ProjectTemplate)
           .filter_by(project_id=project_id)
           .order_by(ProjectTemplate.sort_order)
           .all())
    lines = []
    total = 0
    for pt in pts:
        tmpl = pt.item_template
        price = (unit_prices or {}).get(tmpl.id) or int(pt.unit_price_override or tmpl.unit_price)
        fallback_qty = default_quantity if default_quantity is not None else (pt.default_quantity or 1)
        qty = (quantities or {}).get(tmpl.id, fallback_qty)
        if qty <= 0:
            continue  # 数量0の項目は明細に含めない
        line_total = price * qty
        total += line_total
        lines.append({
            "item_template_id": tmpl.id,
            "item_name": tmpl.name,
            "quantity": qty,
            "unit": tmpl.unit,
            "unit_price": price,
            "tax_rate": tmpl.tax_rate,
            "line_total": line_total,
        })
    return lines, total


def create_issuance_for_member(session: Session, project_id: int,
                                project_member_id: int,
                                recipient_organization: str,
                                recipient_name: str,
                                doc_type: str, fiscal_year: int,
                                month: int,
                                quantities: dict[int, int] | None = None,
                                unit_prices: dict[int, int] | None = None,
                                recipient_department: str = "",
                                show_recipient_person: bool = True) -> Issuance:
    doc_number = get_next_doc_number(session, doc_type, fiscal_year, month)
    lines, total = _build_lines_from_project(
        session, project_id, quantities=quantities, unit_prices=unit_prices)

    issuance = Issuance(
        project_id=project_id,
        project_member_id=project_member_id,
        recipient_organization=recipient_organization,
        recipient_name=recipient_name,
        recipient_department=recipient_department,
        doc_type=doc_type,
        doc_number=doc_number,
        status="準備中",
        amount=total,
        show_recipient_person=show_recipient_person,
    )
    session.add(issuance)
    session.flush()
    for line_data in lines:
        session.add(IssuanceLine(issuance_id=issuance.id, **line_data))
    session.commit()
    session.refresh(issuance)
    return issuance


def create_counter_issuance(session: Session, project_id: int,
                             recipient_organization: str,
                             recipient_name: str,
                             doc_type: str, quantity: int,
                             fiscal_year: int, month: int) -> Issuance:
    doc_number = get_next_doc_number(session, doc_type, fiscal_year, month)
    lines, total = _build_lines_from_project(session, project_id, default_quantity=quantity)
    now = datetime.now()
    issuance = Issuance(
        project_id=project_id,
        project_member_id=None,
        recipient_organization=recipient_organization,
        recipient_name=recipient_name,
        doc_type=doc_type,
        doc_number=doc_number,
        status="発行済み",
        amount=total,
        issued_at=now,
    )
    session.add(issuance)
    session.flush()
    for line_data in lines:
        session.add(IssuanceLine(issuance_id=issuance.id, **line_data))
    session.commit()
    session.refresh(issuance)
    return issuance


def create_combined_issuance(session: Session,
                              issuances_data: list[dict],
                              doc_type: str,
                              recipient_organization: str,
                              recipient_name: str,
                              fiscal_year: int, month: int,
                              staff_id: int | None,
                              staff_name: str,
                              delivery_method: str) -> Issuance:
    doc_number = get_next_doc_number(session, doc_type, fiscal_year, month)
    all_lines = []
    total = 0
    primary_project_id = issuances_data[0]["project_id"] if issuances_data else None
    for data in issuances_data:
        lines, sub_total = _build_lines_from_project(
            session, data["project_id"], data.get("quantity", 1))
        all_lines.extend(lines)
        total += sub_total
    now = datetime.now()
    issuance = Issuance(
        project_id=primary_project_id,
        project_member_id=None,
        recipient_organization=recipient_organization,
        recipient_name=recipient_name,
        doc_type=doc_type,
        doc_number=doc_number,
        status="発行済み",
        amount=total,
        issued_at=now,
        staff_id=staff_id,
        staff_name=staff_name,
        delivery_method=delivery_method,
    )
    session.add(issuance)
    session.flush()
    for line_data in all_lines:
        session.add(IssuanceLine(issuance_id=issuance.id, **line_data))
    for data in issuances_data:
        pm_id = data.get("project_member_id")
        if pm_id:
            prep = (session.query(Issuance)
                    .filter_by(project_member_id=pm_id, status="準備中")
                    .first())
            if prep:
                prep.status = "発行済み"
                prep.issued_at = now
                prep.staff_name = staff_name
    session.commit()
    session.refresh(issuance)
    return issuance


def mark_as_issued(session: Session, issuance_id: int,
                   staff_id: int | None, staff_name: str,
                   delivery_method: str = "窓口手渡し",
                   issued_at: datetime | None = None) -> None:
    issuance = session.get(Issuance, issuance_id)
    if issuance:
        issuance.status = "発行済み"
        issuance.issued_at = issued_at or datetime.now()
        issuance.staff_id = staff_id
        issuance.staff_name = staff_name
        issuance.delivery_method = delivery_method
        session.commit()


def record_payment(session: Session, issuance_id: int,
                   payment_date: date, amount: int,
                   payment_method: str = "現金",
                   staff_id: int | None = None,
                   staff_name: str = "",
                   notes: str = "") -> None:
    issuance = session.get(Issuance, issuance_id)
    if not issuance:
        return
    payment = Payment(
        issuance_id=issuance_id,
        payment_date=payment_date,
        amount=amount,
        payment_method=payment_method,
        staff_id=staff_id,
        staff_name=staff_name,
        notes=notes,
    )
    session.add(payment)
    issuance.status = "支払済み"
    session.commit()


def create_direct_issuance(session: Session, lines_data: list[dict],
                            recipient_organization: str, recipient_name: str,
                            doc_type: str, fiscal_year: int, month: int,
                            staff_id: int | None = None, staff_name: str = "",
                            delivery_method: str = "窓口手渡し",
                            project_name: str = "直接発行",
                            member_number: str = "",
                            recipient_kana: str = "",
                            recipient_department: str = "",
                            recipient_name_kana: str = "",
                            recipient_phone: str = "",
                            company_settings_id: int | None = None,
                            bank_account_id: int | None = None,
                            seal_image_id: int | None = None,
                            show_recipient_person: bool = True) -> Issuance:
    from app.database.models import Project
    sys_proj = (session.query(Project)
                .filter_by(name=project_name, project_type="counter")
                .first())
    if not sys_proj:
        sys_proj = Project(
            name=project_name, fiscal_year=fiscal_year,
            project_type="counter", status="active",
        )
        session.add(sys_proj)
        session.flush()

    doc_number = get_next_doc_number(session, doc_type, fiscal_year, month)
    total = sum(int(l["unit_price"]) * int(l["quantity"]) for l in lines_data)
    now = datetime.now()
    # 領収書は入金済みの証憑なので、発行と同時に入金を記録し「支払済み」にする。
    # 請求書はその場では未入金なので「発行済み」のまま。
    is_receipt = doc_type == "receipt"
    issuance = Issuance(
        project_id=sys_proj.id,
        project_member_id=None,
        member_number=member_number,
        recipient_organization=recipient_organization,
        recipient_kana=recipient_kana,
        recipient_department=recipient_department,
        recipient_name=recipient_name,
        recipient_name_kana=recipient_name_kana,
        recipient_phone=recipient_phone,
        doc_type=doc_type,
        doc_number=doc_number,
        status="支払済み" if is_receipt else "発行済み",
        amount=total,
        issued_at=now,
        staff_id=staff_id,
        staff_name=staff_name,
        delivery_method=delivery_method,
        company_settings_id=company_settings_id,
        bank_account_id=bank_account_id,
        seal_image_id=seal_image_id,
        show_recipient_person=show_recipient_person,
    )
    session.add(issuance)
    session.flush()
    for ld in lines_data:
        session.add(IssuanceLine(
            issuance_id=issuance.id,
            item_template_id=ld.get("item_template_id"),
            item_name=ld["item_name"],
            quantity=ld["quantity"],
            unit=ld["unit"],
            unit_price=ld["unit_price"],
            tax_rate=ld["tax_rate"],
            line_total=int(ld["unit_price"]) * int(ld["quantity"]),
        ))
    if is_receipt:
        session.add(Payment(
            issuance_id=issuance.id,
            payment_date=now.date(),
            amount=total,
            payment_method="現金",
            staff_id=staff_id,
            staff_name=staff_name,
        ))
    session.commit()
    session.refresh(issuance)
    return issuance


def update_direct_issuance(session: Session, issuance_id: int,
                            lines_data: list[dict],
                            recipient_organization: str, recipient_name: str,
                            delivery_method: str,
                            staff_id: int | None = None,
                            staff_name: str = "",
                            member_number: str = "",
                            recipient_kana: str = "",
                            recipient_department: str = "",
                            recipient_name_kana: str = "",
                            recipient_phone: str = "",
                            company_settings_id: int | None = None,
                            bank_account_id: int | None = None,
                            seal_image_id: int | None = None,
                            show_recipient_person: bool = True) -> Issuance:
    issuance = session.get(Issuance, issuance_id)
    if issuance is None:
        raise ValueError("発行データが見つかりません。")
    for line in list(issuance.lines):
        session.delete(line)
    session.flush()
    total = sum(int(l["unit_price"]) * int(l["quantity"]) for l in lines_data)
    issuance.member_number = member_number
    issuance.recipient_organization = recipient_organization
    issuance.recipient_kana = recipient_kana
    issuance.recipient_department = recipient_department
    issuance.recipient_name = recipient_name
    issuance.recipient_name_kana = recipient_name_kana
    issuance.recipient_phone = recipient_phone
    issuance.delivery_method = delivery_method
    issuance.company_settings_id = company_settings_id
    issuance.bank_account_id = bank_account_id
    issuance.seal_image_id = seal_image_id
    issuance.show_recipient_person = show_recipient_person
    issuance.amount = total
    if staff_id is not None:
        issuance.staff_id = staff_id
    if staff_name:
        issuance.staff_name = staff_name
    issuance.issued_at = datetime.now()
    for ld in lines_data:
        session.add(IssuanceLine(
            issuance_id=issuance.id,
            item_template_id=ld.get("item_template_id"),
            item_name=ld["item_name"],
            quantity=ld["quantity"],
            unit=ld["unit"],
            unit_price=ld["unit_price"],
            tax_rate=ld["tax_rate"],
            line_total=int(ld["unit_price"]) * int(ld["quantity"]),
        ))
    session.commit()
    session.refresh(issuance)
    return issuance


def get_pending_issuances_for_project_member(session: Session,
                                             project_member_id: int) -> list[Issuance]:
    return (session.query(Issuance)
            .filter(Issuance.project_member_id == project_member_id,
                    Issuance.status == "準備中")
            .all())


def get_project_issuances(session: Session, project_id: int,
                           status: str | None = None) -> list[Issuance]:
    q = session.query(Issuance).filter_by(project_id=project_id)
    if status:
        q = q.filter(Issuance.status == status)
    return q.order_by(Issuance.created_at.desc()).all()


def issue_receipt_for_invoice(session: Session, invoice_id: int,
                              payment_date: date,
                              payment_method: str = "現金",
                              notes: str = "",
                              staff_id: int | None = None,
                              staff_name: str = "",
                              delivery_method: str = "窓口手渡し") -> Issuance:
    """発行済み請求書から領収書を発行し、入金を記録して請求書を支払済みにする。

    領収書は元請求書の明細・金額・宛名をそのまま引き継ぐ。
    入金額は請求書の全額固定。全体を1トランザクションで実行する。
    """
    invoice = session.get(Issuance, invoice_id)
    if invoice is None:
        raise ValueError("請求書が見つかりません。")
    if invoice.doc_type != "invoice":
        raise ValueError("請求書ではありません。")
    if invoice.status == "支払済み":
        raise ValueError("既に支払済みの請求書です。")

    now = datetime.now()
    doc_number = get_next_doc_number(session, "receipt", now.year, now.month)
    receipt = Issuance(
        project_id=invoice.project_id,
        project_member_id=invoice.project_member_id,
        recipient_organization=invoice.recipient_organization,
        recipient_name=invoice.recipient_name,
        doc_type="receipt",
        doc_number=doc_number,
        status="支払済み",
        amount=invoice.amount,
        issued_at=now,
        staff_id=staff_id,
        staff_name=staff_name,
        delivery_method=delivery_method,
    )
    session.add(receipt)
    session.flush()
    for line in invoice.lines:
        session.add(IssuanceLine(
            issuance_id=receipt.id,
            item_template_id=line.item_template_id,
            item_name=line.item_name,
            quantity=line.quantity,
            unit=line.unit,
            unit_price=line.unit_price,
            tax_rate=line.tax_rate,
            line_total=line.line_total,
        ))

    payment = Payment(
        issuance_id=invoice.id,
        payment_date=payment_date,
        amount=invoice.amount,
        payment_method=payment_method,
        staff_id=staff_id,
        staff_name=staff_name,
        notes=notes,
    )
    session.add(payment)
    invoice.status = "支払済み"
    session.commit()
    session.refresh(receipt)
    return receipt


def search_unpaid_invoices(session: Session, query: str,
                           limit: int = 50) -> list[Issuance]:
    """検索語にマッチする、発行済み・未入金（status="発行済み"）の請求書を返す。

    検索対象: 宛先事業所名・宛先代表者名・名簿会員のフリガナ。
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    invoices = (session.query(Issuance)
                .filter(Issuance.doc_type == "invoice",
                        Issuance.status == "発行済み")
                .order_by(Issuance.issued_at.desc().nulls_last())
                .all())
    results = []
    for iss in invoices:
        parts = [iss.recipient_organization or "", iss.recipient_name or ""]
        if iss.project_member_id:
            pm = session.get(ProjectMember, iss.project_member_id)
            if pm:
                parts.append(pm.organization_kana or "")
        if q in " ".join(parts).lower():
            results.append(iss)
            if len(results) >= limit:
                break
    return results
