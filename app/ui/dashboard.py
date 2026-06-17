# app/ui/dashboard.py
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from app.database.connection import get_session
from app.services.project_service import get_projects, get_project_progress


class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def showEvent(self, event):
        # 画面を開くたびに最新の内容を表示する（更新ボタン不要）
        super().showEvent(event)
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("年度："))
        self._year_combo = QComboBox()
        current_year = date.today().year
        for y in range(current_year + 1, current_year - 5, -1):
            self._year_combo.addItem(f"{y}年度", y)
        self._year_combo.setCurrentIndex(1)
        self._year_combo.currentIndexChanged.connect(self._load)
        top_row.addWidget(self._year_combo)
        btn_rollover = QPushButton("年度更新")
        btn_rollover.clicked.connect(self._rollover)
        top_row.addWidget(btn_rollover)
        top_row.addStretch()
        layout.addLayout(top_row)

        layout.addWidget(QLabel("■ 受付中の名簿"))
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["名簿名", "全件", "請求書発行済", "領収書発行済", "未発行"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)


    def _load(self):
        year = self._year_combo.currentData()
        session = get_session()
        try:
            active = get_projects(session, fiscal_year=year, status="active")

            self._table.setRowCount(0)
            for proj in active:
                p = get_project_progress(session, proj.id)
                row = self._table.rowCount()
                self._table.insertRow(row)
                pending = p["pending"]
                for col, val in enumerate([
                    proj.name,
                    str(p["total"]), str(p["invoice_issued"]),
                    str(p["receipt_issued"]), str(pending)
                ]):
                    item = QTableWidgetItem(val)
                    item.setData(Qt.ItemDataRole.UserRole, proj.id)
                    if col == 4 and pending > 0:
                        item.setForeground(QColor("#DC2626"))
                    self._table.setItem(row, col, item)
        finally:
            session.close()

    def _rollover(self):
        from app.ui.fiscal_year_dialog import FiscalYearDialog
        from PyQt6.QtWidgets import QDialog
        dlg = FiscalYearDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()
