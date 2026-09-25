# app/services/issuance_service.py
from datetime import datetime, date
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.models import (
    Issuance, IssuanceLine, Payment, ProjectTemplate, ProjectMember, Project
)


# この年度（4月始まり）から、番号を「INV-年度-年度内の通し番号」にする。
# それより前は「INV-年月-月ごとの連番」。すでに発行した番号は変えない。
# 番号は全端末で共有するDBで付けるため、切り替え前に全端末の更新が必要
# （古い版の端末は切り替え後も旧形式で番号を出してしまう）。
FISCAL_NUMBERING_FROM = 2027


def get_next_doc_number(session: Session, doc_type: str,
                         fiscal_year: int, month: int) -> str:
    """DBの原子的なUPSERTで次の文書番号を予約する。

    fiscal_year・month は発行する日の暦年・月（名前は歴史的経緯による）。
    2027年4月以降は年度単位の通し番号（例：INV-2027-0001）、それより前は
    年月単位の連番（例：INV-202703-0001）。採番表の year_month には、
    前者は年度（"2027"）、後者は年月（"202703"）を入れるので重ならない。"""
    if doc_type not in ("invoice", "receipt"):
        raise ValueError("文書種別が不正です。")
    prefix = "INV" if doc_type == "invoice" else "RCP"
    fy = fiscal_year_of(date(fiscal_year, month, 1))
    if fy >= FISCAL_NUMBERING_FROM:
        ym = str(fy)
    else:
        ym = f"{fiscal_year}{month:02d}"
    pattern = f"{prefix}-{ym}-%"
    last = (session.query(Issuance)
            .filter(Issuance.doc_number.like(pattern))
            .order_by(Issuance.doc_number.desc())
            .first())
    initial = (
        int(last.doc_number.split("-")[-1]) + 1
        if last else 1
    )
    seq = session.execute(
        text(
            "INSERT INTO document_sequences "
            "(doc_type, year_month, last_value) "
            "VALUES (:doc_type, :year_month, :initial) "
            "ON CONFLICT (doc_type, year_month) DO UPDATE SET "
            "last_value = CASE "
            "WHEN document_sequences.last_value + 1 < excluded.last_value "
            "THEN excluded.last_value "
            "ELSE document_sequences.last_value + 1 END "
            "RETURNING last_value"
        ),
        {
            "doc_type": doc_type,
            "year_month": ym,
            "initial": initial,
        },
    ).scalar_one()
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
        price = (unit_prices or {}).get(tmpl.id)
        if price is None:
            price = int(pt.unit_price_override
                        if pt.unit_price_override is not None
                        else tmpl.unit_price)
        fallback_qty = default_quantity if default_quantity is not None else (
            pt.default_quantity if pt.default_quantity is not None else 1)
        qty = (quantities or {}).get(tmpl.id, fallback_qty)
        if qty <= 0:
            continue  # 数量0の項目は明細に含めない
        tax_rate = pt.tax_rate_override if pt.tax_rate_override is not None else tmpl.tax_rate
        line_total = price * qty
        total += line_total
        lines.append({
            "item_template_id": tmpl.id,
            "item_name": tmpl.name,
            "quantity": qty,
            "unit": tmpl.unit,
            "unit_price": price,
            "tax_rate": tax_rate,
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
                                show_recipient_person: bool = True,
                                roster_no: str = "",
                                company_settings_id: int | None = None,
                                bank_account_id: int | None = None,
                                seal_image_id: int | None = None) -> Issuance:
    doc_number = get_next_doc_number(session, doc_type, fiscal_year, month)
    lines, total = _build_lines_from_project(
        session, project_id, quantities=quantities, unit_prices=unit_prices)

    issuance = Issuance(
        project_id=project_id,
        project_member_id=project_member_id,
        roster_no=roster_no,
        recipient_organization=recipient_organization,
        recipient_name=recipient_name,
        recipient_department=recipient_department,
        doc_type=doc_type,
        doc_number=doc_number,
        status="準備中",
        amount=total,
        show_recipient_person=show_recipient_person,
        company_settings_id=company_settings_id,
        bank_account_id=bank_account_id,
        seal_image_id=seal_image_id,
    )
    session.add(issuance)
    session.flush()
    for line_data in lines:
        session.add(IssuanceLine(issuance_id=issuance.id, **line_data))
    session.commit()
    session.refresh(issuance)
    return issuance


def update_issuance_lines_from_project(
        session: Session, issuance_id: int,
        quantities: dict[int, int] | None = None,
        unit_prices: dict[int, int] | None = None,
        commit: bool = True) -> Issuance:
    """Excel・画面で編集した単価と数量を既存発行データの明細へ反映する。"""
    issuance = session.get(Issuance, issuance_id)
    if issuance is None:
        raise ValueError("発行データが見つかりません。")
    if issuance.status == "支払済み":
        raise ValueError(
            f"{issuance.doc_number or '発行データ'}：支払済みのため"
            "単価・数量は変更できません。")
    lines, total = _build_lines_from_project(
        session,
        issuance.project_id,
        quantities=quantities,
        unit_prices=unit_prices,
    )
    for line in list(issuance.lines):
        session.delete(line)
    session.flush()
    for line_data in lines:
        session.add(IssuanceLine(issuance_id=issuance.id, **line_data))
    issuance.amount = total
    if commit:
        session.commit()
    else:
        session.flush()
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
                   delivery_method: str = "印刷",
                   issued_at: datetime | None = None,
                   commit: bool = True) -> None:
    issuance = session.get(Issuance, issuance_id)
    if issuance:
        issuance.status = "発行済み"
        issuance.issued_at = issued_at or datetime.now()
        issuance.staff_id = staff_id
        issuance.staff_name = staff_name
        issuance.delivery_method = delivery_method
        if commit:
            session.commit()
        else:
            session.flush()


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
                            delivery_method: str = "印刷",
                            project_name: str = "直接発行",
                            member_number: str = "",
                            recipient_kana: str = "",
                            recipient_department: str = "",
                            recipient_name_kana: str = "",
                            recipient_phone: str = "",
                            recipient_email: str = "",
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
        recipient_email=recipient_email,
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


def switch_to_print(session: Session, issuance: Issuance) -> None:
    """メールで送らなかった発行を、同じ番号のまま「印刷」に切り替える。"""
    from app.services.operation_log_service import add_log
    before = issuance.delivery_method
    issuance.delivery_method = "印刷"
    session.commit()
    add_log(session, "発行方法変更", "issuance", issuance.id,
            f"{issuance.doc_number} {before}→印刷")


def cancel_unoutput_issuance(session: Session, issuance: Issuance) -> None:
    """印刷もメール送信もされなかった新規発行を取り消す。

    明細（cascade）と、領収書で同時に作った入金記録を削除する。番号は戻さない：
    複数端末で共有する採番を巻き戻すと、他端末の発行と番号が重なりうるため、
    欠番とし、理由が追えるよう「発行取消」のログを残す。
    修正・再発行の既存データには使わないこと（元の発行が失われる）。"""
    from app.services.operation_log_service import add_log
    label = "請求書" if issuance.doc_type == "invoice" else "領収書"
    iss_id, number = issuance.id, issuance.doc_number
    session.query(Payment).filter_by(issuance_id=iss_id).delete()
    session.delete(issuance)
    session.commit()
    add_log(session, "発行取消", "issuance", iss_id,
            f"{label} {number} 出力なしのため取消（欠番）")


def revert_to_prepared(session: Session, issuance: Issuance) -> None:
    """まとめて発行でメールを送らなかった書類を「準備中」に戻す。

    まとめて発行の書類は準備中の時点で番号が付いているので、戻しても欠番に
    ならず、次に発行するときにそのまま使われる。"""
    from app.services.operation_log_service import add_log
    label = "請求書" if issuance.doc_type == "invoice" else "領収書"
    issuance.status = "準備中"
    session.commit()
    add_log(session, "発行取消", "issuance", issuance.id,
            f"{label} {issuance.doc_number} メール未送信のため準備中に戻した")


PREVIEW_DOC_NUMBER = "（プレビュー）"


def build_preview_issuance(lines_data: list[dict], doc_type: str,
                           **fields) -> Issuance:
    """プレビュー用の発行データを作る。DB には記録せず、採番もしない。

    fields には Issuance の列（recipient_organization など）をそのまま渡す。
    戻り値はどのセッションにも属さない。永続化済みのオブジェクトを関連に
    つなぐとセッションへ巻き込まれるため、関連は明細（lines）だけにする。
    """
    total = sum(int(l["unit_price"]) * int(l["quantity"]) for l in lines_data)
    issuance = Issuance(
        doc_type=doc_type,
        doc_number=PREVIEW_DOC_NUMBER,
        amount=total,
        issued_at=datetime.now(),
        **fields,
    )
    issuance.lines = [
        IssuanceLine(
            item_template_id=ld.get("item_template_id"),
            item_name=ld["item_name"],
            quantity=ld["quantity"],
            unit=ld["unit"],
            unit_price=ld["unit_price"],
            tax_rate=ld["tax_rate"],
            line_total=int(ld["unit_price"]) * int(ld["quantity"]),
        )
        for ld in lines_data
    ]
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
                            recipient_email: str = "",
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
    issuance.recipient_email = recipient_email
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


def get_issuance(session: Session, issuance_id: int) -> Issuance | None:
    return session.get(Issuance, issuance_id)


def get_issuance_with_lines(session: Session,
                            issuance_id: int) -> Issuance | None:
    """明細を読み込んだ発行データを返す。PDF生成に使う。"""
    from sqlalchemy.orm import joinedload
    return (session.query(Issuance)
            .options(joinedload(Issuance.lines))
            .filter_by(id=issuance_id)
            .first())


def search_reissuable_issuances(
        session: Session, fiscal_year: int | None = None,
        project_id: int | None = None,
        doc_type: str | None = None) -> list[tuple[Issuance, Project]]:
    """再発行できる発行データを、名簿とあわせて新しい順に返す。

    対象は発行済みの書類と領収書。領収書は準備中でも控えを出せる。
    一覧に名簿名と名簿種別を出すため、Project を組にして返す。
    """
    from sqlalchemy import and_, or_
    q = (session.query(Issuance, Project)
         .join(Project, Issuance.project_id == Project.id)
         .filter(or_(
             Issuance.doc_type == "receipt",
             Issuance.status == "発行済み",
         )))
    if fiscal_year:
        # 年度は4月始まり。単発発行の集計用名簿は年度が当てにならないので
        # 発行日で判定する（_issuance_fiscal_year と同じ考え方）
        start = datetime(fiscal_year, 4, 1)
        end = datetime(fiscal_year + 1, 4, 1)
        q = q.filter(or_(
            and_(Project.project_type != "counter", Project.fiscal_year == fiscal_year),
            and_(Project.project_type == "counter",
                 Issuance.issued_at >= start, Issuance.issued_at < end),
        ))
    if project_id:
        q = q.filter(Issuance.project_id == project_id)
    if doc_type:
        q = q.filter(Issuance.doc_type == doc_type)
    return q.order_by(Issuance.issued_at.desc()).all()


def get_latest_issuance_for_member(session: Session, project_member_id: int,
                                   doc_type: str) -> Issuance | None:
    """名簿会員の、その種別で最も新しい発行データを返す。"""
    return (session.query(Issuance)
            .filter_by(project_member_id=project_member_id, doc_type=doc_type)
            .order_by(Issuance.created_at.desc())
            .first())


def get_all_issuances(session: Session,
                      status: str | None = None) -> list[Issuance]:
    """名簿を問わず発行データを新しい順に返す。入金管理の絞り込みなし表示用。"""
    q = session.query(Issuance)
    if status:
        q = q.filter(Issuance.status == status)
    return q.order_by(Issuance.created_at.desc()).all()


def get_project_issuances(session: Session, project_id: int,
                           status: str | None = None) -> list[Issuance]:
    q = session.query(Issuance).filter_by(project_id=project_id)
    if status:
        q = q.filter(Issuance.status == status)
    return q.order_by(Issuance.created_at.desc()).all()


def fiscal_year_of(d) -> int:
    """4月始まりの年度。2027年3月は2026年度。"""
    return d.year if d.month >= 4 else d.year - 1


def _issuance_fiscal_year(issuance: Issuance, project: Project | None) -> int | None:
    """書類の年度。まとめて発行は名簿の年度、単発発行は発行日で決める。

    単発発行の集計用名簿（project_type="counter"）は名前だけで使い回され、
    年度が最初に作った年のままなので、名簿の年度は当てにできない。"""
    if project is not None and project.project_type != "counter":
        return project.fiscal_year
    return fiscal_year_of(issuance.issued_at) if issuance.issued_at else None


def get_payment_issuances(session: Session, fiscal_year: int | None = None,
                          project_id: int | None = None,
                          status: str | None = None) -> list[Issuance]:
    """入金管理の一覧用。年度・名簿・状態で絞り込み、新しい順に返す。"""
    rows = (get_project_issuances(session, project_id, status)
            if project_id is not None else get_all_issuances(session, status))
    if fiscal_year is None:
        return rows
    projects = {p.id: p for p in session.query(Project).all()}
    return [i for i in rows
            if _issuance_fiscal_year(i, projects.get(i.project_id)) == fiscal_year]


def count_unpaid_invoices_before(session: Session, fiscal_year: int) -> int:
    """指定年度より前の未入金の請求書の件数（名簿でキャンセルになった人は除く）。

    入金管理を今年度で開いたときに、前年度以前の未入金を見落とさないために使う。"""
    projects = {p.id: p for p in session.query(Project).all()}
    cancelled = {pm_id for (pm_id,) in
                 session.query(ProjectMember.id).filter(ProjectMember.is_cancelled.is_(True))}
    count = 0
    for iss in (session.query(Issuance)
                .filter(Issuance.doc_type == "invoice", Issuance.status == "発行済み")):
        if iss.project_member_id in cancelled:
            continue
        fy = _issuance_fiscal_year(iss, projects.get(iss.project_id))
        if fy is not None and fy < fiscal_year:
            count += 1
    return count


def get_payment_fiscal_years(session: Session, today: date | None = None) -> list[int]:
    """入金管理の年度の選択肢（新しい順）。名簿・書類のある年度と今年度。"""
    projects = {p.id: p for p in session.query(Project).all()}
    years = {fiscal_year_of(today or date.today())}
    # まだ書類のない名簿の年度も選べるように（単発発行の集計用名簿は年度が当てにならない）
    years |= {p.fiscal_year for p in projects.values() if p.project_type != "counter"}
    for iss in session.query(Issuance):
        fy = _issuance_fiscal_year(iss, projects.get(iss.project_id))
        if fy is not None:
            years.add(fy)
    return sorted(years, reverse=True)


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
