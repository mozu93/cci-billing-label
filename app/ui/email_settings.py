# app/ui/email_settings.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QTextEdit,
    QPushButton, QGroupBox, QMessageBox
)
from app.utils.app_config import (
    get_config, save_config,
    get_m365_client_id, get_m365_tenant_id, save_m365_config,
)
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

        grp_m365 = QGroupBox("Microsoft 365 メール送信（Graph API）")
        m365_form = QFormLayout(grp_m365)
        m365_form.setVerticalSpacing(3)
        m365_form.setHorizontalSpacing(8)

        self._m365_client_id = QLineEdit()
        self._m365_client_id.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        self._m365_tenant_id = QLineEdit()
        self._m365_tenant_id.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")

        m365_note = QLabel(
            "請求書・領収書・督促メールの送信と発行通知に使います。\n"
            "Microsoft Entra ID でアプリ登録（Public Client）と Mail.Send 権限が必要です。\n"
            "発行通知の送信先は「設定 → 職員管理」の所属長メールで職員ごとに設定します。"
        )
        m365_note.setWordWrap(True)
        m365_note.setStyleSheet("color: #666; font-size: 11px;")

        m365_form.addRow("アプリケーション (クライアント) ID", self._m365_client_id)
        m365_form.addRow("ディレクトリ (テナント) ID",       self._m365_tenant_id)
        m365_form.addRow("", m365_note)
        layout.addWidget(grp_m365)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("設定を保存")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _load(self):
        self._m365_client_id.setText(get_m365_client_id())
        self._m365_tenant_id.setText(get_m365_tenant_id())

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
        self._stash_tmpl()
        config["email_templates"] = self._tmpl_data
        save_config(config)
        save_m365_config(
            self._m365_client_id.text().strip(),
            self._m365_tenant_id.text().strip(),
        )
        QMessageBox.information(self, "保存", "メール設定を保存しました。")
