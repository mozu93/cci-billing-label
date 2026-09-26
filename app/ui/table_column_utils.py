# app/ui/table_column_utils.py
from typing import Sequence

from PyQt6.QtWidgets import QTableWidget


def hide_empty_columns(table: QTableWidget, candidate_cols: Sequence[int]) -> None:
    """指定した列のうち、表示中の全行で値が空の列を非表示にする。

    ウィンドウ幅を無駄にしないよう、フリガナ・所属など任意項目の列は
    データが無ければ隠す。行が0件（絞り込みでたまたま空）のときは
    判断材料が無いため、列の表示状態を変えずそのままにする。
    """
    row_count = table.rowCount()
    if row_count == 0:
        return
    for col in candidate_cols:
        empty = all(
            not (table.item(r, col) and table.item(r, col).text().strip())
            for r in range(row_count)
        )
        table.setColumnHidden(col, empty)
