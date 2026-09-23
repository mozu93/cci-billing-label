# tests/test_counter_line_layout.py
"""発行項目のヘッダーと行の列揃え。

ヘッダーと行は別々の QHBoxLayout で組まれており、同じ幅になることを
前提にしている。ヘッダーは QLabel、行は QComboBox などで最小幅が違うため、
ウィンドウが狭いと縮み方が食い違って列がズレていた。
"""
import pytest
from PyQt6.QtWidgets import QLabel


def _header_and_row_geometry(w):
    """ヘッダーと1行目の、各列の (x, width) を返す。"""
    hdr = None
    for child in w.findChildren(QLabel):
        if child.text() == "業務名":
            hdr = child.parent()
            break
    assert hdr is not None, "ヘッダーが見つからない"

    def cols(layout):
        out = []
        for i in range(layout.count()):
            item = layout.itemAt(i).widget()
            if item is not None:
                out.append((item.x(), item.width()))
        return out

    return cols(hdr.layout()), cols(w._rows[0].layout())


@pytest.mark.parametrize("width", [1000, 850, 780, 700])
def test_columns_align_at_narrow_widths(qtbot, memory_db, width):
    """1366x768 基準の幅でも、ヘッダーと行の列が一致する。"""
    from app.ui.issuance_counter import IssuanceCounterWidget

    w = IssuanceCounterWidget(doc_type="invoice")
    qtbot.addWidget(w)
    w.resize(width, 600)
    w.show()

    header_cols, row_cols = _header_and_row_geometry(w)
    assert len(header_cols) == len(row_cols), "ヘッダーと行で列数が違う"
    assert header_cols == row_cols
