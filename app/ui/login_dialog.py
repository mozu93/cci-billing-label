# app/ui/login_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QCheckBox,
)
from PyQt6.QtCore import QTimer
from app.database.connection import get_session
from app.services.staff_service import get_active_staff, get_staff, set_password, verify_password
from app.utils import current_user
from app.utils.app_config import get_config, save_config


class _SetPasswordDialog(QDialog):
    """初回ログイン時のパスワード設定ダイアログ。"""

    def __init__(self, staff_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("パスワードの初期設定")
        self.setFixedWidth(340)
        self._password = ""
        self._build(staff_name)

    def _build(self, staff_name):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        msg = QLabel(
            f"「{staff_name}」さん、初めてのログインです。\n"
            "パスワードを設定してください。"
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._pw1 = QLineEdit()
        self._pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw2 = QLineEdit()
        self._pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw2.returnPressed.connect(self._ok)
        form.addRow("新しいパスワード：", self._pw1)
        form.addRow("確認（再入力）：", self._pw2)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("設定してログイン")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._ok)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _ok(self):
        pw1 = self._pw1.text()
        pw2 = self._pw2.text()
        if not pw1:
            QMessageBox.warning(self, "入力エラー", "パスワードを入力してください。")
            return
        if pw1 != pw2:
            QMessageBox.warning(self, "入力エラー", "パスワードが一致しません。再入力してください。")
            self._pw1.clear()
            self._pw2.clear()
            self._pw1.setFocus()
            return
        self._password = pw1
        self.accept()

    def password(self) -> str:
        return self._password


class _PasswordInputDialog(QDialog):
    """通常ログイン時のパスワード入力ダイアログ。"""

    def __init__(self, staff_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ログイン")
        self.setFixedWidth(300)
        self._build(staff_name)

    def _build(self, staff_name):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel(f"「{staff_name}」のパスワードを入力してください。"))

        self._pw = QLineEdit()
        self._pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw.setPlaceholderText("パスワード")
        self._pw.returnPressed.connect(self._ok)
        layout.addWidget(self._pw)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("ログイン")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._ok)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _ok(self):
        if not self._pw.text():
            QMessageBox.warning(self, "入力エラー", "パスワードを入力してください。")
            return
        self.accept()

    def password(self) -> str:
        return self._pw.text()


class ChangePasswordDialog(QDialog):
    """自分のパスワードを変更するダイアログ（ログイン済み状態で使用）。"""

    def __init__(self, staff_id: int, staff_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("パスワードの変更")
        self.setFixedWidth(340)
        self._staff_id = staff_id
        self._build(staff_name)

    def _build(self, staff_name):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel(f"「{staff_name}」のパスワードを変更します。"))

        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._cur = QLineEdit()
        self._cur.setEchoMode(QLineEdit.EchoMode.Password)
        self._new1 = QLineEdit()
        self._new1.setEchoMode(QLineEdit.EchoMode.Password)
        self._new2 = QLineEdit()
        self._new2.setEchoMode(QLineEdit.EchoMode.Password)
        self._new2.returnPressed.connect(self._ok)
        form.addRow("現在のパスワード：", self._cur)
        form.addRow("新しいパスワード：", self._new1)
        form.addRow("確認（再入力）：", self._new2)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("変更する")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._ok)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _ok(self):
        session = get_session()
        try:
            staff = get_staff(session, self._staff_id)
            if staff and staff.password_hash:
                if not verify_password(session, self._staff_id, self._cur.text()):
                    QMessageBox.warning(self, "認証エラー", "現在のパスワードが違います。")
                    self._cur.clear()
                    self._cur.setFocus()
                    return
            new1 = self._new1.text()
            new2 = self._new2.text()
            if not new1:
                QMessageBox.warning(self, "入力エラー", "新しいパスワードを入力してください。")
                return
            if new1 != new2:
                QMessageBox.warning(self, "入力エラー", "パスワードが一致しません。")
                self._new1.clear()
                self._new2.clear()
                self._new1.setFocus()
                return
            set_password(session, self._staff_id, new1)
        finally:
            session.close()
        QMessageBox.information(self, "完了", "パスワードを変更しました。")
        self.accept()


class LoginDialog(QDialog):
    def __init__(self, parent=None, skip_auto_login: bool = False):
        super().__init__(parent)
        self.setWindowTitle("ログイン")
        self.setFixedWidth(320)
        self._build()
        # ダイアログ表示直後に自動ログインを試みる（明示的ログアウト後はスキップ）
        if not skip_auto_login:
            QTimer.singleShot(0, self._try_auto_login)

    def _try_auto_login(self):
        """config に保存されたスタッフIDで自動ログイン"""
        staff_id = get_config().get("auto_login_staff_id")
        if not staff_id:
            return
        session = get_session()
        try:
            staff = get_staff(session, staff_id)
            if staff:
                current_user.set_current(staff.id, staff.name, bool(staff.is_admin))
                self.accept()
        except Exception:
            pass
        finally:
            session.close()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("担当者名")
        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setPlaceholderText("パスワード")
        self._pw_edit.returnPressed.connect(self._login)

        form.addRow("ID：", self._name_edit)
        form.addRow("パスワード：", self._pw_edit)
        layout.addLayout(form)

        self._remember = QCheckBox("次回から自動ログイン")
        self._remember.setChecked(bool(get_config().get("auto_login_staff_id")))
        layout.addWidget(self._remember)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn = QPushButton("ログイン")
        btn.setDefault(True)
        btn.clicked.connect(self._login)
        btn_row.addWidget(btn)
        layout.addLayout(btn_row)

    def _login(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "入力エラー", "IDを入力してください。")
            return

        session = get_session()
        staff_id = staff_name = staff_is_admin = None
        try:
            staff = next(
                (s for s in get_active_staff(session) if s.name == name), None
            )
            if staff is None:
                QMessageBox.warning(self, "認証エラー", "IDまたはパスワードが違います。")
                return

            if staff.password_hash is None:
                # 初回：パスワード設定
                dlg = _SetPasswordDialog(staff.name, self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    return
                set_password(session, staff.id, dlg.password())
            else:
                pw = self._pw_edit.text()
                if not pw:
                    QMessageBox.warning(self, "入力エラー", "パスワードを入力してください。")
                    return
                if not verify_password(session, staff.id, pw):
                    QMessageBox.warning(self, "認証エラー", "IDまたはパスワードが違います。")
                    self._pw_edit.clear()
                    self._pw_edit.setFocus()
                    return

            staff_id = staff.id
            staff_name = staff.name
            staff_is_admin = bool(staff.is_admin)
        finally:
            session.close()

        # 自動ログイン設定を保存 / 解除
        cfg = get_config()
        if self._remember.isChecked():
            cfg["auto_login_staff_id"] = staff_id
        else:
            cfg.pop("auto_login_staff_id", None)
        save_config(cfg)

        current_user.set_current(staff_id, staff_name, staff_is_admin)
        self.accept()
