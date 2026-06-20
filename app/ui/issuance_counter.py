# app/ui/issuance_counter.py
import calendar
import os
import unicodedata
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QGroupBox,
    QLineEdit, QSpinBox, QComboBox, QLabel, QPushButton,
    QMessageBox, QFrame, QScrollArea, QStyleFactory, QDialog,
    QCheckBox, QDateEdit, QCompleter, QListWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QTimer, QThread, QPoint
from PyQt6.QtGui import QIntValidator
from app.database.connection import get_session
from app.services.category_service import get_active_categories
from app.services.item_template_service import get_all_active_templates
from app.services.issuance_service import create_direct_issuance, update_direct_issuance
from app.utils import current_user

# 列幅・行高（px）
W_CAT   = 150
W_PRICE = 90
W_QTY   = 80
W_SUB   = 90
W_SAVE  = 70
W_DEL   = 40
ROW_H   = 48
FIELD_H = 31

_SS_FIELD = (
    "QComboBox, QLineEdit, QSpinBox {"
    " border: 1px solid #b5b5b5; border-radius: 3px;"
    " padding: 3px 4px; background: white; }"
)


class _LineRow(QFrame):
    """発行項目1行（業務名／項目／単価／数量／小計／削除）"""

    def __init__(self, panel: "IssuanceCounterWidget"):
        super().__init__()
        self.panel = panel
        self.setFixedHeight(ROW_H)
        self.setObjectName("LineRow")
        self.setStyleSheet(
            "#LineRow { border-bottom: 1px solid #e2e2e2; background: white; }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(6)

        style = panel._cell_style

        # 業務名
        self.cat_combo = QComboBox()
        self.cat_combo.setFixedWidth(W_CAT)
        self.cat_combo.setFixedHeight(FIELD_H)
        # 項目（テンプレート選択 or 直接入力）
        self.tmpl_combo = QComboBox()
        self.tmpl_combo.setEditable(True)
        self.tmpl_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.tmpl_combo.setFixedHeight(FIELD_H)
        self.tmpl_combo.addItem("（項目を選択または入力）", None)
        self.tmpl_combo.lineEdit().setPlaceholderText("（項目を選択または入力）")
        self.tmpl_combo.lineEdit().textChanged.connect(
            lambda: panel._update_total())
        # 単価
        self.price_edit = QLineEdit("0")
        self.price_edit.setFixedWidth(W_PRICE)
        self.price_edit.setFixedHeight(FIELD_H)
        self.price_edit.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.price_edit.setValidator(QIntValidator(0, 99_999_999, self))
        # 数量
        self.qty_spin = QSpinBox()
        self.qty_spin.setFixedWidth(W_QTY)
        self.qty_spin.setFixedHeight(FIELD_H)
        self.qty_spin.setRange(1, 9999)
        self.qty_spin.setValue(1)
        # 小計
        self.sub_label = QLabel("¥0")
        self.sub_label.setFixedWidth(W_SUB)
        self.sub_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # テンプレ登録
        self.btn_save_tmpl = QPushButton("テンプレ登録")
        self.btn_save_tmpl.setFixedSize(W_SAVE, FIELD_H)
        self.btn_save_tmpl.setEnabled(False)
        self.btn_save_tmpl.setToolTip("この行の品目名と単価をテンプレートマスタに登録します")
        self.btn_save_tmpl.setStyleSheet(
            "QPushButton { font-size: 10px; color: #1565c0;"
            " border: 1px solid #1565c0; border-radius: 3px;"
            " padding: 1px 3px; background: transparent; }"
            "QPushButton:hover { background: #e3f2fd; }"
            "QPushButton:disabled { color: #bbb; border-color: #ccc; }")
        # 削除
        self.btn_del = QPushButton("✕")
        self.btn_del.setFixedSize(W_DEL, FIELD_H)
        self.btn_del.setStyleSheet(
            "QPushButton { color: #cc4444; border: none;"
            " background: transparent; font-weight: bold; }"
            "QPushButton:hover { color: #ff0000; }")

        for w in (self.cat_combo, self.tmpl_combo, self.price_edit, self.qty_spin):
            if style:
                w.setStyle(style)
            w.setStyleSheet(_SS_FIELD)

        lay.addWidget(self.cat_combo)
        lay.addWidget(self.tmpl_combo, 1)
        lay.addWidget(self.price_edit)
        lay.addWidget(self.qty_spin)
        lay.addWidget(self.sub_label)
        lay.addWidget(self.btn_save_tmpl)
        lay.addWidget(self.btn_del)

        # シグナル
        self.cat_combo.currentIndexChanged.connect(
            lambda: self.panel._on_cat_changed(self))
        self.tmpl_combo.currentIndexChanged.connect(
            lambda: self.panel._on_tmpl_changed(self))
        self.tmpl_combo.currentIndexChanged.connect(lambda: self._update_save_btn())
        self.tmpl_combo.lineEdit().textChanged.connect(lambda: self._update_save_btn())
        self.price_edit.textChanged.connect(self.panel._update_total)
        self.qty_spin.valueChanged.connect(self.panel._update_total)
        self.btn_del.clicked.connect(lambda: self.panel._remove_row(self))

    def _update_save_btn(self):
        _PH = "（項目を選択または入力）"
        is_direct = self.tmpl_combo.currentData() is None
        text = self.tmpl_combo.currentText().strip()
        self.btn_save_tmpl.setEnabled(is_direct and bool(text) and text != _PH)

    def price(self) -> int:
        try:
            return int(self.price_edit.text())
        except (ValueError, TypeError):
            return 0


class _PostalWorker(QThread):
    """郵便番号 → 住所変換（zipcloud API）"""
    found = pyqtSignal(str)

    def __init__(self, zipcode: str):
        super().__init__()
        self._zipcode = zipcode

    def run(self):
        try:
            import urllib.request, json
            url = (f"https://zipcloud.ibsnet.co.jp/api/search"
                   f"?zipcode={self._zipcode}")
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
            results = data.get("results")
            if results:
                r = results[0]
                addr = r.get("address1", "") + r.get("address2", "") + r.get("address3", "")
                self.found.emit(addr)
        except Exception:
            pass


class IssuanceCounterWidget(QWidget):
    edit_completed = pyqtSignal()

    def __init__(self, doc_type: str = "receipt", edit_issuance_id: int | None = None):
        super().__init__()
        self._doc_type_str = doc_type
        self._edit_issuance_id = edit_issuance_id
        self._edit_loaded = False
        self._categories = []
        self._templates  = []
        self._cat_name_by_id: dict[int, str] = {}
        self._rows: list[_LineRow] = []
        self._cell_style = QStyleFactory.create("Fusion")
        self._postal_worker: _PostalWorker | None = None
        self._members: list = []
        self._member_by_number: dict = {}
        self._build()

    def showEvent(self, event):
        super().showEvent(event)
        self._reload_master()
        if self._edit_issuance_id is not None and not self._edit_loaded:
            self._load_edit_data()
            self._edit_loaded = True

    # ── マスタ読み込み ───────────────────────────────────

    def _reload_master(self):
        from app.services.member_service import get_all_members
        session = get_session()
        try:
            self._categories = get_active_categories(session)
            self._templates  = get_all_active_templates(session)
            self._members    = get_all_members(session)
        finally:
            session.close()
        self._cat_name_by_id = {c.id: c.name for c in self._categories}
        for row in self._rows:
            self._refresh_cat_combo(row.cat_combo)
            self._refresh_tmpl_combo(row)
        self._setup_completers()

    def _reload_issuer_combo(self, select_company_id: int | None = None,
                             select_bank_id: int | None = None,
                             select_seal_id: int | None = None):
        from app.database.models import CompanySettings
        session = get_session()
        try:
            issuers = session.query(CompanySettings).order_by(CompanySettings.id).all()
            self._issuer_combo.blockSignals(True)
            self._issuer_combo.clear()
            default_idx = 0
            for i, cs in enumerate(issuers):
                label = f"{'★ ' if cs.is_default else ''}{cs.name}"
                self._issuer_combo.addItem(label, cs.id)
                if cs.is_default and select_company_id is None:
                    default_idx = i
            self._issuer_combo.blockSignals(False)

            if select_company_id is not None:
                for i in range(self._issuer_combo.count()):
                    if self._issuer_combo.itemData(i) == select_company_id:
                        self._issuer_combo.setCurrentIndex(i)
                        break
            else:
                self._issuer_combo.setCurrentIndex(default_idx)
        finally:
            session.close()
        self._reload_bank_seal_combo(select_bank_id=select_bank_id,
                                     select_seal_id=select_seal_id)

    def _reload_bank_seal_combo(self, select_bank_id: int | None = None,
                                select_seal_id: int | None = None):
        from app.database.models import BankAccount, SealImage
        company_id = self._issuer_combo.currentData()
        session = get_session()
        try:
            if hasattr(self, "_bank_combo"):
                self._bank_combo.blockSignals(True)
                self._bank_combo.clear()
                self._bank_combo.addItem("（なし）", None)
                if company_id:
                    banks = session.query(BankAccount).filter_by(company_id=company_id).all()
                    for b in banks:
                        label = f"{'★ ' if b.is_default else ''}{b.label} {b.bank_name}"
                        self._bank_combo.addItem(label, b.id)
                self._bank_combo.blockSignals(False)

            self._seal_combo.blockSignals(True)
            self._seal_combo.clear()
            self._seal_combo.addItem("（なし）", None)
            if company_id:
                seals = session.query(SealImage).filter_by(company_id=company_id).all()
                for s in seals:
                    label = f"{'★ ' if s.is_default else ''}{s.label}"
                    self._seal_combo.addItem(label, s.id)
            self._seal_combo.blockSignals(False)

            if hasattr(self, "_bank_combo"):
                if select_bank_id is not None:
                    for i in range(self._bank_combo.count()):
                        if self._bank_combo.itemData(i) == select_bank_id:
                            self._bank_combo.setCurrentIndex(i)
                            break
                else:
                    for i in range(self._bank_combo.count()):
                        if self._bank_combo.itemData(i) is not None:
                            b = session.get(BankAccount, self._bank_combo.itemData(i))
                            if b and b.is_default:
                                self._bank_combo.setCurrentIndex(i)
                                break

            if select_seal_id is not None:
                for i in range(self._seal_combo.count()):
                    if self._seal_combo.itemData(i) == select_seal_id:
                        self._seal_combo.setCurrentIndex(i)
                        break
            else:
                for i in range(self._seal_combo.count()):
                    if self._seal_combo.itemData(i) is not None:
                        s = session.get(SealImage, self._seal_combo.itemData(i))
                        if s and s.is_default:
                            self._seal_combo.setCurrentIndex(i)
                            break
        finally:
            session.close()

    def _on_issuer_combo_changed(self, _):
        self._reload_bank_seal_combo()

    def _load_edit_data(self):
        """編集モード：既存の Issuance からフォームを復元する。"""
        from app.database.connection import get_session
        from app.database.models import Issuance
        from sqlalchemy.orm import joinedload
        session = get_session()
        try:
            iss = (session.query(Issuance)
                   .options(joinedload(Issuance.lines))
                   .filter_by(id=self._edit_issuance_id)
                   .first())
            if iss is None:
                return
            self._member_number_edit.setText(iss.member_number or "")
            self._org_name.setText(iss.recipient_organization or "")
            self._kana_edit.setText(iss.recipient_kana or "")
            self._dept_edit.setText(getattr(iss, "recipient_department", "") or "")
            self._rep_name_edit.setText(iss.recipient_name or "")
            self._rep_kana_edit.setText(iss.recipient_name_kana or "")
            self._phone_edit.setText(iss.recipient_phone or "")
            if any([iss.recipient_kana,
                    getattr(iss, "recipient_department", ""),
                    iss.recipient_name, iss.recipient_name_kana]):
                self._show_detail()
            idx = self._delivery.findText(iss.delivery_method or "")
            if idx >= 0:
                self._delivery.setCurrentIndex(idx)
            if self._doc_type_str == "invoice":
                if iss.company_settings_id is not None:
                    self._reload_issuer_combo(
                        select_company_id=iss.company_settings_id,
                        select_bank_id=iss.bank_account_id,
                        select_seal_id=iss.seal_image_id,
                    )
                self._show_person_chk.setChecked(
                    iss.show_recipient_person if iss.show_recipient_person is not None else True)
            elif self._doc_type_str == "receipt":
                if iss.company_settings_id is not None:
                    self._reload_issuer_combo(
                        select_company_id=iss.company_settings_id,
                        select_seal_id=iss.seal_image_id,
                    )
            for line in iss.lines:
                self._add_row()
                self._populate_row_from_line(self._rows[-1], line)
        finally:
            session.close()
        self._update_total()

    def _populate_row_from_line(self, row: "_LineRow", line) -> None:
        """IssuanceLine の内容を行ウィジェットに復元する。"""
        if line.item_template_id is None:
            # 直接入力行
            row.tmpl_combo.blockSignals(True)
            row.tmpl_combo.setCurrentIndex(0)
            row.tmpl_combo.setEditText(line.item_name or "")
            row.tmpl_combo.blockSignals(False)
            row.price_edit.blockSignals(True)
            row.price_edit.setText(str(int(line.unit_price)))
            row.price_edit.blockSignals(False)
            row.qty_spin.blockSignals(True)
            row.qty_spin.setValue(int(line.quantity))
            row.qty_spin.blockSignals(False)
            return

        tmpl = next((t for t in self._templates if t.id == line.item_template_id), None)
        cat_id = tmpl.category_id if tmpl else None

        # カテゴリ選択（シグナル不要）
        row.cat_combo.blockSignals(True)
        for i in range(row.cat_combo.count()):
            if row.cat_combo.itemData(i) == cat_id:
                row.cat_combo.setCurrentIndex(i)
                break
        row.cat_combo.blockSignals(False)

        # テンプレートコンボを再構築してから選択
        self._refresh_tmpl_combo(row)
        row.tmpl_combo.blockSignals(True)
        for i in range(row.tmpl_combo.count()):
            if row.tmpl_combo.itemData(i) == line.item_template_id:
                row.tmpl_combo.setCurrentIndex(i)
                break
        row.tmpl_combo.blockSignals(False)

        row.price_edit.blockSignals(True)
        row.price_edit.setText(str(int(line.unit_price)))
        row.price_edit.blockSignals(False)

        row.qty_spin.blockSignals(True)
        row.qty_spin.setValue(int(line.quantity))
        row.qty_spin.blockSignals(False)

    def _tmpls_for_cat(self, cat_id) -> list:
        if cat_id is None:
            return self._templates
        return [t for t in self._templates if t.category_id == cat_id]

    def _add_template_master(self):
        """その場で新規テンプレートをマスタ登録し、選択肢に反映する。"""
        from PyQt6.QtWidgets import QDialog
        from app.ui.item_template_management import ItemTemplateDialog
        dlg = ItemTemplateDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload_master()

    def _add_category_master(self):
        """その場で新規業務名（カテゴリ）を登録し、選択肢に反映する。"""
        from PyQt6.QtWidgets import QDialog
        from app.ui.category_management import CategoryEditDialog
        from app.services.category_service import create_category
        dlg = CategoryEditDialog(self, title="業務名の登録")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, sort_order = dlg.values()
        if not name:
            return
        session = get_session()
        try:
            create_category(session, name, sort_order)
        finally:
            session.close()
        self._reload_master()

    # ── UI構築 ───────────────────────────────────────────

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # スクロール可能なコンテンツ領域（発行ボタンは外に固定）
        _content = QWidget()
        _cl = QVBoxLayout(_content)
        _cl.setContentsMargins(0, 0, 0, 0)
        _cl.setSpacing(8)

        # ── 上部2カラム ──────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        grp_dest = QGroupBox("宛先")
        dest_vbox = QVBoxLayout(grp_dest)
        dest_vbox.setContentsMargins(10, 8, 10, 8)
        dest_vbox.setSpacing(4)

        self._member_number_edit = QLineEdit()
        self._member_number_edit.setFixedHeight(FIELD_H)
        self._member_number_edit.textChanged.connect(self._on_member_num_text_changed)

        self._num_popup = QListWidget()
        self._num_popup.setWindowFlags(Qt.WindowType.Popup)
        self._num_popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._num_popup.setMaximumHeight(180)
        self._num_popup.hide()
        self._num_popup.itemClicked.connect(self._on_num_popup_clicked)

        self._btn_clear_member = QPushButton("クリア")
        self._btn_clear_member.setFixedSize(52, FIELD_H)
        self._btn_clear_member.clicked.connect(self._clear_member_fields)

        self._org_name = QLineEdit()
        self._org_name.setFixedHeight(FIELD_H)
        self._org_name.setPlaceholderText("必須")
        self._kana_edit = QLineEdit()
        self._kana_edit.setFixedHeight(FIELD_H)
        self._kana_edit.setPlaceholderText("フリガナ（並び替え・検索用）")
        self._dept_edit = QLineEdit()
        self._dept_edit.setFixedHeight(FIELD_H)
        self._dept_edit.setPlaceholderText("所属・役職名")
        self._rep_name_edit = QLineEdit()
        self._rep_name_edit.setFixedHeight(FIELD_H)
        self._rep_name_edit.setPlaceholderText("氏名（宛名に表示）")
        self._rep_kana_edit = QLineEdit()
        self._rep_kana_edit.setFixedHeight(FIELD_H)
        self._rep_kana_edit.setPlaceholderText("氏名フリガナ")
        self._phone_edit = QLineEdit()
        self._phone_edit.setFixedHeight(FIELD_H)
        self._phone_edit.setPlaceholderText("000-0000-0000")
        self._email = QLineEdit()
        self._email.setFixedHeight(FIELD_H)
        self._email.setPlaceholderText("メール送付の場合に入力")

        def _lbl(text):
            l = QLabel(text)
            l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return l

        def _col_cfg(g):
            g.setSpacing(6)
            g.setColumnMinimumWidth(0, 72)
            g.setColumnMinimumWidth(2, 80)
            g.setColumnStretch(1, 3)
            g.setColumnStretch(3, 2)

        # ── 常時表示（会員番号・事業所名・電話） ──────────────
        grid_basic = QGridLayout()
        _col_cfg(grid_basic)

        num_row_w = QWidget()
        num_row_l = QHBoxLayout(num_row_w)
        num_row_l.setContentsMargins(0, 0, 0, 0)
        num_row_l.setSpacing(4)
        num_row_l.addWidget(self._member_number_edit)
        num_row_l.addWidget(self._btn_clear_member)

        grid_basic.addWidget(_lbl("会員番号"), 0, 0)
        grid_basic.addWidget(num_row_w,        0, 1)
        grid_basic.addWidget(_lbl("電話番号"), 0, 2)
        grid_basic.addWidget(self._phone_edit, 0, 3)
        grid_basic.addWidget(_lbl("事業所名"), 1, 0)
        grid_basic.addWidget(self._org_name,   1, 1, 1, 3)
        dest_vbox.addLayout(grid_basic)

        # ── 詳細トグルボタン ─────────────────────────────────
        self._btn_detail_toggle = QPushButton("▶ フリガナ・氏名・メール等の詳細を入力")
        self._btn_detail_toggle.setFlat(True)
        self._btn_detail_toggle.setStyleSheet(
            "text-align: left; color: #0055aa; padding: 2px 0;"
        )
        self._btn_detail_toggle.clicked.connect(self._toggle_detail)
        dest_vbox.addWidget(self._btn_detail_toggle)

        # ── 詳細欄（折りたたみ） ─────────────────────────────
        self._detail_widget = QWidget()
        grid_detail = QGridLayout(self._detail_widget)
        _col_cfg(grid_detail)
        grid_detail.setContentsMargins(0, 0, 0, 0)

        grid_detail.addWidget(_lbl("フリガナ"),     0, 0)
        grid_detail.addWidget(self._kana_edit,      0, 1, 1, 3)
        grid_detail.addWidget(_lbl("所属・役職"),   1, 0)
        grid_detail.addWidget(self._dept_edit,      1, 1, 1, 3)
        grid_detail.addWidget(_lbl("氏名"),         2, 0)
        grid_detail.addWidget(self._rep_name_edit,  2, 1)
        grid_detail.addWidget(_lbl("氏名フリガナ"), 2, 2)
        grid_detail.addWidget(self._rep_kana_edit,  2, 3)
        grid_detail.addWidget(_lbl("メール"),       3, 0)
        grid_detail.addWidget(self._email,          3, 1, 1, 3)

        self._detail_widget.setVisible(False)
        dest_vbox.addWidget(self._detail_widget)

        top_row.addWidget(grp_dest, 6)

        grp_opts = QGroupBox("発行設定")
        opts_form = QFormLayout(grp_opts)
        opts_form.setContentsMargins(10, 8, 10, 8)
        opts_form.setVerticalSpacing(3)
        opts_form.setHorizontalSpacing(8)
        self._delivery = QComboBox()
        self._delivery.addItems(["印刷", "メール送付"])
        opts_form.addRow("発行方法", self._delivery)
        if self._doc_type_str == "invoice":
            self._issuer_combo = QComboBox()
            self._bank_combo   = QComboBox()
            self._seal_combo   = QComboBox()
            self._issuer_combo.currentIndexChanged.connect(self._on_issuer_combo_changed)
            opts_form.addRow("発行元",   self._issuer_combo)
            opts_form.addRow("銀行口座", self._bank_combo)
            opts_form.addRow("印鑑",     self._seal_combo)

            from app.utils.app_config import get_config as _get_cfg
            self._show_person_chk = QCheckBox("宛名に役職・氏名を印字する")
            self._show_person_chk.setChecked(_get_cfg().get("recipient_person_last", True))
            opts_form.addRow(self._show_person_chk)

            from app.utils.app_config import get_config as _gcfg
            _last_inv = _gcfg().get("last_issuance_counter_invoice", {})
            self._reload_issuer_combo(
                select_company_id=_last_inv.get("company_id"),
                select_bank_id=_last_inv.get("bank_account_id"),
                select_seal_id=_last_inv.get("seal_image_id"),
            )
            _inv_method = _last_inv.get("delivery_method", "印刷")
            _idx = self._delivery.findText(_inv_method)
            if _idx >= 0:
                self._delivery.setCurrentIndex(_idx)

            y, m = (date.today().year, date.today().month + 1) if date.today().month < 12 else (date.today().year + 1, 1)
            default_due = date(y, m, calendar.monthrange(y, m)[1])
            self._due_date = QDateEdit(QDate(default_due.year, default_due.month, default_due.day))
            self._due_date.setCalendarPopup(True)
            self._due_date.setDisplayFormat("yyyy/MM/dd")
            opts_form.addRow("支払期日", self._due_date)
            self._window_envelope_chk = QCheckBox("窓あき封筒モード（住所を印字）")
            opts_form.addRow(self._window_envelope_chk)

            self._addr_widget = QWidget()
            addr_form = QFormLayout(self._addr_widget)
            addr_form.setContentsMargins(0, 4, 0, 0)
            addr_form.setVerticalSpacing(3)
            addr_form.setHorizontalSpacing(8)
            self._postal_code_edit = QLineEdit()
            self._postal_code_edit.setFixedHeight(FIELD_H)
            self._postal_code_edit.setPlaceholderText("例：1234567")
            self._address1_edit = QLineEdit()
            self._address1_edit.setFixedHeight(FIELD_H)
            self._address1_edit.setPlaceholderText("都道府県・市区町村・番地（自動入力）")
            self._address2_edit = QLineEdit()
            self._address2_edit.setFixedHeight(FIELD_H)
            self._address2_edit.setPlaceholderText("建物名・部屋番号（任意）")
            addr_form.addRow("郵便番号", self._postal_code_edit)
            addr_form.addRow("住所",     self._address1_edit)
            addr_form.addRow("住所2",    self._address2_edit)
            self._addr_widget.setVisible(False)
            self._window_envelope_chk.toggled.connect(self._addr_widget.setVisible)
            opts_form.addRow(self._addr_widget)

            self._postal_timer = QTimer(self)
            self._postal_timer.setSingleShot(True)
            self._postal_timer.timeout.connect(self._do_postal_lookup)
            self._postal_code_edit.textChanged.connect(
                lambda: self._postal_timer.start(600))
        else:
            self._issuer_combo = QComboBox()
            self._seal_combo   = QComboBox()
            self._issuer_combo.currentIndexChanged.connect(self._on_issuer_combo_changed)
            opts_form.addRow("発行元", self._issuer_combo)
            opts_form.addRow("印鑑",   self._seal_combo)
            from app.utils.app_config import get_config as _gcfg
            _last_rcp = _gcfg().get("last_issuance_counter_receipt", {})
            self._reload_issuer_combo(
                select_company_id=_last_rcp.get("company_id"),
                select_seal_id=_last_rcp.get("seal_image_id"),
            )
            _rcp_method = _last_rcp.get("delivery_method", "印刷")
            _idx = self._delivery.findText(_rcp_method)
            if _idx >= 0:
                self._delivery.setCurrentIndex(_idx)
            fmt_note = QLabel("印刷形式：A5縦（固定）")
            fmt_note.setStyleSheet("color: #666; font-size: 11px;")
            opts_form.addRow("", fmt_note)
        top_row.addWidget(grp_opts, 3)

        _cl.addLayout(top_row)

        # ── 発行項目 ─────────────────────────────────────
        grp_lines = QGroupBox("発行項目")
        lines_layout = QVBoxLayout(grp_lines)
        lines_layout.setContentsMargins(8, 8, 8, 8)
        lines_layout.setSpacing(0)

        lines_layout.addWidget(self._make_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(240)

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: white;")
        self._rows_vbox = QVBoxLayout(self._rows_container)
        self._rows_vbox.setContentsMargins(0, 0, 0, 2)
        self._rows_vbox.setSpacing(0)
        self._rows_vbox.addStretch()
        scroll.setWidget(self._rows_container)
        lines_layout.addWidget(scroll)

        add_btn_row = QHBoxLayout()
        btn_add = QPushButton("＋ 項目を追加")
        btn_add.setFixedHeight(32)
        btn_add.clicked.connect(self._add_row)
        add_btn_row.addWidget(btn_add)
        btn_new_cat = QPushButton("＋ 新規業務名登録")
        btn_new_cat.setFixedHeight(32)
        btn_new_cat.clicked.connect(self._add_category_master)
        add_btn_row.addWidget(btn_new_cat)
        btn_new_tmpl = QPushButton("＋ 新規テンプレート…")
        btn_new_tmpl.setFixedHeight(32)
        btn_new_tmpl.clicked.connect(self._add_template_master)
        add_btn_row.addWidget(btn_new_tmpl)
        lines_layout.addLayout(add_btn_row)
        _cl.addWidget(grp_lines)

        # ── 合計 ─────────────────────────────────────────
        self._total_label = QLabel("合計：¥0")
        self._total_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #1D4ED8; padding: 6px 2px;")
        _cl.addWidget(self._total_label)

        # スクロール可能領域をメインレイアウトに追加
        _outer_scroll = QScrollArea()
        _outer_scroll.setWidgetResizable(True)
        _outer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        _outer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _outer_scroll.setWidget(_content)
        layout.addWidget(_outer_scroll, 1)

        # ── 発行ボタン（常に画面下部に固定）──────────────
        _btn_lbl = "修正して再発行" if self._edit_issuance_id else "発行する"
        self._btn_issue = QPushButton(_btn_lbl)
        self._btn_issue.setFixedHeight(44)
        self._btn_issue.setStyleSheet(
            "font-size: 14px; font-weight: bold;"
            "background: #1D4ED8; color: white; border-radius: 6px;")
        self._btn_issue.clicked.connect(self._issue)
        layout.addWidget(self._btn_issue)

        if not self._edit_issuance_id:
            self._add_row()

    def _make_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(30)
        hdr.setStyleSheet("background: #eef1f5; border-bottom: 1px solid #d0d0d0;")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(6)
        specs = [("業務名", W_CAT), ("項目", None), ("単価（円）", W_PRICE),
                 ("数量", W_QTY), ("小計", W_SUB), ("", W_SAVE), ("", W_DEL)]
        for text, w in specs:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-weight: bold; color: #333; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if w is None:
                lay.addWidget(lbl, 1)
            else:
                lbl.setFixedWidth(w)
                lay.addWidget(lbl)
        return hdr

    # ── コンボ更新ヘルパ ─────────────────────────────────

    def _refresh_cat_combo(self, combo: QComboBox):
        cur = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("（業務名を選択）", None)
        for c in self._categories:
            combo.addItem(c.name, c.id)
        if cur is not None:
            for i in range(combo.count()):
                if combo.itemData(i) == cur:
                    combo.setCurrentIndex(i)
                    break
        combo.blockSignals(False)

    def _refresh_tmpl_combo(self, row: _LineRow):
        cat_id    = row.cat_combo.currentData()
        cur_id    = row.tmpl_combo.currentData()
        cur_text  = row.tmpl_combo.currentText()  # 直接入力テキストを保持
        candidates = self._tmpls_for_cat(cat_id)
        row.tmpl_combo.blockSignals(True)
        row.tmpl_combo.clear()
        row.tmpl_combo.addItem("（項目を選択または入力）", None)
        for t in candidates:
            label = f"{t.name}　¥{int(t.unit_price):,}/{t.unit}"
            if cat_id is None:
                cname = self._cat_name_by_id.get(t.category_id)
                if cname:
                    label = f"{t.name}（{cname}）　¥{int(t.unit_price):,}/{t.unit}"
            row.tmpl_combo.addItem(label, t.id)
        restored = False
        if cur_id is not None:
            for i in range(row.tmpl_combo.count()):
                if row.tmpl_combo.itemData(i) == cur_id:
                    row.tmpl_combo.setCurrentIndex(i)
                    restored = True
                    break
        if not restored:
            row.tmpl_combo.setCurrentIndex(0)
            # テンプレート未選択かつ直接入力テキストがあれば復元
            _ph = "（項目を選択または入力）"
            if cur_text and cur_text != _ph:
                row.tmpl_combo.setEditText(cur_text)
        row.tmpl_combo.blockSignals(False)

    # ── 行操作 ──────────────────────────────────────────

    def _add_row(self):
        row = _LineRow(self)
        self._refresh_cat_combo(row.cat_combo)
        row.btn_save_tmpl.clicked.connect(lambda: self._save_row_as_template(row))
        # stretch の直前に挿入
        self._rows_vbox.insertWidget(self._rows_vbox.count() - 1, row)
        self._rows.append(row)
        self._update_total()

    def _save_row_as_template(self, row: "_LineRow"):
        from app.ui.item_template_management import ItemTemplateDialog
        _PH = "（項目を選択または入力）"
        name = row.tmpl_combo.currentText().strip()
        if not name or name == _PH:
            QMessageBox.warning(self, "未入力", "項目名を入力してください。")
            return
        dlg = ItemTemplateDialog(
            self,
            default_category_id=row.cat_combo.currentData(),
            default_name=name,
            default_price=row.price(),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        saved_name = dlg.result_name
        self._reload_master()
        # 登録したテンプレートをこの行で選択状態にする
        new_tmpl = next((t for t in self._templates if t.name == saved_name), None)
        if new_tmpl:
            row.cat_combo.blockSignals(True)
            for i in range(row.cat_combo.count()):
                if row.cat_combo.itemData(i) == new_tmpl.category_id:
                    row.cat_combo.setCurrentIndex(i)
                    break
            row.cat_combo.blockSignals(False)
            self._refresh_tmpl_combo(row)
            row.tmpl_combo.blockSignals(True)
            for i in range(row.tmpl_combo.count()):
                if row.tmpl_combo.itemData(i) == new_tmpl.id:
                    row.tmpl_combo.setCurrentIndex(i)
                    break
            row.tmpl_combo.blockSignals(False)
            row._update_save_btn()

    def _remove_row(self, row: _LineRow):
        if row not in self._rows:
            return
        self._rows.remove(row)
        self._rows_vbox.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._update_total()

    # ── シグナルハンドラ ─────────────────────────────────

    def _on_cat_changed(self, row: _LineRow):
        self._refresh_tmpl_combo(row)
        self._update_total()

    def _on_tmpl_changed(self, row: _LineRow):
        self._apply_template_to_row(row)

    def _apply_template_to_row(self, row: _LineRow):
        tmpl_id = row.tmpl_combo.currentData()
        tmpl = next((t for t in self._templates if t.id == tmpl_id), None)
        if tmpl is not None:
            row.price_edit.setText(str(int(tmpl.unit_price)))
        self._update_total()

    def _update_total(self):
        total = 0
        for row in self._rows:
            sub = row.price() * row.qty_spin.value()
            total += sub
            row.sub_label.setText(f"¥{sub:,}")
        self._total_label.setText(f"合計：¥{total:,}")

    # ── 会員マスタ補完 ───────────────────────────────────

    def _setup_completers(self):
        org_names = [m.organization_name for m in self._members if m.organization_name]
        org_c = QCompleter(org_names, self)
        org_c.setFilterMode(Qt.MatchFlag.MatchContains)
        org_c.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        org_c.activated.connect(self._on_org_selected)
        self._org_name.setCompleter(org_c)

        self._member_by_number = {
            m.member_number: m for m in self._members if m.member_number
        }

    def _on_org_selected(self, text: str):
        member = next((m for m in self._members
                       if m.organization_name == text), None)
        if member:
            self._fill_from_member(member)

    def _on_member_num_text_changed(self, text: str):
        q = unicodedata.normalize('NFKC', text.strip())
        self._num_popup.clear()
        if not q or not self._member_by_number:
            self._num_popup.hide()
            return
        q_lower = q.lower()
        starts = sorted(k for k in self._member_by_number if k.lower().startswith(q_lower))
        contains = sorted(k for k in self._member_by_number if q_lower in k.lower() and not k.lower().startswith(q_lower))
        matches = (starts + contains)[:20]
        if not matches:
            self._num_popup.hide()
            return
        for m in matches:
            self._num_popup.addItem(m)
        pos = self._member_number_edit.mapToGlobal(
            QPoint(0, self._member_number_edit.height())
        )
        self._num_popup.move(pos)
        self._num_popup.setFixedWidth(max(self._member_number_edit.width(), 100))
        self._num_popup.show()

    def _on_num_popup_clicked(self, item):
        text = item.text()
        member = self._member_by_number.get(text)
        self._num_popup.hide()
        if member:
            self._fill_from_member(member)

    def _on_num_selected(self, text: str):
        member = self._member_by_number.get(text)
        if member:
            self._fill_from_member(member)

    def _toggle_detail(self):
        visible = not self._detail_widget.isVisible()
        self._detail_widget.setVisible(visible)
        self._btn_detail_toggle.setText(
            "▼ フリガナ・氏名・メール等の詳細を入力" if visible
            else "▶ フリガナ・氏名・メール等の詳細を入力"
        )

    def _show_detail(self):
        self._detail_widget.setVisible(True)
        self._btn_detail_toggle.setText("▼ フリガナ・氏名・メール等の詳細を入力")

    def _hide_detail(self):
        self._detail_widget.setVisible(False)
        self._btn_detail_toggle.setText("▶ フリガナ・氏名・メール等の詳細を入力")

    def _clear_member_fields(self):
        self._num_popup.hide()
        self._member_number_edit.blockSignals(True)
        self._member_number_edit.clear()
        self._member_number_edit.blockSignals(False)
        self._org_name.clear()
        self._kana_edit.clear()
        self._dept_edit.clear()
        self._rep_name_edit.clear()
        self._rep_kana_edit.clear()
        self._phone_edit.clear()
        self._email.clear()
        self._hide_detail()

    def _fill_from_member(self, member):
        self._num_popup.hide()
        self._member_number_edit.blockSignals(True)
        self._member_number_edit.setText(member.member_number or "")
        self._member_number_edit.blockSignals(False)
        self._org_name.setText(member.organization_name or "")
        self._kana_edit.setText(member.organization_kana or "")
        self._dept_edit.setText(getattr(member, "department", "") or "")
        self._rep_name_edit.setText(member.representative_name or "")
        self._rep_kana_edit.setText(member.representative_kana or "")
        self._phone_edit.setText(member.phone or "")
        self._email.setText(member.email or "")
        # 詳細欄に何か入っていれば自動展開
        has_detail = any([
            member.organization_kana, getattr(member, "department", ""),
            member.representative_name, member.representative_kana,
            member.email,
        ])
        if has_detail:
            self._show_detail()
        if self._doc_type_str == "invoice":
            self._postal_code_edit.blockSignals(True)
            self._postal_code_edit.setText(member.postal_code or "")
            self._postal_code_edit.blockSignals(False)
            self._address1_edit.setText(member.address or "")
            self._address2_edit.setText(member.address2 or "")

    # ── 郵便番号検索 ─────────────────────────────────────

    def _do_postal_lookup(self):
        if self._doc_type_str != "invoice":
            return
        zipcode = (self._postal_code_edit.text().strip()
                   .replace("-", "").replace("ー", "").replace("−", ""))
        if len(zipcode) == 7 and zipcode.isdigit():
            if self._postal_worker and self._postal_worker.isRunning():
                self._postal_worker.quit()
            self._postal_worker = _PostalWorker(zipcode)
            self._postal_worker.found.connect(self._address1_edit.setText)
            self._postal_worker.start()

    # ── 発行 ─────────────────────────────────────────────

    def _derive_project_name(self) -> str:
        """選択された項目（テンプレート）の業務名から集計先プロジェクト名を決める。

        業務名コンボの選択ではなく、項目自身が属する業務名を使うので、
        業務名を選ばずに項目だけ選んでも正しい業務名に集計される。
        """
        seen: dict[str, bool] = {}
        for row in self._rows:
            tmpl_id = row.tmpl_combo.currentData()
            tmpl = next((t for t in self._templates if t.id == tmpl_id), None)
            if tmpl is None:
                continue
            name = self._cat_name_by_id.get(tmpl.category_id)
            if name and name not in seen:
                seen[name] = True
        return "・".join(seen.keys()) if seen else "直接発行"

    def _issue(self):
        org = self._org_name.text().strip()
        if not org:
            QMessageBox.warning(self, "入力エラー", "事業所名を入力してください。")
            return
        member_no  = self._member_number_edit.text().strip()
        kana       = self._kana_edit.text().strip()
        dept       = self._dept_edit.text().strip()
        rep        = self._rep_name_edit.text().strip()
        rep_kana   = self._rep_kana_edit.text().strip()
        phone      = self._phone_edit.text().strip()
        email = self._email.text().strip()
        if self._delivery.currentText() == "メール送付":
            if not email:
                QMessageBox.warning(self, "入力エラー",
                                    "発行方法が「メール送付」の場合は"
                                    "メールアドレスを入力してください。")
                return
            from app.services.email_service import validate_email_addr
            try:
                email = validate_email_addr(email)
            except ValueError as e:
                QMessageBox.warning(self, "入力エラー", str(e))
                return
        if not self._rows:
            QMessageBox.warning(self, "入力エラー", "項目を1つ以上追加してください。")
            return

        _PH = "（項目を選択または入力）"
        lines_data = []
        for row in self._rows:
            tmpl_id = row.tmpl_combo.currentData()
            tmpl    = next((t for t in self._templates if t.id == tmpl_id), None)
            if tmpl is not None:
                price = row.price() or int(tmpl.unit_price)
                lines_data.append({
                    "item_template_id": tmpl.id,
                    "item_name":        tmpl.name,
                    "quantity":         row.qty_spin.value(),
                    "unit":             tmpl.unit,
                    "unit_price":       price,
                    "tax_rate":         tmpl.tax_rate,
                })
            else:
                name = row.tmpl_combo.currentText().strip()
                if name and name != _PH:
                    lines_data.append({
                        "item_template_id": None,
                        "item_name":        name,
                        "quantity":         row.qty_spin.value(),
                        "unit":             "式",
                        "unit_price":       row.price(),
                        "tax_rate":         10,
                    })

        if not lines_data:
            QMessageBox.warning(self, "エラー",
                                "項目が入力されていません。\n"
                                "各行で項目を選択するか、直接入力してください。")
            return

        from app.utils.pdf_helpers import get_company_and_bank
        _check_session = get_session()
        try:
            _company, _ = get_company_and_bank(_check_session)
        finally:
            _check_session.close()
        if not _company:
            QMessageBox.warning(
                self, "発行不可",
                "自社情報（会社設定）が未登録のため発行できません。\n"
                "設定 → 会社情報 から登録してください。")
            return

        issuer_company_id = bank_account_id = seal_image_id = None
        show_recipient_person = True
        if self._doc_type_str == "invoice":
            issuer_company_id     = self._issuer_combo.currentData()
            bank_account_id       = self._bank_combo.currentData()
            seal_image_id         = self._seal_combo.currentData()
            show_recipient_person = self._show_person_chk.isChecked()
            from app.utils.app_config import get_config as _get_cfg, save_config as _save_cfg
            _cfg = _get_cfg()
            _cfg["recipient_person_last"] = show_recipient_person
            _cfg["last_issuance_counter_invoice"] = {
                "delivery_method": self._delivery.currentText(),
                "company_id": issuer_company_id,
                "bank_account_id": bank_account_id,
                "seal_image_id": seal_image_id,
            }
            _save_cfg(_cfg)
        elif self._doc_type_str == "receipt":
            issuer_company_id = self._issuer_combo.currentData()
            seal_image_id     = self._seal_combo.currentData()
            from app.utils.app_config import get_config as _get_cfg, save_config as _save_cfg
            _cfg = _get_cfg()
            _cfg["last_issuance_counter_receipt"] = {
                "delivery_method": self._delivery.currentText(),
                "company_id": issuer_company_id,
                "seal_image_id": seal_image_id,
            }
            _save_cfg(_cfg)

        doc_type = self._doc_type_str
        session  = get_session()
        try:
            from app.services.operation_log_service import add_log as _add_log
            label = "請求書" if doc_type == "invoice" else "領収書"
            if self._edit_issuance_id is not None:
                iss = update_direct_issuance(
                    session,
                    issuance_id            = self._edit_issuance_id,
                    lines_data             = lines_data,
                    recipient_organization = org,
                    recipient_name         = rep,
                    delivery_method        = self._delivery.currentText(),
                    staff_id               = current_user.get_id(),
                    staff_name             = current_user.get_name(),
                    member_number          = member_no,
                    recipient_kana         = kana,
                    recipient_department   = dept,
                    recipient_name_kana    = rep_kana,
                    recipient_phone        = phone,
                    company_settings_id   = issuer_company_id,
                    bank_account_id       = bank_account_id,
                    seal_image_id         = seal_image_id,
                    show_recipient_person = show_recipient_person,
                )
                _add_log(session, "内容修正", "issuance", iss.id,
                         f"{label} {iss.doc_number} 宛先：{iss.recipient_organization or iss.recipient_name}")
            else:
                project_name = self._derive_project_name()
                today = date.today()
                iss = create_direct_issuance(
                    session,
                    lines_data             = lines_data,
                    recipient_organization = org,
                    recipient_name         = rep,
                    doc_type               = doc_type,
                    fiscal_year            = today.year,
                    month                  = today.month,
                    staff_id               = current_user.get_id(),
                    staff_name             = current_user.get_name(),
                    delivery_method        = self._delivery.currentText(),
                    project_name           = project_name,
                    member_number          = member_no,
                    recipient_kana         = kana,
                    recipient_department   = dept,
                    recipient_name_kana    = rep_kana,
                    recipient_phone        = phone,
                    company_settings_id   = issuer_company_id,
                    bank_account_id       = bank_account_id,
                    seal_image_id         = seal_image_id,
                    show_recipient_person = show_recipient_person,
                )
                _add_log(session, "発行", "issuance", iss.id,
                         f"{label} {iss.doc_number} 宛先：{iss.recipient_organization or iss.recipient_name}")
            # ── 保存先を選択（メール送付以外）──────────────────────────
            from PyQt6.QtWidgets import QFileDialog
            from app.utils.pdf_helpers import get_pdf_output_dir
            _delivery_text = self._delivery.currentText()
            _save_path: str | None = None
            # 発行・修正再発行どちらも保存先を選択させる（PDF再生成のたびに保存先を確認）
            if _delivery_text != "メール送付":
                _out_dir = get_pdf_output_dir()
                _default_name = os.path.join(_out_dir, f"{iss.doc_number}.pdf")
                _save_path, _ = QFileDialog.getSaveFileName(
                    self, "PDFの保存先を選択", _default_name, "PDF ファイル (*.pdf)"
                )
                if not _save_path:
                    QMessageBox.information(
                        self, "保存キャンセル",
                        "発行は記録されましたが、PDFは保存されませんでした。\n"
                        "再発行タブから出力できます。",
                    )
            from app.utils.pdf_helpers import generate_and_open
            due_date = None
            window_envelope = False
            postal_code = address1 = address2 = ""
            if doc_type == "invoice":
                qd = self._due_date.date()
                due_date = date(qd.year(), qd.month(), qd.day())
                window_envelope = self._window_envelope_chk.isChecked()
                if window_envelope:
                    postal_code = self._postal_code_edit.text().strip()
                    address1    = self._address1_edit.text().strip()
                    address2    = self._address2_edit.text().strip()
            from app.database.models import Project as _Project
            _proj = session.get(_Project, iss.project_id)
            if _delivery_text == "メール送付":
                # メール添付用に生成（ビューアで開かない）
                generate_and_open(iss, session, due_date=due_date, open_file=False,
                                  window_envelope=window_envelope,
                                  recipient_postal_code=postal_code,
                                  recipient_address=address1,
                                  recipient_address2=address2,
                                  project=_proj)
            elif _save_path:
                # 指定パスに保存してビューアで開く
                generate_and_open(iss, session, due_date=due_date,
                                  save_path=_save_path,
                                  window_envelope=window_envelope,
                                  recipient_postal_code=postal_code,
                                  recipient_address=address1,
                                  recipient_address2=address2,
                                  project=_proj)
            if _delivery_text == "メール送付":
                from app.services.email_service import prepare_issuance_email
                from app.services.operation_log_service import add_log
                from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog
                from app.ui.m365_mail_worker import M365MailWorker
                from app.utils.app_config import get_m365_client_id, get_m365_tenant_id
                from PyQt6.QtWidgets import QApplication, QProgressDialog
                try:
                    to_addr, subject, body_html, pdf_path = prepare_issuance_email(
                        session, iss, to_addr=email or None)
                except Exception as prep_err:
                    add_log(session, "メール送信失敗", "issuance", iss.id,
                            f"{iss.doc_number}：{prep_err}")
                    QMessageBox.critical(self, "メール送信エラー", str(prep_err))
                else:
                    dlg = InvoiceMailConfirmDialog(
                        self,
                        to_recipients=[to_addr],
                        subject=subject,
                        body_html=body_html,
                        pdf_path=pdf_path,
                        invoice_no=iss.doc_number,
                        customer_name=(iss.recipient_organization
                                       or iss.recipient_name or ""),
                        amount_text=f"¥{iss.amount:,}" if iss.amount else "",
                    )
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        client_id = get_m365_client_id()
                        tenant_id = get_m365_tenant_id()
                        if not client_id or not tenant_id:
                            QMessageBox.critical(
                                self, "設定エラー",
                                "Microsoft 365 の Client ID / Tenant ID が"
                                "設定されていません。\n"
                                "設定 → メール設定から入力してください。")
                        else:
                            thread = QThread(self)
                            worker = M365MailWorker(
                                client_id, tenant_id, [to_addr],
                                subject, body_html, pdf_path)
                            worker.moveToThread(thread)
                            prog = QProgressDialog(
                                "Microsoft 365 でメール送信中…",
                                None, 0, 0, self)
                            prog.setWindowTitle("メール送信")
                            prog.setWindowModality(
                                Qt.WindowModality.WindowModal)
                            prog.show()
                            _result: dict = {}
                            def _on_done(r, _r=_result, _t=thread):
                                _r["ok"] = r
                                _t.quit()
                            def _on_err(msg, _r=_result, _t=thread):
                                _r["err"] = msg
                                _t.quit()
                            worker.finished.connect(_on_done)
                            worker.failed.connect(_on_err)
                            thread.started.connect(worker.run)
                            thread.finished.connect(prog.close)
                            thread.finished.connect(thread.deleteLater)
                            thread.start()
                            while thread.isRunning():
                                QApplication.processEvents()
                            if "ok" in _result:
                                add_log(session, "メール送信", "issuance",
                                        iss.id,
                                        f"{iss.doc_number} → {to_addr}")
                                QMessageBox.information(
                                    self, "メール送信",
                                    f"{to_addr} にメールを送信しました。")
                            else:
                                err_msg = _result.get("err", "不明なエラー")
                                add_log(session, "メール送信失敗", "issuance",
                                        iss.id,
                                        f"{iss.doc_number}：{err_msg}")
                                QMessageBox.critical(
                                    self, "メール送信エラー", err_msg)
        except Exception as e:
            QMessageBox.critical(self, "発行エラー", str(e))
            return
        finally:
            session.close()

        if self._edit_issuance_id is not None:
            self.edit_completed.emit()
        else:
            self._member_number_edit.clear()
            self._org_name.clear()
            self._kana_edit.clear()
            self._dept_edit.clear()
            self._rep_name_edit.clear()
            self._rep_kana_edit.clear()
            self._phone_edit.clear()
            self._email.clear()
            if self._doc_type_str == "invoice":
                self._postal_code_edit.clear()
                self._address1_edit.clear()
                self._address2_edit.clear()
            for row in list(self._rows):
                self._remove_row(row)
            self._add_row()
            self._update_total()
