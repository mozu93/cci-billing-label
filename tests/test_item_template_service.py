# tests/test_item_template_service.py
from app.services.category_service import create_category
from app.services.item_template_service import (
    create_item_template, get_templates_by_category, get_all_active_templates,
    deactivate_item_template
)


def test_create_template(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(
        db_session, category_id=cat.id, name="青年部会費",
        unit_price=10000, unit="式", tax_rate=0, doc_type="invoice", description=""
    )
    assert tmpl.id is not None
    assert tmpl.unit_price == 10000


def test_get_templates_by_category(db_session):
    cat1 = create_category(db_session, "青年部")
    cat2 = create_category(db_session, "検定")
    create_item_template(db_session, cat1.id, "青年部会費", 10000, "式", 0, "invoice", "")
    create_item_template(db_session, cat2.id, "珠算検定受験料", 3000, "人", 0, "receipt", "珠算検定受験料として")
    result = get_templates_by_category(db_session, cat1.id)
    assert len(result) == 1
    assert result[0].name == "青年部会費"


def test_deactivate_template(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費", 10000, "式", 0, "invoice", "")
    deactivate_item_template(db_session, tmpl.id)
    assert get_all_active_templates(db_session) == []


def test_get_template_detached_is_usable_after_close(db_session):
    """編集ダイアログへ渡すため、セッションから切り離して返す。"""
    from sqlalchemy import inspect
    from app.services.item_template_service import get_template_detached

    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    detached = get_template_detached(db_session, tmpl.id)
    assert detached is not None
    assert inspect(detached).detached is True
    # 切り離した後も、読み込み済みの値は参照できる。
    assert detached.name == "青年部会費"
    assert detached.unit_price == 10000


def test_get_template_detached_returns_none_when_missing(db_session):
    from app.services.item_template_service import get_template_detached

    assert get_template_detached(db_session, 9999) is None


def test_get_item_template(db_session):
    from app.services.item_template_service import get_item_template

    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    found = get_item_template(db_session, tmpl.id)
    assert found is not None
    assert found.name == "青年部会費"
    assert get_item_template(db_session, 9999) is None


def test_find_active_template_by_name(db_session):
    """名前で有効なテンプレートを探す。無効化済みは対象外。"""
    from app.services.item_template_service import find_active_template_by_name

    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    assert find_active_template_by_name(db_session, "青年部会費").id == tmpl.id
    assert find_active_template_by_name(db_session, "存在しない項目") is None

    deactivate_item_template(db_session, tmpl.id)
    assert find_active_template_by_name(db_session, "青年部会費") is None
