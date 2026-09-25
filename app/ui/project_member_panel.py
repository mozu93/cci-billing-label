# app/ui/project_member_panel.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QMessageBox, QDialog,
    QFormLayout, QLineEdit,
    QDialogButtonBox, QStyledItemDelegate, QCheckBox
)
from PyQt6.QtCore import Qt, QEvent, pyqtSignal
from app.database.connection import get_session
from app.database.models import ProjectMember
from app.services.category_service import get_category_names
from app.services.project_service import (
    get_project_members, add_roster_entries, remove_member_from_project,
    set_project_members_cancelled,
    get_project_member, update_project_member_fields, EDITABLE_MEMBER_FIELDS,
    get_project_by_id, members_with_issuances,
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
    "roster_no", "member_number", "organization_name", "organization_kana",
    "representative_name", "representative_kana", "department",
    "postal_code", "address", "address2", "phone", "email",
    None,            # キャンセル
    None,            # 登録日
]

COLS = [
    ("",             28),
    ("NO.",           55),
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
    ("キャンセル",      85),
    ("登録日",         90),
]


class RosterEntryDialog(QDialog):
    """名簿の1エントリ入力ダイアログ"""

    FIELDS = [
        ("roster_no",            "NO."),
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


class ProjectMemberPanel(QWidget):
    #: 名簿の件数が変わったときに発火（一覧側の集計を更新するため）
    roster_changed = pyqtSignal()

    def __init__(self, project_id: int):
        super().__init__()
        self._project_id = project_id
        self._members: list[ProjectMember] = []
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        heading_row = QHBoxLayout()
        # どの名簿かを「業務名　件名」の見出しで示す（同じ件名でも業務名で見分けられる）
        session = get_session()
        try:
            proj = get_project_by_id(session, self._project_id)
            proj_name = proj.name if proj else ""
            cat_name = (get_category_names(session).get(proj.category_id, "")
                        if proj and proj.category_id else "")
        finally:
            session.close()
        title = QLabel("名簿：" + "　".join(x for x in (cat_name, proj_name) if x))
        title.setStyleSheet("font-weight: bold; color: #1D4ED8;")
        heading_row.addWidget(title)
        heading_row.addSpacing(16)
        heading_row.addStretch()
        heading_row.addWidget(QLabel("検索："))
        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.setPlaceholderText("事業所名・フリガナ・氏名・氏名フリガナで絞り込み")
        self._search.setMinimumWidth(240)
        self._search.textChanged.connect(self._apply_filter)
        heading_row.addWidget(self._search, 1)
        btn_export = QPushButton("Excel出力")
        btn_export.setToolTip(
            "表示中の名簿（検索で絞り込んでいればその行）を、全項目でExcelに出力します。")
        btn_export.clicked.connect(self._export_excel)
        heading_row.addWidget(btn_export)
        layout.addLayout(heading_row)

        # 見切れないよう名前は短くし、詳しい説明はツールチップで補う。
        # 左に「名簿に追加する」、右に「チェックした行への操作」をまとめる
        def _btn(text, tip, slot):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            return b

        btn_add = _btn("1件追加", "名簿に1件を手入力で追加します。", self._add_entry)
        btn_import = _btn(
            "Excel・貼付で追加",
            "Excelファイルや貼り付けたデータを、いまの名簿を消さずに追加します。\n"
            "すでに名簿にある行は重複としてスキップできます。",
            self._open_import)
        btn_edit = _btn("編集", "選んだ行の内容を編集します（行のダブルクリックでも開けます）。",
                        self._edit_entry)
        btn_cancel = _btn("参加キャンセル",
                          "チェックした行を参加キャンセルにします。\n"
                          "発行済みの書類は履歴として残り、今後の発行と入金管理の対象から外れます。",
                          lambda: self._set_cancelled_checked(True))
        btn_restore = _btn("キャンセル解除", "チェックした行の参加キャンセルを取り消します。",
                           lambda: self._set_cancelled_checked(False))
        self._btn_del = _btn("削除", "チェックした行を名簿から削除します。",
                             self._remove_checked)

        btn_row = QHBoxLayout()
        for b in (btn_add, btn_import):
            btn_row.addWidget(b)
        btn_row.addStretch()
        for b in (btn_edit, btn_cancel, btn_restore, self._btn_del):
            btn_row.addWidget(b)
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
            self._members = get_project_members(
                session, self._project_id, newest_first=True)
        finally:
            session.close()
        self._apply_filter()

    def _export_excel(self):
        """表示中の名簿を、画面の並び順のまま全項目でExcelに書き出す。"""
        if self._table.rowCount() == 0:
            QMessageBox.information(self, "Excel出力", "出力する名簿がありません。")
            return
        from PyQt6.QtWidgets import QFileDialog
        from app.services.report_service import export_to_excel
        path, _ = QFileDialog.getSaveFileName(
            self, "名簿をExcelに出力", "名簿.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        headers = [name for name, _w in COLS[1:]]   # チェック列は出さない
        rows = []
        for r in range(self._table.rowCount()):
            rows.append({h: (self._table.item(r, c).text()
                             if self._table.item(r, c) else "")
                         for c, h in enumerate(headers, start=1)})
        try:
            export_to_excel(rows, headers, path)
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            return
        QMessageBox.information(self, "Excel出力", f"Excelを保存しました。\n{path}")

    def _apply_filter(self, text: str = ""):
        """指定された宛名項目だけを対象に、名簿をリアルタイムで絞り込む。"""
        query = text.strip().casefold()
        if query:
            fields = (
                "organization_name", "organization_kana",
                "representative_name", "representative_kana",
            )
            pms = [
                pm for pm in self._members
                if any(query in (getattr(pm, field) or "").casefold()
                       for field in fields)
            ]
        else:
            pms = self._members
        self._populate_table(pms)

    def _populate_table(self, pms: list[ProjectMember]):
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
                pm.roster_no or "",
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
                "キャンセル" if pm.is_cancelled else "",
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
                if pm.is_cancelled:
                    item.setForeground(Qt.GlobalColor.gray)
                self._table.setItem(row, data_col, item)

        self._table.setSortingEnabled(True)
        self._table.blockSignals(False)
        if self._search.text().strip():
            self._count_label.setText(
                f"{len(pms)} 件を表示（全 {len(self._members)} 件）")
        else:
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
            update_project_member_fields(
                session, pm_id, {field: item.text().strip()})
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
            self.roster_changed.emit()

    def _edit_entry(self):
        pm_id = self._current_pm_id()
        if pm_id is None:
            QMessageBox.information(self, "未選択", "編集する行を選択してください。")
            return
        session = get_session()
        try:
            pm = get_project_member(session, pm_id)
            if pm is None:
                return
            initial = {field: getattr(pm, field)
                       for field in EDITABLE_MEMBER_FIELDS}
        finally:
            session.close()

        # 入力ダイアログの表示中はセッションを開いたままにしない。
        dlg = RosterEntryDialog(self, initial=initial)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        session = get_session()
        try:
            update_project_member_fields(session, pm_id, dlg.values())
        finally:
            session.close()
        self._load()

    def _open_import(self):
        """いまの名簿を残したまま、Excel／貼り付けから行を追加する。"""
        from app.ui.roster_import import RosterImportDialog
        dlg = RosterImportDialog(self._project_id, self)
        if dlg.exec():
            self._load()
            self.roster_changed.emit()

    def _remove_checked(self):
        ids = self._checked_pm_ids()
        if not ids:
            QMessageBox.information(self, "未選択",
                                    "削除する行をチェックしてください。")
            return
        # 発行済みの書類がある行は削除しない。1件でも含まれていれば全体を止める
        # （一部だけ消えると、何が消えたか分かりにくいため）
        session = get_session()
        try:
            issued = members_with_issuances(session, ids)
        finally:
            session.close()
        if issued:
            names = [pm.organization_name or pm.representative_name or f"ID {pm.id}"
                     for pm in self._members if pm.id in set(issued)]
            QMessageBox.warning(
                self, "削除できません",
                "次の行は請求書・領収書を発行済みのため、名簿から削除できません。\n"
                "参加をやめた場合は「参加キャンセル」を使ってください"
                "（発行済みの書類は履歴として残り、今後の発行と入金管理の対象から外れます）。\n\n"
                + "\n".join(f"・{n}" for n in names[:10])
                + (f"\n…ほか {len(names) - 10} 件" if len(names) > 10 else ""))
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
        self.roster_changed.emit()

    def _set_cancelled_checked(self, cancelled: bool):
        ids = self._checked_pm_ids()
        if not ids:
            QMessageBox.information(self, "未選択",
                                    "対象の行をチェックしてください。")
            return
        action = "参加キャンセル" if cancelled else "キャンセルを戻す"
        detail = ("発行済みの請求書・領収書は履歴として残ります。\n"
                  "入金管理と今後の発行対象からは除外されます。"
                  if cancelled else "入金管理と発行対象に再び表示されます。")
        if QMessageBox.question(
                self, action, f"チェックした {len(ids)} 件を{action}しますか？\n\n{detail}"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            set_project_members_cancelled(session, ids, cancelled)
        finally:
            session.close()
        self._load()
        self.roster_changed.emit()
