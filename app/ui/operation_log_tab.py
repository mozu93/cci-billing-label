# app/ui/operation_log_tab.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QComboBox, QPushButton, QHeaderView, QDateEdit, QFileDialog,
    QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt, QDate
from app.database.connection import get_session
from app.database.models import OperationLog


_ACTIONS = ["すべて", "発行", "内容修正", "再発行", "入金記録", "メール送信", "メール送信失敗", "督促メール送信"]

_COLS = [
    ("日時",     180),
    ("担当者",    90),
    ("操作",      80),
    ("詳細",       0),  # stretch
]

_KEYS = ["日時", "担当者", "操作", "詳細"]


class OperationLogWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._rows: list[dict] = []
        self._build()

    def showEvent(self, event):
        super().showEvent(event)
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        # --- フィルタ行 ---
        top = QHBoxLayout()
        top.addWidget(QLabel("開始日："))
        self._from_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self._from_date.setCalendarPopup(True)
        self._from_date.dateChanged.connect(self._load)
        top.addWidget(self._from_date)

        top.addWidget(QLabel("終了日："))
        self._to_date = QDateEdit(QDate.currentDate())
        self._to_date.setCalendarPopup(True)
        self._to_date.dateChanged.connect(self._load)
        top.addWidget(self._to_date)

        top.addWidget(QLabel("操作："))
        self._action_combo = QComboBox()
        self._action_combo.addItems(_ACTIONS)
        self._action_combo.currentIndexChanged.connect(self._load)
        top.addWidget(self._action_combo)

        btn_csv = QPushButton("CSV出力")
        btn_csv.clicked.connect(self._export_csv)
        top.addWidget(btn_csv)
        top.addStretch()
        layout.addLayout(top)

        # --- 検索行 ---
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("検索："))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("担当者・操作・詳細でキーワードフィルタ")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._filter_table)
        search_row.addWidget(self._search_edit)
        layout.addLayout(search_row)

        # --- テーブル ---
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels([c[0] for c in _COLS])
        hdr = self._table.horizontalHeader()
        hdr.setSortIndicatorShown(True)
        for i, (_, w) in enumerate(_COLS):
            if w == 0:
                hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            else:
                hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
                self._table.setColumnWidth(i, w)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(self._count_lbl)

    def _load(self):
        from datetime import datetime
        fd = self._from_date.date()
        td = self._to_date.date()
        from_dt = datetime(fd.year(), fd.month(), fd.day(), 0, 0, 0)
        to_dt   = datetime(td.year(), td.month(), td.day(), 23, 59, 59)
        action  = self._action_combo.currentText()

        session = get_session()
        try:
            q = (session.query(OperationLog)
                 .filter(OperationLog.created_at >= from_dt)
                 .filter(OperationLog.created_at <= to_dt))
            if action != "すべて":
                q = q.filter(OperationLog.action == action)
            logs = q.order_by(OperationLog.created_at.desc()).all()
            self._rows = [
                {
                    "日時":   l.created_at.strftime("%Y/%m/%d %H:%M:%S"),
                    "担当者": l.staff_name or "",
                    "操作":   l.action,
                    "詳細":   l.detail or "",
                }
                for l in logs
            ]
        finally:
            session.close()

        self._filter_table()

    def _filter_table(self):
        keyword = self._search_edit.text().strip().lower()
        if keyword:
            rows = [r for r in self._rows if any(keyword in r[k].lower() for k in _KEYS)]
        else:
            rows = self._rows
        self._render(rows)

    def _render(self, rows: list[dict]):
        # ソート中に行挿入するとQtが毎行ソートして重くなるため一時無効化
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            for col, key in enumerate(_KEYS):
                self._table.setItem(r, col, QTableWidgetItem(row[key]))
        self._table.setSortingEnabled(True)
        self._count_lbl.setText(f"{len(rows)} 件")

    def _export_csv(self):
        keyword = self._search_edit.text().strip().lower()
        if keyword:
            rows = [r for r in self._rows if any(keyword in r[k].lower() for k in _KEYS)]
        else:
            rows = self._rows
        if not rows:
            QMessageBox.information(self, "情報", "データがありません。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV保存", "", "CSV (*.csv)")
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=_KEYS)
            writer.writeheader()
            writer.writerows(rows)
        QMessageBox.information(self, "完了", f"CSVを保存しました。\n{path}")
