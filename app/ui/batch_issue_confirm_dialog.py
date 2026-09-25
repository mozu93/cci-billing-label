# app/ui/batch_issue_confirm_dialog.py
"""まとめて発行：「発行する」で、発行方法と支払期日（領収書は発行日）を確かめる。

発行の設定に置いていたときは、メール送付のまま押すといきなり送信画面になり、
支払期日も入力し忘れやすかった。発行のたびにここで決める。
"""
from datetime import date

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QButtonGroup, QDateEdit, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout,
    QLabel, QRadioButton, QVBoxLayout,
)


class BatchIssueConfirmDialog(QDialog):
    def __init__(self, parent, count: int, doc_type: str, delivery: str,
                 doc_date: date):
        super().__init__(parent)
        label = "請求書" if doc_type == "invoice" else "領収書"
        self.setWindowTitle(f"{label}の発行")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        self._message = QLabel(f"チェックした {count} 件の{label}を発行します。")
        self._message.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._message)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.addWidget(QLabel("発行方法："), 0, 0)
        self._print_radio = QRadioButton("印刷")
        self._mail_radio = QRadioButton("メール送付")
        group = QButtonGroup(self)
        group.addButton(self._print_radio)
        group.addButton(self._mail_radio)
        (self._mail_radio if delivery == "メール送付" else self._print_radio).setChecked(True)
        radios = QHBoxLayout()
        radios.addWidget(self._print_radio)
        radios.addSpacing(16)
        radios.addWidget(self._mail_radio)
        radios.addStretch()
        grid.addLayout(radios, 0, 1)

        self._date_label = QLabel("支払期日：" if doc_type == "invoice" else "発行日：")
        grid.addWidget(self._date_label, 1, 0)
        self._date_edit = QDateEdit(QDate(doc_date.year, doc_date.month, doc_date.day))
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy/MM/dd")
        grid.addWidget(self._date_edit, 1, 1)
        layout.addLayout(grid)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("発行する")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def delivery(self) -> str:
        return "メール送付" if self._mail_radio.isChecked() else "印刷"

    def doc_date(self) -> date:
        return self._date_edit.date().toPyDate()
