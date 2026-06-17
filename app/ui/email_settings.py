# app/ui/email_settings.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QSpinBox, QCheckBox, QComboBox, QTextEdit,
    QPushButton, QGroupBox, QMessageBox
)
from app.utils.app_config import get_config, save_config
from app.services.email_service import (
    _TEMPLATE_DEFAULTS, PLACEHOLDER_KEYS
)


class EmailSettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        grp = QGroupBox("SMTP設定")
        form = QFormLayout(grp)
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._host = QLineEdit()
        self._host.setPlaceholderText("例：smtp.gmail.com")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(587)
        self._user = QLineEdit()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._from_addr = QLineEdit()
        self._from_name = QLineEdit()
        self._use_tls = QCheckBox("STARTTLS を使用")
        self._use_tls.setChecked(True)
        self._test_addr = QLineEdit()
        form.addRow("SMTPサーバー", self._host)
        form.addRow("ポート", self._port)
        form.addRow("ユーザー名", self._user)
        form.addRow("パスワード", self._password)
        form.addRow("送信元アドレス", self._from_addr)
        form.addRow("送信者名", self._from_name)
        form.addRow("", self._use_tls)
        form.addRow("テスト送信先", self._test_addr)
        layout.addWidget(grp)

        grp_t = QGroupBox("送信メールテンプレート")
        tform = QFormLayout(grp_t)
        tform.setVerticalSpacing(3)
        tform.setHorizontalSpacing(8)
        self._tmpl_type = QComboBox()
        self._tmpl_type.addItem("請求書", "invoice")
        self._tmpl_type.addItem("領収書", "receipt")
        self._tmpl_type.addItem("督促（支払期限超過）", "reminder")
        self._tmpl_type.currentIndexChanged.connect(self._on_tmpl_type_changed)
        self._tmpl_subject = QLineEdit()
        self._tmpl_body = QTextEdit()
        self._tmpl_body.setAcceptRichText(False)
        self._tmpl_body.setMinimumHeight(150)
        help_lbl = QLabel(
            "差し込みタグ："
            + "　".join("{" + k + "}" for k in PLACEHOLDER_KEYS)
            + "　{支払期限}（督促のみ）"
            + "\n発行時に各宛先の情報に置き換えられます。"
        )
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #666; font-size: 11px;")
        tform.addRow("対象書類", self._tmpl_type)
        tform.addRow("件名", self._tmpl_subject)
        tform.addRow("本文", self._tmpl_body)
        tform.addRow("", help_lbl)
        layout.addWidget(grp_t)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("設定を保存")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        btn_test = QPushButton("テストメール送信")
        btn_test.clicked.connect(self._test)
        btn_row.addWidget(btn_test)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _load(self):
        smtp = get_config().get("smtp", {})
        self._host.setText(smtp.get("host", ""))
        self._port.setValue(int(smtp.get("port", 587)))
        self._user.setText(smtp.get("user", ""))
        self._password.setText(smtp.get("password", ""))
        self._from_addr.setText(smtp.get("from_addr", ""))
        self._from_name.setText(smtp.get("from_name", ""))
        self._use_tls.setChecked(smtp.get("use_tls", True))
        self._test_addr.setText(smtp.get("test_addr", ""))

        saved = get_config().get("email_templates", {})
        self._tmpl_data = {}
        for key, (d_subject, d_body) in _TEMPLATE_DEFAULTS.items():
            t = saved.get(key, {})
            self._tmpl_data[key] = {
                "subject": t.get("subject") or d_subject,
                "body": t.get("body") or d_body,
            }
        self._cur_tmpl_key = self._tmpl_type.currentData()
        self._show_tmpl(self._cur_tmpl_key)

    def _show_tmpl(self, key: str):
        self._tmpl_subject.setText(self._tmpl_data[key]["subject"])
        self._tmpl_body.setPlainText(self._tmpl_data[key]["body"])

    def _stash_tmpl(self):
        self._tmpl_data[self._cur_tmpl_key] = {
            "subject": self._tmpl_subject.text().strip(),
            "body": self._tmpl_body.toPlainText(),
        }

    def _on_tmpl_type_changed(self):
        self._stash_tmpl()
        self._cur_tmpl_key = self._tmpl_type.currentData()
        self._show_tmpl(self._cur_tmpl_key)

    def _save(self):
        config = get_config()
        config["smtp"] = {
            "host": self._host.text().strip(),
            "port": self._port.value(),
            "user": self._user.text().strip(),
            "password": self._password.text(),
            "from_addr": self._from_addr.text().strip(),
            "from_name": self._from_name.text().strip(),
            "use_tls": self._use_tls.isChecked(),
            "test_addr": self._test_addr.text().strip(),
        }
        self._stash_tmpl()
        config["email_templates"] = self._tmpl_data
        save_config(config)
        QMessageBox.information(self, "保存", "メール設定を保存しました。")

    def _test(self):
        self._save()
        try:
            from app.services.email_service import send_test_email
            send_test_email("テスト送信", "cci-billingからのテストメールです。")
            QMessageBox.information(self, "成功", "テストメールを送信しました。")
        except Exception as e:
            QMessageBox.critical(self, "送信エラー", str(e))
