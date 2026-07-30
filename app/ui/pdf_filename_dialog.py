from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout,
)


_FIELDS = (
    ("roster_no", "名簿NO.（ファイル名は番号のみ）"),
    ("organization", "事業所名"),
    ("issued_date", "発行日"),
    ("doc_number", "管理番号"),
    ("amount", "請求金額"),
)


class PdfFilenameDialog(QDialog):
    """PDFファイル名に含める項目を選択するダイアログ。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDFファイル名の設定")
        self.setFixedWidth(390)

        from app.utils.app_config import get_config
        selected = get_config().get("pdf_filename_fields", ["doc_number"])

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "ファイル名に含める項目を選択してください。\n"
            "選択した項目は「_」で連結されます。"))

        self._checks = {}
        for key, label in _FIELDS:
            chk = QCheckBox(label)
            chk.setChecked(key in selected)
            chk.toggled.connect(self._update_preview)
            self._checks[key] = chk
            layout.addWidget(chk)

        self._preview = QLabel()
        self._preview.setStyleSheet(
            "background: #F8FAFC; border: 1px solid #E2E8F0;"
            " border-radius: 4px; padding: 8px;")
        layout.addWidget(QLabel("例："))
        layout.addWidget(self._preview)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("キャンセル")
        cancel.clicked.connect(self.reject)
        save = QPushButton("設定を保存")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self._update_preview()

    def selected_fields(self) -> list[str]:
        return [key for key, _ in _FIELDS if self._checks[key].isChecked()]

    def _update_preview(self):
        from app.utils.pdf_helpers import build_pdf_filename

        class _Example:
            roster_no = "12"
            recipient_organization = "〇〇商事"
            recipient_name = "山田太郎"
            issued_at = None
            doc_number = "INV-202607-0001"
            amount = 11000

        self._preview.setText(build_pdf_filename(
            _Example(), fields=self.selected_fields(),
            issued_date="20260730"))

    def _save(self):
        fields = self.selected_fields()
        if not fields:
            QMessageBox.warning(self, "設定エラー", "項目を1つ以上選択してください。")
            return
        from app.utils.app_config import get_config, save_config
        cfg = get_config()
        cfg["pdf_filename_fields"] = fields
        save_config(cfg)
        self.accept()
