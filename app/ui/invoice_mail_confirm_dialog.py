# app/ui/invoice_mail_confirm_dialog.py
from pathlib import Path
import html
import re

from PyQt6.QtCore import QEvent, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
)


class InvoiceMailConfirmDialog(QDialog):
    """タグ付きテンプレートの編集・プレビューを行う送信前確認画面。"""

    def __init__(
        self,
        parent=None,
        sender: str = "",
        to_recipients: list[str] | None = None,
        cc_recipients: list[str] | None = None,
        bcc_recipients: list[str] | None = None,
        subject: str = "",
        body_html: str = "",
        pdf_path: str = "",
        invoice_no: str = "",
        customer_name: str = "",
        amount_text: str = "",
        template_kind: str = "",
        template_context: dict[str, str] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("請求書メール送信確認")
        self.resize(1180, 800)
        self.setMinimumSize(960, 680)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._template_kind = template_kind
        self._template_context = template_context or {}
        self._pdf_path = pdf_path
        self._available_templates: list[dict] = []

        to_recipients = to_recipients or []
        cc_recipients = cc_recipients or []
        bcc_recipients = bcc_recipients or []

        if not sender:
            from app.utils.app_config import get_m365_account_username
            sender = get_m365_account_username()

        # 書類種別が分かる場合、表示・編集するのは差し込み前テンプレート。
        if template_kind:
            from app.services.email_service import get_email_templates
            self._available_templates = get_email_templates(template_kind)
            selected = next(
                (item for item in self._available_templates
                 if item["is_default"]),
                self._available_templates[0],
            )
            subject = selected["subject"]
            template_body = selected["body"]
        else:
            probe = QTextEdit()
            probe.setHtml(body_html)
            template_body = probe.toPlainText()
            probe.deleteLater()

        layout = QVBoxLayout(self)
        address_form = QFormLayout()
        address_form.setHorizontalSpacing(12)
        address_form.setVerticalSpacing(4)

        def _label(value: str) -> QLabel:
            widget = QLabel(value)
            widget.setWordWrap(True)
            return widget

        self._to_edit = QLineEdit(", ".join(to_recipients))
        self._cc_edit = QLineEdit(", ".join(cc_recipients))
        self._bcc_edit = QLineEdit(", ".join(bcc_recipients))
        address_form.addRow(
            "送信者（M365）", _label(sender or "サインイン中のユーザー"))
        address_form.addRow("宛先", self._to_edit)
        address_form.addRow("CC", self._cc_edit)
        address_form.addRow("BCC", self._bcc_edit)

        pdf_row = QHBoxLayout()
        pdf_row.addWidget(_label(Path(pdf_path).name if pdf_path else ""), 1)
        self._pdf_preview_button = QPushButton("請求書PDFをプレビュー")
        self._pdf_preview_button.setEnabled(bool(pdf_path))
        self._pdf_preview_button.clicked.connect(self._open_pdf_preview)
        pdf_row.addWidget(self._pdf_preview_button)
        address_form.addRow("添付PDF", pdf_row)
        if invoice_no:
            address_form.addRow("請求書番号", _label(invoice_no))
        if customer_name:
            address_form.addRow("請求先", _label(customer_name))
        if amount_text:
            address_form.addRow("金額", _label(amount_text))
        layout.addLayout(address_form)

        editor_group = QGroupBox("送信テンプレート（タグの状態で編集）")
        editor_form = QFormLayout(editor_group)
        self._template_choice = QComboBox()
        for template in self._available_templates:
            label = (
                "★ " + template["name"]
                if template["is_default"] else template["name"])
            self._template_choice.addItem(label, template)
        if self._available_templates:
            default_index = next(
                (index for index, template
                 in enumerate(self._available_templates)
                 if template["is_default"]),
                0,
            )
            self._template_choice.setCurrentIndex(default_index)
        self._subject_edit = QLineEdit(subject)
        self._body_edit = QTextEdit()
        self._body_edit.setAcceptRichText(False)
        self._body_edit.setPlainText(template_body)
        self._body_edit.setMinimumHeight(230)
        self._subject_edit.installEventFilter(self)
        self._body_edit.installEventFilter(self)
        self._last_template_editor = self._body_edit

        self._tag_table = QTableWidget(0, 2)
        self._tag_table.setHorizontalHeaderLabels(
            ["タグ", "送信時に置き換わる内容"])
        self._tag_table.verticalHeader().setVisible(False)
        self._tag_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._tag_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._tag_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._tag_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._tag_table.setMinimumHeight(170)
        self._tag_table.setMaximumHeight(190)
        self._tag_table.setToolTip(
            "タグをダブルクリックすると、件名または本文のカーソル位置へ挿入します")
        self._tag_table.itemDoubleClicked.connect(self._insert_tag)
        from app.services.email_service import (
            PLACEHOLDER_DESCRIPTIONS,
            PLACEHOLDER_KEYS,
        )
        self._tag_table.setRowCount(len(PLACEHOLDER_KEYS))
        for row, key in enumerate(PLACEHOLDER_KEYS):
            tag = "{" + key + "}"
            tag_item = QTableWidgetItem(tag)
            description_item = QTableWidgetItem(
                PLACEHOLDER_DESCRIPTIONS[key])
            tag_item.setData(Qt.ItemDataRole.UserRole, tag)
            description_item.setData(Qt.ItemDataRole.UserRole, tag)
            self._tag_table.setItem(row, 0, tag_item)
            self._tag_table.setItem(row, 1, description_item)

        tag_help = QLabel(
            "タグをダブルクリックすると、最後に選択した件名または本文へ"
            "挿入できます。右側のプレビューには実データが表示されます。")
        tag_help.setWordWrap(True)
        tag_help.setStyleSheet("color: #666; font-size: 11px;")
        if self._available_templates:
            editor_form.addRow("使用テンプレート", self._template_choice)
        editor_form.addRow("件名", self._subject_edit)
        editor_form.addRow("本文", self._body_edit)
        editor_form.addRow("差し込みタグ", self._tag_table)
        editor_form.addRow("", tag_help)

        preview_group = QGroupBox("本文プレビュー（実データ差し込み後）")
        preview_layout = QFormLayout(preview_group)
        self._preview_subject = QLineEdit()
        self._preview_subject.setReadOnly(True)
        self._preview_body = QTextBrowser()
        self._preview_body.setMinimumHeight(420)
        preview_layout.addRow("件名", self._preview_subject)
        preview_layout.addRow("本文", self._preview_body)

        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.addWidget(editor_group)
        content_splitter.addWidget(preview_group)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setSizes([550, 550])
        layout.addWidget(content_splitter, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("送信する")
        buttons.button(
            QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        if self._template_kind:
            self._save_template_button = QPushButton(
                "件名・本文をテンプレート保存")
            self._save_template_button.clicked.connect(self._save_template)
            buttons.addButton(
                self._save_template_button,
                QDialogButtonBox.ButtonRole.ActionRole,
            )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._subject_edit.textChanged.connect(self._update_preview)
        # document の変更を直接監視し、入力・貼り付け・タグ挿入を即時反映する。
        self._body_edit.document().contentsChanged.connect(
            self._update_preview)
        self._template_choice.currentIndexChanged.connect(
            self._on_template_changed)
        self._update_preview()

    @staticmethod
    def _split_addresses(value: str) -> list[str]:
        return [
            address.strip()
            for address in re.split(r"[,;\n]+", value or "")
            if address.strip()
        ]

    def to_recipients(self) -> list[str]:
        return self._split_addresses(self._to_edit.text())

    def cc_recipients(self) -> list[str]:
        return self._split_addresses(self._cc_edit.text())

    def bcc_recipients(self) -> list[str]:
        return self._split_addresses(self._bcc_edit.text())

    def template_subject(self) -> str:
        return self._subject_edit.text().strip()

    def template_body(self) -> str:
        return self._body_edit.toPlainText()

    def _render(self, value: str) -> str:
        from app.services.email_service import render_email_template
        return render_email_template(value, self._template_context)

    def subject(self) -> str:
        return self._render(self.template_subject())

    def rendered_body(self) -> str:
        return self._render(self.template_body())

    def body_html(self) -> str:
        return (
            "<div style='font-family:sans-serif; font-size:14px; "
            "line-height:1.8;'>"
            + html.escape(self.rendered_body()).replace("\n", "<br>")
            + "</div>"
        )

    def eventFilter(self, watched, event):
        if (
            watched in (self._subject_edit, self._body_edit)
            and event.type() == QEvent.Type.FocusIn
        ):
            self._last_template_editor = watched
        return super().eventFilter(watched, event)

    def _insert_tag(self, item) -> None:
        tag = item.data(Qt.ItemDataRole.UserRole) or item.text()
        target = self._last_template_editor
        if target is self._subject_edit:
            cursor = target.cursorPosition()
            text = target.text()
            target.setText(text[:cursor] + tag + text[cursor:])
            target.setCursorPosition(cursor + len(tag))
        else:
            target.insertPlainText(tag)
        target.setFocus()

    def _update_preview(self) -> None:
        self._preview_subject.setText(self.subject())
        self._preview_body.setPlainText(self.rendered_body())

    def _on_template_changed(self) -> None:
        template = self._template_choice.currentData()
        if not template:
            return
        self._subject_edit.setText(template["subject"])
        self._body_edit.setPlainText(template["body"])

    def _open_pdf_preview(self) -> None:
        path = Path(self._pdf_path)
        if not path.is_file():
            QMessageBox.warning(
                self, "PDFプレビュー",
                "プレビューする請求書PDFが見つかりません。")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(
                self, "PDFプレビュー",
                "請求書PDFを開けませんでした。")

    def _save_template(self) -> None:
        subject = self.template_subject()
        body = self.template_body()
        if not subject or not body.strip():
            QMessageBox.warning(
                self, "入力エラー",
                "テンプレートとして保存する件名と本文を入力してください。")
            return
        answer = QMessageBox.question(
            self,
            "テンプレート保存",
            "現在のタグ付き件名と本文を、次回以降の標準テンプレートとして"
            "保存しますか？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        from app.services.email_service import save_email_template
        selected = self._template_choice.currentData()
        save_email_template(
            self._template_kind,
            subject,
            body,
            template_id=selected["id"] if selected else None,
        )
        if selected:
            selected["subject"] = subject
            selected["body"] = body
            self._template_choice.setItemData(
                self._template_choice.currentIndex(), selected)
        QMessageBox.information(
            self, "テンプレート保存",
            "件名と本文のテンプレートを保存しました。")

    def _accept(self) -> None:
        recipients = (
            [("宛先", address) for address in self.to_recipients()]
            + [("CC", address) for address in self.cc_recipients()]
            + [("BCC", address) for address in self.bcc_recipients()]
        )
        if not self.to_recipients():
            QMessageBox.warning(self, "入力エラー", "宛先を入力してください。")
            return
        try:
            from app.utils.mail_validator import validate_email_address
            for field, address in recipients:
                validate_email_address(address, field)
        except ValueError as exc:
            QMessageBox.warning(self, "入力エラー", str(exc))
            return
        if not self.template_subject():
            QMessageBox.warning(self, "入力エラー", "件名を入力してください。")
            return
        if not self.template_body().strip():
            QMessageBox.warning(self, "入力エラー", "本文を入力してください。")
            return

        answer = QMessageBox.question(
            self,
            "メール送信確認",
            "プレビューの内容でメールを送信しますか？\n\n"
            f"宛先：{', '.join(self.to_recipients())}\n"
            f"件名：{self.subject()}\n"
            f"添付：{Path(self._pdf_path).name if self._pdf_path else 'なし'}",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.accept()
