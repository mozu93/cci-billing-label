# app/ui/invoice_mail_confirm_dialog.py
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel,
    QTextBrowser, QDialogButtonBox,
)
from PyQt6.QtCore import Qt


class InvoiceMailConfirmDialog(QDialog):
    """送信前確認ダイアログ。OK を押すと accept() される。"""

    def __init__(
        self,
        parent=None,
        sender:         str = "",
        to_recipients:  list[str] | None = None,
        cc_recipients:  list[str] | None = None,
        bcc_recipients: list[str] | None = None,
        subject:        str = "",
        body_html:      str = "",
        pdf_path:       str = "",
        invoice_no:     str = "",
        customer_name:  str = "",
        amount_text:    str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("請求書メール送信確認")
        self.resize(700, 580)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        to_recipients  = to_recipients  or []
        cc_recipients  = cc_recipients  or []
        bcc_recipients = bcc_recipients or []

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(4)

        def _lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setWordWrap(True)
            return l

        form.addRow("送信者（M365）", _lbl(sender or "サインイン中のユーザー"))
        form.addRow("宛先",         _lbl(", ".join(to_recipients)))
        if cc_recipients:
            form.addRow("CC",       _lbl(", ".join(cc_recipients)))
        if bcc_recipients:
            form.addRow("BCC",      _lbl(", ".join(bcc_recipients)))
        form.addRow("件名",         _lbl(subject))
        form.addRow("添付PDF",      _lbl(Path(pdf_path).name if pdf_path else ""))
        if invoice_no:
            form.addRow("請求書番号", _lbl(invoice_no))
        if customer_name:
            form.addRow("請求先",    _lbl(customer_name))
        if amount_text:
            form.addRow("金額",      _lbl(amount_text))

        layout.addLayout(form)

        layout.addWidget(QLabel("本文プレビュー："))
        browser = QTextBrowser()
        browser.setHtml(body_html)
        browser.setMinimumHeight(200)
        layout.addWidget(browser)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("送信する")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
