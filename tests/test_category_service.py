# tests/test_category_service.py
from app.services.category_service import (
    create_category, get_active_categories, update_category, deactivate_category
)


def test_create_category(db_session):
    cat = create_category(db_session, "青年部", sort_order=0)
    assert cat.id is not None
    assert cat.name == "青年部"


def test_get_active_categories_sorted(db_session):
    create_category(db_session, "青年部", sort_order=1)
    create_category(db_session, "女性部", sort_order=0)
    cats = get_active_categories(db_session)
    assert cats[0].name == "女性部"
    assert cats[1].name == "青年部"


def test_deactivate_category(db_session):
    cat = create_category(db_session, "青年部")
    deactivate_category(db_session, cat.id)
    assert get_active_categories(db_session) == []
