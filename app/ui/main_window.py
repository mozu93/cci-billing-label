# app/ui/main_window.py
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel, QMessageBox,
    QApplication,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import pyqtSignal, QTimer


class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("商工会議所請求書・領収書発行システム")
        _screen = QApplication.primaryScreen()
        _avail_h = _screen.availableGeometry().height() if _screen else 800
        self.resize(900, min(728, _avail_h))
        self.setMinimumSize(780, 500)
        self._setup_menu()
        self._build_tabs()
        self._setup_statusbar()
        QTimer.singleShot(0, self._run_auto_backup)

    def _setup_menu(self):
        from app.version import __version__
        menubar = self.menuBar()

        # ファイルメニュー
        file_menu = menubar.addMenu("ファイル")
        act_logout = QAction("ログアウト", self)
        act_logout.setShortcut("Ctrl+Shift+L")
        act_logout.triggered.connect(self._logout)
        file_menu.addAction(act_logout)
        file_menu.addSeparator()
        act_db = QAction("初期設定（DB接続設定）...", self)
        act_db.triggered.connect(self._open_db_settings)
        file_menu.addAction(act_db)
        file_menu.addSeparator()
        act_exit = QAction("終了", self)
        act_exit.setShortcut("Alt+F4")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # ヘルプメニュー
        help_menu = menubar.addMenu("ヘルプ")
        act_manual = QAction("使い方マニュアル", self)
        act_manual.triggered.connect(self._open_manual)
        help_menu.addAction(act_manual)
        help_menu.addSeparator()
        act_about = QAction("バージョン情報", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _open_manual(self):
        import os, sys
        from pathlib import Path
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).parent.parent.parent
        manual = base / "docs" / "manual" / "manual.html"
        if manual.exists():
            os.startfile(str(manual))
        else:
            QMessageBox.warning(self, "マニュアル", f"マニュアルファイルが見つかりません:\n{manual}")

    def _build_tabs(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from app.ui.update_banner import UpdateBanner
        self._banner = UpdateBanner(self)
        layout.addWidget(self._banner)

        tabs = QTabWidget()

        from app.ui.counter_issuance_tab import CounterIssuanceTab
        tabs.addTab(CounterIssuanceTab(), "単発発行")

        from app.ui.batch_issuance_tab import BatchIssuanceTab
        tabs.addTab(BatchIssuanceTab(), "まとめて発行")

        from app.ui.label_issuance_tab import LabelIssuanceTab
        tabs.addTab(LabelIssuanceTab(), "宛名ラベル発行")

        from app.ui.reissue_tab import ReissueWidget
        tabs.addTab(ReissueWidget(), "修正・再発行")

        from app.ui.settings_tab import MasterTab, SettingsTab
        tabs.addTab(MasterTab(), "登録・マスタ")
        tabs.addTab(SettingsTab(), "設定")

        tabs.setCurrentIndex(0)
        layout.addWidget(tabs)

    def _setup_statusbar(self):
        from app.version import __version__
        from app.utils import current_user
        sb = self.statusBar()
        sb.setStyleSheet(
            "QStatusBar { background: #F8FAFC; border-top: 1px solid #E2E8F0; "
            "font-size: 12px; color: #64748B; }"
            "QStatusBar::item { border: none; }"
        )
        # ログイン中ユーザー名
        user_name = current_user.get_name()
        if user_name:
            user_lbl = QLabel(f"👤 {user_name}")
            user_lbl.setStyleSheet("color: #475569; font-size: 12px; padding: 0 8px;")
            sb.addPermanentWidget(user_lbl)
        ver_lbl = QLabel(f"v{__version__}")
        ver_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; padding: 0 8px;")
        sb.addPermanentWidget(ver_lbl)
        sb.showMessage("準備完了")

    def _run_auto_backup(self):
        from pathlib import Path
        from app.services.backup_service import auto_backup_if_needed
        try:
            path = auto_backup_if_needed()
            if path:
                self.statusBar().showMessage(
                    f"自動バックアップ完了: {Path(path).name}", 5000
                )
        except Exception:
            pass  # 自動バックアップ失敗はサイレント

    def _logout(self):
        reply = QMessageBox.question(
            self,
            "ログアウト",
            "ログアウトしてログイン画面に戻りますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.logout_requested.emit()

    def _open_db_settings(self):
        from app.ui.first_run_wizard import FirstRunWizard
        dlg = FirstRunWizard(parent=self, is_initial_setup=False)
        dlg.exec()

    def _show_about(self):
        from app.version import __version__
        QMessageBox.about(
            self,
            "バージョン情報",
            f"<b>CCI請求書システム</b><br>"
            f"バージョン {__version__}<br><br>"
            f"商工会議所向け請求書・領収書発行システムです。",
        )
