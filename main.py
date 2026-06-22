# main.py
import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QFont
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
    app.setFont(QFont("Meiryo UI", 10))

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
    session = get_session()
    try:
        has_staff = bool(get_active_staff(session))
    finally:
        session.close()

    if not has_staff:
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

    from app.ui.login_dialog import LoginDialog
    from app.ui.main_window import MainWindow
    from app.utils import current_user

    # ログイン→メインウィンドウのループ（ログアウト時に再ログインへ戻る）
    skip_auto_login = False
    while True:
        dlg = LoginDialog(skip_auto_login=skip_auto_login)
        if dlg.exec() != LoginDialog.DialogCode.Accepted:
            sys.exit(0)

        window = MainWindow()
        logged_out = False

        def _on_logout():
            nonlocal logged_out, skip_auto_login
            logged_out = True
            skip_auto_login = True  # ログアウト後は自動ログインをスキップ
            current_user.clear()
            window.close()
            app.quit()  # イベントループを確実に終了

        window.logout_requested.connect(_on_logout)
        window.show()
        app.exec()

        if not logged_out:
            # ウィンドウが閉じられた（アプリ終了）
            sys.exit(0)


if __name__ == "__main__":
    main()
