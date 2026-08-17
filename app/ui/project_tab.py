# app/ui/project_tab.py
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QComboBox, QLabel, QHeaderView, QDialog, QSplitter,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from app.database.connection import get_session
from app.services.project_service import (
    get_projects, close_project, reopen_project,
    get_project_progress, get_project_by_id
)
from app.ui.project_form import ProjectFormDialog
from app.ui.project_member_panel import ProjectMemberPanel


class ProjectTab(QWidget):
    def __init__(self):
        super().__init__()
        self._export_rows: list[dict] = []
        self._build()
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

        btn_add = QPushButton("＋ 名簿・請求内容を作成")
        btn_add.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 4px 12px; }"
            "QPushButton:hover { background: #1D4ED8; }")
        btn_add.clicked.connect(self._add)
        btn_edit = QPushButton("編集")
        btn_edit.clicked.connect(self._edit)
        self._btn_close = QPushButton("完了")
        self._btn_close.clicked.connect(self._close)
        self._btn_reopen = QPushButton("完了を戻す")
        self._btn_reopen.clicked.connect(self._reopen)
        btn_rollover = QPushButton("年度更新")
        btn_rollover.clicked.connect(self._rollover)
        self._btn_close.setEnabled(False)
        self._btn_reopen.setEnabled(False)
        top_row.addWidget(btn_add)
        top_row.addWidget(btn_edit)
        top_row.addWidget(self._btn_close)
        top_row.addWidget(self._btn_reopen)
        top_row.addWidget(btn_rollover)
        top_row.addStretch()

        self._status_combo = QComboBox()
        self._status_combo.addItem("受付中", "active")
        self._status_combo.addItem("完了", "closed")
        self._status_combo.addItem("すべて", None)
        self._status_combo.setCurrentIndex(0)
        self._status_combo.currentIndexChanged.connect(self._load)
        top_row.addWidget(QLabel("状態："))
        top_row.addWidget(self._status_combo)
        layout.addLayout(top_row)

        export_row = QHBoxLayout()
        btn_csv = QPushButton("CSV出力")
        btn_csv.clicked.connect(self._export_csv)
        btn_excel = QPushButton("Excel出力")
        btn_excel.clicked.connect(self._export_excel)
        export_row.addWidget(btn_csv)
        export_row.addWidget(btn_excel)
        export_row.addStretch()
        layout.addLayout(export_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(
            ["業務名", "件名", "全件", "請求書発行済", "領収書発行済", "未発行", "総額", "入金件数", "入金額"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.currentCellChanged.connect(self._on_select)
        splitter.addWidget(self._table)

        self._member_panel_container = QWidget()
        from PyQt6.QtWidgets import QVBoxLayout as VL
        self._member_panel_layout = VL(self._member_panel_container)
        self._empty_label = QLabel(
            "受付中のデータはありません。\n"
            "「＋ 名簿・請求内容を作成」から、件名と請求内容を登録してください。")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: #64748B; font-size: 13px; padding: 24px;")
        self._member_panel_layout.addWidget(self._empty_label)
        splitter.addWidget(self._member_panel_container)
        splitter.setSizes([300, 300])
        layout.addWidget(splitter)

    def _load(self):
        year = self._year_combo.currentData()
        status = self._status_combo.currentData()
        session = get_session()
        try:
            from app.database.models import Category, Issuance, Payment
            cat_name = {c.id: c.name for c in session.query(Category).all()}
            projects = get_projects(session, fiscal_year=year, status=status)
            self._table.setRowCount(0)
            self._export_rows = []
            for proj in projects:
                p = get_project_progress(session, proj.id)
                pending = p["pending"]
                total_amount = sum(
                    int(iss.amount) for iss in
                    session.query(Issuance).filter_by(project_id=proj.id).all())
                payments = (session.query(Payment).join(
                        Issuance, Payment.issuance_id == Issuance.id
                    ).filter(Issuance.project_id == proj.id).all())
                paid_count = len(payments)
                paid_amount = sum(int(payment.amount) for payment in payments)
                row = self._table.rowCount()
                self._table.insertRow(row)
                for col, val in enumerate([
                    cat_name.get(proj.category_id, ""), proj.name,
                    str(p["total"]), str(p["invoice_issued"]),
                    str(p["receipt_issued"]), str(pending),
                    f"¥{total_amount:,}", str(paid_count), f"¥{paid_amount:,}",
                ]):
                    item = QTableWidgetItem(val)
                    item.setData(Qt.ItemDataRole.UserRole, proj.id)
                    if col == 5 and pending > 0:
                        item.setForeground(QColor("#DC2626"))
                    self._table.setItem(row, col, item)
                self._export_rows.append({
                    "業務名": cat_name.get(proj.category_id, ""),
                    "件名": proj.name,
                    "全件": p["total"],
                    "請求書発行済": p["invoice_issued"],
                    "領収書発行済": p["receipt_issued"],
                    "未発行": pending,
                    "総額": total_amount,
                    "入金件数": paid_count,
                    "入金額": paid_amount,
                })
            self._clear_member_panel()
            if projects:
                self._empty_label.setText(
                    "一覧からデータを選択すると、名簿の確認・取り込みができます。")
            else:
                self._empty_label.setText(
                    "受付中のデータはありません。\n"
                    "「＋ 名簿・請求内容を作成」から、件名と請求内容を登録してください。")
            self._empty_label.setVisible(True)
        finally:
            session.close()

    def _on_select(self, row, *_):
        if row < 0:
            self._btn_close.setEnabled(False)
            self._btn_reopen.setEnabled(False)
            return
        project_id = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            proj = get_project_by_id(session, project_id)
            project_type = proj.project_type if proj else "list"
            status = proj.status if proj else None
        finally:
            session.close()
        self._btn_close.setEnabled(status == "active")
        self._btn_reopen.setEnabled(status == "closed")
        self._clear_member_panel()
        self._empty_label.setVisible(False)
        if project_type == "list":
            panel = ProjectMemberPanel(project_id)
            panel.roster_changed.connect(
                lambda pid=project_id: self._refresh_project_row(pid))
            self._member_panel_layout.addWidget(panel)

    def _refresh_project_row(self, project_id: int):
        """名簿の増減を、一覧の該当行（件数・金額）だけに反映する。

        _load() だと選択が外れて名簿パネルが作り直されるため、行だけ更新する。
        """
        from app.database.models import Issuance, Payment
        session = get_session()
        try:
            p = get_project_progress(session, project_id)
            issuances = (session.query(Issuance)
                         .filter_by(project_id=project_id).all())
            total_amount = sum(int(i.amount) for i in issuances)
            payments = (session.query(Payment).join(
                    Issuance, Payment.issuance_id == Issuance.id
                ).filter(Issuance.project_id == project_id).all())
            paid_count = len(payments)
            paid_amount = sum(int(payment.amount) for payment in payments)
        finally:
            session.close()

        values = {
            2: str(p["total"]), 3: str(p["invoice_issued"]),
            4: str(p["receipt_issued"]), 5: str(p["pending"]),
            6: f"¥{total_amount:,}", 7: str(paid_count), 8: f"¥{paid_amount:,}",
        }
        for row in range(self._table.rowCount()):
            head = self._table.item(row, 0)
            if not head or head.data(Qt.ItemDataRole.UserRole) != project_id:
                continue
            for col, val in values.items():
                cell = self._table.item(row, col)
                if cell is None:
                    continue
                cell.setText(val)
                if col == 5:
                    cell.setData(
                        Qt.ItemDataRole.ForegroundRole,
                        QColor("#DC2626") if p["pending"] > 0 else None)
            if row < len(self._export_rows):
                self._export_rows[row].update({
                    "全件": p["total"],
                    "請求書発行済": p["invoice_issued"],
                    "領収書発行済": p["receipt_issued"],
                    "未発行": p["pending"],
                    "総額": total_amount,
                    "入金件数": paid_count,
                    "入金額": paid_amount,
                })
            break

    def _clear_member_panel(self):
        for i in reversed(range(self._member_panel_layout.count())):
            w = self._member_panel_layout.itemAt(i).widget()
            if w and w is not self._empty_label:
                self._member_panel_layout.removeWidget(w)
                w.deleteLater()

    def _selected_project_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        return self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _add(self):
        dlg = ProjectFormDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.saved_fiscal_year is not None:
                idx = self._year_combo.findData(dlg.saved_fiscal_year)
                if idx >= 0:
                    self._year_combo.blockSignals(True)
                    self._year_combo.setCurrentIndex(idx)
                    self._year_combo.blockSignals(False)
            self._load()
            if dlg.created_project_id is not None:
                self._select_project(dlg.created_project_id)
                from app.ui.roster_import import RosterImportDialog
                import_dlg = RosterImportDialog(dlg.created_project_id, self)
                if import_dlg.exec() == QDialog.DialogCode.Accepted:
                    self._select_project(dlg.created_project_id)

    def _select_project(self, project_id: int):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == project_id:
                self._table.setCurrentCell(row, 0)
                return

    def _edit(self):
        pid = self._selected_project_id()
        if pid is None:
            return
        dlg = ProjectFormDialog(project_id=pid, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _close(self):
        pid = self._selected_project_id()
        if pid is None:
            return
        session = get_session()
        try:
            close_project(session, pid)
        finally:
            session.close()
        self._load()

    def _reopen(self):
        pid = self._selected_project_id()
        if pid is None:
            return
        session = get_session()
        try:
            reopen_project(session, pid)
        finally:
            session.close()
        self._load()

    def _export_csv(self):
        if not self._export_rows:
            QMessageBox.information(self, "情報", "データがありません。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV保存", "", "CSV (*.csv)")
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(self._export_rows[0].keys()))
            writer.writeheader()
            writer.writerows(self._export_rows)
        QMessageBox.information(self, "完了", f"CSVを保存しました。\n{path}")

    def _export_excel(self):
        if not self._export_rows:
            QMessageBox.information(self, "情報", "データがありません。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Excel保存", "", "Excel (*.xlsx)")
        if not path:
            return
        from app.services.report_service import export_to_excel
        headers = list(self._export_rows[0].keys())
        try:
            export_to_excel(self._export_rows, headers, path)
            QMessageBox.information(self, "完了", f"Excelを保存しました。\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))

    def _rollover(self):
        from app.ui.fiscal_year_dialog import FiscalYearDialog
        dlg = FiscalYearDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()
