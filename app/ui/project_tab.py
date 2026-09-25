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
    get_projects, get_project_progress, get_project_by_id
)
from app.services.category_service import get_category_names
from app.services.issuance_service import fiscal_year_of
from app.services.report_service import get_project_amount_summary
from app.ui.project_form import ProjectFormDialog
from app.ui.project_member_panel import ProjectMemberPanel

_EMPTY_TEXT = ("この年度の名簿・請求内容はありません。\n"
               "「＋ 名簿・請求内容を作成」から、件名と請求内容を登録してください。")


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
        # 年度は4月始まり（入金管理とそろえる）。翌年度も選べるようにする
        current_year = fiscal_year_of(date.today())
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
        # 「完了」「年度更新」は廃止した。名簿は毎年新しく作り、年度で絞り込む
        btn_csv = QPushButton("CSV出力")
        btn_csv.clicked.connect(self._export_csv)
        btn_excel = QPushButton("Excel出力")
        btn_excel.clicked.connect(self._export_excel)
        top_row.addWidget(btn_add)
        top_row.addWidget(btn_edit)
        top_row.addStretch()
        # 出力は一覧全体への操作なので、右端にまとめて1行にする
        top_row.addWidget(btn_csv)
        top_row.addWidget(btn_excel)
        layout.addLayout(top_row)

        # 名簿の確認・編集が主作業になるため、下側を広く確保する。
        # 境界は利用者がドラッグして、案件一覧と名簿の高さを調整できる。
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        self._splitter = splitter

        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(
            ["業務名", "件名", "全件", "請求書発行済", "領収書発行済", "未発行", "総額", "入金件数", "入金額"])
        # 件名を伸縮列にすると、幅が足りないとき他の列に押されて20px程度に
        # つぶれ読めなかった。固定幅（ドラッグで変更可）にし、余りは最後の列が埋める。
        # 足りないときは横スクロールする
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(1, 180)
        hdr.setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setMinimumHeight(140)
        self._table.currentCellChanged.connect(self._on_select)
        # 上は件名ごとの集計、下は選んだ件名の名簿。見出しで区別する
        top_area = QWidget()
        top_layout = QVBoxLayout(top_area)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        top_title = QLabel("件名の一覧（発行・入金の状況）")
        top_title.setStyleSheet("font-weight: bold; color: #1D4ED8;")
        top_layout.addWidget(top_title)
        top_layout.addWidget(self._table)
        splitter.addWidget(top_area)

        self._member_panel_container = QWidget()
        from PyQt6.QtWidgets import QVBoxLayout as VL
        self._member_panel_layout = VL(self._member_panel_container)
        self._member_panel_container.setMinimumHeight(300)
        self._empty_label = QLabel(_EMPTY_TEXT)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: #64748B; font-size: 13px; padding: 24px;")
        self._member_panel_layout.addWidget(self._empty_label)
        splitter.addWidget(self._member_panel_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([180, 520])
        layout.addWidget(splitter)

    def _load(self):
        year = self._year_combo.currentData()
        session = get_session()
        try:
            cat_name = get_category_names(session)
            projects = get_projects(session, fiscal_year=year)
            self._table.setRowCount(0)
            self._export_rows = []
            for proj in projects:
                p = get_project_progress(session, proj.id)
                pending = p["pending"]
                amounts = get_project_amount_summary(session, proj.id)
                total_amount = amounts["total"]
                paid_count = amounts["paid_count"]
                paid_amount = amounts["paid"]
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
                self._empty_label.setText(_EMPTY_TEXT)
            self._empty_label.setVisible(True)
        finally:
            session.close()

    def _on_select(self, row, *_):
        if row < 0:
            return
        project_id = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            proj = get_project_by_id(session, project_id)
            project_type = proj.project_type if proj else "list"
        finally:
            session.close()
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
        session = get_session()
        try:
            p = get_project_progress(session, project_id)
            amounts = get_project_amount_summary(session, project_id)
            total_amount = amounts["total"]
            paid_count = amounts["paid_count"]
            paid_amount = amounts["paid"]
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
                    # 取り込んだ名簿を一覧の件数と名簿欄にすぐ反映する
                    self._refresh_project_row(dlg.created_project_id)
                    self._select_project(dlg.created_project_id)

    def _select_project(self, project_id: int):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == project_id:
                if row == self._table.currentRow():
                    # 同じ行を選び直しても選択変更が起きず名簿欄が更新されないため、
                    # 明示的に読み直す（取り込み直後に名簿が空のままに見えていた）
                    self._on_select(row)
                else:
                    self._table.setCurrentCell(row, 0)
                return

    def _edit(self):
        pid = self._selected_project_id()
        if pid is None:
            return
        dlg = ProjectFormDialog(project_id=pid, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
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
