# tests/test_counter_item_combo_label.py
"""項目コンボの表示は品目名だけにする。

単価と単位は隣の入力欄に出ているので、コンボに重ねると重複するうえ、
狭い幅では品目名が見切れて読めなくなる。
"""


def _mk_templates(session):
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    cat_a = create_category(session, "その他")
    cat_b = create_category(session, "青年部")
    t1 = create_item_template(session, cat_a.id, "情報部会参加費",
                              1000, "式", 0, "both", "")
    t2 = create_item_template(session, cat_b.id, "青年部会費",
                              10000, "式", 0, "both", "")
    return cat_a, t1, t2


def test_item_combo_shows_name_without_price(qtbot, memory_db):
    """業務名で絞ったときは、品目名だけを出す。"""
    from app.database.connection import get_session
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    cat_a, t1, t2 = _mk_templates(s)
    cat_a_id, t1_id = cat_a.id, t1.id
    s.close()

    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    w._reload_master()
    row = w._rows[0]
    for i in range(row.cat_combo.count()):
        if row.cat_combo.itemData(i) == cat_a_id:
            row.cat_combo.setCurrentIndex(i)
            break

    labels = [row.tmpl_combo.itemText(i)
              for i in range(row.tmpl_combo.count())
              if row.tmpl_combo.itemData(i) == t1_id]
    assert labels == ["情報部会参加費"]


def test_item_combo_keeps_category_when_unfiltered(qtbot, memory_db):
    """業務名を絞っていないときは、どの業務のものか分かるよう業務名を添える。"""
    from app.database.connection import get_session
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    cat_a, t1, t2 = _mk_templates(s)
    t1_id = t1.id
    s.close()

    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    w._reload_master()
    row = w._rows[0]
    w._refresh_tmpl_combo(row)

    labels = [row.tmpl_combo.itemText(i)
              for i in range(row.tmpl_combo.count())
              if row.tmpl_combo.itemData(i) == t1_id]
    assert labels == ["情報部会参加費（その他）"]


def test_selected_item_text_is_readable_at_base_width(qtbot, memory_db):
    """基準幅780pxで、選んだ品目名が項目欄に収まる。"""
    from PyQt6.QtGui import QFontMetrics
    from app.database.connection import get_session
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    cat_a, t1, t2 = _mk_templates(s)
    cat_a_id, t1_id = cat_a.id, t1.id
    s.close()

    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    w.resize(780, 600)
    w.show()
    w._reload_master()
    row = w._rows[0]
    for i in range(row.cat_combo.count()):
        if row.cat_combo.itemData(i) == cat_a_id:
            row.cat_combo.setCurrentIndex(i)
            break
    for i in range(row.tmpl_combo.count()):
        if row.tmpl_combo.itemData(i) == t1_id:
            row.tmpl_combo.setCurrentIndex(i)
            break

    text = row.tmpl_combo.currentText()
    needed = QFontMetrics(row.tmpl_combo.font()).horizontalAdvance(text)
    # 矢印ボタンと内側の余白ぶんを引いた、文字を出せる幅。
    usable = row.tmpl_combo.width() - 34
    assert needed <= usable, (
        f"項目欄に収まらない: 必要 {needed}px / 使える {usable}px / {text!r}")
