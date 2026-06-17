# app/services/fiscal_year_service.py
from sqlalchemy.orm import Session
from app.database.models import Project
from app.services.project_service import (
    get_project_by_id, get_project_templates, get_project_members,
    add_template_to_project, copy_roster_from_project
)


def rollover_fiscal_year(session: Session,
                          from_year: int, to_year: int,
                          project_ids: list[int],
                          keep_members: dict[int, bool]) -> list[Project]:
    new_projects = []
    for pid in project_ids:
        old_proj = get_project_by_id(session, pid)
        if not old_proj or old_proj.fiscal_year != from_year:
            continue

        new_name = old_proj.name.replace(f"{from_year}年度", f"{to_year}年度")
        if new_name == old_proj.name:
            new_name = f"{to_year}年度 {old_proj.name}"

        new_proj = Project(
            name=new_name,
            category_id=old_proj.category_id,
            fiscal_year=to_year,
            project_type=old_proj.project_type,
            status="active",
            notes=old_proj.notes or "",
        )
        session.add(new_proj)
        session.flush()

        for pt in get_project_templates(session, pid):
            add_template_to_project(
                session, new_proj.id,
                pt.item_template_id,
                unit_price_override=int(pt.unit_price_override) if pt.unit_price_override else None,
                sort_order=pt.sort_order
            )

        if keep_members.get(pid, True):
            copy_roster_from_project(session, pid, new_proj.id)

        new_projects.append(new_proj)

    session.commit()
    return new_projects


def get_rollover_candidates(session: Session, fiscal_year: int) -> list[Project]:
    return (session.query(Project)
            .filter(Project.fiscal_year == fiscal_year,
                    Project.status.in_(["active", "closed"]))
            .order_by(Project.name)
            .all())
