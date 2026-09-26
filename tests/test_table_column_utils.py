# tests/test_table_column_utils.py
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from app.ui.table_column_utils import hide_empty_columns


def _table(rows: list[list[str]]) -> QTableWidget:
    cols = len(rows[0]) if rows else 0
    t = QTableWidget(len(rows), cols)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            t.setItem(r, c, QTableWidgetItem(val))
    return t


def test_hides_column_that_is_empty_in_every_row(qtbot):
    t = _table([["事業所A", ""], ["事業所B", ""]])
    qtbot.addWidget(t)
    hide_empty_columns(t, [0, 1])
    assert not t.isColumnHidden(0)
    assert t.isColumnHidden(1)


def test_keeps_column_visible_if_any_row_has_value(qtbot):
    t = _table([["事業所A", ""], ["事業所B", "ジギョウショB"]])
    qtbot.addWidget(t)
    hide_empty_columns(t, [0, 1])
    assert not t.isColumnHidden(1)


def test_does_nothing_when_table_has_no_rows(qtbot):
    t = QTableWidget(0, 2)
    qtbot.addWidget(t)
    t.setColumnHidden(1, False)
    hide_empty_columns(t, [0, 1])
    assert not t.isColumnHidden(1)   # 変化しない


def test_missing_item_counts_as_empty(qtbot):
    t = QTableWidget(2, 1)
    qtbot.addWidget(t)
    # 1行目だけ item を設定し、2行目は setItem していない
    t.setItem(0, 0, QTableWidgetItem(""))
    hide_empty_columns(t, [0])
    assert t.isColumnHidden(0)
