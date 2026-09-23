# tests/test_counter_unit_field.py
"""単発発行の発行項目に単位を入力・修正できる。

これまで単位はテンプレートの値（直接入力なら「式」固定）で、画面から
直せなかった。名簿側の編集画面には単位欄があり、扱いが揃っていなかった。
"""


def _mk_template(session, unit: str):
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    cat = create_category(session, "その他")
    return create_item_template(session, cat.id, "情報部会参加費",
                                1000, unit, 0, "both", "")


def test_unit_defaults_to_shiki_for_direct_input(qtbot, memory_db):
    """直接入力の行は、従来どおり「式」で始まる。"""
    from app.ui.issuance_counter import IssuanceCounterWidget

    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    assert w._rows[0].unit() == "式"


def test_selecting_template_fills_its_unit(qtbot, memory_db):
    """テンプレートを選ぶと、その単位が入る。"""
    from app.database.connection import get_session
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    tmpl = _mk_template(s, "人")
    tmpl_id = tmpl.id
    s.close()

    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    w._reload_master()
    row = w._rows[0]
    w._refresh_tmpl_combo(row)
    for i in range(row.tmpl_combo.count()):
        if row.tmpl_combo.itemData(i) == tmpl_id:
            row.tmpl_combo.setCurrentIndex(i)
            break
    assert row.unit() == "人"


def test_edited_unit_is_used_instead_of_template(qtbot, memory_db):
    """画面で直した単位が、テンプレートの単位より優先される。"""
    from app.database.connection import get_session
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    tmpl = _mk_template(s, "式")
    tmpl_id = tmpl.id
    s.close()

    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    w._reload_master()
    row = w._rows[0]
    w._refresh_tmpl_combo(row)
    for i in range(row.tmpl_combo.count()):
        if row.tmpl_combo.itemData(i) == tmpl_id:
            row.tmpl_combo.setCurrentIndex(i)
            break
    row.unit_edit.setText("名")

    lines = w._collect_lines_data()
    assert len(lines) == 1
    assert lines[0]["unit"] == "名"


def test_edit_mode_restores_saved_unit(qtbot, memory_db):
    """内容修正で開くと、保存済みの単位が復元される。"""
    from app.database.connection import get_session
    from app.services.issuance_service import create_direct_issuance
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    iss = create_direct_issuance(
        s, lines_data=[{"item_template_id": None, "item_name": "会費",
                        "quantity": 1, "unit": "名", "unit_price": 5000,
                        "tax_rate": 0}],
        recipient_organization="○○商事", recipient_name="",
        doc_type="invoice", fiscal_year=2026, month=6)
    iss_id = iss.id
    s.close()

    w = IssuanceCounterWidget("invoice", edit_issuance_id=iss_id)
    qtbot.addWidget(w)
    w._reload_master()
    w._load_edit_data()

    assert w._rows[0].unit() == "名"
