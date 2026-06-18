# app/services/project_service.py
from sqlalchemy.orm import Session
from app.database.models import Project, ProjectTemplate, ProjectMember, Issuance


def create_project(session: Session, name: str, category_id: int,
                   fiscal_year: int, project_type: str,
                   notes: str = "",
                   company_settings_id: int | None = None,
                   bank_account_id: int | None = None,
                   seal_image_id: int | None = None) -> Project:
    proj = Project(
        name=name, category_id=category_id,
        fiscal_year=fiscal_year, project_type=project_type,
        status="active", notes=notes,
        company_settings_id=company_settings_id,
        bank_account_id=bank_account_id,
        seal_image_id=seal_image_id,
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return proj


def get_projects(session: Session, fiscal_year: int | None = None,
                 status: str | None = None) -> list[Project]:
    q = session.query(Project).filter(Project.project_type != "counter")
    if fiscal_year is not None:
        q = q.filter(Project.fiscal_year == fiscal_year)
    if status is not None:
        q = q.filter(Project.status == status)
    return q.order_by(Project.name).all()


def get_project_by_id(session: Session, project_id: int) -> Project | None:
    return session.get(Project, project_id)


def reopen_project(session: Session, project_id: int) -> None:
    proj = session.get(Project, project_id)
    if proj:
        proj.status = "active"
        session.commit()


def close_project(session: Session, project_id: int) -> None:
    proj = session.get(Project, project_id)
    if proj:
        proj.status = "closed"
        session.commit()


def add_template_to_project(session: Session, project_id: int,
                             template_id: int,
                             unit_price_override: int | None = None,
                             tax_rate_override: int | None = None,
                             sort_order: int = 0,
                             default_quantity: int = 1) -> ProjectTemplate:
    pt = ProjectTemplate(
        project_id=project_id,
        item_template_id=template_id,
        sort_order=sort_order,
        unit_price_override=unit_price_override,
        tax_rate_override=tax_rate_override,
        default_quantity=default_quantity,
    )
    session.add(pt)
    session.commit()
    return pt


def remove_template_from_project(session: Session, project_id: int,
                                  template_id: int) -> None:
    pt = (session.query(ProjectTemplate)
          .filter_by(project_id=project_id, item_template_id=template_id)
          .first())
    if pt:
        session.delete(pt)
        session.commit()


def get_project_templates(session: Session, project_id: int) -> list[ProjectTemplate]:
    from sqlalchemy.orm import joinedload
    return (session.query(ProjectTemplate)
            .options(joinedload(ProjectTemplate.item_template))
            .filter_by(project_id=project_id)
            .order_by(ProjectTemplate.sort_order)
            .all())


def add_roster_entries(session: Session, project_id: int,
                       entries: list[dict]) -> list[ProjectMember]:
    base = session.query(ProjectMember).filter_by(project_id=project_id).count()
    pms = []
    for i, e in enumerate(entries):
        pm = ProjectMember(
            project_id=project_id,
            member_number=e.get("member_number", ""),
            organization_name=e.get("organization_name", ""),
            organization_kana=e.get("organization_kana", ""),
            representative_name=e.get("representative_name", ""),
            representative_kana=e.get("representative_kana", ""),
            department=e.get("department", ""),
            postal_code=e.get("postal_code", ""),
            address=e.get("address", ""),
            address2=e.get("address2", ""),
            phone=e.get("phone", ""),
            email=e.get("email", ""),
            notes=e.get("notes", ""),
            sort_order=base + i,
        )
        session.add(pm)
        pms.append(pm)
    session.commit()
    return pms


def copy_roster_from_project(session: Session, src_project_id: int,
                             dst_project_id: int) -> list[ProjectMember]:
    src = get_project_members(session, src_project_id)
    entries = [{
        "member_number": p.member_number,
        "organization_name": p.organization_name,
        "organization_kana": p.organization_kana,
        "representative_name": p.representative_name,
        "representative_kana": p.representative_kana,
        "department": p.department,
        "postal_code": p.postal_code,
        "address": p.address,
        "address2": p.address2,
        "phone": p.phone,
        "email": p.email,
        "notes": p.notes,
    } for p in src]
    return add_roster_entries(session, dst_project_id, entries)


def get_project_members(session: Session, project_id: int,
                        newest_first: bool = False) -> list[ProjectMember]:
    q = session.query(ProjectMember).filter_by(project_id=project_id)
    if newest_first:
        return q.order_by(ProjectMember.created_at.desc()).all()
    return q.order_by(ProjectMember.sort_order).all()


def remove_member_from_project(session: Session, project_member_id: int) -> None:
    pm = session.get(ProjectMember, project_member_id)
    if pm:
        session.delete(pm)
        session.commit()


def get_project_progress(session: Session, project_id: int) -> dict:
    members = get_project_members(session, project_id)
    total = len(members)
    pm_ids = [pm.id for pm in members]
    if not pm_ids:
        # 会員名簿を持たない（窓口/フリー発行など）プロジェクトは発行単位で集計
        rows = session.query(Issuance.doc_type, Issuance.status)\
            .filter(Issuance.project_id == project_id).all()
        total = len(rows)
        invoice_issued = sum(1 for dt, s in rows
                             if dt == "invoice" and s in ("発行済み", "支払済み"))
        receipt_issued = sum(1 for dt, s in rows
                             if dt == "receipt" and s in ("発行済み", "支払済み"))
        issued = sum(1 for _, s in rows if s in ("発行済み", "支払済み"))
        paid = sum(1 for _, s in rows if s == "支払済み")
        return {"total": total, "issued": issued, "paid": paid,
                "invoice_issued": invoice_issued, "receipt_issued": receipt_issued,
                "pending": total - issued}

    # 各会員について領収書・請求書の発行状況を判定
    issued_rows = session.query(Issuance.project_member_id, Issuance.doc_type)\
        .filter(
            Issuance.project_member_id.in_(pm_ids),
            Issuance.status.in_(["発行済み", "支払済み"])
        ).all()

    paid_pms = set(
        row[0] for row in
        session.query(Issuance.project_member_id)
        .filter(
            Issuance.project_member_id.in_(pm_ids),
            Issuance.status == "支払済み"
        ).all()
    )

    pm_has_receipt = set()
    pm_has_invoice = set()
    for pm_id, doc_type in issued_rows:
        if doc_type == "receipt":
            pm_has_receipt.add(pm_id)
        elif doc_type == "invoice":
            pm_has_invoice.add(pm_id)

    receipt_issued = len(pm_has_receipt)
    # 請求書のみ（領収書未発行）の会員
    invoice_only = pm_has_invoice - pm_has_receipt
    invoice_issued = len(invoice_only)
    issued = len(pm_has_invoice | pm_has_receipt)
    paid = len(paid_pms)
    return {"total": total, "issued": issued, "paid": paid,
            "invoice_issued": invoice_issued, "receipt_issued": receipt_issued,
            "pending": total - issued}
