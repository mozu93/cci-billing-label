# app/ui/fiscal_year_dialog.py
from datetime import date
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QTableWidget, QTableWidgetItem, QCheckBox, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.fiscal_year_service import (
    get_rollover_candidates, rollover_fiscal_year
)
from app.services.project_service import get_project_members


class FiscalYearDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("年度更新")
        self.resize(700, 500)
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("更新元年度："))
        self._from_year = QSpinBox()
        self._from_year.setRange(2020, 2099)
        self._from_year.setValue(date.today().year)
        self._from_year.valueChanged.connect(self._load)
        top.addWidget(self._from_year)
        top.addWidget(QLabel("→　更新先年度："))
        self._to_year = QSpinBox()
        self._to_year.setRange(2020, 2099)
        self._to_year.setValue(date.today().year + 1)
        top.addWidget(self._to_year)
        top.addStretch()
        layout.addLayout(top)
        layout.addWidget(QLabel("引き継ぐ名簿にチェック、会員引き継ぎを選択してください。"))
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["選択", "名簿名", "会員引き継ぎ"])
        layout.addWidget(self._table)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_exec = QPushButton("年度更新を実行する")
        btn_exec.clicked.connect(self._execute)
        btn_row.addWidget(btn_exec)
        layout.addLayout(btn_row)

    def _load(self):
        from_year = self._from_year.value()
        session = get_session()
        try:
            candidates = get_rollover_candidates(session, from_year)
        finally:
            session.close()
        self._table.setRowCount(0)
        for proj in candidates:
            row = self._table.rowCount()
            self._table.insertRow(row)
            cb_select = QCheckBox()
            cb_select.setChecked(True)
            self._table.setCellWidget(row, 0, cb_select)
            self._table.setItem(row, 1, QTableWidgetItem(proj.name))
            cb_keep = QCheckBox()
            cb_keep.setChecked(proj.project_type == "list")
            self._table.setCellWidget(row, 2, cb_keep)
            self._table.item(row, 1).setData(Qt.ItemDataRole.UserRole, proj.id)

    def _execute(self):
        to_year = self._to_year.value()
        from_year = self._from_year.value()
        if to_year <= from_year:
            QMessageBox.warning(self, "エラー", "更新先年度は更新元年度より大きい値を指定してください。")
            return
        project_ids = []
        keep_members = {}
        for row in range(self._table.rowCount()):
            cb_select = self._table.cellWidget(row, 0)
            if not (cb_select and cb_select.isChecked()):
                continue
            proj_id = self._table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            cb_keep = self._table.cellWidget(row, 2)
            project_ids.append(proj_id)
            keep_members[proj_id] = cb_keep.isChecked() if cb_keep else False
        if not project_ids:
            QMessageBox.warning(self, "エラー", "引き継ぐ名簿を選択してください。")
            return
        session = get_session()
        try:
            new_projects = rollover_fiscal_year(
                session, from_year=from_year, to_year=to_year,
                project_ids=project_ids, keep_members=keep_members
            )
            QMessageBox.information(self, "完了",
                                    f"{len(new_projects)} 件の名簿を{to_year}年度にコピーしました。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
        finally:
            session.close()
        self.accept()
