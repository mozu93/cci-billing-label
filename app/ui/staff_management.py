# app/ui/staff_management.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QMessageBox, QHeaderView,
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.staff_service import (
    create_staff, get_all_staff, deactivate_staff, reactivate_staff,
    reset_password, set_admin, count_admins, has_any_admin,
)
from app.utils import current_user


class StaffManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _can_admin(self) -> bool:
        """管理者操作を許可するか（管理者本人、または管理者が誰もいない初期状態）。"""
        session = get_session()
        try:
            if not has_any_admin(session):
                return True
        finally:
            session.close()
        return current_user.is_admin()

    def _build(self):
        layout = QVBoxLayout(self)

        # スタッフ追加（管理者のみ）
        add_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("スタッフ名を入力")
        self._btn_add = QPushButton("追加")
        self._btn_add.clicked.connect(self._add)
        add_row.addWidget(QLabel("氏名："))
        add_row.addWidget(self._name_input)
        add_row.addWidget(self._btn_add)
        layout.addLayout(add_row)

        # テーブル：ID / 氏名 / 管理者 / パスワード / 状態
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["ID", "氏名", "管理者", "パスワード", "状態"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setStyleSheet("QComboBox { min-height: 0; padding: 1px 4px; }")
        layout.addWidget(self._table)

        # 全員が使えるボタン
        own_row = QHBoxLayout()
        btn_change_pw = QPushButton("自分のパスワードを変更")
        btn_change_pw.clicked.connect(self._change_my_password)
        own_row.addWidget(btn_change_pw)
        own_row.addStretch()
        layout.addLayout(own_row)

        # 管理者専用ボタン
        admin_row = QHBoxLayout()
        self._btn_deact = QPushButton("無効化")
        self._btn_deact.clicked.connect(self._deactivate)
        self._btn_react = QPushButton("有効化")
        self._btn_react.clicked.connect(self._reactivate)
        self._btn_reset_pw = QPushButton("パスワードをリセット")
        self._btn_reset_pw.clicked.connect(self._reset_password)
        self._btn_toggle_admin = QPushButton("管理者に設定 / 解除")
        self._btn_toggle_admin.clicked.connect(self._toggle_admin)
        for btn in (self._btn_deact, self._btn_react, self._btn_reset_pw, self._btn_toggle_admin):
            admin_row.addWidget(btn)
        admin_row.addStretch()
        layout.addLayout(admin_row)

        self._admin_btns = [
            self._btn_add, self._btn_deact, self._btn_react,
            self._btn_reset_pw, self._btn_toggle_admin,
        ]

    def _load(self):
        session = get_session()
        try:
            staff_list = get_all_staff(session)
        finally:
            session.close()

        self._table.setRowCount(0)
        for s in staff_list:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self._table.setItem(row, 1, QTableWidgetItem(s.name))
            self._table.setItem(row, 2, QTableWidgetItem("○" if s.is_admin else "－"))
            self._table.setItem(row, 3, QTableWidgetItem("設定済" if s.password_hash else "未設定"))
            self._table.setItem(row, 4, QTableWidgetItem("有効" if s.is_active else "無効"))
        self._table.resizeRowsToContents()

        # 管理者権限の有無でボタン表示を切替
        can = self._can_admin()
        for btn in self._admin_btns:
            btn.setVisible(can)

    def _selected_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        return int(self._table.item(row, 0).text())

    def _add(self):
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "入力エラー", "氏名を入力してください。")
            return
        session = get_session()
        try:
            create_staff(session, name)
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            return
        finally:
            session.close()
        self._name_input.clear()
        self._load()

    def _deactivate(self):
        staff_id = self._selected_id()
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
        self._load()

    def _reactivate(self):
        staff_id = self._selected_id()
        if staff_id is None:
            return
        session = get_session()
        try:
            reactivate_staff(session, staff_id)
        finally:
            session.close()
        self._load()

    def _reset_password(self):
        staff_id = self._selected_id()
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
        self._load()

    def _toggle_admin(self):
        staff_id = self._selected_id()
        if staff_id is None:
            QMessageBox.warning(self, "選択エラー", "スタッフを選択してください。")
            return
        row = self._table.currentRow()
        name = self._table.item(row, 1).text()
        is_currently_admin = self._table.item(row, 2).text() == "○"
        new_admin = not is_currently_admin
        action = "解除" if is_currently_admin else "設定"
        if QMessageBox.question(
                self, "管理者変更の確認",
                f"「{name}」の管理者権限を{action}します。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            set_admin(session, staff_id, new_admin)
        except ValueError as e:
            QMessageBox.warning(self, "設定エラー", str(e))
            return
        finally:
            session.close()
        self._load()

    def _change_my_password(self):
        uid = current_user.get_id()
        uname = current_user.get_name()
        if uid is None:
            return
        from app.ui.login_dialog import ChangePasswordDialog
        dlg = ChangePasswordDialog(uid, uname, self)
        dlg.exec()
