# app/ui/staff_management.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QMessageBox, QHeaderView,
    QDialog, QFormLayout, QDialogButtonBox, QComboBox, QGroupBox,
    QCheckBox, QFileDialog,
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.staff_service import (
    create_staff, get_all_staff, deactivate_staff, reactivate_staff,
    reset_password, set_admin, has_any_admin, update_staff,
    set_department_head, update_staff_email, get_department_heads,
    import_staff_from_csv,
)
from app.utils import current_user

# ── 職員テーブル列定数 ────────────────────────────────────────
SCOL_ID    = 0
SCOL_NAME  = 1
SCOL_SUP   = 2  # 担当所属長
SCOL_HEAD  = 3  # 所属長フラグ
SCOL_EMAIL = 4  # メールアドレス
SCOL_ADMIN = 5  # 管理者
SCOL_PW    = 6  # パスワード
SCOL_STAT  = 7  # 状態


# ── 職員 追加・編集ダイアログ ────────────────────────────────────

class _StaffDialog(QDialog):
    def __init__(self, parent=None, name="", supervisor_id=None,
                 is_department_head=False, email="", department_heads=None):
        super().__init__(parent)
        self.setWindowTitle("職員の登録" if not name else "職員の編集")
        self.resize(360, 160)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)

        self._name = QLineEdit(name)

        self._sup_combo = QComboBox()
        self._sup_combo.addItem("（なし）", None)
        for s in (department_heads or []):
            self._sup_combo.addItem(f"{s.name}　{s.email or ''}", s.id)
        if supervisor_id is not None:
            for i in range(self._sup_combo.count()):
                if self._sup_combo.itemData(i) == supervisor_id:
                    self._sup_combo.setCurrentIndex(i)
                    break

        self._head_chk = QCheckBox("この職員自身が所属長である")
        self._head_chk.setChecked(is_department_head)

        self._email = QLineEdit(email)
        self._email.setPlaceholderText("例：staff@example.com（所属長の場合は必須）")

        form.addRow("氏名 *",        self._name)
        form.addRow("担当所属長",    self._sup_combo)
        form.addRow("所属長フラグ",  self._head_chk)
        form.addRow("メールアドレス", self._email)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "入力エラー", "氏名を入力してください。")
            return
        if self._head_chk.isChecked() and not self._email.text().strip():
            QMessageBox.warning(self, "入力エラー",
                                "所属長フラグがONの場合、メールアドレスは必須です。")
            return
        self.accept()

    def values(self) -> tuple[str, int | None, bool, str]:
        return (self._name.text().strip(),
                self._sup_combo.currentData(),
                self._head_chk.isChecked(),
                self._email.text().strip())


# ── メイン管理ウィジェット ───────────────────────────────────────

class StaffManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._department_heads: list = []
        self._build()
        self._load_department_heads()
        self._load_staff()

    def _can_admin(self) -> bool:
        session = get_session()
        try:
            if not has_any_admin(session):
                return True
        finally:
            session.close()
        return current_user.is_admin()

    def _build(self):
        layout = QVBoxLayout(self)

        grp_staff = QGroupBox("職員")
        staff_vbox = QVBoxLayout(grp_staff)

        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            ["ID", "氏名", "担当所属長", "所属長フラグ", "メールアドレス",
             "管理者", "パスワード", "状態"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(SCOL_ID,    QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(SCOL_ID, 36)
        hdr.setSectionResizeMode(SCOL_NAME,  QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(SCOL_NAME, 120)
        hdr.setSectionResizeMode(SCOL_SUP,   QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(SCOL_SUP, 120)
        hdr.setSectionResizeMode(SCOL_EMAIL, QHeaderView.ResizeMode.Stretch)
        for col in (SCOL_HEAD, SCOL_ADMIN, SCOL_PW, SCOL_STAT):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        staff_vbox.addWidget(self._table)

        own_row = QHBoxLayout()
        btn_change_pw = QPushButton("自分のパスワードを変更")
        btn_change_pw.clicked.connect(self._change_my_password)
        own_row.addWidget(btn_change_pw)
        own_row.addStretch()
        staff_vbox.addLayout(own_row)

        admin_row = QHBoxLayout()
        self._btn_add          = QPushButton("追加")
        self._btn_edit         = QPushButton("編集")
        self._btn_deact        = QPushButton("無効化")
        self._btn_react        = QPushButton("有効化")
        self._btn_reset_pw     = QPushButton("パスワードをリセット")
        self._btn_toggle_admin = QPushButton("管理者に設定 / 解除")
        self._btn_add.clicked.connect(self._add)
        self._btn_edit.clicked.connect(self._edit)
        self._btn_deact.clicked.connect(self._deactivate)
        self._btn_react.clicked.connect(self._reactivate)
        self._btn_reset_pw.clicked.connect(self._reset_password)
        self._btn_toggle_admin.clicked.connect(self._toggle_admin)
        for btn in (self._btn_add, self._btn_edit, self._btn_deact,
                    self._btn_react, self._btn_reset_pw, self._btn_toggle_admin):
            admin_row.addWidget(btn)
        admin_row.addStretch()
        staff_vbox.addLayout(admin_row)

        self._admin_btns = [
            self._btn_add, self._btn_edit, self._btn_deact, self._btn_react,
            self._btn_reset_pw, self._btn_toggle_admin,
        ]
        layout.addWidget(grp_staff)

        # ── CSVインポートセクション ───────────────────────────────
        grp_csv = QGroupBox("CSVインポート（追記）")
        csv_layout = QVBoxLayout(grp_csv)
        csv_layout.setSpacing(6)

        desc = QLabel(
            "CSV/Excelから職員を一括追加します。同名の職員はスキップされます。\n"
            "対応列：氏名（必須）・メールアドレス・所属長フラグ（○/1）・担当所属長（氏名）"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#555; font-size:11px;")
        csv_layout.addWidget(desc)

        file_row = QHBoxLayout()
        self._csv_path = QLineEdit()
        self._csv_path.setReadOnly(True)
        self._csv_path.setPlaceholderText("CSV / Excel ファイルを選択してください")
        btn_browse = QPushButton("ファイルを選択…")
        btn_browse.clicked.connect(self._csv_browse)
        file_row.addWidget(self._csv_path, 1)
        file_row.addWidget(btn_browse)
        csv_layout.addLayout(file_row)

        import_row = QHBoxLayout()
        self._btn_csv_import = QPushButton("インポート実行")
        self._btn_csv_import.setEnabled(False)
        self._btn_csv_import.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 4px 14px; }"
            "QPushButton:hover { background: #1D4ED8; }"
            "QPushButton:disabled { background: #94A3B8; color: white; }")
        self._btn_csv_import.clicked.connect(self._csv_import)
        self._csv_result = QLabel("")
        import_row.addWidget(self._btn_csv_import)
        import_row.addWidget(self._csv_result, 1)
        csv_layout.addLayout(import_row)
        layout.addWidget(grp_csv)

    # ── 所属長リスト更新 ──────────────────────────────────────────

    def _load_department_heads(self):
        session = get_session()
        try:
            self._department_heads = get_department_heads(session)
        finally:
            session.close()

    # ── 職員 CRUD ────────────────────────────────────────────────

    def _load_staff(self):
        session = get_session()
        try:
            staff_list = get_all_staff(session)
            rows = []
            for s in staff_list:
                sup_label = ""
                if s.supervisor_id and s.supervisor:
                    sup_label = s.supervisor.name
                rows.append((
                    s.id, s.name, sup_label, s.supervisor_id,
                    s.is_department_head, s.email or "",
                    s.is_admin, s.password_hash, s.is_active,
                ))
        finally:
            session.close()

        self._table.setRowCount(0)
        for sid, name, sup_label, sup_id, is_head, email, is_admin, pw_hash, is_active in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, SCOL_ID,   QTableWidgetItem(str(sid)))
            self._table.setItem(row, SCOL_NAME,  QTableWidgetItem(name))
            item_sup = QTableWidgetItem(sup_label)
            item_sup.setData(Qt.ItemDataRole.UserRole, sup_id)
            self._table.setItem(row, SCOL_SUP,   item_sup)
            self._table.setItem(row, SCOL_HEAD,
                                QTableWidgetItem("○" if is_head else "－"))
            self._table.setItem(row, SCOL_EMAIL, QTableWidgetItem(email))
            self._table.setItem(row, SCOL_ADMIN,
                                QTableWidgetItem("○" if is_admin else "－"))
            self._table.setItem(row, SCOL_PW,
                                QTableWidgetItem("設定済" if pw_hash else "未設定"))
            self._table.setItem(row, SCOL_STAT,
                                QTableWidgetItem("有効" if is_active else "無効"))
        self._table.resizeRowsToContents()

        can = self._can_admin()
        for btn in self._admin_btns:
            btn.setVisible(can)

    def _selected_staff_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        return int(self._table.item(row, SCOL_ID).text())

    def _add(self):
        self._load_department_heads()
        dlg = _StaffDialog(self, department_heads=self._department_heads)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, sup_id, is_head, email = dlg.values()
        session = get_session()
        try:
            create_staff(session, name, supervisor_id=sup_id,
                         is_department_head=is_head, email=email)
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            return
        finally:
            session.close()
        self._load_department_heads()
        self._load_staff()

    def _edit(self):
        staff_id = self._selected_staff_id()
        if staff_id is None:
            QMessageBox.warning(self, "未選択", "編集する職員を選択してください。")
            return
        row = self._table.currentRow()
        current_sup_id = self._table.item(row, SCOL_SUP).data(Qt.ItemDataRole.UserRole)
        current_head = self._table.item(row, SCOL_HEAD).text() == "○"
        current_email = self._table.item(row, SCOL_EMAIL).text()
        self._load_department_heads()
        dlg = _StaffDialog(
            self,
            name=self._table.item(row, SCOL_NAME).text(),
            supervisor_id=current_sup_id,
            is_department_head=current_head,
            email=current_email,
            department_heads=self._department_heads,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, sup_id, is_head, email = dlg.values()
        session = get_session()
        try:
            update_staff(session, staff_id, name, supervisor_id=sup_id,
                         is_department_head=is_head, email=email)
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            return
        finally:
            session.close()
        self._load_department_heads()
        self._load_staff()

    def _deactivate(self):
        staff_id = self._selected_staff_id()
        if staff_id is None:
            return
        name = self._table.item(self._table.currentRow(), SCOL_NAME).text()
        if QMessageBox.question(
                self, "無効化の確認",
                f"スタッフ「{name}」を無効化します。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            deactivate_staff(session, staff_id)
        finally:
            session.close()
        self._load_staff()

    def _reactivate(self):
        staff_id = self._selected_staff_id()
        if staff_id is None:
            return
        session = get_session()
        try:
            reactivate_staff(session, staff_id)
        finally:
            session.close()
        self._load_staff()

    def _reset_password(self):
        staff_id = self._selected_staff_id()
        if staff_id is None:
            QMessageBox.warning(self, "選択エラー", "スタッフを選択してください。")
            return
        name = self._table.item(self._table.currentRow(), SCOL_NAME).text()
        if QMessageBox.question(
                self, "パスワードリセットの確認",
                f"「{name}」のパスワードをリセットします。\n"
                "次回ログイン時に新しいパスワードの設定が必要になります。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            reset_password(session, staff_id)
        finally:
            session.close()
        self._load_staff()

    def _toggle_admin(self):
        staff_id = self._selected_staff_id()
        if staff_id is None:
            QMessageBox.warning(self, "選択エラー", "スタッフを選択してください。")
            return
        row = self._table.currentRow()
        name = self._table.item(row, SCOL_NAME).text()
        is_currently_admin = self._table.item(row, SCOL_ADMIN).text() == "○"
        action = "解除" if is_currently_admin else "設定"
        if QMessageBox.question(
                self, "管理者変更の確認",
                f"「{name}」の管理者権限を{action}します。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            set_admin(session, staff_id, not is_currently_admin)
        except ValueError as e:
            QMessageBox.warning(self, "設定エラー", str(e))
            return
        finally:
            session.close()
        self._load_staff()

    def _change_my_password(self):
        uid = current_user.get_id()
        uname = current_user.get_name()
        if uid is None:
            return
        from app.ui.login_dialog import ChangePasswordDialog
        dlg = ChangePasswordDialog(uid, uname, self)
        dlg.exec()

    # ── CSVインポート ──────────────────────────────────────────────

    def _csv_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "CSVファイルを選択", "",
            "CSV / Excel (*.csv *.xlsx *.xls);;すべてのファイル (*)"
        )
        if path:
            self._csv_path.setText(path)
            self._btn_csv_import.setEnabled(True)
            self._csv_result.setText("")

    def _csv_import(self):
        path = self._csv_path.text()
        if not path:
            return
        session = get_session()
        try:
            added, skipped = import_staff_from_csv(session, path)
            self._csv_result.setText(f"追加：{added} 件　スキップ：{skipped} 件")
            self._csv_result.setStyleSheet("color:green; font-weight:bold;")
        except Exception as e:
            self._csv_result.setText(f"エラー：{e}")
            self._csv_result.setStyleSheet("color:red;")
        finally:
            session.close()
        self._load_department_heads()
        self._load_staff()
