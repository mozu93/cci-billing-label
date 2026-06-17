# app/ui/member_import_widget.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QMessageBox,
    QDialog, QTableWidget, QTableWidgetItem, QComboBox,
    QHeaderView, QAbstractItemView,
)


class MemberMappingDialog(QDialog):
    """CSVヘッダー → DBフィールドのマッピングを確認・編集するダイアログ。"""

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("列マッピングの確認")
        self.setMinimumSize(680, 440)
        self._combos: dict[str, QComboBox] = {}

        from app.services.member_service import (
            read_csv_headers_and_preview, detect_mapping, _FIELD_LABELS,
        )
        try:
            headers, preview = read_csv_headers_and_preview(file_path)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"CSVの読み込みに失敗しました：{e}")
            self._headers: list[str] = []
            self._build([], [], {}, {})
            return

        self._headers = headers
        auto_mapping = detect_mapping(headers)
        self._build(headers, preview, auto_mapping, _FIELD_LABELS)

    def _build(self, headers, preview, auto_mapping, field_labels):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        desc = QLabel(
            "CSVの各列をどのフィールドに取り込むか確認・変更してください。\n"
            "不要な列は「（対象外）」のままにしてください。\n"
            "※ インポートすると既存データがすべて削除されてから再登録されます。"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        table = QTableWidget(len(headers), 3)
        table.setHorizontalHeaderLabels(["CSV列名", "取り込み先", "サンプル値"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setDefaultSectionSize(160)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)

        field_options = [("（対象外）", "")] + [
            (label, field) for field, label in field_labels.items()
        ]

        for row, hdr in enumerate(headers):
            table.setItem(row, 0, QTableWidgetItem(hdr))

            combo = QComboBox()
            combo.setStyleSheet("QComboBox { min-height: 0; padding: 1px 4px; }")
            for label, field in field_options:
                combo.addItem(label, field)
            detected = auto_mapping.get(hdr, "")
            for i in range(combo.count()):
                if combo.itemData(i) == detected:
                    combo.setCurrentIndex(i)
                    break
            self._combos[hdr] = combo
            table.setCellWidget(row, 1, combo)

            sample = (preview[0].get(hdr) or "").strip() if preview else ""
            table.setItem(row, 2, QTableWidgetItem(sample))

        table.resizeRowsToContents()

        layout.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("インポート実行")
        btn_ok.setStyleSheet(
            "QPushButton { background: #1D4ED8; color: white; border-radius: 4px; "
            "font-weight: bold; padding: 6px 18px; }"
        )
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def get_mapping(self) -> dict[str, str]:
        """確定したマッピング {csv_header: field_name}（対象外は除外）。"""
        return {hdr: combo.currentData()
                for hdr, combo in self._combos.items()
                if combo.currentData()}


class MemberImportWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._file_path = ""
        self._build()
        self._refresh_count()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        desc = QLabel(
            "CSVファイルから会員データ（約4,000件）を一括登録します。\n"
            "インポートを実行すると既存データは全削除されてから再登録されます。\n\n"
            "対応ヘッダー例：会員番号・事業所名・フリガナ・氏名・氏名フリガナ・"
            "電話番号・メール・郵便番号・住所・住所2"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        file_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("CSVファイルを選択してください")
        btn_browse = QPushButton("ファイルを選択…")
        btn_browse.clicked.connect(self._browse)
        file_row.addWidget(self._path_edit, 1)
        file_row.addWidget(btn_browse)
        layout.addLayout(file_row)

        self._btn_import = QPushButton("インポート（全削除→再登録）")
        self._btn_import.setFixedHeight(36)
        self._btn_import.setEnabled(False)
        self._btn_import.setStyleSheet(
            "QPushButton:enabled { background: #1D4ED8; color: white; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:disabled { background: #ccc; color: #666; border-radius: 4px; }"
        )
        self._btn_import.clicked.connect(self._do_import)
        layout.addWidget(self._btn_import)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #555;")
        layout.addWidget(self._count_label)

        self._result_label = QLabel("")
        layout.addWidget(self._result_label)

        layout.addStretch()

    def _refresh_count(self):
        from app.database.connection import get_session
        from app.services.member_service import count_members
        session = get_session()
        try:
            n = count_members(session)
        finally:
            session.close()
        self._count_label.setText(f"現在の登録件数：{n:,} 件")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "CSVファイルを選択", "", "CSVファイル (*.csv);;すべてのファイル (*)"
        )
        if path:
            self._file_path = path
            self._path_edit.setText(path)
            self._btn_import.setEnabled(True)
            self._result_label.setText("")

    def _do_import(self):
        if not self._file_path:
            return
        dlg = MemberMappingDialog(self._file_path, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        mapping = dlg.get_mapping()
        if not mapping:
            QMessageBox.warning(self, "警告", "取り込み先が1つも設定されていません。")
            return
        from app.database.connection import get_session
        from app.services.member_service import import_from_csv_with_mapping
        session = get_session()
        try:
            count = import_from_csv_with_mapping(session, self._file_path, mapping)
            self._result_label.setText(f"インポート完了：{count:,} 件を登録しました。")
            self._result_label.setStyleSheet("color: green; font-weight: bold;")
        except Exception as e:
            self._result_label.setText(f"エラー：{e}")
            self._result_label.setStyleSheet("color: red;")
        finally:
            session.close()
        self._refresh_count()
