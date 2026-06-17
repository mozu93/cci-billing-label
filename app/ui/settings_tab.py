# app/ui/settings_tab.py
from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QPushButton, QLabel, QMessageBox,
)
from PyQt6.QtCore import Qt


class MasterTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        inner = QTabWidget()

        from app.ui.staff_management import StaffManagementWidget
        from app.ui.category_management import CategoryManagementWidget
        from app.ui.item_template_management import ItemTemplateManagementWidget
        from app.ui.member_import_widget import MemberImportWidget

        inner.addTab(StaffManagementWidget(), "スタッフ管理")
        inner.addTab(CategoryManagementWidget(), "業務名")
        inner.addTab(ItemTemplateManagementWidget(), "請求項目テンプレート")
        inner.addTab(MemberImportWidget(), "会員マスタ")

        layout.addWidget(inner)


class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        inner = QTabWidget()

        from app.ui.company_settings import CompanySettingsWidget
        from app.ui.email_settings import EmailSettingsWidget
        from app.ui.backup_settings import BackupSettingsWidget
        from app.ui.operation_log_tab import OperationLogWidget
        from app.utils import current_user

        inner.addTab(CompanySettingsWidget(), "発行元情報")
        inner.addTab(EmailSettingsWidget(), "メール設定")
        inner.addTab(BackupSettingsWidget(), "バックアップ")
        inner.addTab(OperationLogWidget(), "操作ログ")

        if current_user.is_admin():
            inner.addTab(_AdminWidget(), "管理者")

        layout.addWidget(inner)


_RED_BTN = (
    "QPushButton { background: #dc2626; color: white; "
    "border: none; padding: 6px 18px; border-radius: 4px; font-weight: bold; }"
    "QPushButton:hover { background: #b91c1c; }"
)
_ORANGE_BTN = (
    "QPushButton { background: #ea580c; color: white; "
    "border: none; padding: 6px 18px; border-radius: 4px; font-weight: bold; }"
    "QPushButton:hover { background: #c2410c; }"
)


def _make_group(title: str, description: str, btn_label: str,
                btn_style: str, slot) -> QGroupBox:
    grp = QGroupBox(title)
    lay = QVBoxLayout(grp)
    lay.setSpacing(8)
    desc = QLabel(description)
    desc.setStyleSheet("color: #555; font-size: 12px;")
    desc.setWordWrap(True)
    lay.addWidget(desc)
    btn_row = QHBoxLayout()
    btn = QPushButton(btn_label)
    btn.setStyleSheet(btn_style)
    btn.clicked.connect(slot)
    btn_row.addWidget(btn)
    btn_row.addStretch()
    lay.addLayout(btn_row)
    return grp


class _AdminWidget(QWidget):
    """管理者専用タブ：開発・運用向けデータ操作を提供する。"""

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)
        root.setSpacing(16)
        root.setContentsMargins(16, 16, 16, 16)

        root.addWidget(_make_group(
            "発行番号リセット",
            "発行済み書類（請求書・領収書）と入金記録のみを削除します。\n"
            "次に発行すると番号が 0001 から振り直されます。\n"
            "案件・名簿・会員マスタ・発行元情報・スタッフ・テンプレートは保持されます。",
            "発行番号をリセットする",
            _ORANGE_BTN,
            self._on_reset_numbers,
        ))

        root.addWidget(_make_group(
            "全データ削除",
            "発行元情報（会社情報・銀行口座・印鑑）以外のすべてのデータを削除します。\n"
            "スタッフ・業務名・テンプレート・案件・名簿・発行書類・会員マスタがすべて消えます。",
            "全データを削除する",
            _RED_BTN,
            self._on_delete_all,
        ))

        root.addWidget(_make_group(
            "業務データ初期化",
            "案件・発行書類・入金記録・会員マスタ・操作ログを削除します。\n"
            "スタッフ・発行元情報・業務名・テンプレートは保持されます。",
            "業務データを初期化する",
            _RED_BTN,
            self._on_init_clicked,
        ))

    # ── 発行番号リセット ────────────────────────────────────────
    def _on_reset_numbers(self):
        ans = QMessageBox.warning(
            self, "発行番号リセットの確認",
            "発行済み書類と入金記録をすべて削除します。\n番号は次回発行時に 0001 から始まります。\n\n実行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._exec_delete(
            ["payments", "issuance_lines", "issuances"],
            "発行番号リセット完了",
            "発行書類と入金記録を削除しました。",
        )

    # ── 全データ削除 ────────────────────────────────────────────
    def _on_delete_all(self):
        ans = QMessageBox.warning(
            self, "全データ削除の確認",
            "発行元情報以外のすべてのデータを削除します。\n"
            "（スタッフ・業務名・テンプレート・案件・名簿・発行書類・会員マスタ）\n\n実行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._exec_delete(
            [
                "payments", "issuance_lines", "issuances",
                "project_members", "project_templates", "projects",
                "members", "operation_logs",
                "item_templates", "categories", "staff",
            ],
            "全データ削除完了",
            "発行元情報以外のデータをすべて削除しました。\nアプリを再起動することを推奨します。",
        )

    # ── 業務データ初期化（既存機能） ────────────────────────────
    def _on_init_clicked(self):
        ans = QMessageBox.warning(
            self, "業務データ初期化の確認",
            "案件・発行書類・入金記録・会員マスタ・操作ログを削除します。\n\n実行しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._exec_delete(
            [
                "payments", "issuance_lines", "issuances",
                "project_members", "project_templates", "projects",
                "members", "operation_logs",
            ],
            "初期化完了",
            "業務データを初期化しました。\nアプリを再起動することを推奨します。",
        )

    # ── 共通削除処理 ────────────────────────────────────────────
    def _exec_delete(self, tables: list[str], ok_title: str, ok_msg: str):
        from app.database.connection import get_session
        from sqlalchemy import text
        session = get_session()
        try:
            for tbl in tables:
                session.execute(text(f"DELETE FROM {tbl}"))
            session.commit()
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "削除エラー", f"削除中にエラーが発生しました。\n{e}")
            return
        finally:
            session.close()
        QMessageBox.information(self, ok_title, ok_msg)
