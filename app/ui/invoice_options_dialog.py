# app/ui/invoice_options_dialog.py
import calendar
from datetime import date
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QDateEdit, QPushButton, QLabel, QCheckBox
)
from PyQt6.QtCore import QDate


def _next_month_end(from_date=None) -> date:
    """指定日（省略時は今日）の翌月末を返す。"""
    d = from_date or date.today()
    if hasattr(d, "date"):
        d = d.date()
    y, m = (d.year, d.month + 1) if d.month < 12 else (d.year + 1, 1)
    return date(y, m, calendar.monthrange(y, m)[1])


class InvoiceOptionsDialog(QDialog):
    """請求書PDF生成前に支払期限と出力オプションを確認するダイアログ。"""

    def __init__(self, issued_at=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("請求書の発行オプション")
        self.setFixedSize(320, 160)

        from app.utils.app_config import get_config
        _cfg = get_config()

        default = _next_month_end(issued_at)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._due = QDateEdit(QDate(default.year, default.month, default.day))
        self._due.setCalendarPopup(True)
        self._due.setDisplayFormat("yyyy/MM/dd")
        form.addRow("支払期限", self._due)

        self._window_envelope = QCheckBox("窓あき封筒モード（宛先に住所を印字する）")
        self._window_envelope.setChecked(_cfg.get("window_envelope_last", False))
        form.addRow(self._window_envelope)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("発行")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def due_date(self) -> date:
        qd = self._due.date()
        return date(qd.year(), qd.month(), qd.day())

    def window_envelope(self) -> bool:
        checked = self._window_envelope.isChecked()
        from app.utils.app_config import get_config, save_config
        cfg = get_config()
        cfg["window_envelope_last"] = checked
        save_config(cfg)
        return checked
