# app/ui/staff_management.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QMessageBox, QHeaderView,
    QDialog, QFormLayout, QDialogButtonBox, QComboBox, QGroupBox,
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.staff_service import (
    create_staff, get_all_staff, deactivate_staff, reactivate_staff,
    reset_password, set_admin, has_any_admin, update_staff,
)
from app.services.supervisor_service import (
    create_supervisor, get_all_supervisors,
    update_supervisor, deactivate_supervisor,
)
from app.utils import current_user


# ── 所属長 追加・編集ダイアログ ─────────────────────────────

class _SupervisorDialog(QDialog):
    def __init__(self, parent=None, name="", email=""):
        super().__init__(parent)
        self.setWindowTitle("所属長の登録" if not name else "所属長の編集")
        self.resize(340, 120)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)
        self._name  = QLineEdit(name)
        self._email = QLineEdit(email)
        self._email.setPlaceholderText("例：buchou@example.com")
        form.addRow("氏名 *",   self._name)
        form.addRow("メール",   self._email)
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
        self.accept()

    def values(self) -> tuple[str, str]:
        return self._name.text().strip(), self._email.text().strip()


# ── 職員 追加・編集ダイアログ ────────────────────────────────

class _StaffDialog(QDialog):
    def __init__(self, parent=None, name="", supervisor_id=None, supervisors=None):
        super().__init__(parent)
        self.setWindowTitle("職員の登録" if not name else "職員の編集")
        self.resize(340, 120)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(10)
        self._name = QLineEdit(name)
        self._sup_combo = QComboBox()
        self._sup_combo.addItem("（なし）", None)
        for sup in (supervisors or []):
            self._sup_combo.addItem(f"{sup.name}　{sup.email}", sup.id)
        if supervisor_id is not None:
            for i in range(self._sup_combo.count()):
                if self._sup_combo.itemData(i) == supervisor_id:
                    self._sup_combo.setCurrentIndex(i)
                    break
        form.addRow("氏名 *",   self._name)
        form.addRow("所属長",   self._sup_combo)
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
        self.accept()

    def values(self) -> tuple[str, int | None]:
        return self._name.text().strip(), self._sup_combo.currentData()


# ── メイン管理ウィジェット ───────────────────────────────────

class StaffManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._supervisors: list = []
        self._build()
        self._load_supervisors()
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

        # ── 所属長セクション ─────────────────────────────────
        grp_sup = QGroupBox("所属長")
        sup_vbox = QVBoxLayout(grp_sup)

        self._sup_table = QTableWidget(0, 3)
        self._sup_table.setHorizontalHeaderLabels(["ID", "氏名", "メール"])
        shdr = self._sup_table.horizontalHeader()
        shdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._sup_table.setColumnWidth(0, 36)
        shdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._sup_table.setColumnWidth(1, 130)
        shdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._sup_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._sup_table.setMaximumHeight(130)
        sup_vbox.addWidget(self._sup_table)

        sup_btn_row = QHBoxLayout()
        self._btn_sup_add  = QPushButton("追加")
        self._btn_sup_edit = QPushButton("編集")
        self._btn_sup_del  = QPushButton("削除")
        self._btn_sup_add.clicked.connect(self._sup_add)
        self._btn_sup_edit.clicked.connect(self._sup_edit)
        self._btn_sup_del.clicked.connect(self._sup_delete)
        for b in (self._btn_sup_add, self._btn_sup_edit, self._btn_sup_del):
            sup_btn_row.addWidget(b)
        sup_btn_row.addStretch()
        sup_vbox.addLayout(sup_btn_row)
        layout.addWidget(grp_sup)

        # ── 職員セクション ───────────────────────────────────
        grp_staff = QGroupBox("職員")
        staff_vbox = QVBoxLayout(grp_staff)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["ID", "氏名", "所属長", "管理者", "パスワード", "状態"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 36)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(1, 140)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
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
            self._btn_sup_add, self._btn_sup_edit, self._btn_sup_del,
            self._btn_add, self._btn_edit, self._btn_deact, self._btn_react,
            self._btn_reset_pw, self._btn_toggle_admin,
        ]
        layout.addWidget(grp_staff)

    # ── 所属長 CRUD ─────────────────────────────────────────

    def _load_supervisors(self):
        session = get_session()
        try:
            self._supervisors = get_all_supervisors(session)
        finally:
            session.close()
        self._sup_table.setRowCount(0)
        for sup in self._supervisors:
            row = self._sup_table.rowCount()
            self._sup_table.insertRow(row)
            self._sup_table.setItem(row, 0, QTableWidgetItem(str(sup.id)))
            self._sup_table.setItem(row, 1, QTableWidgetItem(sup.name))
            self._sup_table.setItem(row, 2, QTableWidgetItem(sup.email or ""))
        self._sup_table.resizeRowsToContents()

    def _selected_sup_id(self) -> int | None:
        row = self._sup_table.currentRow()
        if row < 0:
            return None
        return int(self._sup_table.item(row, 0).text())

    def _sup_add(self):
        dlg = _SupervisorDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, email = dlg.values()
        session = get_session()
        try:
            create_supervisor(session, name, email)
        finally:
            session.close()
        self._load_supervisors()
        self._load_staff()

    def _sup_edit(self):
        sup_id = self._selected_sup_id()
        if sup_id is None:
            QMessageBox.warning(self, "未選択", "編集する所属長を選択してください。")
            return
        row = self._sup_table.currentRow()
        dlg = _SupervisorDialog(
            self,
            name=self._sup_table.item(row, 1).text(),
            email=self._sup_table.item(row, 2).text(),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, email = dlg.values()
        session = get_session()
        try:
            update_supervisor(session, sup_id, name, email)
        finally:
            session.close()
        self._load_supervisors()
        self._load_staff()

    def _sup_delete(self):
        sup_id = self._selected_sup_id()
        if sup_id is None:
            QMessageBox.warning(self, "未選択", "削除する所属長を選択してください。")
            return
        name = self._sup_table.item(self._sup_table.currentRow(), 1).text()
        if QMessageBox.question(
                self, "削除の確認",
                f"所属長「{name}」を削除します。\n"
                "この所属長が設定された職員は所属長なしになります。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            deactivate_supervisor(session, sup_id)
        finally:
            session.close()
        self._load_supervisors()
        self._load_staff()

    # ── 職員 CRUD ───────────────────────────────────────────

    def _load_staff(self):
        session = get_session()
        try:
            staff_list = get_all_staff(session)
            rows = []
            for s in staff_list:
                sup_label = ""
                if s.supervisor_id and s.supervisor:
                    sup_label = s.supervisor.name
                rows.append((s.id, s.name, sup_label,
                             s.supervisor_id,
                             s.is_admin, s.password_hash, s.is_active))
        finally:
            session.close()

        self._table.setRowCount(0)
        for sid, name, sup_label, sup_id, is_admin, pw_hash, is_active in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(sid)))
            self._table.setItem(row, 1, QTableWidgetItem(name))
            item_sup = QTableWidgetItem(sup_label)
            item_sup.setData(Qt.ItemDataRole.UserRole, sup_id)
            self._table.setItem(row, 2, item_sup)
            self._table.setItem(row, 3, QTableWidgetItem("○" if is_admin else "－"))
            self._table.setItem(row, 4, QTableWidgetItem("設定済" if pw_hash else "未設定"))
            self._table.setItem(row, 5, QTableWidgetItem("有効" if is_active else "無効"))
        self._table.resizeRowsToContents()

        can = self._can_admin()
        for btn in self._admin_btns:
            btn.setVisible(can)

    def _selected_staff_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        return int(self._table.item(row, 0).text())

    def _add(self):
        dlg = _StaffDialog(self, supervisors=self._supervisors)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, sup_id = dlg.values()
        session = get_session()
        try:
            create_staff(session, name, supervisor_id=sup_id)
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            return
        finally:
            session.close()
        self._load_staff()

    def _edit(self):
        staff_id = self._selected_staff_id()
        if staff_id is None:
            QMessageBox.warning(self, "未選択", "編集する職員を選択してください。")
            return
        row = self._table.currentRow()
        current_sup_id = self._table.item(row, 2).data(Qt.ItemDataRole.UserRole)
        dlg = _StaffDialog(
            self,
            name=self._table.item(row, 1).text(),
            supervisor_id=current_sup_id,
            supervisors=self._supervisors,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, sup_id = dlg.values()
        session = get_session()
        try:
            update_staff(session, staff_id, name, supervisor_id=sup_id)
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            return
        finally:
            session.close()
        self._load_staff()

    def _deactivate(self):
        staff_id = self._selected_staff_id()
        if staff_id is None:
            return
        name = self._table.item(self._table.currentRow(), 1).text()
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
        name = self._table.item(self._table.currentRow(), 1).text()
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
        name = self._table.item(row, 1).text()
        is_currently_admin = self._table.item(row, 3).text() == "○"
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
