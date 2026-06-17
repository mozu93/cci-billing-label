# app/services/category_service.py
from sqlalchemy.orm import Session
from app.database.models import Category


def create_category(session: Session, name: str, sort_order: int = 0) -> Category:
    cat = Category(name=name, sort_order=sort_order)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat


def get_active_categories(session: Session) -> list[Category]:
    return (session.query(Category)
            .filter_by(is_active=True)
            .order_by(Category.sort_order, Category.name)
            .all())


def update_category(session: Session, category_id: int,
                    name: str, sort_order: int) -> Category:
    cat = session.get(Category, category_id)
    cat.name = name
    cat.sort_order = sort_order
    session.commit()
    return cat


def deactivate_category(session: Session, category_id: int) -> None:
    cat = session.get(Category, category_id)
    if cat:
        cat.is_active = False
        session.commit()
