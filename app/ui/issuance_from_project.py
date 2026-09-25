# app/ui/issuance_from_project.py
import calendar
import os
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QComboBox, QLineEdit, QMessageBox,
    QSpinBox, QFileDialog, QProgressDialog, QCheckBox, QDateEdit,
    QFrame, QGridLayout,
)
from PyQt6.QtCore import Qt, QTimer, QDate
from app.database.connection import get_session
from app.services.project_service import (
    get_projects, get_project_members, get_project_templates,
    get_member_item_settings, save_member_item_setting,
    get_project_by_id, get_project_member,
)
from app.services.category_service import get_active_categories
from app.services.company_service import (
    list_issuers, list_bank_accounts, list_seals,
)
from app.services.issuance_service import (
    create_issuance_for_member,
    mark_as_issued,
    update_issuance_lines_from_project,
    get_issuance,
    get_latest_issuance_for_member,
)
from app.utils import current_user


COL_CHK  = 0
COL_NUM  = 1   # 会員番号
COL_ORG  = 2   # 事業所名
COL_KANA = 3   # フリガナ
COL_DEPT = 4   # 所属・役職（宛名の並びに合わせ、代表者名の左）
COL_REP  = 5   # 代表者名
COL_PROJ = 6   # 件名（すべて選択時専用）
COL_ITEM = 6   # 項目ごとの単価・数量の最初の列（件名を選んだとき。単価・数量の順に2列ずつ）
# 数量列: 5 〜 5+len(templates)-1  ※件名選択時
# 請求書列 = 5+len(templates)、領収書列 = 6+len(templates) — テンプレート数で可変


class _QtySpinBox(QSpinBox):
    """テーブル内数量入力用: Enter で同列の次行へフォーカスを移動する。"""

    def __init__(self, table: "QTableWidget", row: int, col: int):
        super().__init__()
        self._tbl = table
        self._row = row
        self._col = col

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            next_row = self._row + 1
            if next_row < self._tbl.rowCount():
                nxt = self._tbl.cellWidget(next_row, self._col)
                if nxt:
                    nxt.setFocus()
                    nxt.selectAll()
        else:
            super().keyPressEvent(event)


class _CheckableTable(QTableWidget):
    """チェックボックス列の Shift+クリック範囲選択に対応したテーブル。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_checked_row: int = -1

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


class IssuanceFromProjectWidget(QWidget):
    def __init__(self, doc_type: str = "invoice"):
        super().__init__()
        self._doc_type = doc_type
        self._templates: list[dict] = []  # [{id, name}, ...]
        self._sort_col: int = -1   # -1 = 登録順（sort_order）
        self._sort_asc: bool = True
        self._qty_cache: dict[int, dict[int, int]] = {}    # {pm_id: {tmpl_id: qty}}
        self._price_cache: dict[int, dict[int, int]] = {}  # {pm_id: {tmpl_id: unit_price}}
        self._loading_members = False
        self._all_projects: list = []
        self._build()
        self._restore_from_project_settings()
        self._load_projects()

    @property
    def _is_all_mode(self) -> bool:
        return self._proj_combo.count() > 0 and self._proj_combo.currentData() is None

    @property
    def _col_inv(self) -> int:
        return COL_PROJ + 1 if self._is_all_mode else COL_ITEM + len(self._templates) * 2

    @property
    def _col_rcp(self) -> int:
        return COL_PROJ + 2 if self._is_all_mode else COL_ITEM + 1 + len(self._templates) * 2

    def _build(self):
        layout = QVBoxLayout(self)

        # ── フィルタ行（年度 / 業務区分 / 件名 / 表示） ──────────────────
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
        self._proj_combo.setMinimumWidth(180)
        self._proj_combo.currentIndexChanged.connect(self._on_project_changed)
        filter_row.addWidget(self._proj_combo)
        filter_row.addWidget(QLabel("表示："))
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["未発行のみ", "すべて"])
        self._filter_combo.currentIndexChanged.connect(self._load_members)
        filter_row.addWidget(self._filter_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # ── 発行の設定（普段は1行の要約、「変更」で開いて編集する） ─────────
        label = "請求書" if self._doc_type == "invoice" else "領収書"
        self._delivery_combo = QComboBox()
        self._delivery_combo.addItems(["印刷", "メール送付"])

        self._issuer_combo = QComboBox()
        self._bank_combo = QComboBox()
        self._seal_combo = QComboBox()
        self._issuer_combo.setMinimumWidth(180)
        self._bank_combo.setMinimumWidth(180)
        self._seal_combo.setMinimumWidth(150)
        self._issuer_combo.currentIndexChanged.connect(self._on_issuer_changed)
        self._bank_combo.currentIndexChanged.connect(self._on_issuer_detail_changed)
        self._seal_combo.currentIndexChanged.connect(self._on_issuer_detail_changed)

        if self._doc_type == "invoice":
            today = date.today()
            nm_year = today.year + 1 if today.month == 12 else today.year
            nm_month = 1 if today.month == 12 else today.month + 1
            last_day = calendar.monthrange(nm_year, nm_month)[1]
            self._due_date = QDateEdit(QDate(nm_year, nm_month, last_day))
            self._due_date.setCalendarPopup(True)
            self._due_date.setDisplayFormat("yyyy/MM/dd")
            self._window_envelope_chk = QCheckBox("窓あき封筒モード")
            self._show_person_chk = QCheckBox("役職名・氏名を印字")
            self._show_person_chk.setChecked(True)
            date_edit = self._due_date
        else:
            today = date.today()
            self._issued_date = QDateEdit(QDate(today.year, today.month, today.day))
            self._issued_date.setCalendarPopup(True)
            self._issued_date.setDisplayFormat("yyyy/MM/dd")
            date_edit = self._issued_date

        self._pdf_output_combo = QComboBox()
        self._pdf_output_combo.addItem(
            "事業所ごとの個別PDF", "individual")
        self._pdf_output_combo.addItem(
            "一括PDF＋個別PDF", "merged")
        self._pdf_output_combo.setToolTip(
            "個別PDFでは、各事業所を設定済みのファイル名で保存します。")
        btn_filename = QPushButton("ファイル名設定…")
        btn_filename.setToolTip(
            "PDFファイル名に事業所名・発行日・管理番号・請求金額を設定します。")
        btn_filename.clicked.connect(self._open_filename_settings)

        settings_box = QFrame()
        settings_box.setObjectName("SettingsBox")
        settings_box.setStyleSheet(
            "#SettingsBox { border: 1px solid #CBD5E1; border-radius: 6px;"
            " background: #F8FAFC; }")
        box_layout = QVBoxLayout(settings_box)
        box_layout.setContentsMargins(10, 6, 10, 6)
        box_layout.setSpacing(6)

        head = QHBoxLayout()
        head_title = QLabel("発行の設定")
        head_title.setStyleSheet("font-weight: bold; color: #1D4ED8;")
        head.addWidget(head_title, 0, Qt.AlignmentFlag.AlignTop)
        self._settings_summary = QLabel("")
        self._settings_summary.setWordWrap(True)
        self._settings_summary.setStyleSheet("color: #334155;")
        head.addWidget(self._settings_summary, 1)
        self._btn_settings_toggle = QPushButton("▼ 変更")
        self._btn_settings_toggle.setToolTip(
            "発行元・口座・印鑑・PDF出力などを変更します"
            "（発行方法と支払期日は「発行する」のときに確認します）")
        self._btn_settings_toggle.clicked.connect(self._toggle_settings_panel)
        head.addWidget(self._btn_settings_toggle, 0, Qt.AlignmentFlag.AlignTop)
        box_layout.addLayout(head)

        self._settings_panel = QWidget()
        grid = QGridLayout(self._settings_panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        def _lbl(text):
            lb = QLabel(text)
            lb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return lb

        # 発行方法と支払期日（発行日）は発行のたびに「発行する」のダイアログで決める。
        # 部品は発行処理が値を読むので残し、画面には出さない
        for hidden in (self._delivery_combo, date_edit):
            hidden.setParent(self)
            hidden.setVisible(False)
        grid.addWidget(_lbl("発行元："), 0, 0)
        grid.addWidget(self._issuer_combo, 0, 1)
        grid.addWidget(_lbl("口座："), 0, 2)
        grid.addWidget(self._bank_combo, 0, 3)
        grid.addWidget(_lbl("印鑑："), 1, 0)
        grid.addWidget(self._seal_combo, 1, 1)
        grid.addWidget(_lbl("PDF出力："), 1, 2)
        pdf_row = QHBoxLayout()
        pdf_row.setSpacing(6)
        pdf_row.addWidget(self._pdf_output_combo, 1)
        pdf_row.addWidget(btn_filename)
        grid.addLayout(pdf_row, 1, 3)
        if self._doc_type == "invoice":
            opts = QHBoxLayout()
            opts.addWidget(self._window_envelope_chk)
            opts.addSpacing(12)
            opts.addWidget(self._show_person_chk)
            opts.addStretch()
            grid.addLayout(opts, 2, 1, 1, 3)
        grid.setColumnStretch(4, 1)
        self._settings_panel.setVisible(False)
        box_layout.addWidget(self._settings_panel)
        layout.addWidget(settings_box)
        self._reload_issuers()

        # 設定を変えたら要約を更新する
        for combo in (self._issuer_combo, self._bank_combo,
                      self._seal_combo, self._pdf_output_combo):
            combo.currentIndexChanged.connect(self._update_settings_summary)
        if self._doc_type == "invoice":
            self._window_envelope_chk.toggled.connect(self._update_settings_summary)
            self._show_person_chk.toggled.connect(self._update_settings_summary)

        # ── 一覧の操作（検索 / Excel）：一覧のすぐ上 ─────────────────────
        tools_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("事業所名・代表者名で絞り込み")
        self._search.setMinimumWidth(120)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._load_members)
        self._search.textChanged.connect(lambda: self._timer.start(300))
        tools_row.addWidget(self._search, 1)
        tools_row.addSpacing(8)
        self._btn_export_xlsx = QPushButton("Excel出力")
        self._btn_export_xlsx.setToolTip(
            "表示中の名簿と数量をExcelに出力します。\n"
            "Excelで数量を入力後、「Excel取込」で読み込めます。")
        self._btn_export_xlsx.clicked.connect(self._export_excel)
        tools_row.addWidget(self._btn_export_xlsx)
        self._btn_import_xlsx = QPushButton("Excel取込")
        self._btn_import_xlsx.setToolTip(
            "Excel出力したファイルを読み込み、数量と発行チェックを画面に反映します。")
        self._btn_import_xlsx.clicked.connect(self._import_excel)
        tools_row.addWidget(self._btn_import_xlsx)
        layout.addLayout(tools_row)

        self._table = _CheckableTable(0, 7)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table.horizontalHeader().setSortIndicatorShown(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        # ヘッダー左端に本物のチェックボックスを配置
        self._header_chk = QCheckBox(self._table.horizontalHeader())
        self._header_chk.setTristate(False)
        self._header_chk.toggled.connect(self._on_header_checkbox_toggled)
        self._table.horizontalHeader().sectionResized.connect(
            lambda _l, _o, _n: self._reposition_header_chk())
        self._table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._setup_table_columns()
        layout.addWidget(self._table)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # ── プレビュー・発行（画面最下部に1行で固定。単発発行とそろえる）──────
        self._btn_preview = QPushButton(f"チェックした{label}をプレビュー")
        self._btn_preview.setFixedHeight(44)
        self._btn_preview.setMinimumWidth(220)
        self._btn_preview.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1D4ED8;"
            " background: white; border: 2px solid #1D4ED8; border-radius: 6px;")
        self._btn_preview.clicked.connect(self._preview_checked)
        self._btn_issue = QPushButton(f"チェックした{label}を発行する")
        self._btn_issue.setFixedHeight(44)
        self._btn_issue.setStyleSheet(
            "font-size: 14px; font-weight: bold;"
            " background: #2563EB; color: white; border-radius: 6px;")
        self._btn_issue.clicked.connect(self._issue_checked)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addWidget(self._btn_preview)
        bottom_row.addWidget(self._btn_issue, 1)
        layout.addLayout(bottom_row)
        self._update_settings_summary()

    # ── 発行の設定（要約と折りたたみ） ──────────────────────────────

    _WJ = chr(0x2060)   # WORD JOINER（この位置では改行しない）

    def _toggle_settings_panel(self):
        visible = not self._settings_panel.isVisible()
        self._settings_panel.setVisible(visible)
        self._btn_settings_toggle.setText("▲ 閉じる" if visible else "▼ 変更")

    def _update_settings_summary(self, *_):
        """発行の設定を1行の要約にする。閉じていても設定値を確認できるように。"""
        def _name(combo):
            return combo.currentText().replace("★", "").strip() or "（なし）"

        parts = [f"発行元：{_name(self._issuer_combo)}"]
        parts.append(f"口座：{_name(self._bank_combo)}")
        parts.append(f"印鑑：{_name(self._seal_combo)}")
        parts.append("個別PDF" if self._pdf_output_combo.currentData() == "individual"
                     else "一括PDF＋個別PDF")
        if self._doc_type == "invoice":
            if self._window_envelope_chk.isChecked():
                parts.append("窓あき封筒")
            parts.append("役職・氏名を印字" if self._show_person_chk.isChecked()
                         else "役職・氏名なし")
        # 項目の途中（「個別｜PDF」など）で折り返さないよう、各項目の文字間に
        # WORD JOINER を挟む。改行は区切りの「／」の位置でだけ起きる
        self._settings_summary.setText(
            "／".join(self._WJ.join(p) for p in parts))

    def _setup_table_columns(self):
        hdr = self._table.horizontalHeader()
        fixed       = QHeaderView.ResizeMode.Fixed
        interactive = QHeaderView.ResizeMode.Interactive
        rtc         = QHeaderView.ResizeMode.ResizeToContents

        if self._is_all_mode:
            self._table.setColumnCount(COL_PROJ + 3)
            self._table.setHorizontalHeaderLabels(
                ["", "会員番号", "事業所名", "フリガナ", "所属・役職", "代表者名",
                 "件名", "請求書", "領収書"])
            hdr.setSectionResizeMode(COL_CHK,  fixed);      self._table.setColumnWidth(COL_CHK,  30)
            hdr.setSectionResizeMode(COL_NUM,  interactive); self._table.setColumnWidth(COL_NUM,  80)
            hdr.setSectionResizeMode(COL_ORG,  interactive); self._table.setColumnWidth(COL_ORG, 180)
            hdr.setSectionResizeMode(COL_KANA, interactive); self._table.setColumnWidth(COL_KANA,140)
            hdr.setSectionResizeMode(COL_REP,  interactive); self._table.setColumnWidth(COL_REP, 100)
            hdr.setSectionResizeMode(COL_DEPT, interactive); self._table.setColumnWidth(COL_DEPT,120)
            hdr.setSectionResizeMode(COL_PROJ, interactive); self._table.setColumnWidth(COL_PROJ,200)
            hdr.setSectionResizeMode(self._col_inv, rtc)
            hdr.setSectionResizeMode(self._col_rcp, rtc)
        else:
            n = len(self._templates)
            self._table.setColumnCount(COL_ITEM + 2 + n * 2)
            headers = ["", "会員番号", "事業所名", "フリガナ", "所属・役職", "代表者名"]
            for tmpl in self._templates:
                headers.append(f"{tmpl['name']}\n単価")
                headers.append(f"{tmpl['name']}\n数量")
            headers += ["請求書", "領収書"]
            self._table.setHorizontalHeaderLabels(headers)
            hdr.setSectionResizeMode(COL_CHK,  fixed);      self._table.setColumnWidth(COL_CHK,  30)
            hdr.setSectionResizeMode(COL_NUM,  interactive); self._table.setColumnWidth(COL_NUM,  80)
            hdr.setSectionResizeMode(COL_ORG,  interactive); self._table.setColumnWidth(COL_ORG, 180)
            hdr.setSectionResizeMode(COL_KANA, interactive); self._table.setColumnWidth(COL_KANA,140)
            hdr.setSectionResizeMode(COL_REP,  interactive); self._table.setColumnWidth(COL_REP, 100)
            hdr.setSectionResizeMode(COL_DEPT, interactive); self._table.setColumnWidth(COL_DEPT,120)
            for i in range(n):
                hdr.setSectionResizeMode(COL_ITEM + i * 2, interactive)
                self._table.setColumnWidth(COL_ITEM + i * 2, 80)
                hdr.setSectionResizeMode(COL_ITEM + i * 2 + 1, interactive)
                self._table.setColumnWidth(COL_ITEM + i * 2 + 1, 100)
            for col in (self._col_inv, self._col_rcp):
                hdr.setSectionResizeMode(col, rtc)

        if self._sort_col >= 0:
            hdr.setSortIndicator(
                self._sort_col,
                Qt.SortOrder.AscendingOrder if self._sort_asc else Qt.SortOrder.DescendingOrder)
        else:
            hdr.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self._reposition_header_chk()

    # ── ヘッダークリック：全選択 / 全解除 ─────────────────────────

    def _on_header_clicked(self, col: int):
        if col == COL_CHK:
            return  # QCheckBox ウィジェットが処理
        # 数量・単価 SpinBox 列はソート対象外
        spin_cols = set(range(COL_ITEM, COL_ITEM + len(self._templates) * 2))
        if col in spin_cols:
            return
        self._save_qty_cache()
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._load_members()

    def _reposition_header_chk(self):
        hdr = self._table.horizontalHeader()
        x = hdr.sectionViewportPosition(COL_CHK)
        w = hdr.sectionSize(COL_CHK)
        h = hdr.height()
        chk = self._header_chk
        chk.resize(chk.sizeHint())
        chk.move(x + (w - chk.width()) // 2, (h - chk.height()) // 2)
        chk.show()

    def _on_header_checkbox_toggled(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            it = self._table.item(r, COL_CHK)
            if it:
                it.setCheckState(state)
        self._table.blockSignals(False)

    def _on_row_double_clicked(self, row: int, col: int):
        if not self._is_all_mode:
            return
        proj_item = self._table.item(row, COL_PROJ)
        if not proj_item:
            return
        proj_name = proj_item.text()
        for i in range(self._proj_combo.count()):
            if self._proj_combo.itemText(i) == proj_name:
                self._proj_combo.setCurrentIndex(i)
                return

    # ── プロジェクト読み込み ───────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._load_projects()
        self._reposition_header_chk()

    def _load_projects(self):
        session = get_session()
        try:
            # 「完了」は廃止したので状態は問わない（年度で絞り込む）
            self._all_projects = get_projects(session)
            cats = get_active_categories(session)
        finally:
            session.close()

        # 年度コンボ（重複なし降順）。当年度（4月始まり）は名簿がなくても選べる
        from app.services.issuance_service import fiscal_year_of
        this_year = fiscal_year_of(date.today())
        years = sorted({p.fiscal_year for p in self._all_projects} | {this_year},
                       reverse=True)
        current_year = self._year_combo.currentData()
        self._year_combo.blockSignals(True)
        self._year_combo.clear()
        self._year_combo.addItem("すべて", None)
        for y in years:
            self._year_combo.addItem(f"{y}年度", y)
        # デフォルト：当年度（来年度の名簿を先に作っても当年度を表示する）
        if current_year is None:
            self._year_combo.setCurrentIndex(self._year_combo.findData(this_year))
        else:
            for i in range(self._year_combo.count()):
                if self._year_combo.itemData(i) == current_year:
                    self._year_combo.setCurrentIndex(i)
                    break
        self._year_combo.blockSignals(False)

        # 業務区分コンボ：_all_projects に含まれるカテゴリのみ表示（窓口除外済み）
        used_cat_ids = {p.category_id for p in self._all_projects}
        current_cat = self._cat_combo.currentData()
        self._cat_combo.blockSignals(True)
        self._cat_combo.clear()
        self._cat_combo.addItem("すべて", None)
        for c in cats:
            if c.id in used_cat_ids:
                self._cat_combo.addItem(c.name, c.id)
        for i in range(self._cat_combo.count()):
            if self._cat_combo.itemData(i) == current_cat:
                self._cat_combo.setCurrentIndex(i)
                break
        self._cat_combo.blockSignals(False)

        self._filter_projects()

    def _filter_projects(self):
        sel_year = self._year_combo.currentData()
        sel_cat  = self._cat_combo.currentData()
        current_id = self._proj_combo.currentData()
        is_first_load = self._proj_combo.count() == 0
        self._proj_combo.blockSignals(True)
        self._proj_combo.clear()
        self._proj_combo.addItem("すべて", None)
        for p in self._all_projects:
            if sel_year is not None and p.fiscal_year != sel_year:
                continue
            if sel_cat is not None and p.category_id != sel_cat:
                continue
            self._proj_combo.addItem(p.name, p.id)
        if is_first_load:
            # 初回：最初のプロジェクトを自動選択（あれば）
            if self._proj_combo.count() > 1:
                self._proj_combo.setCurrentIndex(1)
        else:
            # 以前の選択を復元（current_id が None なら「すべて」のまま）
            for i in range(self._proj_combo.count()):
                if self._proj_combo.itemData(i) == current_id:
                    self._proj_combo.setCurrentIndex(i)
                    break
        self._proj_combo.blockSignals(False)
        self._on_project_changed()

    def _on_project_changed(self):
        project_id = self._proj_combo.currentData()
        is_all = project_id is None
        if is_all:
            self._templates = []
        else:
            session = get_session()
            try:
                pts = get_project_templates(session, project_id)
                self._templates = [
                    {
                        "id": pt.item_template.id,
                        "name": pt.item_template.name,
                        "unit": pt.item_template.unit or "式",
                        "unit_price": int(pt.unit_price_override or pt.item_template.unit_price or 0),
                        "tax_rate": (pt.tax_rate_override if pt.tax_rate_override is not None
                                      else pt.item_template.tax_rate),
                        "default_qty": int(pt.default_quantity) if pt.default_quantity is not None else 1,
                    }
                    for pt in pts
                ]
                # その名簿で前回使った支払期日を、プレビューと発行ダイアログの初期値にする
                proj = get_project_by_id(session, project_id)
                if self._doc_type == "invoice" and proj and proj.due_date:
                    d = proj.due_date
                    self._due_date.setDate(QDate(d.year, d.month, d.day))
            finally:
                session.close()
        for btn in (self._btn_issue, self._btn_preview,
                    self._btn_export_xlsx, self._btn_import_xlsx):
            btn.setEnabled(not is_all)
        self._btn_issue.setToolTip("件名を選択すると発行できます" if is_all else "")
        self._setup_table_columns()
        self._select_project_issuer(project_id)
        self._load_members()

    def _reload_issuers(self, company_id=None, bank_id=None, seal_id=None):
        session = get_session()
        try:
            issuers = list_issuers(session)
        finally:
            session.close()
        self._issuer_combo.blockSignals(True)
        self._issuer_combo.clear()
        default_idx = 0
        for i, issuer in enumerate(issuers):
            self._issuer_combo.addItem(f"{'★ ' if issuer.is_default else ''}{issuer.name}", issuer.id)
            if issuer.is_default: default_idx = i
        idx = next((i for i in range(self._issuer_combo.count()) if self._issuer_combo.itemData(i) == company_id), default_idx)
        if self._issuer_combo.count(): self._issuer_combo.setCurrentIndex(idx)
        self._issuer_combo.blockSignals(False)
        self._reload_bank_seal(bank_id, seal_id)

    def _reload_bank_seal(self, bank_id=None, seal_id=None):
        company_id = self._issuer_combo.currentData()
        session = get_session()
        try:
            banks = list_bank_accounts(session, company_id) if company_id else []
            seals = list_seals(session, company_id) if company_id else []
        finally:
            session.close()
        for combo, items, selected in ((self._bank_combo, banks, bank_id), (self._seal_combo, seals, seal_id)):
            combo.blockSignals(True); combo.clear(); combo.addItem("（既定）", None)
            for item in items: combo.addItem(f"{'★ ' if item.is_default else ''}{item.label}", item.id)
            if selected is not None:
                pos = combo.findData(selected)
                if pos >= 0: combo.setCurrentIndex(pos)
            combo.blockSignals(False)

    def _on_issuer_changed(self, _index):
        self._reload_bank_seal()
        try:
            self._save_project_issuer_settings()
        except Exception as error:
            self._show_shared_save_error(error)

    def _on_issuer_detail_changed(self, _index):
        try:
            self._save_project_issuer_settings()
        except Exception as error:
            self._show_shared_save_error(error)

    def _show_shared_save_error(self, error):
        self._status_label.setText(f"共有DBへの保存に失敗しました：{error}")

    def _save_project_issuer_settings(self):
        project_id = self._proj_combo.currentData()
        if project_id is None or not hasattr(self, "_issuer_combo"):
            return
        session = get_session()
        try:
            project = get_project_by_id(session, project_id)
            if project:
                project.company_settings_id = self._issuer_combo.currentData()
                project.bank_account_id = self._bank_combo.currentData()
                project.seal_image_id = self._seal_combo.currentData()
                session.commit()
        finally:
            session.close()

    def _select_project_issuer(self, project_id):
        company_id = bank_id = seal_id = None
        if project_id is not None:
            session = get_session()
            try:
                project = get_project_by_id(session, project_id)
                if project:
                    company_id, bank_id, seal_id = project.company_settings_id, project.bank_account_id, project.seal_image_id
            finally:
                session.close()
        self._reload_issuers(company_id, bank_id, seal_id)
    # ── メンバー一覧読み込み ──────────────────────────────────────

    _STATUS_SHORT = {"発行済み": "発行済", "支払済み": "支払済", "準備中": "準備中"}

    def _cell_text(self, iss) -> str:
        if iss is None:
            return "未発行"
        short = self._STATUS_SHORT.get(iss.status, iss.status)
        return f"{short} {iss.doc_number}".strip()

    def _load_members(self):
        project_id = self._proj_combo.currentData()
        query    = self._search.text().strip().lower()
        show_all = self._filter_combo.currentIndex() == 1
        doc_type = self._doc_type
        is_all   = self._is_all_mode

        if is_all:
            project_ids   = [self._proj_combo.itemData(i)
                             for i in range(self._proj_combo.count())
                             if self._proj_combo.itemData(i) is not None]
            proj_name_map = {self._proj_combo.itemData(i): self._proj_combo.itemText(i)
                             for i in range(1, self._proj_combo.count())}
        else:
            project_ids   = [project_id]
            proj_name_map = {}

        session = get_session()
        try:
            pm_data = []
            issued_count = 0
            for pid in project_ids:
                for pm in get_project_members(session, pid):
                    if pm.is_cancelled:
                        continue
                    inv = get_latest_issuance_for_member(
                        session, pm.id, "invoice")
                    rcp = get_latest_issuance_for_member(
                        session, pm.id, "receipt")
                    voided = inv is None and rcp is not None
                    sel = inv if doc_type == "invoice" else rcp
                    sel_status = sel.status if sel else "未発行"
                    hide_issued = sel_status in ("発行済み", "支払済み")
                    hide_voided = doc_type == "invoice" and voided
                    if hide_issued:
                        issued_count += 1
                    if not show_all and (hide_issued or hide_voided):
                        continue
                    if query:
                        targets = [
                            pm.organization_name or "",
                            pm.representative_name or "",
                            pm.organization_kana or "",
                        ]
                        if not any(query in t.lower() for t in targets):
                            continue
                    inv_text = "無効" if voided else self._cell_text(inv)
                    pm_data.append((
                        pm.id, pm,
                        inv_text, self._cell_text(rcp),
                        inv.id if inv else None, rcp.id if rcp else None,
                        proj_name_map.get(pid, ""),
                    ))
            member_settings = get_member_item_settings(
                session, [item[0] for item in pm_data])
        finally:
            session.close()

        # ソート
        col_inv = self._col_inv
        col_rcp = self._col_rcp
        sc = self._sort_col

        def _key(item):
            _, pm, inv_text, rcp_text, _, _, proj_name = item
            if sc < 0:                         return pm.sort_order or 0
            if sc == COL_NUM:                  return pm.member_number or ""
            if sc == COL_ORG:                  return pm.organization_name or ""
            if sc == COL_KANA:                 return pm.organization_kana or ""
            if sc == COL_REP:                  return pm.representative_name or ""
            if sc == COL_DEPT:                 return pm.department or ""
            if is_all and sc == COL_PROJ:      return proj_name
            if sc == col_inv:                  return inv_text
            if sc == col_rcp:                  return rcp_text
            return ""

        pm_data.sort(key=_key, reverse=(sc >= 0 and not self._sort_asc))

        self._table._last_checked_row = -1
        self._header_chk.blockSignals(True)
        self._header_chk.setChecked(False)
        self._header_chk.blockSignals(False)

        self._loading_members = True
        self._table.setRowCount(0)
        for pm_id, pm, inv_text, rcp_text, inv_id, rcp_id, proj_name in pm_data:
            row = self._table.rowCount()
            self._table.insertRow(row)

            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(row, COL_CHK, chk_item)

            row_data = (pm_id, inv_id, rcp_id)
            fixed_cols = [
                (COL_NUM,  pm.member_number or ""),
                (COL_ORG,  pm.organization_name or ""),
                (COL_KANA, pm.organization_kana or ""),
                (COL_REP,  pm.representative_name or ""),
                (COL_DEPT, pm.department or ""),
            ]
            if is_all:
                fixed_cols.append((COL_PROJ, proj_name))
            fixed_cols += [(col_inv, inv_text), (col_rcp, rcp_text)]
            for col, val in fixed_cols:
                it = QTableWidgetItem(val)
                it.setData(Qt.ItemDataRole.UserRole, row_data)
                self._table.setItem(row, col, it)

            for col_offset, tmpl in enumerate(self._templates):
                price_col = COL_ITEM + col_offset * 2
                qty_col   = COL_ITEM + col_offset * 2 + 1
                _base = "QSpinBox { min-height: 0; padding: 1px 4px; }"
                _mod  = "QSpinBox { min-height: 0; padding: 1px 4px; background: #FFF9C4; }"

                default_price = tmpl["unit_price"]
                price_spin = _QtySpinBox(self._table, row, price_col)
                price_spin.setRange(0, 9999999)
                saved = member_settings.get((pm_id, tmpl["id"]))
                saved_price = int(saved.unit_price) if saved and saved.unit_price is not None else default_price
                saved_qty = int(saved.quantity) if saved and saved.quantity is not None else tmpl["default_qty"]
                cached_price = self._price_cache.get(pm_id, {}).get(tmpl["id"], saved_price)
                price_spin.setValue(cached_price)
                price_spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                price_spin.setStyleSheet(_mod if cached_price != default_price else _base)

                def _on_price(v, pid=pm_id, tid=tmpl["id"], dp=default_price,
                              sp=price_spin, b=_base, m=_mod):
                    self._price_cache.setdefault(pid, {})[tid] = v
                    if not self._loading_members:
                        session = get_session()
                        try:
                            save_member_item_setting(session, pid, tid, unit_price=v)
                        except Exception as error:
                            self._show_shared_save_error(error)
                        finally:
                            session.close()
                    sp.setStyleSheet(m if v != dp else b)

                price_spin.valueChanged.connect(_on_price)
                self._table.setCellWidget(row, price_col, price_spin)

                default_qty = saved_qty
                spin = _QtySpinBox(self._table, row, qty_col)
                spin.setRange(0, 9999)
                cached_qty = self._qty_cache.get(pm_id, {}).get(tmpl["id"], default_qty)
                spin.setValue(cached_qty)
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spin.setStyleSheet(_mod if cached_qty != default_qty else _base)

                def _on_qty(v, pid=pm_id, tid=tmpl["id"], dq=default_qty,
                            sp=spin, b=_base, m=_mod):
                    self._qty_cache.setdefault(pid, {})[tid] = v
                    if not self._loading_members:
                        session = get_session()
                        try:
                            save_member_item_setting(session, pid, tid, quantity=v)
                        except Exception as error:
                            self._show_shared_save_error(error)
                        finally:
                            session.close()
                    sp.setStyleSheet(m if v != dq else b)

                spin.valueChanged.connect(_on_qty)
                self._table.setCellWidget(row, qty_col, spin)

        self._loading_members = False

        hdr = self._table.horizontalHeader()
        if self._sort_col >= 0:
            hdr.setSortIndicator(
                self._sort_col,
                Qt.SortOrder.AscendingOrder if self._sort_asc else Qt.SortOrder.DescendingOrder)
        else:
            hdr.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self._table.resizeRowsToContents()
        doc_label = "請求書" if doc_type == "invoice" else "領収書"
        if show_all:
            self._status_label.setText(
                f"{len(pm_data)} 件表示　（{doc_label}発行済 {issued_count} 件）")
        else:
            self._status_label.setText(
                f"未発行 {len(pm_data)} 件　／　{doc_label}発行済 {issued_count} 件")

    # ── 行数量取得 / キャッシュ保存 ──────────────────────────────

    def _get_row_quantities(self, row: int) -> dict[int, int]:
        result = {}
        for col_offset, tmpl in enumerate(self._templates):
            spin = self._table.cellWidget(row, COL_ITEM + col_offset * 2 + 1)
            if isinstance(spin, _QtySpinBox):
                result[tmpl["id"]] = spin.value()
        return result

    def _get_row_prices(self, row: int) -> dict[int, int]:
        result = {}
        for col_offset, tmpl in enumerate(self._templates):
            spin = self._table.cellWidget(row, COL_ITEM + col_offset * 2)
            if isinstance(spin, _QtySpinBox):
                result[tmpl["id"]] = spin.value()
        return result

    def _save_qty_cache(self):
        for r in range(self._table.rowCount()):
            data_item = self._table.item(r, COL_ORG)
            if not data_item:
                continue
            pm_id, _, _ = data_item.data(Qt.ItemDataRole.UserRole)
            self._qty_cache[pm_id] = self._get_row_quantities(r)
            self._price_cache[pm_id] = self._get_row_prices(r)

    # ── Excel入出力 ───────────────────────────────────────────────

    _XLSX_FIXED_HEADERS = ["ID", "会員番号", "事業所名", "フリガナ", "代表者名"]

    def _export_excel(self):
        """表示中の名簿＋項目ごとの単価・数量をExcelに出力する。"""
        project_id = self._proj_combo.currentData()
        if project_id is None:
            QMessageBox.information(self, "案件未選択", "件名を選択してください。")
            return
        if not self._templates:
            QMessageBox.information(
                self, "項目なし",
                "この案件には項目テンプレートが設定されていません。")
            return
        if self._table.rowCount() == 0:
            QMessageBox.information(self, "対象なし", "表示中の名簿がありません。")
            return

        proj_name = self._proj_combo.currentText()
        safe = "".join(c for c in proj_name if c not in '\\/:*?"<>|')
        path, _ = QFileDialog.getSaveFileName(
            self, "Excel出力", f"{safe}_単価数量入力.xlsx", "Excel (*.xlsx)")
        if not path:
            return

        import openpyxl
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "単価数量入力"

        # ヘッダー：項目ごとに「単価」「数量」の2列
        headers = self._XLSX_FIXED_HEADERS + [
            col
            for t in self._templates
            for col in [f"{t['name']}（単価）", f"{t['name']}（数量）"]
        ]
        ws.append(headers)

        fill_fixed = PatternFill("solid", fgColor="DDEBF7")   # 固定列：青
        fill_price = PatternFill("solid", fgColor="FCE4D6")   # 単価列：橙
        fill_qty   = PatternFill("solid", fgColor="E2EFDA")   # 数量列：緑
        n_fixed = len(self._XLSX_FIXED_HEADERS)
        for ci, cell in enumerate(ws[1]):
            cell.font = Font(bold=True)
            pos = ci - n_fixed
            if ci < n_fixed:
                cell.fill = fill_fixed
            elif pos % 2 == 0:
                cell.fill = fill_price
            else:
                cell.fill = fill_qty

        exported = 0
        for r in range(self._table.rowCount()):
            data_item = self._table.item(r, COL_ORG)
            if not data_item:
                continue
            pm_id, _, _ = data_item.data(Qt.ItemDataRole.UserRole)
            qty   = self._get_row_quantities(r)
            price = self._get_row_prices(r)
            row_vals = [
                pm_id,
                self._table.item(r, COL_NUM).text(),
                self._table.item(r, COL_ORG).text(),
                self._table.item(r, COL_KANA).text(),
                self._table.item(r, COL_REP).text(),
            ]
            for t in self._templates:
                row_vals.append(price.get(t["id"], t["unit_price"]))
                row_vals.append(qty.get(t["id"], 0))
            ws.append(row_vals)
            exported += 1

        widths = [6, 10, 28, 22, 14] + [10, 10] * len(self._templates)
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        try:
            wb.save(path)
        except PermissionError:
            QMessageBox.critical(
                self, "保存エラー",
                "ファイルを保存できませんでした。\n"
                "同じファイルをExcelで開いたままになっていないか確認してください。")
            return
        QMessageBox.information(
            self, "Excel出力",
            f"{exported}件を出力しました。\n{path}\n\n"
            "Excelで単価・数量を編集後、「Excel取込」で読み込んでください。\n"
            "・数量0の項目は明細に含まれません\n"
            "・全項目0の行は発行対象外になります\n"
            "・ID列は照合に使うため変更しないでください")

    def _import_excel(self):
        """Excel出力で編集したファイルを読み込み、数量とチェックを画面に反映する。"""
        if self._table.rowCount() == 0:
            QMessageBox.information(self, "対象なし", "表示中の名簿がありません。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Excel取込", "", "Excel (*.xlsx)")
        if not path:
            return

        import openpyxl
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            all_rows = [list(r) for r in ws.iter_rows(values_only=True)]
            wb.close()
        except Exception as e:
            QMessageBox.critical(self, "読込エラー", str(e))
            return
        if not all_rows:
            QMessageBox.warning(self, "読込エラー", "データが見つかりませんでした。")
            return

        header = [str(c).strip() if c is not None else "" for c in all_rows[0]]
        if "ID" not in header:
            QMessageBox.critical(
                self, "読込エラー",
                "見出し行に「ID」列が見つかりません。\n"
                "「Excel出力」で出力したファイルを使用してください。")
            return
        id_col = header.index("ID")

        # 数量列・単価列を検出（新フォーマット優先、旧フォーマットも対応）
        qty_cols: dict[int, int] = {}    # {tmpl_id: col_index}
        price_cols: dict[int, int] = {}  # {tmpl_id: col_index}
        missing_cols: list[str] = []
        for t in self._templates:
            new_qty_key   = f"{t['name']}（数量）"
            new_price_key = f"{t['name']}（単価）"
            if new_qty_key in header:
                qty_cols[t["id"]]   = header.index(new_qty_key)
                if new_price_key in header:
                    price_cols[t["id"]] = header.index(new_price_key)
            elif t["name"] in header:
                # 旧フォーマット（テンプレート名のみ = 数量列）
                qty_cols[t["id"]] = header.index(t["name"])
            else:
                missing_cols.append(t["name"])

        if not qty_cols:
            QMessageBox.critical(
                self, "読込エラー",
                "この案件の項目に対応する数量列が1つも見つかりません。\n"
                "案件の選択が出力時と同じか確認してください。")
            return

        def _parse_int(v, label: str, lo: int, hi: int,
                       bad: list[str], row_no: int) -> int | None:
            if v is None or str(v).strip() == "":
                return None
            try:
                f = float(str(v).strip())
                iv = int(f)
                if iv < lo:
                    raise ValueError
                if iv != f:
                    bad.append(f"{row_no}行目: {label}「{v}」は整数でないため{iv}として扱います")
                if iv > hi:
                    bad.append(f"{row_no}行目: {label}「{v}」は上限の{hi}に丸めました")
                    iv = hi
                return iv
            except (ValueError, OverflowError):
                bad.append(f"{row_no}行目: {label}「{v}」が不正です（スキップ）")
                return None

        file_qty:   dict[int, dict[int, int]] = {}
        file_price: dict[int, dict[int, int]] = {}
        bad_rows: list[str] = []
        for i, cells in enumerate(all_rows[1:], start=2):
            raw_id = cells[id_col] if id_col < len(cells) else None
            if raw_id is None or str(raw_id).strip() == "":
                continue
            try:
                pm_id = int(str(raw_id).strip())
            except ValueError:
                bad_rows.append(f"{i}行目: ID「{raw_id}」が数値ではありません")
                continue
            q = {}
            for tid, col in qty_cols.items():
                v = cells[col] if col < len(cells) else None
                iv = _parse_int(v, "数量", 0, 9999, bad_rows, i)
                q[tid] = iv if iv is not None else 0
            file_qty[pm_id] = q

            p = {}
            for tid, col in price_cols.items():
                v = cells[col] if col < len(cells) else None
                iv = _parse_int(v, "単価", 0, 9_999_999, bad_rows, i)
                if iv is not None:
                    p[tid] = iv
            if p:
                file_price[pm_id] = p

        applied = 0
        checked = 0
        for r in range(self._table.rowCount()):
            data_item = self._table.item(r, COL_ORG)
            if not data_item:
                continue
            pm_id, _, _ = data_item.data(Qt.ItemDataRole.UserRole)
            if pm_id not in file_qty:
                continue
            q = file_qty.pop(pm_id)
            p = file_price.pop(pm_id, {})
            for col_offset, tmpl in enumerate(self._templates):
                price_spin = self._table.cellWidget(r, COL_ITEM + col_offset * 2)
                qty_spin   = self._table.cellWidget(r, COL_ITEM + col_offset * 2 + 1)
                if isinstance(price_spin, _QtySpinBox) and tmpl["id"] in p:
                    price_spin.setValue(p[tmpl["id"]])
                if isinstance(qty_spin, _QtySpinBox) and tmpl["id"] in q:
                    qty_spin.setValue(q[tmpl["id"]])
            total = sum(q.values())
            chk = self._table.item(r, COL_CHK)
            if chk:
                chk.setCheckState(Qt.CheckState.Checked if total > 0
                                  else Qt.CheckState.Unchecked)
            if total > 0:
                checked += 1
            applied += 1
        self._save_qty_cache()

        has_price = bool(price_cols)
        msg = [f"{applied}件の{'単価・' if has_price else ''}数量を反映し、{checked}件に発行チェックを入れました。",
               "内容を確認のうえ「選択行に発行」ボタンで発行してください。"]
        if file_qty:
            msg.append(f"※名簿に表示されていないID {len(file_qty)}件は反映できませんでした。\n"
                       "（発行済み等で非表示の可能性。表示を「すべて」にして再度取り込んでください）")
        if missing_cols:
            msg.append("※次の項目の数量列が見つかりませんでした：" + "、".join(missing_cols))
        if bad_rows:
            shown = "\n".join(bad_rows[:5])
            more = f"\n…ほか{len(bad_rows) - 5}件" if len(bad_rows) > 5 else ""
            msg.append(f"※読み込めなかった値：\n{shown}{more}")
        QMessageBox.information(self, "Excel取込", "\n\n".join(msg))

    # ── チェック済み行の取得 ──────────────────────────────────────

    def _checked_rows(self) -> list[tuple[int, tuple]]:
        result = []
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, COL_CHK)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                data_item = self._table.item(r, COL_ORG)
                if data_item:
                    result.append((r, data_item.data(Qt.ItemDataRole.UserRole)))
        return result

    def _open_filename_settings(self):
        from app.ui.pdf_filename_dialog import PdfFilenameDialog
        PdfFilenameDialog(self).exec()

    def _restore_from_project_settings(self):
        from app.utils.app_config import get_config
        cfg = get_config().get("last_issuance_from_project", {})
        method = cfg.get("delivery_method", "印刷")
        idx = self._delivery_combo.findText(method)
        if idx >= 0:
            self._delivery_combo.setCurrentIndex(idx)
        if self._doc_type == "invoice":
            self._window_envelope_chk.setChecked(cfg.get("window_envelope", False))
            self._show_person_chk.setChecked(cfg.get("show_person", True))
        output_mode = cfg.get("pdf_output_mode", "individual")
        output_idx = self._pdf_output_combo.findData(output_mode)
        if output_idx >= 0:
            self._pdf_output_combo.setCurrentIndex(output_idx)

    # ── 発行処理 ──────────────────────────────────────────────────

    def _preview_checked(self):
        """選択行の現在値でPDFを生成する（IssuanceはDBへ保存しない）。"""
        rows = self._checked_rows()
        if len(rows) != 1:
            QMessageBox.information(
                self, "プレビュー対象",
                "プレビューする行を1行だけ選択してください。")
            return
        row_idx, (pm_id, _invoice_id, _receipt_id) = rows[0]
        if not self._templates:
            QMessageBox.information(self, "項目なし", "発行項目が設定されていません。")
            return

        session = get_session()
        try:
            from app.utils.pdf_helpers import (
                build_preview_issuance, generate_and_open, get_pdf_output_dir,
            )
            project_id = self._proj_combo.currentData()
            project = get_project_by_id(session, project_id)
            member = get_project_member(session, pm_id)
            if not project or not member:
                QMessageBox.warning(self, "プレビュー不可", "案件または名簿が見つかりません。")
                return

            quantities = self._get_row_quantities(row_idx)
            prices = self._get_row_prices(row_idx)
            lines = []
            for tmpl in self._templates:
                qty = quantities.get(tmpl["id"], tmpl["default_qty"])
                if qty <= 0:
                    continue
                price = prices.get(tmpl["id"], tmpl["unit_price"])
                lines.append({
                    "item_template_id": tmpl["id"],
                    "item_name": tmpl["name"],
                    "quantity": qty,
                    "unit": tmpl.get("unit", "式"),
                    "unit_price": price,
                    "tax_rate": tmpl.get("tax_rate", 10),
                })
            if not lines:
                QMessageBox.information(self, "プレビュー不可", "数量がすべて0です。")
                return

            issuance = build_preview_issuance(lines, self._doc_type)
            issuance.project_id = project.id
            issuance.project_member_id = member.id
            issuance.recipient_organization = member.organization_name or ""
            issuance.recipient_name = member.representative_name or ""
            issuance.recipient_department = member.department or ""
            issuance.roster_no = member.roster_no or ""
            issuance.company_settings_id = self._issuer_combo.currentData()
            issuance.bank_account_id = self._bank_combo.currentData()
            issuance.seal_image_id = self._seal_combo.currentData()
            if self._doc_type == "invoice":
                issuance.show_recipient_person = self._show_person_chk.isChecked()
                qd = self._due_date.date()
                due_date = date(qd.year(), qd.month(), qd.day())
                window_envelope = self._window_envelope_chk.isChecked()
            else:
                due_date = None
                window_envelope = False
            safe_name = "".join(c for c in (member.organization_name or member.representative_name or "preview")
                                if c not in '\\/:*?"<>|')
            path = os.path.join(get_pdf_output_dir(), f"_preview_{safe_name}.pdf")
            result = generate_and_open(
                issuance, session, due_date=due_date, open_file=True,
                save_path=path, window_envelope=window_envelope,
                project=project, commit=False,
            )
            if not result:
                QMessageBox.warning(self, "プレビュー不可", "発行元情報が設定されていません。")
        except Exception as error:
            QMessageBox.critical(self, "プレビューエラー", str(error))
        finally:
            session.rollback()
            session.close()

    def _do_issue_rows(self, rows: list[tuple[int, tuple]]) -> list[str]:
        """rows = [(row_idx, (pm_id, inv_id, rcp_id)), ...] を発行して PDF 生成。
        エラーメッセージのリストを返す。

        支払期限ダイアログはDB変更前に表示し、キャンセル時は何も変更しない。
        PDF生成に失敗した行は発行済みを取り消して「準備中」に戻す。
        """
        from app.utils.app_config import get_config as _gcfg, save_config as _scfg
        _cfg = _gcfg()
        _cfg["last_issuance_from_project"] = {
            "delivery_method": self._delivery_combo.currentText(),
            "window_envelope": self._window_envelope_chk.isChecked() if self._doc_type == "invoice" else False,
            "show_person": self._show_person_chk.isChecked() if self._doc_type == "invoice" else True,
            "pdf_output_mode": self._pdf_output_combo.currentData(),
        }
        _scfg(_cfg)

        project_id = self._proj_combo.currentData()
        doc_type = self._doc_type
        delivery = self._delivery_combo.currentText()
        errors = []

        # ── 対象行の事前確定（DB変更前）─────────────────────────
        targets = []
        for row_idx, (pm_id, invoice_id, receipt_id) in rows:
            if doc_type == "invoice" and invoice_id is None and receipt_id is not None:
                continue  # 無効化済み
            quantities = self._get_row_quantities(row_idx)
            unit_prices = self._get_row_prices(row_idx)
            issuance_id = invoice_id if doc_type == "invoice" else receipt_id
            if issuance_id is None and quantities and not any(quantities.values()):
                org_item = self._table.item(row_idx, COL_ORG)
                name = org_item.text() if org_item else f"{row_idx + 1}行目"
                errors.append(f"{name}：数量がすべて0のためスキップしました")
                continue
            targets.append((pm_id, issuance_id, quantities, unit_prices))
        if not targets:
            return errors, []

        # ── 支払期限・封筒オプション（請求書のみ）/ 発行日（領収書のみ）──
        due_date = None
        window_envelope = False
        show_recipient_person = True
        receipt_issued_at = None
        if doc_type == "invoice":
            qd = self._due_date.date()
            due_date = date(qd.year(), qd.month(), qd.day())
            window_envelope = self._window_envelope_chk.isChecked()
            show_recipient_person = self._show_person_chk.isChecked()
        else:
            from datetime import datetime as _dt
            qd = self._issued_date.date()
            receipt_issued_at = _dt(qd.year(), qd.month(), qd.day())

        # ── 保存先フォルダを選択（メール送付以外）──────────────────
        save_dir: str | None = None
        if delivery != "メール送付":
            from app.utils.pdf_helpers import get_pdf_output_dir
            save_dir = QFileDialog.getExistingDirectory(
                self, "PDFの保存先フォルダを選択", get_pdf_output_dir()
            )
            if not save_dir:
                return errors  # キャンセル → DB変更なしで終了

        # ── 発行 → PDF生成（失敗時は発行を取り消す）──────────────
        session = get_session()
        issued_issuances = []
        pdf_paths = []
        notify_items = []
        open_each = len(targets) == 1 and delivery != "メール送付"
        try:
            from app.utils.pdf_helpers import generate_and_open, merge_and_open
            for pm_id, issuance_id, quantities, unit_prices in targets:
                try:
                    pm = get_project_member(session, pm_id)
                    if issuance_id is None:
                        today = date.today()
                        iss = create_issuance_for_member(
                            session, project_id=project_id,
                            project_member_id=pm_id,
                            recipient_organization=pm.organization_name,
                            recipient_name=pm.representative_name,
                            recipient_department=pm.department or "",
                            doc_type=doc_type,
                            fiscal_year=today.year, month=today.month,
                            quantities=quantities if quantities else None,
                            unit_prices=unit_prices if unit_prices else None,
                            show_recipient_person=show_recipient_person,
                            roster_no=pm.roster_no or "",
                        )
                        issuance_id = iss.id
                    else:
                        # Excel取込や画面で変更した単価・数量を、既存の
                        # 準備中／発行済みデータにも反映してからPDFを作る。
                        update_issuance_lines_from_project(
                            session,
                            issuance_id,
                            quantities=quantities,
                            unit_prices=unit_prices,
                            commit=False,
                        )

                    iss = get_issuance(session, issuance_id)
                    if iss is None:
                        continue
                    iss.member_number = pm.member_number or ""
                    iss.recipient_organization = pm.organization_name or ""
                    iss.recipient_kana = pm.organization_kana or ""
                    iss.recipient_department = pm.department or ""
                    iss.recipient_name = pm.representative_name or ""
                    iss.recipient_name_kana = pm.representative_kana or ""
                    iss.recipient_phone = pm.phone or ""
                    iss.recipient_email = pm.email or ""
                    iss.company_settings_id = self._issuer_combo.currentData()
                    iss.bank_account_id = self._bank_combo.currentData()
                    iss.seal_image_id = self._seal_combo.currentData()
                    if doc_type == "invoice":
                        iss.show_recipient_person = show_recipient_person
                    # 旧データを再出力する場合も、現在の名簿NO.をファイル名に利用する。
                    if (iss.roster_no or "") != (pm.roster_no or ""):
                        iss.roster_no = pm.roster_no or ""
                    was_issued = iss.status == "発行済み"
                    if not was_issued:
                        mark_as_issued(session, issuance_id,
                                       staff_id=current_user.get_id(),
                                       staff_name=current_user.get_name(),
                                       delivery_method=delivery,
                                       issued_at=receipt_issued_at,
                                       commit=False)
                        iss = get_issuance(session, issuance_id)
                    elif (iss.delivery_method or "") != delivery:
                        # 発行済み行の再実行時も配付方法を実態に合わせる
                        iss.delivery_method = delivery

                    try:
                        _proj = get_project_by_id(session, iss.project_id)
                        if due_date and _proj and _proj.due_date != due_date:
                            _proj.due_date = due_date
                        if save_dir:
                            from app.utils.pdf_helpers import (
                                available_pdf_path, build_pdf_filename,
                            )
                            _pdf_save_path = available_pdf_path(
                                save_dir, build_pdf_filename(iss))
                        else:
                            _pdf_save_path = None
                        path = generate_and_open(iss, session, due_date=due_date,
                                                 open_file=open_each,
                                                 save_path=_pdf_save_path,
                                                 window_envelope=window_envelope,
                                                 project=_proj,
                                                 commit=False,
                                                 receipt_include_copy=not (
                                                     delivery == "メール送付"
                                                     and doc_type == "receipt"
                                                 ))
                        if not path:
                            raise RuntimeError("発行元情報が設定されていません。")
                        session.commit()
                        pdf_paths.append(path)
                        if not was_issued:
                            from app.services.operation_log_service import add_log
                            _lbl = "請求書" if doc_type == "invoice" else "領収書"
                            add_log(
                                session, "発行", "issuance", issuance_id,
                                f"{_lbl} {iss.doc_number} 宛先："
                                f"{iss.recipient_organization or iss.recipient_name}",
                            )
                    except Exception as e:
                        # 明細・金額・発行状態をPDF生成前の状態へ戻す。
                        session.rollback()
                        name = (iss.recipient_organization
                                or iss.recipient_name or iss.doc_number)
                        errors.append(
                            f"{name}：PDF生成に失敗したため変更を取り消しました（{e}）")
                        continue
                    issued_issuances.append((iss, session, was_issued))
                    notify_items.append({
                        "doc_number": iss.doc_number or "",
                        "recipient": iss.recipient_organization or iss.recipient_name or "",
                        "amount": iss.amount,
                    })
                except Exception as e:
                    errors.append(str(e))

            if delivery == "メール送付" and issued_issuances:
                reverted = self._send_issue_emails(issued_issuances, errors)
                # 送らずに準備中へ戻した分は、上長への発行通知にも含めない
                notify_items = [n for n in notify_items
                                if n["doc_number"] not in reverted]
            elif (len(pdf_paths) > 1
                  and self._pdf_output_combo.currentData() == "merged"):
                # 一括発行：個別に開かず1つに結合して開く（連続印刷用）
                try:
                    merge_and_open(pdf_paths, self._proj_combo.currentText(), output_dir=save_dir)
                except Exception as e:
                    errors.append(f"PDF結合に失敗しました：{e}")
            elif len(pdf_paths) > 1 and save_dir:
                # 個別PDFモード：各社のPDFを確認できるよう保存先を開く。
                os.startfile(save_dir)
        finally:
            session.close()
        return errors, notify_items

    def _send_issue_emails(self, issued_issuances: list, errors: list[str]) -> list[str]:
        """発行方法「メール送付」で発行した分を、確認1回で一括送信する。

        issued_issuances は (書類, セッション, 以前から発行済みだったか) の一覧。
        1件目を見本に送信確認画面を1回だけ出し、そこで直した件名・本文のテンプレートを
        各書類に差し込んで送る（以前は1件ずつ確認画面と最終確認が出ていた）。
        送らなかった書類（宛先なし・キャンセル・中止・失敗）のうち、今回はじめて
        発行済みにしたものは「準備中」に戻す。戻した番号を返す。
        """
        from PyQt6.QtCore import QThread
        from PyQt6.QtWidgets import QApplication, QDialog
        from app.services import email_service
        from app.services.issuance_service import revert_to_prepared
        from app.services.operation_log_service import add_log
        from app.ui import invoice_mail_confirm_dialog, m365_mail_worker
        from app.utils.app_config import get_m365_client_id, get_m365_tenant_id
        label = "請求書" if self._doc_type == "invoice" else "領収書"

        def _finish(sent: int, not_sent: list) -> list[str]:
            reverted: list[str] = []
            for iss, sess, was_issued in not_sent:
                if not was_issued:
                    revert_to_prepared(sess, iss)
                    reverted.append(iss.doc_number)
            msg = f"{sent} 件のメールを送信しました。"
            if reverted:
                msg += (f"\n送信しなかった {len(reverted)} 件は「準備中」に戻しました"
                        "（番号はそのままで、次に発行するときに使われます）。")
            QMessageBox.information(self, "メール送信", msg)
            return reverted

        client_id = get_m365_client_id()
        tenant_id = get_m365_tenant_id()
        if not client_id or not tenant_id:
            QMessageBox.critical(
                self, "設定エラー",
                "Microsoft 365 の Client ID / Tenant ID が設定されていません。\n"
                "設定 → メール送信設定から入力してください。")
            return _finish(0, list(issued_issuances))

        # 宛先とPDFを用意する。宛先のない書類はこの時点で送信対象から外す
        sendable: list = []     # (item, to_addr, pdf_path)
        not_sent: list = []
        for item in issued_issuances:
            iss, sess, _was_issued = item
            email = ""
            if iss.project_member_id:
                pm = get_project_member(sess, iss.project_member_id)
                email = (pm.email or "").strip() if pm else ""
            try:
                to_addr, _s, _b, pdf_path = email_service.prepare_issuance_email(
                    sess, iss, to_addr=email or None)
            except Exception as prep_err:
                errors.append(f"メール準備失敗：{prep_err}")
                add_log(sess, "メール送信失敗", "issuance", iss.id,
                        f"{label} {iss.doc_number}：{prep_err}")
                not_sent.append(item)
                continue
            sendable.append((item, to_addr, pdf_path))
        if not sendable:
            return _finish(0, not_sent)

        # 1件目を見本に、送信確認画面を1回だけ出す
        (first, first_sess, _), first_to, first_pdf = sendable[0]
        dlg = invoice_mail_confirm_dialog.InvoiceMailConfirmDialog(
            self,
            to_recipients=[first_to],
            pdf_path=first_pdf,
            invoice_no=first.doc_number,
            customer_name=first.recipient_organization or first.recipient_name or "",
            amount_text=f"¥{first.amount:,}" if first.amount else "",
            template_kind=first.doc_type,
            template_context=email_service.get_issuance_email_context(first_sess, first),
            bulk_count=len(sendable),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return _finish(0, not_sent + [s[0] for s in sendable])
        skipped = f"（メールアドレスがない {len(not_sent)} 件は送りません）" if not_sent else ""
        if QMessageBox.question(
                self, "一括送信の確認",
                f"{len(sendable)} 件に{label}のメールを送信します{skipped}。\n"
                "よろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return _finish(0, not_sent + [s[0] for s in sendable])

        subject_t, body_t = dlg.template_subject(), dlg.template_body()
        cc, bcc = dlg.cc_recipients(), dlg.bcc_recipients()
        mails = []
        for (iss, sess, _), to_addr, pdf_path in sendable:
            subject, body_html = email_service.render_issuance_email(
                email_service.get_issuance_email_context(sess, iss), subject_t, body_t)
            mails.append({"to": to_addr, "subject": subject, "body_html": body_html,
                          "pdf_path": pdf_path, "doc_number": iss.doc_number,
                          "cc": cc, "bcc": bcc, "iss_id": iss.id})

        # 進み具合を表示しながら一括送信（「中止」で止められる）
        thread = QThread(self)
        worker = m365_mail_worker.M365ReminderBatchWorker(client_id, tenant_id, mails)
        worker.moveToThread(thread)
        progress = QProgressDialog(
            f"{label}のメールを送信中…", "送信を中止", 0, len(mails), self)
        progress.setWindowTitle("メール一括送信")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        worker.progress.connect(lambda cur, _tot: progress.setValue(cur))
        progress.canceled.connect(worker.cancel)
        worker.done.connect(lambda _sent, errs: (errors.extend(errs), thread.quit()))
        thread.started.connect(worker.run)
        thread.start()
        # 待ち画面（WindowModal）の間はメイン画面を閉じられないので、
        # スレッドが動作中に破棄されることはない
        while thread.isRunning():
            QApplication.processEvents()
        progress.setValue(len(mails))
        thread.deleteLater()

        # 結果を書類に反映する。送れなかった分（失敗・中止で未送信）は準備中に戻す
        from datetime import datetime
        succeeded = {r["item"]["iss_id"] for r in worker.results if r["success"]}
        sent = 0
        for (iss, sess, was_issued), to_addr, _pdf in sendable:
            if iss.id in succeeded:
                mail = next(m for m in mails if m["iss_id"] == iss.id)
                iss.recipient_email = to_addr
                iss.mail_subject = mail["subject"]
                iss.mail_sent_at = datetime.now()
                iss.mail_delivery_status = "pending"
                iss.mail_delivery_message = "Microsoft 365の配信結果を確認してください。"
                iss.mail_delivery_checked_at = None
                sess.commit()
                add_log(sess, "メール送信", "issuance", iss.id,
                        f"{label} {iss.doc_number} → {to_addr}")
                sent += 1
            else:
                not_sent.append((iss, sess, was_issued))
        return _finish(sent, not_sent)

    def _confirm_issue(self, count: int) -> bool:
        """発行方法と支払期日（領収書は発行日）をダイアログで確かめる。

        支払期日の初期値は、その名簿で前回使った支払期日（なければ今の値＝翌月末）。
        キャンセルなら False（何もしない）。"""
        from PyQt6.QtWidgets import QDialog
        from app.ui import batch_issue_confirm_dialog
        if self._doc_type == "invoice":
            doc_date = self._due_date.date().toPyDate()
            project_id = self._proj_combo.currentData()
            if project_id is not None:
                session = get_session()
                try:
                    proj = get_project_by_id(session, project_id)
                    if proj and proj.due_date:
                        doc_date = proj.due_date
                finally:
                    session.close()
        else:
            doc_date = date.today()
        dlg = batch_issue_confirm_dialog.BatchIssueConfirmDialog(
            self, count=count, doc_type=self._doc_type,
            delivery=self._delivery_combo.currentText(), doc_date=doc_date)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        self._delivery_combo.setCurrentText(dlg.delivery())
        chosen = dlg.doc_date()
        target = self._due_date if self._doc_type == "invoice" else self._issued_date
        target.setDate(QDate(chosen.year, chosen.month, chosen.day))
        return True

    def _issue_checked(self):
        targets = self._checked_rows()
        if not targets:
            QMessageBox.information(self, "未選択",
                                    "発行する行のチェックボックスにチェックを入れてください。")
            return
        if not self._confirm_issue(len(targets)):
            return
        errors, notify_items = self._do_issue_rows(targets)
        if errors:
            QMessageBox.critical(self, "PDF生成エラー", "\n".join(errors))
        self._send_admin_notification(notify_items)
        self._load_members()

    def _issue_all(self):
        project_id = self._proj_combo.currentData()
        if project_id is None:
            return
        label = "請求書" if self._doc_type == "invoice" else "領収書"
        ans = QMessageBox.question(
            self, "確認",
            f"表示中の全員ぶんを{label}で発行します。よろしいですか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        all_rows = []
        for r in range(self._table.rowCount()):
            data_item = self._table.item(r, COL_ORG)
            if data_item:
                all_rows.append((r, data_item.data(Qt.ItemDataRole.UserRole)))
        if not self._confirm_issue(len(all_rows)):
            return
        errors, notify_items = self._do_issue_rows(all_rows)
        if errors:
            QMessageBox.critical(self, "PDF生成エラー", "\n".join(errors))
        self._send_admin_notification(notify_items)
        self._load_members()

    def _send_admin_notification(self, notify_items: list[dict]):
        """発行完了後に所属長へ通知メールをバックグラウンド送信する。"""
        if not notify_items:
            return
        from app.utils.app_config import get_m365_client_id, get_m365_tenant_id
        client_id = get_m365_client_id()
        tenant_id = get_m365_tenant_id()
        if not client_id or not tenant_id:
            return

        # ログイン中の職員の所属長メールを取得
        staff_id = current_user.get_id()
        if not staff_id:
            return
        session = get_session()
        try:
            from app.services.staff_service import get_staff
            staff = get_staff(session, staff_id)
            supervisor_email = ""
            if staff and staff.supervisor_id:
                sup = get_staff(session, staff.supervisor_id)
                supervisor_email = (sup.email or "").strip() if sup else ""
        finally:
            session.close()
        if not supervisor_email:
            return

        import html as _html
        import threading
        from app.ui.m365_mail_worker import M365MailWorker

        doc_label  = "請求書" if self._doc_type == "invoice" else "領収書"
        staff_name = _html.escape(current_user.get_name() or "担当者")
        doc_label_e = _html.escape(doc_label)
        today = date.today().strftime("%Y/%m/%d")
        subject = f"[発行通知] {doc_label} {len(notify_items)}件（{today}）"

        rows_html = ""
        for it in notify_items:
            amount_str = f"¥{it['amount']:,}" if it["amount"] else "-"
            rows_html += (
                f"<tr>"
                f"<td style='padding:4px 8px;'>{_html.escape(it['doc_number'])}</td>"
                f"<td style='padding:4px 8px;'>{_html.escape(it['recipient'])}</td>"
                f"<td style='padding:4px 8px; text-align:right;'>{_html.escape(amount_str)}</td>"
                f"</tr>"
            )
        body_html = (
            f"<p><b>{staff_name}</b> が以下の{doc_label_e}を発行しました。</p>"
            f"<table border='1' cellspacing='0' "
            f"style='border-collapse:collapse; font-family:sans-serif; font-size:13px;'>"
            f"<tr style='background:#f0f0f0;'>"
            f"<th style='padding:4px 8px;'>書類番号</th>"
            f"<th style='padding:4px 8px;'>宛先</th>"
            f"<th style='padding:4px 8px;'>金額</th></tr>"
            f"{rows_html}</table>"
            f"<p style='color:#555; font-size:12px; margin-top:12px;'>"
            f"アプリで内容を確認してください。</p>"
        )

        # QThread(self) にすると、送信後も止まらないスレッドが画面と一緒に破棄され、
        # アプリ終了時に Qt がプロセスを強制終了していた（0xC0000409）。
        # 画面に結びつかない Python スレッドで送り、終了時は送信完了を待つ（daemon=False）
        worker = M365MailWorker(client_id, tenant_id, [supervisor_email], subject, body_html)
        threading.Thread(target=worker.run, name="admin-notification",
                         daemon=False).start()
