# app/services/item_template_service.py
from sqlalchemy.orm import Session
from app.database.models import ItemTemplate


def create_item_template(session: Session, category_id: int, name: str,
                          unit_price: int, unit: str, tax_rate: int,
                          doc_type: str, description: str) -> ItemTemplate:
    tmpl = ItemTemplate(
        category_id=category_id, name=name, unit_price=unit_price,
        unit=unit, tax_rate=tax_rate, doc_type=doc_type, description=description
    )
    session.add(tmpl)
    session.commit()
    session.refresh(tmpl)
    return tmpl


def get_templates_by_category(session: Session, category_id: int) -> list[ItemTemplate]:
    return (session.query(ItemTemplate)
            .filter_by(category_id=category_id, is_active=True)
            .order_by(ItemTemplate.name)
            .all())


def get_all_active_templates(session: Session) -> list[ItemTemplate]:
    from sqlalchemy.orm import joinedload
    return (session.query(ItemTemplate)
            .options(joinedload(ItemTemplate.category))
            .filter_by(is_active=True)
            .order_by(ItemTemplate.category_id, ItemTemplate.name)
            .all())


def update_item_template(session: Session, template_id: int, **kwargs) -> ItemTemplate:
    tmpl = session.get(ItemTemplate, template_id)
    for key, value in kwargs.items():
        setattr(tmpl, key, value)
    session.commit()
    return tmpl


def deactivate_item_template(session: Session, template_id: int) -> None:
    tmpl = session.get(ItemTemplate, template_id)
    if tmpl:
        tmpl.is_active = False
        session.commit()
