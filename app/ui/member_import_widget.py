# app/ui/member_import_widget.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QMessageBox,
    QDialog, QTableWidget, QTableWidgetItem, QComboBox,
    QHeaderView, QAbstractItemView, QFormLayout, QDialogButtonBox,
    QGroupBox, QScrollArea,
)
from PyQt6.QtCore import Qt


# ── CSVマッピングダイアログ ──────────────────────────────────────

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
        return {hdr: combo.currentData()
                for hdr, combo in self._combos.items()
                if combo.currentData()}


# ── 会員編集ダイアログ ────────────────────────────────────────────

class _MemberDialog(QDialog):
    _FIELDS = [
        ("member_number",       "会員番号"),
        ("organization_name",   "事業所名"),
        ("organization_kana",   "フリガナ（事業所）"),
        ("representative_name", "氏名"),
        ("representative_kana", "氏名フリガナ"),
        ("department",          "所属・役職"),
        ("phone",               "電話番号"),
        ("email",               "メール"),
        ("postal_code",         "郵便番号"),
        ("address",             "住所"),
        ("address2",            "住所2"),
    ]

    def __init__(self, parent=None, member=None):
        super().__init__(parent)
        self.setWindowTitle("会員の編集" if member else "会員の追加")
        self.resize(420, 380)
        self._edits: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(5)
        form.setHorizontalSpacing(10)

        for field, label in self._FIELDS:
            edit = QLineEdit()
            if member:
                edit.setText(getattr(member, field, "") or "")
            self._edits[field] = edit
            form.addRow(label, edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self):
        if not self._edits["organization_name"].text().strip() \
                and not self._edits["member_number"].text().strip():
            QMessageBox.warning(self, "入力エラー",
                                "事業所名または会員番号のどちらかを入力してください。")
            return
        self.accept()

    def values(self) -> dict[str, str]:
        return {f: e.text().strip() for f, e in self._edits.items()}


# ── 会員マスタ管理ウィジェット ────────────────────────────────────

_COLS = ["ID", "会員番号", "事業所名", "フリガナ", "氏名", "電話番号", "メール"]
_COL_FIELDS = ["id", "member_number", "organization_name",
               "organization_kana", "representative_name", "phone", "email"]

COL_ID   = 0
COL_NO   = 1
COL_ORG  = 2
COL_KANA = 3
COL_NAME = 4
COL_TEL  = 5
COL_MAIL = 6


class MemberImportWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._file_path = ""
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 検索バー
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("事業所名・フリガナ・会員番号で検索…")
        self._search.textChanged.connect(self._on_search)
        search_row.addWidget(self._search, 1)
        self._count_label = QLabel()
        self._count_label.setStyleSheet("color:#555;")
        search_row.addWidget(self._count_label)
        root.addLayout(search_row)

        # テーブル
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_ID,   QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_ID, 40)
        hdr.setSectionResizeMode(COL_NO,   QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_ORG,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_KANA, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_KANA, 130)
        hdr.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_NAME, 100)
        hdr.setSectionResizeMode(COL_TEL,  QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_TEL, 110)
        hdr.setSectionResizeMode(COL_MAIL, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(COL_MAIL, 160)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.doubleClicked.connect(self._edit)
        root.addWidget(self._table, 1)

        # ボタン行
        btn_row = QHBoxLayout()
        btn_add  = QPushButton("追加")
        btn_edit = QPushButton("編集")
        btn_del  = QPushButton("削除")
        btn_add.clicked.connect(self._add)
        btn_edit.clicked.connect(self._edit)
        btn_del.clicked.connect(self._delete)
        for b in (btn_add, btn_edit, btn_del):
            btn_row.addWidget(b)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # CSVインポートセクション
        grp = QGroupBox("CSVインポート（全削除→再登録）")
        grp_layout = QVBoxLayout(grp)
        grp_layout.setSpacing(6)
        desc = QLabel(
            "CSVから一括登録します。実行すると既存データがすべて削除されます。\n"
            "対応ヘッダー例：会員番号・事業所名・フリガナ・氏名・電話番号・メール・郵便番号・住所")
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#555; font-size:11px;")
        grp_layout.addWidget(desc)

        file_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("CSVファイルを選択してください")
        btn_browse = QPushButton("ファイルを選択…")
        btn_browse.clicked.connect(self._browse)
        file_row.addWidget(self._path_edit, 1)
        file_row.addWidget(btn_browse)
        grp_layout.addLayout(file_row)

        import_row = QHBoxLayout()
        self._btn_import = QPushButton("インポート実行")
        self._btn_import.setEnabled(False)
        self._btn_import.setStyleSheet(
            "QPushButton:enabled { background:#1D4ED8; color:white; "
            "border-radius:4px; font-weight:bold; padding:4px 14px; }"
            "QPushButton:disabled { background:#ccc; color:#666; "
            "border-radius:4px; padding:4px 14px; }"
        )
        self._btn_import.clicked.connect(self._do_import)
        self._import_result = QLabel("")
        import_row.addWidget(self._btn_import)
        import_row.addWidget(self._import_result, 1)
        grp_layout.addLayout(import_row)
        root.addWidget(grp)

    # ── データ読み込み ─────────────────────────────────────────

    def _load(self, query: str = ""):
        from app.database.connection import get_session
        from app.services.member_service import get_all_members, search_members, count_members
        session = get_session()
        try:
            total = count_members(session)
            if query:
                members = search_members(session, query, limit=500)
            else:
                members = get_all_members(session)
            self._fill_table(members)
            shown = len(members)
            self._count_label.setText(
                f"表示：{shown:,} 件 / 全{total:,} 件" if query
                else f"全{total:,} 件")
        finally:
            session.close()

    def _fill_table(self, members):
        self._table.setRowCount(0)
        for m in members:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, field in enumerate(_COL_FIELDS):
                val = str(getattr(m, field, "") or "")
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, m.id)
                self._table.setItem(row, col, item)
        self._table.resizeRowsToContents()

    def _on_search(self, text: str):
        self._load(text.strip())

    def _selected_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, COL_ID)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ── CRUD ──────────────────────────────────────────────────

    def _add(self):
        dlg = _MemberDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        from app.database.connection import get_session
        from app.services.member_service import create_member
        session = get_session()
        try:
            create_member(session, **dlg.values())
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            return
        finally:
            session.close()
        self._load(self._search.text().strip())

    def _edit(self):
        mid = self._selected_id()
        if mid is None:
            QMessageBox.warning(self, "未選択", "編集する会員を選択してください。")
            return
        from app.database.connection import get_session
        from app.services.member_service import get_member, update_member
        session = get_session()
        try:
            m = get_member(session, mid)
            if m is None:
                return
            dlg = _MemberDialog(self, member=m)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            update_member(session, mid, **dlg.values())
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            return
        finally:
            session.close()
        self._load(self._search.text().strip())

    def _delete(self):
        mid = self._selected_id()
        if mid is None:
            QMessageBox.warning(self, "未選択", "削除する会員を選択してください。")
            return
        row = self._table.currentRow()
        name = self._table.item(row, COL_ORG).text() or self._table.item(row, COL_NAME).text()
        if QMessageBox.question(
                self, "削除の確認",
                f"「{name}」を削除します。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        from app.database.connection import get_session
        from app.services.member_service import delete_member
        session = get_session()
        try:
            delete_member(session, mid)
        finally:
            session.close()
        self._load(self._search.text().strip())

    # ── CSVインポート ──────────────────────────────────────────

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "CSVファイルを選択", "", "CSVファイル (*.csv);;すべてのファイル (*)"
        )
        if path:
            self._file_path = path
            self._path_edit.setText(path)
            self._btn_import.setEnabled(True)
            self._import_result.setText("")

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
            self._import_result.setText(f"完了：{count:,} 件を登録しました。")
            self._import_result.setStyleSheet("color:green; font-weight:bold;")
        except Exception as e:
            self._import_result.setText(f"エラー：{e}")
            self._import_result.setStyleSheet("color:red;")
        finally:
            session.close()
        self._load(self._search.text().strip())
