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
