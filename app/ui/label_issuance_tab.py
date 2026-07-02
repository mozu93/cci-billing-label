# app/ui/label_issuance_tab.py
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QComboBox, QLineEdit, QMessageBox,
    QCheckBox, QPlainTextEdit, QAbstractItemDelegate, QStyledItemDelegate,
)
from PyQt6.QtCore import Qt, QTimer

from app.database.connection import get_session
from app.services.project_service import get_projects, get_project_members
from app.services.category_service import get_active_categories

COL_CHK  = 0
COL_NUM  = 1   # 会員番号（編集不可）
COL_ORG  = 2   # 事業所名（Alt+Enter 折り返し可）
COL_KANA = 3   # フリガナ（編集不可）
COL_REP  = 4   # 代表者名（Alt+Enter 折り返し可）
COL_DEPT = 5   # 役職・所属（Alt+Enter 折り返し可）
COL_POST = 6   # 郵便番号（編集不可）
COL_ADDR = 7   # 住所（編集可）

_HEADERS = ["", "会員番号", "事業所名", "フリガナ", "代表者名", "役職・所属", "郵便番号", "住所"]

LABEL_MODES = [
    ("宛名（氏名あり）", "normal"),
    ("宛名（氏名なし）", "no_person"),
    ("事業所名のみ",     "simple"),
    ("名札",            "nametag"),
]

# ソート対象列 → _rows_data キーのマッピング
_SORT_KEYS = {
    COL_NUM:  "member_number",
    COL_ORG:  "org_name",
    COL_KANA: "org_kana",
    COL_REP:  "rep_name",
    COL_DEPT: "dept",
    COL_POST: "postal_code",
    COL_ADDR: "address",
}


class _MultilineDelegate(QStyledItemDelegate):
    """Alt+Enter で改行を挿入できるセル用デリゲート"""

    def createEditor(self, parent, option, index):
        editor = QPlainTextEdit(parent)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setStyleSheet("background: white; border: 1px solid #2563EB;")
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):
        editor.setPlainText(index.data(Qt.ItemDataRole.EditRole) or "")
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.toPlainText(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def displayText(self, value, locale):
        return (value or "").replace("\n", " ｜ ")

    def eventFilter(self, obj, event):
        if isinstance(obj, QPlainTextEdit) and event.type() == event.Type.KeyPress:
            key  = event.key()
            mods = event.modifiers()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if mods & Qt.KeyboardModifier.AltModifier:
                    obj.insertPlainText("\n")
                    return True
                self.commitData.emit(obj)
                self.closeEditor.emit(obj, QAbstractItemDelegate.EndEditHint.NoHint)
                return True
            if key == Qt.Key.Key_Tab:
                self.commitData.emit(obj)
                self.closeEditor.emit(obj, QAbstractItemDelegate.EndEditHint.NoHint)
                return True
        return super().eventFilter(obj, event)


class _CheckableTable(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_checked_row = -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self.indexAt(event.pos())
            if idx.isValid() and idx.column() == COL_CHK:
                item = self.item(idx.row(), COL_CHK)
                if item and (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                    if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                            and self._last_checked_row >= 0):
                        new_state = (Qt.CheckState.Unchecked
                                     if item.checkState() == Qt.CheckState.Checked
                                     else Qt.CheckState.Checked)
                        r1 = min(self._last_checked_row, idx.row())
                        r2 = max(self._last_checked_row, idx.row())
                        self.blockSignals(True)
                        for r in range(r1, r2 + 1):
                            it = self.item(r, COL_CHK)
                            if it:
                                it.setCheckState(new_state)
                        self.blockSignals(False)
                        self._last_checked_row = idx.row()
                        return
                    else:
                        self._last_checked_row = idx.row()
        super().mousePressEvent(event)


class LabelIssuanceTab(QWidget):
    def __init__(self):
        super().__init__()
        self._all_projects: list[dict] = []
        self._rows_data: list[dict] = []   # ORM 非依存の plain dict
        self._sort_col: int = -1
        self._sort_asc: bool = True
        self._build()
        self._load_projects()

    def _build(self):
        layout = QVBoxLayout(self)

        # ── フィルタ行（年度 / 業務区分 / 件名 / 検索） ───────────────────
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("年度："))
        self._year_combo = QComboBox()
        self._year_combo.setMinimumWidth(95)
        self._year_combo.currentIndexChanged.connect(self._filter_projects)
        filter_row.addWidget(self._year_combo)

        filter_row.addWidget(QLabel("業務区分："))
        self._cat_combo = QComboBox()
        self._cat_combo.setMinimumWidth(110)
        self._cat_combo.currentIndexChanged.connect(self._filter_projects)
        filter_row.addWidget(self._cat_combo)

        filter_row.addWidget(QLabel("件名："))
        self._proj_combo = QComboBox()
        self._proj_combo.setMinimumWidth(160)
        self._proj_combo.currentIndexChanged.connect(self._on_project_changed)
        filter_row.addWidget(self._proj_combo)
        filter_row.addStretch()
        filter_row.addWidget(QLabel("検索："))
        self._search = QLineEdit()
        self._search.setPlaceholderText("事業所名・代表者名で絞り込み")
        self._search.setMinimumWidth(120)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._load_members)
        self._search.textChanged.connect(lambda: self._timer.start(300))
        filter_row.addWidget(self._search)
        layout.addLayout(filter_row)

        # ── アクション行（モード / 用紙 / フォント / 生成ボタン） ─────────
        action_row = QHBoxLayout()
        from app.services.pdf.label_pdf import (
            LABEL_LAYOUTS, FONT_OPTIONS, DEFAULT_FONT_KEY
        )

        action_row.addWidget(QLabel("モード："))
        self._mode_combo = QComboBox()
        for label, _ in LABEL_MODES:
            self._mode_combo.addItem(label)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        action_row.addWidget(self._mode_combo)

        action_row.addWidget(QLabel("用紙："))
        self._layout_combo = QComboBox()
        self._layout_combo.setMinimumWidth(160)
        self._layout_combo.setMaximumWidth(260)
        action_row.addWidget(self._layout_combo)
        self._on_mode_changed()  # 初期値を設定

        action_row.addWidget(QLabel("フォント："))
        self._font_combo = QComboBox()
        for label in FONT_OPTIONS.keys():
            self._font_combo.addItem(label)
        fidx = self._font_combo.findText(DEFAULT_FONT_KEY)
        if fidx >= 0:
            self._font_combo.setCurrentIndex(fidx)
        action_row.addWidget(self._font_combo)

        action_row.addStretch()
        self._btn_generate = QPushButton("ラベルPDF生成")
        self._btn_generate.setFixedHeight(36)
        self._btn_generate.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 0 12px; }"
            "QPushButton:hover { background: #1D4ED8; }"
            "QPushButton:disabled { background: #94A3B8; color: white; }")
        self._btn_generate.setEnabled(False)
        self._btn_generate.clicked.connect(self._generate_pdf)
        action_row.addWidget(self._btn_generate)
        layout.addLayout(action_row)

        # ── テーブル ─────────────────────────────────────────────────────
        self._table = _CheckableTable(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_CHK,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_NUM,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_ORG,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_KANA, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(COL_REP,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_DEPT, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(COL_POST, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_ADDR, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(COL_CHK,  30)
        self._table.setColumnWidth(COL_NUM,  70)
        self._table.setColumnWidth(COL_KANA, 120)
        self._table.setColumnWidth(COL_REP,  100)
        self._table.setColumnWidth(COL_DEPT, 120)
        self._table.setColumnWidth(COL_POST, 80)
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked |
            QTableWidget.EditTrigger.SelectedClicked
        )
        _delegate = _MultilineDelegate(self._table)
        for col in (COL_ORG, COL_REP, COL_DEPT):
            self._table.setItemDelegateForColumn(col, _delegate)
        hdr.sectionClicked.connect(self._on_header_clicked)
        hdr.setSortIndicatorShown(True)
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        self._header_chk = QCheckBox(self._table.horizontalHeader())
        self._header_chk.setTristate(False)
        self._header_chk.toggled.connect(self._on_header_toggled)
        self._table.horizontalHeader().sectionResized.connect(
            lambda _l, _o, _n: self._reposition_header_chk()
        )

    def _on_mode_changed(self):
        from app.services.pdf.label_pdf import LABEL_LAYOUTS
        mode_key = LABEL_MODES[self._mode_combo.currentIndex()][1]
        self._layout_combo.blockSignals(True)
        self._layout_combo.clear()
        if mode_key == "nametag":
            lo = LABEL_LAYOUTS["a_one_51002"]
            self._layout_combo.addItem(lo.name, "a_one_51002")
            self._layout_combo.setEnabled(False)
        else:
            for key in ("a_one_28185", "a_one_28187"):
                lo = LABEL_LAYOUTS[key]
                self._layout_combo.addItem(lo.name, key)
            self._layout_combo.setEnabled(True)
        self._layout_combo.blockSignals(False)

    def _reposition_header_chk(self):
        hdr = self._table.horizontalHeader()
        x = hdr.sectionViewportPosition(COL_CHK)
        w = hdr.sectionSize(COL_CHK)
        h = hdr.height()
        cw = self._header_chk.sizeHint().width()
        ch = self._header_chk.sizeHint().height()
        self._header_chk.move(x + (w - cw) // 2, (h - ch) // 2)

    def _on_header_toggled(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            it = self._table.item(r, COL_CHK)
            if it:
                it.setCheckState(state)
        self._table.blockSignals(False)
        self._update_status()

    def _on_item_changed(self, item):
        if item.column() == COL_CHK:
            self._update_status()

    def _on_header_clicked(self, col: int):
        if col == COL_CHK or col not in _SORT_KEYS:
            return
        # ソート前にチェック済み行の member_number を記録して復元する
        checked_nums = {
            self._table.item(r, COL_NUM).text()
            for r in range(self._table.rowCount())
            if self._table.item(r, COL_CHK)
            and self._table.item(r, COL_CHK).checkState() == Qt.CheckState.Checked
            and self._table.item(r, COL_NUM)
        }
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        key = _SORT_KEYS[col]
        self._rows_data.sort(
            key=lambda d: (d[key] or "").lower(),
            reverse=not self._sort_asc,
        )
        self._populate_table()
        self._update_sort_headers()
        # チェック状態を復元
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            num_item = self._table.item(r, COL_NUM)
            chk_item = self._table.item(r, COL_CHK)
            if num_item and chk_item and num_item.text() in checked_nums:
                chk_item.setCheckState(Qt.CheckState.Checked)
        self._table.blockSignals(False)
        self._update_status()

    def _update_sort_headers(self):
        for col, base in enumerate(_HEADERS):
            if col == self._sort_col:
                label = base + (" ▲" if self._sort_asc else " ▼")
            else:
                label = base
            item = self._table.horizontalHeaderItem(col)
            if item:
                item.setText(label)
            else:
                self._table.setHorizontalHeaderItem(col, QTableWidgetItem(label))
        self._table.horizontalHeader().setSortIndicator(
            self._sort_col,
            Qt.SortOrder.AscendingOrder if self._sort_asc else Qt.SortOrder.DescendingOrder,
        )

    def _load_projects(self):
        with get_session() as session:
            self._all_projects = [
                {
                    "id": p.id,
                    "name": p.name,
                    "fiscal_year": p.fiscal_year,
                    "category_id": p.category_id,
                }
                for p in get_projects(session)
            ]
            cats = [{"id": c.id, "name": c.name} for c in get_active_categories(session)]

        self._year_combo.blockSignals(True)
        self._cat_combo.blockSignals(True)
        years = sorted({p["fiscal_year"] for p in self._all_projects}, reverse=True)
        self._year_combo.clear()
        self._year_combo.addItem("すべての年度", None)
        for y in years:
            self._year_combo.addItem(f"{y}年度", y)
        self._cat_combo.clear()
        self._cat_combo.addItem("すべて", None)
        for c in cats:
            self._cat_combo.addItem(c["name"], c["id"])
        self._year_combo.blockSignals(False)
        self._cat_combo.blockSignals(False)
        self._filter_projects()

    def _filter_projects(self):
        year = self._year_combo.currentData()
        cat_id = self._cat_combo.currentData()
        filtered = [
            p for p in self._all_projects
            if (year is None or p["fiscal_year"] == year)
            and (cat_id is None or p["category_id"] == cat_id)
        ]
        self._proj_combo.blockSignals(True)
        self._proj_combo.clear()
        self._proj_combo.addItem("（件名を選択）", None)
        for p in filtered:
            self._proj_combo.addItem(p["name"], p["id"])
        self._proj_combo.blockSignals(False)
        self._on_project_changed()

    def _on_project_changed(self):
        self._btn_generate.setEnabled(False)
        self._load_members()

    def _load_members(self):
        project_id = self._proj_combo.currentData()
        self._table.setRowCount(0)
        self._rows_data = []
        if project_id is None:
            self._status_label.setText("件名を選択してください")
            return

        kw = self._search.text().strip().lower()
        with get_session() as session:
            members = get_project_members(session, project_id)
            self._rows_data = [
                {
                    "member_number": pm.member_number or "",
                    "org_name":      pm.organization_name or "",
                    "org_kana":      pm.organization_kana or "",
                    "rep_name":      pm.representative_name or "",
                    "dept":          pm.department or "",
                    "postal_code":   pm.postal_code or "",
                    "address":       pm.address or "",
                }
                for pm in members
                if not kw
                or kw in (pm.organization_name or "").lower()
                or kw in (pm.organization_kana or "").lower()
                or kw in (pm.representative_name or "").lower()
            ]

        if self._sort_col >= 0 and self._sort_col in _SORT_KEYS:
            key = _SORT_KEYS[self._sort_col]
            self._rows_data.sort(
                key=lambda d: (d[key] or "").lower(),
                reverse=not self._sort_asc,
            )

        self._populate_table()
        self._btn_generate.setEnabled(len(self._rows_data) > 0)
        self._update_status()
        QTimer.singleShot(0, self._reposition_header_chk)

    def _populate_table(self):
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._rows_data))
        for r, d in enumerate(self._rows_data):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(r, COL_CHK, chk)

            # 編集不可列
            for col, key in [
                (COL_NUM,  "member_number"),
                (COL_KANA, "org_kana"),
                (COL_POST, "postal_code"),
            ]:
                item = QTableWidgetItem(d[key])
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(r, col, item)

            # 編集可能列
            for col, key in [
                (COL_ORG,  "org_name"),
                (COL_REP,  "rep_name"),
                (COL_DEPT, "dept"),
                (COL_ADDR, "address"),
            ]:
                item = QTableWidgetItem(d[key])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(r, col, item)

        self._table.blockSignals(False)
        if self._sort_col >= 0:
            self._update_sort_headers()

    def _update_status(self):
        total = self._table.rowCount()
        checked = sum(
            1 for r in range(total)
            if self._table.item(r, COL_CHK)
            and self._table.item(r, COL_CHK).checkState() == Qt.CheckState.Checked
        )
        self._status_label.setText(f"{total} 件表示　／　チェック済み {checked} 件")

    def _generate_pdf(self):
        def _cell(r, col):
            item = self._table.item(r, col)
            return item.text() if item else ""

        checked_rows = [
            r for r in range(self._table.rowCount())
            if self._table.item(r, COL_CHK)
            and self._table.item(r, COL_CHK).checkState() == Qt.CheckState.Checked
        ]
        if not checked_rows:
            QMessageBox.warning(self, "未選択", "ラベルを生成するメンバーを選択してください。")
            return

        entries = [
            type("_E", (), {
                "company_name":    _cell(r, COL_ORG),
                "postal_code":     _cell(r, COL_POST),
                "address1":        _cell(r, COL_ADDR),
                "address2":        "",
                "title":           _cell(r, COL_DEPT),
                "person_name":     _cell(r, COL_REP),
                "barcode_address": "",
                "entry_mode":      "inherit",
            })()
            for r in checked_rows
        ]

        batch_mode = LABEL_MODES[self._mode_combo.currentIndex()][1]
        layout_key = self._layout_combo.currentData() or "a_one_28185"
        font_key   = self._font_combo.currentText()

        from app.utils.pdf_helpers import get_pdf_output_dir
        from app.services.pdf.label_pdf import generate_label_pdf
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(get_pdf_output_dir(), f"label_{ts}.pdf")

        try:
            generate_label_pdf(entries, output_path, batch_mode, layout_key, font_key)
            os.startfile(output_path)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"PDF生成に失敗しました:\n{e}")
