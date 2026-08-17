# app/ui/main_window.py
from PyQt6.QtWidgets import (
    QDialog, QMainWindow, QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QMessageBox, QApplication,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QTimer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("商工会議所請求書・領収書発行システム")
        _screen = QApplication.primaryScreen()
        _avail = _screen.availableGeometry() if _screen else None
        _avail_w = _avail.width() if _avail else 1200
        _avail_h = _avail.height() if _avail else 800
        self.resize(min(1120, _avail_w), min(760, _avail_h))
        self.setMinimumSize(900, 600)
        self._manual_pane_override = False
        self._setup_menu()
        self._build_nav()
        self._setup_statusbar()
        QTimer.singleShot(0, self._run_auto_backup)

    def _setup_menu(self):
        from app.version import __version__
        menubar = self.menuBar()

        # ファイルメニュー
        file_menu = menubar.addMenu("ファイル")
        act_staff = QAction("担当者を変更...", self)
        act_staff.triggered.connect(self._change_staff)
        file_menu.addAction(act_staff)
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

    def _build_nav(self):
        """左ナビゲーション + QStackedWidget を構築する。

        ページ本体は従来のタブウィジェットをそのまま流用する。QStackedWidget は
        ページ切替時に QShowEvent を発行するため、各ページの showEvent による
        自動リロードは従来どおり機能する。
        """
        from app.ui.nav_shell import (
            NavRail, PageShell, COMPACT_THRESHOLD,
            GLYPH_DOCUMENT, GLYPH_LIST, GLYPH_MONEY, GLYPH_PRINT, GLYPH_EDIT,
            GLYPH_LIBRARY, GLYPH_MAIL, GLYPH_SETTINGS,
        )
        from app.ui.counter_issuance_tab import CounterIssuanceTab
        from app.ui.batch_issuance_tab import BatchIssuanceTab
        from app.ui.payment_dialog import PaymentManagementWidget
        from app.ui.label_issuance_tab import LabelIssuanceTab
        from app.ui.reissue_tab import ReissueWidget
        from app.ui.settings_tab import MasterTab, SettingsTab
        from app.ui.email_settings import EmailTemplateWidget
        from app.ui.update_banner import UpdateBanner

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._banner = UpdateBanner(self)
        outer.addWidget(self._banner)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, 1)

        # (見出し, グリフ, ページ本体) — 最後の「設定」はペイン下部に分離配置する
        pages = [
            ("単発発行",           GLYPH_DOCUMENT, CounterIssuanceTab),
            ("まとめて発行",       GLYPH_LIST,     BatchIssuanceTab),
            ("入金管理",           GLYPH_MONEY,    PaymentManagementWidget),
            ("宛名ラベル発行",     GLYPH_PRINT,    LabelIssuanceTab),
            ("修正・再発行",       GLYPH_EDIT,     ReissueWidget),
            ("登録・マスタ",       GLYPH_LIBRARY,  MasterTab),
            ("メールテンプレート", GLYPH_MAIL,     EmailTemplateWidget),
            ("設定",               GLYPH_SETTINGS, SettingsTab),
        ]

        self._nav = NavRail([(title, glyph) for title, glyph, _ in pages],
                            footer_count=1)
        body.addWidget(self._nav)

        self._stack = QStackedWidget()
        for title, _glyph, factory in pages:
            self._stack.addWidget(PageShell(title, factory()))
        self._stack.setCurrentIndex(0)
        body.addWidget(self._stack, 1)

        self._compact_threshold = COMPACT_THRESHOLD
        self._nav.currentChanged.connect(self._stack.setCurrentIndex)
        self._nav.toggleRequested.connect(self._toggle_pane)

    def _toggle_pane(self):
        """ハンバーガーボタンによる手動切替。以降は自動切替を抑止する。"""
        self._manual_pane_override = True
        self._nav.set_compact(not self._nav.is_compact())

    def resizeEvent(self, event):
        # NavigationView の Auto 相当：幅 1008px を境に展開／折りたたみを切り替える
        super().resizeEvent(event)
        if not self._manual_pane_override and hasattr(self, "_nav"):
            self._nav.set_compact(self.width() < self._compact_threshold)

    def _setup_statusbar(self):
        from app.version import __version__
        from app.utils import current_user
        sb = self.statusBar()  # 見た目は theme.py の QStatusBar 定義に従う
        # ログイン中ユーザー名
        user_name = current_user.get_name()
        if user_name:
            self._user_lbl = QLabel(f"👤 {user_name}")
            self._user_lbl.setStyleSheet("color: #475569; font-size: 12px; padding: 0 8px;")
            sb.addPermanentWidget(self._user_lbl)
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

    def _change_staff(self):
        from app.database.connection import get_session
        from app.services.staff_service import get_staff
        from app.ui.staff_selection_dialog import StaffSelectionDialog
        from app.utils import current_user
        from app.utils.app_config import get_config, save_config

        dlg = StaffSelectionDialog(self, current_user.get_id())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        staff_id = dlg.selected_staff_id()
        session = get_session()
        try:
            staff = get_staff(session, staff_id)
            if staff is None or not staff.is_active:
                QMessageBox.warning(self, "担当者の変更", "選択した担当者は使用できません。")
                return
            current_user.set_current(staff.id, staff.name, bool(staff.is_admin))
        finally:
            session.close()
        cfg = get_config()
        cfg["auto_login_staff_id"] = staff_id
        save_config(cfg)
        self._user_lbl.setText(f"👤 {current_user.get_name()}")
        QMessageBox.information(
            self,
            "担当者の変更",
            "担当者を変更しました。\n管理者向け画面の表示は次回起動時に反映されます。",
        )

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
