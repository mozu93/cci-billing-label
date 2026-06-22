# app/ui/first_run_wizard.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QMessageBox, QFormLayout
)
from app.utils.app_config import save_config


class FirstRunWizard(QDialog):
    def __init__(self, parent=None, is_initial_setup: bool = True):
        super().__init__(parent)
        self._is_initial_setup = is_initial_setup
        self.setWindowTitle("初期設定")
        self.setFixedSize(480, 340)
        self._build()
        self._load_current_config()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("データベースの接続先を設定してください。"))

        self._db_type = QComboBox()
        self._db_type.addItems(["PostgreSQL（複数人共有）", "SQLite（個人使用・開発用）"])
        self._db_type.currentIndexChanged.connect(self._on_type_change)

        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._host = QLineEdit("localhost")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(5432)
        self._database = QLineEdit("cci_billing")
        self._user = QLineEdit("postgres")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("DB種別", self._db_type)
        form.addRow("ホスト", self._host)
        form.addRow("ポート", self._port)
        form.addRow("データベース名", self._database)
        form.addRow("ユーザー名", self._user)
        form.addRow("パスワード", self._password)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_test = QPushButton("接続テスト")
        btn_test.clicked.connect(self._test_connection)
        btn_label = "保存して開始" if self._is_initial_setup else "保存"
        btn_ok = QPushButton(btn_label)
        btn_ok.clicked.connect(self._save)
        btn_row.addWidget(btn_test)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _load_current_config(self):
        """現在の設定をフォームに反映する。"""
        from app.utils.app_config import get_config
        config = get_config()
        db_type = config.get("db_type", "postgresql")
        if db_type == "postgresql":
            self._db_type.setCurrentIndex(0)
            self._host.setText(config.get("host", "localhost"))
            self._port.setValue(config.get("port", 5432))
            self._database.setText(config.get("database", "cci_billing"))
            self._user.setText(config.get("user", "postgres"))
            self._password.setText(config.get("password", ""))
        else:
            self._db_type.setCurrentIndex(1)
            self._on_type_change(1)

    def _on_type_change(self, index):
        is_pg = index == 0
        for w in [self._host, self._port, self._database, self._user, self._password]:
            w.setEnabled(is_pg)

    def _build_config(self) -> dict:
        """既存の設定にDBキーのみマージして返す（他の設定を消さない）。"""
        from app.utils.app_config import get_config
        config = get_config()  # 既存設定をベースにする
        if self._db_type.currentIndex() == 0:
            config.update({
                "db_type": "postgresql",
                "host": self._host.text().strip(),
                "port": self._port.value(),
                "database": self._database.text().strip(),
                "user": self._user.text().strip(),
                "password": self._password.text(),
                "db_configured": True,
            })
        else:
            config["db_type"] = "sqlite"
            config["db_configured"] = True
            for key in ["host", "port", "database", "user", "password"]:
                config.pop(key, None)
        return config

    def _test_connection(self):
        config = self._build_config()
        save_config(config)
        try:
            from app.database.connection import init_db
            init_db()
            QMessageBox.information(self, "成功", "接続に成功しました。")
        except Exception as e:
            QMessageBox.critical(self, "接続エラー", str(e))

    def _save(self):
        config = self._build_config()
        save_config(config)
        try:
            from app.database.connection import init_db
            init_db()
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"DB初期化に失敗しました：\n{e}")
            return
        if not self._is_initial_setup:
            QMessageBox.information(
                self, "保存完了",
                "DB接続設定を保存しました。\n"
                "設定変更を反映するにはアプリの再起動が必要な場合があります。",
            )
        self.accept()
