# app/ui/project_member_panel.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QMessageBox, QDialog,
    QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QStyledItemDelegate, QCheckBox
)
from PyQt6.QtCore import Qt, QEvent
from app.database.connection import get_session
from app.database.models import ProjectMember
from app.services.project_service import (
    get_project_members, add_roster_entries, remove_member_from_project,
    copy_roster_from_project, get_projects
)

COL_CHK = 0  # チェックボックス列


class _CompactDelegate(QStyledItemDelegate):
    """インライン編集エディタのジオメトリをセル矩形に固定する。"""

    def createEditor(self, parent, option, index):
        if index.column() == COL_CHK:
            return None
        editor = super().createEditor(parent, option, index)
        if editor is not None:
            editor.setStyleSheet(
                "QLineEdit { min-height: 0; padding: 1px 6px; "
                "border: 1.5px solid #3B82F6; border-radius: 3px; }"
            )
        return editor

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def eventFilter(self, editor, event):
        if (event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self.commitData.emit(editor)
            self.closeEditor.emit(
                editor, QStyledItemDelegate.EndEditHint.NoHint)
            view = self.parent()
            if view is not None:
                cur = view.currentIndex()
                nxt = cur.sibling(cur.row() + 1, cur.column())
                if nxt.isValid():
                    view.setCurrentIndex(nxt)
                    view.edit(nxt)
            return True
        return super().eventFilter(editor, event)


# col 0 = チェックボックス（None=編集不可）、以降は元の順
_COL_FIELDS = [
    None,            # チェックボックス
    "member_number", "organization_name", "organization_kana",
    "representative_name", "representative_kana", "department",
    "postal_code", "address", "address2", "phone", "email",
    None,            # 登録日
]

COLS = [
    ("",             28),
    ("会員番号",       80),
    ("事業所名",      180),
    ("フリガナ",      160),
    ("氏名",          100),
    ("氏名フリガナ",  130),
    ("所属・役職名",  120),
    ("郵便番号",       80),
    ("住所１",        200),
    ("住所２",        140),
    ("電話",          110),
    ("メール",        180),
    ("登録日",         90),
]


class RosterEntryDialog(QDialog):
    """名簿の1エントリ入力ダイアログ"""

    FIELDS = [
        ("member_number",        "会員番号"),
        ("organization_name",    "事業所名"),
        ("organization_kana",    "フリガナ（事業所）"),
        ("representative_name",  "氏名"),
        ("representative_kana",  "氏名フリガナ"),
        ("department",           "所属・役職名"),
        ("postal_code",          "郵便番号"),
        ("address",              "住所１"),
        ("address2",             "住所２"),
        ("phone",                "電話"),
        ("email",                "メール"),
    ]

    def __init__(self, parent=None, initial: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("名簿エントリ")
        self.resize(420, 300)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._fields: dict[str, QLineEdit] = {}
        for key, label in self.FIELDS:
            le = QLineEdit()
            if initial and key in initial:
                le.setText(initial[key] or "")
            self._fields[key] = le
            form.addRow(label + ":", le)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setText("保存")
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("キャンセル")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self):
        org = self._fields["organization_name"].text().strip()
        rep = self._fields["representative_name"].text().strip()
        if not org and not rep:
            QMessageBox.warning(
                self, "入力エラー",
                "事業所名または代表者名のいずれかを入力してください。"
            )
            return
        self.accept()

    def values(self) -> dict:
        return {key: self._fields[key].text() for key, _ in self.FIELDS}


class ProjectCopyDialog(QDialog):
    """他の名簿からコピーするダイアログ"""

    def __init__(self, current_project_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("他の名簿からコピー")
        self.resize(360, 120)
        self._selected_id: int | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("コピー元の名簿を選択してください："))

        self._combo = QComboBox()
        session = get_session()
        try:
            projects = get_projects(session)
        finally:
            session.close()
        for p in projects:
            if p.id == current_project_id:
                continue
            label = f"{p.fiscal_year}年度 {p.name}"
            self._combo.addItem(label, p.id)
        layout.addWidget(self._combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("コピー")
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_project_id(self) -> int | None:
        return self._combo.currentData()


class ProjectMemberPanel(QWidget):
    def __init__(self, project_id: int):
        super().__init__()
        self._project_id = project_id
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("名簿"))

        btn_row = QHBoxLayout()
        btn_add = QPushButton("行を追加")
        btn_add.clicked.connect(self._add_entry)
        btn_edit = QPushButton("編集")
        btn_edit.clicked.connect(self._edit_entry)
        btn_copy = QPushButton("他の名簿からコピー")
        btn_copy.clicked.connect(self._copy_from_project)
        btn_import = QPushButton("取り込み（Excel/貼り付け）")
        btn_import.clicked.connect(self._open_import)
        self._btn_del = QPushButton("選択削除")
        self._btn_del.clicked.connect(self._remove_checked)
        for b in [btn_add, btn_edit, btn_copy, btn_import, self._btn_del]:
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._table = QTableWidget(0, len(COLS))
        self._table.setHorizontalHeaderLabels([c[0] for c in COLS])
        hdr = self._table.horizontalHeader()
        for i, (_, w) in enumerate(COLS):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            self._table.setColumnWidth(i, w)
        self._table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        vhdr = self._table.verticalHeader()
        vhdr.setDefaultSectionSize(26)
        vhdr.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self._table.setItemDelegate(_CompactDelegate(self._table))
        self._table.setSortingEnabled(True)
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table)
        self._count_label = QLabel("")
        layout.addWidget(self._count_label)

        # ヘッダーチェックボックス（全選択／全解除）
        self._header_chk = QCheckBox(self._table.horizontalHeader())
        self._header_chk.setToolTip("全選択 / 全解除")
        self._header_chk.toggled.connect(self._on_header_chk_toggled)
        hdr.sectionResized.connect(lambda *_: self._reposition_header_chk())
        self._reposition_header_chk()

    def _reposition_header_chk(self):
        hdr = self._table.horizontalHeader()
        x = hdr.sectionPosition(COL_CHK)
        w = hdr.sectionSize(COL_CHK)
        h = hdr.height()
        cb_w = self._header_chk.sizeHint().width()
        cb_h = self._header_chk.sizeHint().height()
        self._header_chk.move(x + (w - cb_w) // 2, (h - cb_h) // 2)
        self._header_chk.raise_()

    def _on_header_chk_toggled(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._table.blockSignals(True)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_CHK)
            if item:
                item.setCheckState(state)
        self._table.blockSignals(False)

    def _load(self):
        session = get_session()
        try:
            pms = get_project_members(session, self._project_id, newest_first=True)
        finally:
            session.close()
        self._table.blockSignals(True)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        self._header_chk.blockSignals(True)
        self._header_chk.setChecked(False)
        self._header_chk.blockSignals(False)

        for pm in pms:
            row = self._table.rowCount()
            self._table.insertRow(row)
            reg = pm.created_at.strftime("%Y/%m/%d") if pm.created_at else ""
            vals = [
                pm.member_number or "",
                pm.organization_name or "",
                pm.organization_kana or "",
                pm.representative_name or "",
                pm.representative_kana or "",
                pm.department or "",
                pm.postal_code or "",
                pm.address or "",
                pm.address2 or "",
                pm.phone or "",
                pm.email or "",
                reg,
            ]

            # チェックボックス列
            chk_item = QTableWidgetItem()
            chk_item.setData(Qt.ItemDataRole.UserRole, pm.id)
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(row, COL_CHK, chk_item)

            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, pm.id)
                data_col = col + 1  # COL_CHK の分シフト
                if _COL_FIELDS[data_col] is None:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row, data_col, item)

        self._table.setSortingEnabled(True)
        self._table.blockSignals(False)
        self._count_label.setText(f"{len(pms)} 件")

    def _checked_pm_ids(self) -> list[int]:
        ids = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_CHK)
            if item and item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _on_item_changed(self, item: QTableWidgetItem):
        col = item.column()
        if col == COL_CHK:
            return
        field = _COL_FIELDS[col] if col < len(_COL_FIELDS) else None
        if field is None:
            return
        pm_id = item.data(Qt.ItemDataRole.UserRole)
        if pm_id is None:
            return
        session = get_session()
        try:
            pm = session.get(ProjectMember, pm_id)
            if pm:
                setattr(pm, field, item.text().strip())
                session.commit()
        finally:
            session.close()

    def _current_pm_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, COL_CHK)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _add_entry(self):
        dlg = RosterEntryDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = get_session()
            try:
                add_roster_entries(session, self._project_id, [dlg.values()])
            finally:
                session.close()
            self._load()

    def _edit_entry(self):
        pm_id = self._current_pm_id()
        if pm_id is None:
            QMessageBox.information(self, "未選択", "編集する行を選択してください。")
            return
        session = get_session()
        try:
            pm = session.get(ProjectMember, pm_id)
            if pm is None:
                return
            initial = {
                "member_number": pm.member_number,
                "organization_name": pm.organization_name,
                "organization_kana": pm.organization_kana,
                "representative_name": pm.representative_name,
                "representative_kana": pm.representative_kana,
                "department": pm.department,
                "postal_code": pm.postal_code,
                "address": pm.address,
                "address2": pm.address2,
                "phone": pm.phone,
                "email": pm.email,
            }
            dlg = RosterEntryDialog(self, initial=initial)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                vals = dlg.values()
                for key, value in vals.items():
                    setattr(pm, key, value)
                session.commit()
        finally:
            session.close()
        self._load()

    def _copy_from_project(self):
        dlg = ProjectCopyDialog(self._project_id, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            src_id = dlg.selected_project_id()
            if src_id is None:
                return
            session = get_session()
            try:
                copy_roster_from_project(session, src_id, self._project_id)
            finally:
                session.close()
            self._load()

    def _open_import(self):
        from app.ui.roster_import import RosterImportDialog
        dlg = RosterImportDialog(self._project_id, self)
        if dlg.exec():
            self._load()

    def _remove_checked(self):
        ids = self._checked_pm_ids()
        if not ids:
            QMessageBox.information(self, "未選択",
                                    "削除する行をチェックしてください。")
            return
        if QMessageBox.question(
                self, "削除の確認",
                f"チェックした {len(ids)} 件を名簿から削除します。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            for pm_id in ids:
                remove_member_from_project(session, pm_id)
        finally:
            session.close()
        self._load()
