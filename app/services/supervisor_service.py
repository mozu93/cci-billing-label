# app/services/supervisor_service.py
from sqlalchemy.orm import Session
from app.database.models import Supervisor


def create_supervisor(session: Session, name: str, email: str = "") -> Supervisor:
    sup = Supervisor(name=name, email=email)
    session.add(sup)
    session.commit()
    session.refresh(sup)
    return sup


def get_all_supervisors(session: Session) -> list[Supervisor]:
    return (session.query(Supervisor)
            .filter_by(is_active=True)
            .order_by(Supervisor.name)
            .all())


def update_supervisor(session: Session, supervisor_id: int,
                      name: str, email: str = "") -> Supervisor:
    sup = session.get(Supervisor, supervisor_id)
    sup.name = name
    sup.email = email
    session.commit()
    return sup


def deactivate_supervisor(session: Session, supervisor_id: int) -> None:
    sup = session.get(Supervisor, supervisor_id)
    if sup:
        sup.is_active = False
        session.commit()


def sync_supervisor_for_staff(session: Session, staff) -> None:
    """is_department_head フラグに連動して Supervisor レコードを自動同期する。

    所属長フラグON → 対応する Supervisor レコードを作成または有効化・更新。
    所属長フラグOFF → 対応する Supervisor レコードを無効化。
    """
    existing = (session.query(Supervisor)
                .filter_by(staff_id=staff.id)
                .first())
    if staff.is_department_head:
        if existing:
            existing.name     = staff.name
            existing.email    = staff.email or ""
            existing.is_active = True
        else:
            session.add(Supervisor(
                name=staff.name,
                email=staff.email or "",
                staff_id=staff.id,
            ))
    else:
        if existing:
            existing.is_active = False
    session.commit()
