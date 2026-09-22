# tests/test_category_service.py
from app.services.category_service import (
    create_category, get_active_categories, deactivate_category
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


def test_get_category(db_session):
    from app.services.category_service import get_category

    cat = create_category(db_session, "青年部", sort_order=3)
    found = get_category(db_session, cat.id)
    assert found.name == "青年部"
    assert found.sort_order == 3


def test_get_category_returns_none_when_missing(db_session):
    from app.services.category_service import get_category

    assert get_category(db_session, 9999) is None


def test_get_category_names_includes_inactive(db_session):
    """過去データの表示に使うため、無効化済みの業務名も含める。"""
    from app.services.category_service import (
        get_category_names, deactivate_category)

    active = create_category(db_session, "青年部")
    retired = create_category(db_session, "旧部会")
    deactivate_category(db_session, retired.id)

    names = get_category_names(db_session)
    assert names[active.id] == "青年部"
    assert names[retired.id] == "旧部会"
