# app/ui/email_settings.py
from PyQt6.QtCore import QEvent, QThread, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.email_service import (
    PLACEHOLDER_DESCRIPTIONS,
    PLACEHOLDER_KEYS,
    create_email_template,
    delete_email_template,
    get_email_templates,
    rename_email_template,
    save_email_template,
    set_default_email_template,
)
from app.utils.app_config import (
    get_m365_account_username,
    get_m365_client_id,
    get_m365_sender_address,
    get_m365_test_recipient,
    get_m365_tenant_id,
    save_m365_config,
)


class EmailTemplateWidget(QWidget):
    """請求書・領収書・督促メールの文面を管理する独立画面。"""

    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        heading = QLabel("メールテンプレート")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)
        description = QLabel(
            "請求書・領収書・督促メールの件名と本文を設定します。"
            "差し込みタグは送信時に請求先や発行元の実データへ置き換わります。")
        description.setWordWrap(True)
        description.setStyleSheet("color: #555;")
        layout.addWidget(description)

        editor_group = QGroupBox("テンプレート編集")
        editor_form = QFormLayout(editor_group)
        editor_form.setVerticalSpacing(8)
        editor_form.setHorizontalSpacing(10)

        self._tmpl_type = QComboBox()
        self._tmpl_type.addItem("請求書メール", "invoice")
        self._tmpl_type.addItem("領収書メール", "receipt")
        self._tmpl_type.addItem("督促メール（支払期限超過）", "reminder")
        self._template_choice = QComboBox()
        self._template_choice.currentIndexChanged.connect(
            self._on_template_changed)
        new_button = QPushButton("新規作成")
        new_button.clicked.connect(self._new_template)
        rename_button = QPushButton("名前変更")
        rename_button.clicked.connect(self._rename_template)
        delete_button = QPushButton("削除")
        delete_button.clicked.connect(self._delete_template)
        default_button = QPushButton("既定に設定")
        default_button.clicked.connect(self._set_default_template)
        template_actions = QGridLayout()
        template_actions.setContentsMargins(0, 0, 0, 0)
        template_actions.setHorizontalSpacing(8)
        template_actions.setVerticalSpacing(6)
        template_actions.addWidget(new_button, 0, 0)
        template_actions.addWidget(rename_button, 0, 1)
        template_actions.addWidget(delete_button, 1, 0)
        template_actions.addWidget(default_button, 1, 1)
        template_actions.setColumnStretch(0, 1)
        template_actions.setColumnStretch(1, 1)
        self._tmpl_subject = QLineEdit()
        self._tmpl_body = QTextEdit()
        self._tmpl_body.setAcceptRichText(False)
        self._tmpl_body.setMinimumHeight(390)
        self._tmpl_body.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._tmpl_subject.installEventFilter(self)
        self._tmpl_body.installEventFilter(self)
        self._last_template_editor = self._tmpl_body

        editor_form.addRow("対象メール", self._tmpl_type)
        editor_form.addRow("テンプレート", self._template_choice)
        editor_form.addRow("操作", template_actions)
        editor_form.addRow("件名", self._tmpl_subject)
        editor_form.addRow("本文", self._tmpl_body)

        tag_group = QGroupBox("差し込みタグ（ダブルクリックで挿入）")
        tag_layout = QVBoxLayout(tag_group)
        tag_note = QLabel(
            "タグをダブルクリックすると、最後に選択した件名または本文の"
            "カーソル位置へ挿入します。")
        tag_note.setWordWrap(True)
        tag_note.setStyleSheet("color: #555;")
        tag_layout.addWidget(tag_note)

        self._tag_table = QTableWidget(0, 2)
        self._tag_table.setHorizontalHeaderLabels(
            ["差し込みタグ", "送信時に置き換わる内容"])
        self._tag_table.verticalHeader().setVisible(False)
        self._tag_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._tag_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._tag_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._tag_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._tag_table.setMinimumHeight(390)
        self._tag_table.itemDoubleClicked.connect(self._insert_tag)
        tag_layout.addWidget(self._tag_table)

        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.addWidget(editor_group)
        content_splitter.addWidget(tag_group)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 2)
        content_splitter.setSizes([560, 400])
        layout.addWidget(content_splitter, 1)

        button_row = QHBoxLayout()
        save_button = QPushButton("このテンプレートを保存")
        save_button.setToolTip("現在表示している件名と本文を保存します")
        save_button.clicked.connect(self._save_current_template)
        button_row.addWidget(save_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        self._tmpl_type.currentIndexChanged.connect(
            self._on_tmpl_type_changed)

    def _load(self):
        self._cur_tmpl_key = self._tmpl_type.currentData()
        self._reload_template_choices()
        self._refresh_tag_table()

    def _on_tmpl_type_changed(self):
        self._cur_tmpl_key = self._tmpl_type.currentData()
        self._reload_template_choices()
        self._refresh_tag_table()

    def _reload_template_choices(self, select_id: str | None = None):
        self._template_choice.blockSignals(True)
        self._template_choice.clear()
        templates = get_email_templates(self._cur_tmpl_key)
        for template in templates:
            label = (
                "★ " + template["name"]
                if template["is_default"] else template["name"])
            self._template_choice.addItem(label, template)
        index = 0
        if select_id:
            for candidate in range(self._template_choice.count()):
                if (self._template_choice.itemData(candidate)["id"]
                        == select_id):
                    index = candidate
                    break
        else:
            for candidate in range(self._template_choice.count()):
                if self._template_choice.itemData(candidate)["is_default"]:
                    index = candidate
                    break
        self._template_choice.setCurrentIndex(index)
        self._template_choice.blockSignals(False)
        self._show_selected_template()

    def _selected_template(self) -> dict | None:
        return self._template_choice.currentData()

    def _show_selected_template(self):
        template = self._selected_template()
        if not template:
            self._tmpl_subject.clear()
            self._tmpl_body.clear()
            return
        self._tmpl_subject.setText(template["subject"])
        self._tmpl_body.setPlainText(template["body"])

    def _on_template_changed(self):
        self._show_selected_template()

    def eventFilter(self, watched, event):
        if (
            watched in (self._tmpl_subject, self._tmpl_body)
            and event.type() == QEvent.Type.FocusIn
        ):
            self._last_template_editor = watched
        return super().eventFilter(watched, event)

    def _refresh_tag_table(self):
        keys = list(PLACEHOLDER_KEYS)
        if self._cur_tmpl_key == "reminder":
            keys.append("支払期限")
        self._tag_table.setRowCount(len(keys))
        for row, key in enumerate(keys):
            tag = "{" + key + "}"
            tag_item = QTableWidgetItem(tag)
            description_item = QTableWidgetItem(
                PLACEHOLDER_DESCRIPTIONS[key])
            tag_item.setData(Qt.ItemDataRole.UserRole, tag)
            description_item.setData(Qt.ItemDataRole.UserRole, tag)
            self._tag_table.setItem(row, 0, tag_item)
            self._tag_table.setItem(row, 1, description_item)

    def _insert_tag(self, item):
        tag = item.data(Qt.ItemDataRole.UserRole) or item.text()
        target = self._last_template_editor
        if target is self._tmpl_subject:
            cursor = target.cursorPosition()
            text = target.text()
            target.setText(text[:cursor] + tag + text[cursor:])
            target.setCursorPosition(cursor + len(tag))
        else:
            target.insertPlainText(tag)
        target.setFocus()

    def _save_current_template(self):
        template = self._selected_template()
        subject = self._tmpl_subject.text().strip()
        body = self._tmpl_body.toPlainText()
        if not template or not subject or not body.strip():
            QMessageBox.warning(
                self, "テンプレート保存", "件名と本文を入力してください。")
            return
        save_email_template(
            self._cur_tmpl_key,
            subject,
            body,
            template_id=template["id"],
        )
        self._reload_template_choices(template["id"])
        QMessageBox.information(
            self, "テンプレート保存",
            f"「{template['name']}」を保存しました。")

    def _new_template(self):
        name, ok = QInputDialog.getText(
            self, "テンプレート新規作成", "テンプレート名：")
        name = name.strip()
        if not ok or not name:
            return
        template_id = create_email_template(
            self._cur_tmpl_key,
            name,
            self._tmpl_subject.text().strip(),
            self._tmpl_body.toPlainText(),
        )
        self._reload_template_choices(template_id)

    def _rename_template(self):
        template = self._selected_template()
        if not template:
            return
        name, ok = QInputDialog.getText(
            self,
            "テンプレート名変更",
            "新しいテンプレート名：",
            text=template["name"],
        )
        name = name.strip()
        if not ok or not name:
            return
        rename_email_template(
            self._cur_tmpl_key, template["id"], name)
        self._reload_template_choices(template["id"])

    def _delete_template(self):
        template = self._selected_template()
        if not template:
            return
        answer = QMessageBox.question(
            self,
            "テンプレート削除",
            f"「{template['name']}」を削除しますか？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_email_template(self._cur_tmpl_key, template["id"])
        except ValueError as exc:
            QMessageBox.warning(self, "テンプレート削除", str(exc))
            return
        self._reload_template_choices()

    def _set_default_template(self):
        template = self._selected_template()
        if not template:
            return
        set_default_email_template(
            self._cur_tmpl_key, template["id"])
        self._reload_template_choices(template["id"])
        QMessageBox.information(
            self, "既定テンプレート",
            f"「{template['name']}」を既定に設定しました。")


class EmailSettingsWidget(QWidget):
    """Microsoft 365の接続・送信アカウント設定。"""

    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        group = QGroupBox("Microsoft 365 メール送信（Graph API）")
        form = QFormLayout(group)
        form.setVerticalSpacing(6)
        form.setHorizontalSpacing(8)

        self._m365_client_id = QLineEdit()
        self._m365_client_id.setPlaceholderText(
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        self._m365_tenant_id = QLineEdit()
        self._m365_tenant_id.setPlaceholderText(
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        self._m365_account = QComboBox()
        self._m365_account.setMinimumWidth(240)
        self._m365_sender = QLineEdit()
        self._m365_sender.setPlaceholderText(
            "空欄：送信アカウント本人／入力：代理送信元アドレス")
        self._test_recipient = QLineEdit()
        self._test_recipient.setPlaceholderText("テストメールの受信先")

        sign_in_button = QPushButton("サインイン／確認")
        sign_in_button.clicked.connect(self._sign_in)
        sign_out_button = QPushButton("サインアウト")
        sign_out_button.clicked.connect(self._sign_out)
        account_row = QHBoxLayout()
        account_row.addWidget(self._m365_account, 1)
        account_row.addWidget(sign_in_button)
        account_row.addWidget(sign_out_button)

        test_button = QPushButton("テストメール送信")
        test_button.clicked.connect(self._send_test_mail)
        test_row = QHBoxLayout()
        test_row.addWidget(self._test_recipient, 1)
        test_row.addWidget(test_button)

        note = QLabel(
            "請求書・領収書・督促メールの送信と発行通知に使います。\n"
            "Microsoft Entra ID でアプリ登録（Public Client）と Mail.Send "
            "権限が必要です。\n"
            "代理送信には Mail.Send.Shared と、対象メールボックス側の"
            "「差出人として送信」または「代理人として送信」権限も必要です。\n"
            "OAuthトークンはWindowsの暗号化機能を使って保存します。\n"
            "メール本文はメイン画面の「メールテンプレート」で設定します。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-size: 11px;")

        form.addRow("アプリケーション (クライアント) ID",
                    self._m365_client_id)
        form.addRow("ディレクトリ (テナント) ID", self._m365_tenant_id)
        form.addRow("送信アカウント", account_row)
        form.addRow("代理送信元", self._m365_sender)
        form.addRow("テスト送信先", test_row)
        form.addRow("", note)
        layout.addWidget(group)

        button_row = QHBoxLayout()
        save_button = QPushButton("メール送信設定を保存")
        save_button.clicked.connect(self._save)
        button_row.addWidget(save_button)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addStretch()

    def _load(self):
        self._m365_client_id.setText(get_m365_client_id())
        self._m365_tenant_id.setText(get_m365_tenant_id())
        self._refresh_accounts(get_m365_account_username())
        self._m365_sender.setText(get_m365_sender_address())
        self._test_recipient.setText(get_m365_test_recipient())

    def _m365_ids(self) -> tuple[str, str]:
        return (
            self._m365_client_id.text().strip(),
            self._m365_tenant_id.text().strip(),
        )

    def _refresh_accounts(self, preferred: str = ""):
        self._m365_account.clear()
        client_id, tenant_id = self._m365_ids()
        if client_id and tenant_id:
            try:
                from app.services.m365_auth_service import M365AuthService
                self._m365_account.addItems(
                    M365AuthService(client_id, tenant_id).get_cached_accounts())
            except Exception:
                pass
        if preferred and self._m365_account.findText(preferred) < 0:
            self._m365_account.addItem(preferred)
        if preferred:
            self._m365_account.setCurrentText(preferred)

    def _sign_in(self):
        client_id, tenant_id = self._m365_ids()
        if not client_id or not tenant_id:
            QMessageBox.warning(
                self, "入力エラー",
                "Client ID と Tenant ID を入力してからサインインしてください。")
            return
        try:
            from app.services.m365_auth_service import M365AuthService
            service = M365AuthService(
                client_id,
                tenant_id,
                include_shared=bool(self._m365_sender.text().strip()),
            )
            _token, username = service.acquire_token_with_account(
                force_interactive=True)
        except Exception as exc:
            QMessageBox.critical(self, "Microsoft 365 認証", str(exc))
            return
        self._refresh_accounts(username)
        save_m365_config(client_id, tenant_id, username)
        QMessageBox.information(
            self, "Microsoft 365 認証",
            f"送信アカウントを確認しました。\n\n{username}")

    def _sign_out(self):
        client_id, tenant_id = self._m365_ids()
        if not client_id or not tenant_id:
            return
        try:
            from app.services.m365_auth_service import M365AuthService
            M365AuthService(client_id, tenant_id).sign_out()
        except Exception as exc:
            QMessageBox.critical(self, "サインアウト", str(exc))
            return
        self._m365_account.clear()
        save_m365_config(client_id, tenant_id, "")
        QMessageBox.information(self, "サインアウト", "認証情報を削除しました。")

    def _save_m365_fields(self) -> None:
        save_m365_config(
            self._m365_client_id.text().strip(),
            self._m365_tenant_id.text().strip(),
            self._m365_account.currentText().strip(),
            self._m365_sender.text().strip(),
            self._test_recipient.text().strip(),
        )

    def _send_test_mail(self):
        client_id, tenant_id = self._m365_ids()
        recipient = self._test_recipient.text().strip()
        if not client_id or not tenant_id:
            QMessageBox.warning(
                self, "入力エラー",
                "Client ID と Tenant ID を入力してください。")
            return
        try:
            from app.services.email_service import validate_email_addr
            recipient = validate_email_addr(recipient)
        except ValueError as exc:
            QMessageBox.warning(self, "入力エラー", str(exc))
            return

        self._save_m365_fields()
        sender = self._m365_sender.text().strip()
        sender_label = sender or self._m365_account.currentText().strip()
        body = (
            "<div style='font-family:sans-serif;font-size:14px;line-height:1.8;'>"
            "<p>CCI請求書発行システムからのテストメールです。</p>"
            f"<p>送信元：{sender_label}</p>"
            "<p>このメールを受信できれば、メール送信設定は正常です。</p>"
            "</div>"
        )
        from app.ui.m365_mail_worker import M365MailWorker
        thread = QThread(self)
        worker = M365MailWorker(
            client_id, tenant_id, [recipient],
            "【CCI請求書発行システム】テストメール",
            body, sender_address=sender,
        )
        worker.moveToThread(thread)
        progress = QProgressDialog(
            "テストメールを送信しています…", None, 0, 0, self)
        progress.setWindowTitle("テストメール")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        result: dict = {}

        def _done(value):
            result["ok"] = value
            thread.quit()

        def _failed(message):
            result["error"] = message
            thread.quit()

        worker.finished.connect(_done)
        worker.failed.connect(_failed)
        thread.started.connect(worker.run)
        thread.finished.connect(progress.close)
        thread.start()
        while thread.isRunning():
            QApplication.processEvents()
        thread.deleteLater()

        if "ok" in result:
            QMessageBox.information(
                self, "テストメール",
                f"テストメールを送信しました。\n宛先：{recipient}\n"
                f"送信元：{sender_label}")
        else:
            QMessageBox.critical(
                self, "テストメール送信失敗",
                result.get("error", "不明なエラー"))

    def _save(self):
        self._save_m365_fields()
        QMessageBox.information(
            self, "保存", "メール送信設定を保存しました。")
