# app/ui/label_issuance_tab.py
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QComboBox, QLineEdit, QMessageBox,
    QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer

from app.database.connection import get_session
from app.services.project_service import get_projects, get_project_members
from app.services.category_service import get_active_categories

COL_CHK  = 0
COL_NUM  = 1
COL_ORG  = 2
COL_KANA = 3
COL_REP  = 4
COL_POST = 5

LABEL_MODES = [
    ("宛名（氏名あり）", "normal"),
    ("宛名（氏名なし）", "no_person"),
    ("事業所名のみ",     "simple"),
    ("名札",            "nametag"),
    ("卓上プレート",     "split4"),
]


class _LabelEntryAdapter:
    def __init__(self, pm):
        self.company_name    = pm.organization_name or ""
        self.postal_code     = pm.postal_code or ""
        self.address1        = pm.address or ""
        self.address2        = pm.address2 or ""
        self.title           = pm.department or ""
        self.person_name     = pm.representative_name or ""
        self.barcode_address = ""
        self.entry_mode      = "inherit"


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
        self._all_projects: list = []
        self._pm_data: list = []
        self._build()
        self._load_projects()

    def _build(self):
        layout = QVBoxLayout(self)

        # ── フィルタ行（年度 / 業務区分 / 件名） ─────────────────────────
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("年度："))
        self._year_combo = QComboBox()
        self._year_combo.setMinimumWidth(95)
        self._year_combo.currentIndexChanged.connect(self._filter_projects)
        filter_row.addWidget(self._year_combo)

        filter_row.addWidget(QLabel("業務区分："))
        self._cat_combo = QComboBox()
        self._cat_combo.setMinimumWidth(120)
        self._cat_combo.currentIndexChanged.connect(self._filter_projects)
        filter_row.addWidget(self._cat_combo)

        filter_row.addWidget(QLabel("件名："))
        self._proj_combo = QComboBox()
        self._proj_combo.setMinimumWidth(200)
        self._proj_combo.currentIndexChanged.connect(self._on_project_changed)
        filter_row.addWidget(self._proj_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # ── アクション行（モード / 用紙 / フォント / 生成ボタン / 検索） ─
        action_row = QHBoxLayout()
        from app.services.pdf.label_pdf import (
            LABEL_LAYOUTS, FONT_OPTIONS, DEFAULT_LAYOUT_KEY, DEFAULT_FONT_KEY
        )

        action_row.addWidget(QLabel("モード："))
        self._mode_combo = QComboBox()
        for label, _ in LABEL_MODES:
            self._mode_combo.addItem(label)
        action_row.addWidget(self._mode_combo)

        action_row.addWidget(QLabel("用紙："))
        self._layout_combo = QComboBox()
        for key, lo in LABEL_LAYOUTS.items():
            self._layout_combo.addItem(lo.name, key)
        idx = self._layout_combo.findData(DEFAULT_LAYOUT_KEY)
        if idx >= 0:
            self._layout_combo.setCurrentIndex(idx)
        action_row.addWidget(self._layout_combo)

        action_row.addWidget(QLabel("フォント："))
        self._font_combo = QComboBox()
        for label in FONT_OPTIONS.keys():
            self._font_combo.addItem(label)
        fidx = self._font_combo.findText(DEFAULT_FONT_KEY)
        if fidx >= 0:
            self._font_combo.setCurrentIndex(fidx)
        action_row.addWidget(self._font_combo)

        self._btn_generate = QPushButton("ラベルPDF生成")
        self._btn_generate.setEnabled(False)
        self._btn_generate.clicked.connect(self._generate_pdf)
        action_row.addWidget(self._btn_generate)

        action_row.addStretch()
        action_row.addWidget(QLabel("検索："))
        self._search = QLineEdit()
        self._search.setPlaceholderText("事業所名・代表者名で絞り込み")
        self._search.setMinimumWidth(150)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._load_members)
        self._search.textChanged.connect(lambda: self._timer.start(300))
        action_row.addWidget(self._search)
        layout.addLayout(action_row)

        # ── テーブル ─────────────────────────────────────────────────────
        self._table = _CheckableTable(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["", "会員番号", "事業所名", "フリガナ", "代表者名", "郵便番号"]
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_CHK,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_NUM,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_ORG,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_KANA, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_REP,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_POST, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_CHK,  30)
        self._table.setColumnWidth(COL_NUM,  80)
        self._table.setColumnWidth(COL_REP, 100)
        self._table.setColumnWidth(COL_POST, 90)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
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

    def _load_projects(self):
        with get_session() as session:
            self._all_projects = get_projects(session)
            cats = get_active_categories(session)

        self._year_combo.blockSignals(True)
        self._cat_combo.blockSignals(True)
        years = sorted({p.fiscal_year for p in self._all_projects}, reverse=True)
        self._year_combo.clear()
        for y in years:
            self._year_combo.addItem(f"{y}年度", y)
        self._cat_combo.clear()
        self._cat_combo.addItem("すべて", None)
        for c in cats:
            self._cat_combo.addItem(c.name, c.id)
        self._year_combo.blockSignals(False)
        self._cat_combo.blockSignals(False)
        self._filter_projects()

    def _filter_projects(self):
        year = self._year_combo.currentData()
        cat_id = self._cat_combo.currentData()
        filtered = [
            p for p in self._all_projects
            if (year is None or p.fiscal_year == year)
            and (cat_id is None or p.category_id == cat_id)
        ]
        self._proj_combo.blockSignals(True)
        self._proj_combo.clear()
        self._proj_combo.addItem("（件名を選択）", None)
        for p in filtered:
            self._proj_combo.addItem(p.name, p.id)
        self._proj_combo.blockSignals(False)
        self._on_project_changed()

    def _on_project_changed(self):
        self._btn_generate.setEnabled(False)
        self._load_members()

    def _load_members(self):
        project_id = self._proj_combo.currentData()
        self._table.setRowCount(0)
        self._pm_data = []
        if project_id is None:
            self._status_label.setText("件名を選択してください")
            return

        kw = self._search.text().strip().lower()
        with get_session() as session:
            members = get_project_members(session, project_id)
            self._pm_data = [
                pm for pm in members
                if not kw
                or kw in (pm.organization_name or "").lower()
                or kw in (pm.organization_kana or "").lower()
                or kw in (pm.representative_name or "").lower()
            ]

        self._table.blockSignals(True)
        self._table.setRowCount(len(self._pm_data))
        for r, pm in enumerate(self._pm_data):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(r, COL_CHK,  chk)
            self._table.setItem(r, COL_NUM,  QTableWidgetItem(pm.member_number or ""))
            self._table.setItem(r, COL_ORG,  QTableWidgetItem(pm.organization_name or ""))
            self._table.setItem(r, COL_KANA, QTableWidgetItem(pm.organization_kana or ""))
            self._table.setItem(r, COL_REP,  QTableWidgetItem(pm.representative_name or ""))
            self._table.setItem(r, COL_POST, QTableWidgetItem(pm.postal_code or ""))
        self._table.blockSignals(False)

        self._btn_generate.setEnabled(len(self._pm_data) > 0)
        self._update_status()
        QTimer.singleShot(0, self._reposition_header_chk)

    def _update_status(self):
        total = self._table.rowCount()
        checked = sum(
            1 for r in range(total)
            if self._table.item(r, COL_CHK)
            and self._table.item(r, COL_CHK).checkState() == Qt.CheckState.Checked
        )
        self._status_label.setText(f"{total} 件表示　／　チェック済み {checked} 件")

    def _generate_pdf(self):
        checked_pms = [
            self._pm_data[r]
            for r in range(self._table.rowCount())
            if self._table.item(r, COL_CHK)
            and self._table.item(r, COL_CHK).checkState() == Qt.CheckState.Checked
        ]
        if not checked_pms:
            QMessageBox.warning(self, "未選択", "ラベルを生成するメンバーを選択してください。")
            return

        entries     = [_LabelEntryAdapter(pm) for pm in checked_pms]
        batch_mode  = LABEL_MODES[self._mode_combo.currentIndex()][1]
        layout_key  = self._layout_combo.currentData()
        font_key    = self._font_combo.currentText()

        from app.utils.pdf_helpers import get_pdf_output_dir
        from app.services.pdf.label_pdf import generate_label_pdf
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(get_pdf_output_dir(), f"label_{ts}.pdf")

        try:
            generate_label_pdf(entries, output_path, batch_mode, layout_key, font_key)
            os.startfile(output_path)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"PDF生成に失敗しました:\n{e}")
