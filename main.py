# main.py
import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QFont, QFontInfo
from app.ui.theme import STYLESHEET


def _excepthook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(msg, file=sys.stderr)
    try:
        QMessageBox.critical(None, "予期しないエラー", str(exc_value))
    except Exception:
        pass


def main():
    sys.excepthook = _excepthook
    app = QApplication(sys.argv)
    app.setApplicationName("商工会議所請求書・領収書発行システム")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    # Windows 11 の日本語 UI 標準フォント。無い環境では Meiryo UI にフォールバックする。
    _ui_font = QFont("Yu Gothic UI", 10)
    _ui_font.setStyleStrategy(QFont.StyleStrategy.PreferDefault)
    if not QFontInfo(_ui_font).family().startswith("Yu Gothic"):
        _ui_font = QFont("Meiryo UI", 10)
    app.setFont(_ui_font)

    from app.utils.app_config import is_first_run
    if is_first_run():
        from app.ui.first_run_wizard import FirstRunWizard
        wiz = FirstRunWizard()
        if wiz.exec() != FirstRunWizard.DialogCode.Accepted:
            sys.exit(0)

    from app.database.connection import init_db
    from app.ui.first_run_wizard import FirstRunWizard
    while True:
        try:
            init_db()
            break
        except Exception as e:
            QMessageBox.critical(None, "DB接続エラー",
                f"データベースに接続できませんでした。\n\n{e}\n\n設定を確認してください。")
            dlg = FirstRunWizard()
            if dlg.exec() != FirstRunWizard.DialogCode.Accepted:
                sys.exit(0)

    from app.database.connection import get_session
    from app.services.staff_service import get_active_staff
    from app.utils import current_user
    from app.utils.app_config import get_config
    session = get_session()
    try:
        active_staff = get_active_staff(session)
    finally:
        session.close()

    if not active_staff:
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel
        from app.ui.staff_management import StaffManagementWidget
        dlg = QDialog()
        dlg.setWindowTitle("スタッフ登録")
        dlg.setFixedSize(600, 400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("最初にスタッフを登録してください。"))
        layout.addWidget(StaffManagementWidget())
        btn = QPushButton("完了")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec()

        session = get_session()
        try:
            active_staff = get_active_staff(session)
        finally:
            session.close()

    # 社内専用アプリのためパスワード認証は行わない。端末に保存された担当者が
    # なければ、初回だけ担当者を選択してもらう。
    preferred_id = get_config().get("auto_login_staff_id")
    staff = next((s for s in active_staff if s.id == preferred_id), None)
    if staff is None:
        from app.ui.staff_selection_dialog import StaffSelectionDialog
        dlg = StaffSelectionDialog()
        if dlg.exec() != StaffSelectionDialog.DialogCode.Accepted:
            sys.exit(0)
        selected_id = dlg.selected_staff_id()
        staff = next((s for s in active_staff if s.id == selected_id), None)
        if staff is None:
            sys.exit(0)
        cfg = get_config()
        cfg["auto_login_staff_id"] = staff.id
        from app.utils.app_config import save_config
        save_config(cfg)
    current_user.set_current(staff.id, staff.name, bool(staff.is_admin))

    from app.ui.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
