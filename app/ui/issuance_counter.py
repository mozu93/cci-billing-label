# app/ui/issuance_counter.py
import calendar
import os
import unicodedata
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QGroupBox,
    QLineEdit, QSpinBox, QComboBox, QLabel, QPushButton,
    QMessageBox, QFrame, QScrollArea, QStyleFactory, QDialog,
    QCheckBox, QDateEdit, QCompleter,
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QTimer, QThread, QStringListModel
from PyQt6.QtGui import QIntValidator
from app.database.connection import get_session
from app.services.category_service import get_active_categories
from app.services.company_service import (
    list_issuers, list_bank_accounts, list_seals, get_bank_account, get_seal
)
from app.services.item_template_service import get_all_active_templates
from app.services.issuance_service import (
    create_direct_issuance, update_direct_issuance, get_issuance_with_lines
)
from app.services.project_service import get_project_by_id
from app.ui.item_template_management import TAX_RATE_OPTIONS
from app.utils import current_user
from app.utils.applog import get_logger

_log = get_logger(__name__)

# 列幅・行高（px）
W_CAT   = 120
W_PRICE = 90
W_QTY   = 80
W_UNIT  = 60
W_TAX   = 110
W_SUB   = 90
W_SAVE  = 70
W_DEL   = 40
# 項目列だけは伸縮する。ヘッダー(QLabel)と行(QComboBox)で最小幅が違うと、
# 幅が足りなくなったときに縮み方が食い違って列がズレるため、同じ値を使う。
# 品目名が見切れない幅を確保する。基準幅780pxでも他の列と両立する。
W_ITEM_MIN = 150
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
        # ヘッダーのラベルと同じ最小幅にして、狭いときの縮み方を揃える。
        self.tmpl_combo.setMinimumWidth(W_ITEM_MIN)
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
        # 0 も入力できる。数量0の行は発行時に明細から除く（_issue）
        self.qty_spin.setRange(0, 9999)
        self.qty_spin.setValue(1)
        # 単位（テンプレートの値を初期値にし、ここで直せる）
        self.unit_edit = QLineEdit("式")
        self.unit_edit.setFixedWidth(W_UNIT)
        self.unit_edit.setFixedHeight(FIELD_H)
        self.unit_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_edit.setMaxLength(8)
        # 税区分（テンプレート選択時はその税率を初期値にし、その場で変更できる）
        self.tax_combo = QComboBox()
        self.tax_combo.setFixedWidth(W_TAX)
        self.tax_combo.setFixedHeight(FIELD_H)
        for label, value in TAX_RATE_OPTIONS:
            self.tax_combo.addItem(label, value)
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

        for w in (self.cat_combo, self.tmpl_combo, self.price_edit,
                  self.qty_spin, self.unit_edit, self.tax_combo):
            if style:
                w.setStyle(style)
            w.setStyleSheet(_SS_FIELD)

        lay.addWidget(self.cat_combo)
        lay.addWidget(self.tmpl_combo, 1)
        lay.addWidget(self.price_edit)
        lay.addWidget(self.qty_spin)
        lay.addWidget(self.unit_edit)
        lay.addWidget(self.tax_combo)
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

    def unit(self) -> str:
        """空欄のまま発行されても PDF が崩れないよう「式」で補う。"""
        return self.unit_edit.text().strip() or "式"


class _PostalWorker(QThread):
    """郵便番号 → 住所変換（zipcloud API）"""
    found = pyqtSignal(str)

    def __init__(self, zipcode: str):
        super().__init__()
        self._zipcode = zipcode

    def run(self):
        try:
            import urllib.request
            import json
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
            _log.info("郵便番号検索に失敗: %s", self._zipcode, exc_info=True)


class IssuanceCounterWidget(QWidget):
    edit_completed = pyqtSignal()

    def __init__(self, doc_type: str = "receipt", edit_issuance_id: int | None = None,
                 simplified: bool = False):
        super().__init__()
        self._doc_type_str = doc_type
        self._simplified = simplified
        self._edit_issuance_id = edit_issuance_id
        self._edit_loaded = False
        self._categories = []
        self._templates  = []
        self._cat_name_by_id: dict[int, str] = {}
        self._rows: list[_LineRow] = []
        self._cell_style = QStyleFactory.create("Fusion")
        self._postal_worker: _PostalWorker | None = None
        self._last_issued_signature: tuple | None = None
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
        session = get_session()
        try:
            issuers = list_issuers(session)
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
        company_id = self._issuer_combo.currentData()
        session = get_session()
        try:
            if hasattr(self, "_bank_combo"):
                self._bank_combo.blockSignals(True)
                self._bank_combo.clear()
                self._bank_combo.addItem("（なし）", None)
                if company_id:
                    banks = list_bank_accounts(session, company_id)
                    for b in banks:
                        label = f"{'★ ' if b.is_default else ''}{b.label} {b.bank_name}"
                        self._bank_combo.addItem(label, b.id)
                self._bank_combo.blockSignals(False)

            self._seal_combo.blockSignals(True)
            self._seal_combo.clear()
            self._seal_combo.addItem("（なし）", None)
            if company_id:
                seals = list_seals(session, company_id)
                for s in seals:
                    label = f"{'★ ' if s.is_default else ''}{s.label}"
                    self._seal_combo.addItem(label, s.id)
            self._seal_combo.blockSignals(False)

            if hasattr(self, "_bank_combo"):
                bank_selected = False
                if select_bank_id is not None:
                    for i in range(self._bank_combo.count()):
                        if self._bank_combo.itemData(i) == select_bank_id:
                            self._bank_combo.setCurrentIndex(i)
                            bank_selected = True
                            break
                if not bank_selected:
                    for i in range(self._bank_combo.count()):
                        if self._bank_combo.itemData(i) is not None:
                            b = get_bank_account(
                                session, self._bank_combo.itemData(i))
                            if b and b.is_default:
                                self._bank_combo.setCurrentIndex(i)
                                bank_selected = True
                                break
                # 既存データにデフォルト指定がない場合も「なし」にせず、
                # その発行元で最初に登録された口座を初期選択する。
                if not bank_selected and self._bank_combo.count() > 1:
                    self._bank_combo.setCurrentIndex(1)

            if select_seal_id is not None:
                for i in range(self._seal_combo.count()):
                    if self._seal_combo.itemData(i) == select_seal_id:
                        self._seal_combo.setCurrentIndex(i)
                        break
            else:
                for i in range(self._seal_combo.count()):
                    if self._seal_combo.itemData(i) is not None:
                        s = get_seal(session, self._seal_combo.itemData(i))
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
        session = get_session()
        try:
            iss = get_issuance_with_lines(session, self._edit_issuance_id)
            if iss is None:
                return
            self._member_number_edit.setText(iss.member_number or "")
            self._org_name.setText(iss.recipient_organization or "")
            self._kana_edit.setText(iss.recipient_kana or "")
            self._dept_edit.setText(getattr(iss, "recipient_department", "") or "")
            self._rep_name_edit.setText(iss.recipient_name or "")
            self._rep_kana_edit.setText(iss.recipient_name_kana or "")
            self._phone_edit.setText(iss.recipient_phone or "")
            self._email.setText(getattr(iss, "recipient_email", "") or "")
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
            row.unit_edit.setText(line.unit or "式")
            idx = row.tax_combo.findData(line.tax_rate)
            if idx >= 0:
                row.tax_combo.setCurrentIndex(idx)
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

        # テンプレートの現在の単位・税率ではなく、発行時に保存した値を出す。
        row.unit_edit.setText(line.unit or "式")
        idx = row.tax_combo.findData(line.tax_rate)
        if idx >= 0:
            row.tax_combo.setCurrentIndex(idx)

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

        grp_dest = QGroupBox("宛先（空欄可）" if self._simplified else "宛先")
        dest_vbox = QVBoxLayout(grp_dest)
        dest_vbox.setContentsMargins(10, 8, 10, 8)
        dest_vbox.setSpacing(4)

        self._member_number_edit = QLineEdit()
        self._member_number_edit.setFixedHeight(FIELD_H)
        # 候補一覧は QCompleter で出す。自前の Popup（QListWidget）だとキー入力を
        # 横取りし、1桁入力すると2桁目以降が入らなかった。QCompleter の一覧は
        # キー入力を入力欄へ流す。並び順は自前で決めるので、Qt 側では絞り込まない
        self._member_number_model = QStringListModel(self)
        self._member_number_completer = QCompleter(self._member_number_model, self)
        self._member_number_completer.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self._member_number_completer.setWidget(self._member_number_edit)
        self._member_number_completer.activated.connect(self._on_num_selected)
        # textEdited は利用者の入力でだけ届く（候補選択後の setText では再表示しない）
        self._member_number_edit.textEdited.connect(self._on_member_num_text_changed)

        self._btn_clear_member = QPushButton("クリア")
        self._btn_clear_member.setFixedSize(52, FIELD_H)
        self._btn_clear_member.clicked.connect(self._clear_member_fields)

        self._org_name = QLineEdit()
        self._org_name.setFixedHeight(FIELD_H)
        self._org_name.setPlaceholderText("任意（空欄可）" if self._simplified else "必須")
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
        # 所属・役職と氏名は宛名の印字に関わるので、折りたたまず常に見せる
        grid_basic.addWidget(_lbl("所属・役職"), 2, 0)
        grid_basic.addWidget(self._dept_edit,     2, 1)
        grid_basic.addWidget(_lbl("氏名"),       2, 2)
        grid_basic.addWidget(self._rep_name_edit, 2, 3)
        dest_vbox.addLayout(grid_basic)

        if self._doc_type_str == "invoice":
            # 宛名・住所の印字オプションは、影響する入力欄のすぐ下に置く
            from app.utils.app_config import get_config as _get_cfg
            self._show_person_chk = QCheckBox("宛名に役職・氏名を印字する")
            self._show_person_chk.setChecked(_get_cfg().get("recipient_person_last", True))
            dest_vbox.addWidget(self._show_person_chk)
            dest_vbox.addLayout(self._build_address_section())

        # ── 詳細トグルボタン ─────────────────────────────────
        self._btn_detail_toggle = QPushButton("▶ フリガナ・メール等の詳細を入力")
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
        grid_detail.addWidget(self._kana_edit,      0, 1)
        grid_detail.addWidget(_lbl("氏名フリガナ"), 0, 2)
        grid_detail.addWidget(self._rep_kana_edit,  0, 3)
        grid_detail.addWidget(_lbl("メール"),       1, 0)
        grid_detail.addWidget(self._email,          1, 1, 1, 3)

        self._detail_widget.setVisible(False)
        dest_vbox.addWidget(self._detail_widget)

        top_row.addWidget(grp_dest, 6)

        grp_opts = QGroupBox("発行設定")
        opts_form = QFormLayout(grp_opts)
        opts_form.setContentsMargins(10, 8, 10, 8)
        opts_form.setVerticalSpacing(3)
        opts_form.setHorizontalSpacing(8)
        self._delivery = QComboBox()
        self._delivery.addItems(["印刷"] if self._simplified else ["印刷", "メール送付"])
        opts_form.addRow("発行方法", self._delivery)
        if self._doc_type_str == "invoice":
            self._issuer_combo = QComboBox()
            self._bank_combo   = QComboBox()
            self._seal_combo   = QComboBox()
            self._issuer_combo.currentIndexChanged.connect(self._on_issuer_combo_changed)
            opts_form.addRow("発行元",   self._issuer_combo)
            opts_form.addRow("銀行口座", self._bank_combo)
            opts_form.addRow("印鑑",     self._seal_combo)

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
            # 支払期日は下部の合計欄に置く（_build の末尾）
            self._due_date = QDateEdit(QDate(default_due.year, default_due.month, default_due.day))
            self._due_date.setCalendarPopup(True)
            self._due_date.setDisplayFormat("yyyy/MM/dd")
            self._btn_filename = QPushButton("PDFファイル名を設定…")
            self._btn_filename.clicked.connect(self._open_filename_settings)
            opts_form.addRow("保存名", self._btn_filename)
        else:
            self._issuer_combo = QComboBox()
            self._seal_combo   = QComboBox()
            self._issuer_combo.currentIndexChanged.connect(self._on_issuer_combo_changed)
            opts_form.addRow("発行元", self._issuer_combo)
            opts_form.addRow("印鑑",   self._seal_combo)
            from app.utils.app_config import get_config as _gcfg
            _cfg_key = "last_issuance_counter_simplified" if self._simplified else "last_issuance_counter_receipt"
            _last_rcp = _gcfg().get(_cfg_key, {})
            self._reload_issuer_combo(
                select_company_id=_last_rcp.get("company_id"),
                select_seal_id=_last_rcp.get("seal_image_id"),
            )
            if not self._simplified:
                _rcp_method = _last_rcp.get("delivery_method", "印刷")
                _idx = self._delivery.findText(_rcp_method)
                if _idx >= 0:
                    self._delivery.setCurrentIndex(_idx)
            fmt_note = QLabel("印刷形式：A5縦（固定）")
            fmt_note.setStyleSheet("color: #666; font-size: 11px;")
            opts_form.addRow("", fmt_note)
            if self._simplified:
                self._count_spin = QSpinBox()
                self._count_spin.setRange(1, 999)
                self._count_spin.setValue(1)
                opts_form.addRow("発行枚数", self._count_spin)
                self._copy_chk = QCheckBox("控えを出力する")
                self._copy_chk.setChecked(_last_rcp.get("include_copy", True))
                opts_form.addRow("", self._copy_chk)
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

        # ── 支払期日・合計（発行ボタンの直前に必ず目に入る位置） ──────
        self._summary_bar = QWidget()
        bar = QHBoxLayout(self._summary_bar)
        bar.setContentsMargins(2, 0, 2, 0)
        bar.setSpacing(8)
        if self._doc_type_str == "invoice":
            due_lbl = QLabel("支払期日")
            due_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
            self._due_date.setFixedHeight(FIELD_H)
            self._due_date.setStyleSheet("font-size: 14px; font-weight: bold;")
            bar.addWidget(due_lbl)
            bar.addWidget(self._due_date)
        bar.addStretch()
        # 直前に発行した番号（入力を残すので、発行済みかどうかをここで示す）
        self._issued_label = QLabel("")
        self._issued_label.setStyleSheet("color: #15803D; font-weight: bold;")
        bar.addWidget(self._issued_label)
        bar.addSpacing(16)
        self._total_label = QLabel("合計：¥0")
        self._total_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #1D4ED8; padding: 6px 2px;")
        bar.addWidget(self._total_label)

        # スクロール可能領域をメインレイアウトに追加
        _outer_scroll = QScrollArea()
        _outer_scroll.setWidgetResizable(True)
        _outer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        _outer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _outer_scroll.setWidget(_content)
        layout.addWidget(_outer_scroll, 1)

        # 支払期日・合計は発行ボタンとともに画面下部に固定（スクロールで隠れない）
        layout.addWidget(self._summary_bar)

        # ── 発行ボタン（常に画面下部に固定）──────────────
        _btn_lbl = "修正して再発行" if self._edit_issuance_id else "発行する"
        self._btn_issue = QPushButton(_btn_lbl)
        self._btn_issue.setFixedHeight(44)
        self._btn_issue.setStyleSheet(
            "font-size: 14px; font-weight: bold;"
            "background: #1D4ED8; color: white; border-radius: 6px;")
        self._btn_issue.clicked.connect(self._issue)

        self._btn_preview = QPushButton("プレビュー")
        self._btn_preview.setFixedSize(140, 44)
        self._btn_preview.setToolTip("今の入力内容で「見本」入りのPDFを表示します（発行はしません）")
        self._btn_preview.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1D4ED8;"
            "background: white; border: 2px solid #1D4ED8; border-radius: 6px;")
        self._btn_preview.clicked.connect(self._preview)

        self._btn_test_send = QPushButton("テスト送信")
        self._btn_test_send.setFixedSize(120, 44)
        self._btn_test_send.setToolTip(
            "番号を使わずに、自分宛てに「見本」のメールを試し送信します（発行はしません）")
        self._btn_test_send.setStyleSheet(self._btn_preview.styleSheet())
        self._btn_test_send.clicked.connect(self._test_send)
        # メール送付のときだけ使う
        self._btn_test_send.setVisible(self._delivery.currentText() == "メール送付")
        self._delivery.currentTextChanged.connect(
            lambda text: self._btn_test_send.setVisible(text == "メール送付"))

        # 宛先欄の「クリア」（会員情報だけ消す）と区別する
        self._btn_clear = QPushButton("すべてクリア")
        self._btn_clear.setFixedSize(110, 44)
        self._btn_clear.setToolTip("入力をすべて消して、新しく作成します")
        self._btn_clear.clicked.connect(self._clear_all)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        if not self._edit_issuance_id:   # 修正・再発行の画面では使わない
            action_row.addWidget(self._btn_clear)
        action_row.addWidget(self._btn_preview)
        action_row.addWidget(self._btn_test_send)
        action_row.addWidget(self._btn_issue, 1)
        layout.addLayout(action_row)

        if not self._edit_issuance_id:
            self._add_row()

    def _build_address_section(self) -> QVBoxLayout:
        """宛先欄の住所部分（請求書のみ）。

        住所は会員情報として常に見せ、印字しないとき（窓あき封筒でない）は
        グレーにして編集できないようにする。"""
        box = QVBoxLayout()
        box.setContentsMargins(0, 6, 0, 0)
        box.setSpacing(4)

        self._window_envelope_chk = QCheckBox("窓あき封筒で住所を印字する")
        box.addWidget(self._window_envelope_chk)

        self._postal_code_edit = QLineEdit()
        self._postal_code_edit.setFixedHeight(FIELD_H)
        self._postal_code_edit.setFixedWidth(90)
        self._postal_code_edit.setPlaceholderText("例：1234567")
        self._address1_edit = QLineEdit()
        self._address1_edit.setFixedHeight(FIELD_H)
        self._address1_edit.setPlaceholderText("都道府県・市区町村・番地（自動入力）")
        self._address2_edit = QLineEdit()
        self._address2_edit.setFixedHeight(FIELD_H)
        self._address2_edit.setPlaceholderText("建物名・部屋番号（任意）")

        def _lbl(text):
            l = QLabel(text)
            l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return l

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setColumnMinimumWidth(0, 72)   # 上の宛先欄と見出しの幅をそろえる
        grid.setColumnStretch(3, 1)
        grid.addWidget(_lbl("郵便番号"),        0, 0)
        grid.addWidget(self._postal_code_edit, 0, 1)
        grid.addWidget(_lbl("住所"),           0, 2)
        grid.addWidget(self._address1_edit,    0, 3)
        grid.addWidget(_lbl("住所2"),          1, 2)
        grid.addWidget(self._address2_edit,    1, 3)
        box.addLayout(grid)

        def _set_address_enabled(on: bool):
            for f in (self._postal_code_edit, self._address1_edit, self._address2_edit):
                f.setEnabled(on)
        _set_address_enabled(False)
        self._window_envelope_chk.toggled.connect(_set_address_enabled)

        self._postal_timer = QTimer(self)
        self._postal_timer.setSingleShot(True)
        self._postal_timer.timeout.connect(self._do_postal_lookup)
        self._postal_code_edit.textChanged.connect(
            lambda: self._postal_timer.start(600))
        return box

    def _make_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(30)
        hdr.setStyleSheet("background: #eef1f5; border-bottom: 1px solid #d0d0d0;")
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(6)
        specs = [("業務名", W_CAT), ("項目", None), ("単価（円）", W_PRICE),
                 ("数量", W_QTY), ("単位", W_UNIT), ("税区分", W_TAX),
                 ("小計", W_SUB), ("", W_SAVE), ("", W_DEL)]
        for text, w in specs:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-weight: bold; color: #333; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if w is None:
                # 行の項目コンボと同じ最小幅にして、縮み方を揃える。
                lbl.setMinimumWidth(W_ITEM_MIN)
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
            # 単価と単位は隣の入力欄に出るので、ここには載せない。
            # 重複するうえ、狭い幅では品目名が見切れて読めなくなる。
            label = t.name
            if cat_id is None:
                cname = self._cat_name_by_id.get(t.category_id)
                if cname:
                    label = f"{t.name}（{cname}）"
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
            default_unit=row.unit(),
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
            row.unit_edit.setText(tmpl.unit or "式")
            idx = row.tax_combo.findData(tmpl.tax_rate)
            if idx >= 0:
                row.tax_combo.setCurrentIndex(idx)
        self._update_total()

    def _collect_lines_data(self) -> list[dict]:
        """各行を発行用の明細データにする。単位は画面の値を優先する。"""
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
                    "unit":             row.unit(),
                    "unit_price":       price,
                    "tax_rate":         row.tax_combo.currentData(),
                })
            else:
                name = row.tmpl_combo.currentText().strip()
                if name and name != _PH:
                    lines_data.append({
                        "item_template_id": None,
                        "item_name":        name,
                        "quantity":         row.qty_spin.value(),
                        "unit":             row.unit(),
                        "unit_price":       row.price(),
                        "tax_rate":         row.tax_combo.currentData(),
                    })
        return lines_data

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

    def _member_number_candidates(self) -> list[str]:
        """入力中の会員番号の候補。前方一致を先、部分一致を後に、最大20件。"""
        q = unicodedata.normalize('NFKC', self._member_number_edit.text().strip())
        if not q:
            return []
        q_lower = q.lower()
        starts = sorted(k for k in self._member_by_number if k.lower().startswith(q_lower))
        contains = sorted(k for k in self._member_by_number if q_lower in k.lower() and not k.lower().startswith(q_lower))
        return (starts + contains)[:20]

    def _on_member_num_text_changed(self, _text: str):
        matches = self._member_number_candidates()
        self._member_number_model.setStringList(matches)
        if matches:
            self._member_number_completer.complete()
        else:
            self._member_number_completer.popup().hide()

    def _on_num_selected(self, text: str):
        member = self._member_by_number.get(text)
        if member:
            self._fill_from_member(member)

    def _toggle_detail(self):
        visible = not self._detail_widget.isVisible()
        self._detail_widget.setVisible(visible)
        self._btn_detail_toggle.setText(
            "▼ フリガナ・メール等の詳細を入力" if visible
            else "▶ フリガナ・メール等の詳細を入力"
        )

    def _show_detail(self):
        self._detail_widget.setVisible(True)
        self._btn_detail_toggle.setText("▼ フリガナ・メール等の詳細を入力")

    def _hide_detail(self):
        self._detail_widget.setVisible(False)
        self._btn_detail_toggle.setText("▶ フリガナ・メール等の詳細を入力")

    def _clear_member_fields(self):
        self._member_number_completer.popup().hide()
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
        self._member_number_completer.popup().hide()
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
        # 詳細欄（折りたたみ側）に何か入っていれば自動展開。
        # 所属・役職と氏名は常に表示しているので判定に含めない
        has_detail = any([
            member.organization_kana, member.representative_kana, member.email,
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

    def _open_filename_settings(self):
        from app.ui.pdf_filename_dialog import PdfFilenameDialog
        PdfFilenameDialog(self).exec()

    def _issuable_lines(self) -> list[dict] | None:
        """発行（プレビュー）に使う明細。使えないときは警告して None を返す。"""
        if not self._rows:
            QMessageBox.warning(self, "入力エラー", "項目を1つ以上追加してください。")
            return None
        all_lines = self._collect_lines_data()
        # 数量0の行は明細に含めない（まとめて発行と同じ扱い）
        lines_data = [l for l in all_lines if l["quantity"] > 0]
        if not all_lines:
            QMessageBox.warning(self, "エラー",
                                "項目が入力されていません。\n"
                                "各行で項目を選択するか、直接入力してください。")
            return None
        if not lines_data:
            QMessageBox.warning(self, "エラー",
                                "数量が1以上の項目がありません。\n"
                                "数量0の項目は明細に含まれません。")
            return None
        return lines_data

    def _build_preview(self) -> tuple:
        """今の入力内容から、未保存の発行データとプレビュー PDF の作成引数を作る。

        入力に不足があれば警告して (None, None) を返す。"""
        org = self._org_name.text().strip()
        if not org and not self._simplified:
            QMessageBox.warning(self, "入力エラー", "事業所名を入力してください。")
            return None, None
        lines_data = self._issuable_lines()
        if lines_data is None:
            return None, None

        from app.services.issuance_service import build_preview_issuance
        is_invoice = self._doc_type_str == "invoice"
        fields = dict(
            recipient_organization=org,
            recipient_name=self._rep_name_edit.text().strip(),
            recipient_department=self._dept_edit.text().strip(),
            member_number=self._member_number_edit.text().strip(),
            company_settings_id=self._issuer_combo.currentData(),
            seal_image_id=self._seal_combo.currentData(),
        )
        kwargs = dict(subject=self._derive_project_name())
        if is_invoice:
            qd = self._due_date.date()
            fields.update(bank_account_id=self._bank_combo.currentData(),
                          show_recipient_person=self._show_person_chk.isChecked())
            kwargs.update(
                due_date=date(qd.year(), qd.month(), qd.day()),
                window_envelope=self._window_envelope_chk.isChecked(),
                recipient_postal_code=self._postal_code_edit.text().strip(),
                recipient_address=self._address1_edit.text().strip(),
                recipient_address2=self._address2_edit.text().strip())
        else:
            # 発行時と同じく、メール送付の領収書は控えなし
            kwargs["receipt_include_copy"] = self._delivery.currentText() != "メール送付"
        return build_preview_issuance(lines_data, self._doc_type_str, **fields), kwargs

    def _preview(self):
        """今の入力内容で「見本」入りの PDF を作って開く。DB には記録しない。"""
        iss, kwargs = self._build_preview()
        if iss is None:
            return
        from app.services.print_service import open_pdf
        from app.utils import pdf_helpers
        session = get_session()
        try:
            path = pdf_helpers.generate_preview_pdf(session, iss, **kwargs)
        except Exception as e:
            _log.warning("プレビューの作成に失敗", exc_info=True)
            QMessageBox.critical(self, "プレビューエラー", str(e))
            return
        finally:
            session.close()
        if not path:
            QMessageBox.warning(
                self, "プレビュー不可",
                "自社情報（会社設定）が未登録のためプレビューできません。\n"
                "設定 → 会社情報 から登録してください。")
            return
        open_pdf(path)

    def _issue_simplified(self):
        """簡易インボイス：宛先なしで、指定枚数ぶん連番発行する。

        請求書化・メール送付・修正再発行は対象外の、印刷専用の簡易な発行経路。
        既存の _issue() は分岐が多いため、混ぜずに独立させている。"""
        lines_data = self._issuable_lines()
        if lines_data is None:
            return
        total = sum(int(l["unit_price"]) * int(l["quantity"]) for l in lines_data)
        if total == 0 and QMessageBox.question(
                self, "合計0円の確認",
                "合計が0円です。このまま発行しますか？"
        ) != QMessageBox.StandardButton.Yes:
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

        org        = self._org_name.text().strip()
        member_no  = self._member_number_edit.text().strip()
        kana       = self._kana_edit.text().strip()
        dept       = self._dept_edit.text().strip()
        rep        = self._rep_name_edit.text().strip()
        rep_kana   = self._rep_kana_edit.text().strip()
        phone      = self._phone_edit.text().strip()
        email      = self._email.text().strip()
        issuer_company_id = self._issuer_combo.currentData()
        seal_image_id     = self._seal_combo.currentData()
        count         = self._count_spin.value()
        include_copy  = self._copy_chk.isChecked()

        from app.utils.app_config import get_config as _get_cfg, save_config as _save_cfg
        _cfg = _get_cfg()
        _cfg["last_issuance_counter_simplified"] = {
            "company_id": issuer_company_id,
            "seal_image_id": seal_image_id,
            "include_copy": include_copy,
        }
        _save_cfg(_cfg)

        from app.services.operation_log_service import add_log as _add_log
        from app.services.print_service import open_pdf
        from app.utils import pdf_helpers

        session = get_session()
        issuances: list = []
        issued_numbers: list[str] = []
        paths: list[str] = []
        merged_path: str | None = None
        try:
            today = date.today()
            project_name = self._derive_project_name()
            for _ in range(count):
                iss = create_direct_issuance(
                    session,
                    lines_data             = lines_data,
                    recipient_organization = org,
                    recipient_name         = rep,
                    doc_type               = "receipt",
                    fiscal_year            = today.year,
                    month                  = today.month,
                    staff_id               = current_user.get_id(),
                    staff_name             = current_user.get_name(),
                    delivery_method        = "印刷",
                    project_name           = project_name,
                    member_number          = member_no,
                    recipient_kana         = kana,
                    recipient_department   = dept,
                    recipient_name_kana    = rep_kana,
                    recipient_phone        = phone,
                    recipient_email        = email,
                    company_settings_id   = issuer_company_id,
                    seal_image_id         = seal_image_id,
                )
                issuances.append(iss)
                issued_numbers.append(iss.doc_number)
                _add_log(session, "発行", "issuance", iss.id,
                         f"領収書 {iss.doc_number} 宛先："
                         f"{iss.recipient_organization or '（簡易インボイス）'}")

            if include_copy or len(issuances) == 1:
                for iss in issuances:
                    path = pdf_helpers.generate_and_open(
                        iss, session, open_file=False,
                        receipt_include_copy=include_copy,
                        project=get_project_by_id(session, iss.project_id))
                    if not path:
                        QMessageBox.warning(
                            self, "発行不可",
                            "自社情報（会社設定）が未登録のため発行できません。\n"
                            "設定 → 会社情報 から登録してください。")
                        return
                    paths.append(path)
            else:
                # 控え不要・複数枚：原本のみを2件（上下）ずつA5にまとめて印刷する
                from app.services.pdf.receipt_pdf import generate_receipt_originals_pdf
                project = get_project_by_id(session, issuances[0].project_id)
                company, _bank, seal = pdf_helpers.get_issuer_for_project(
                    session, project, issuance=issuances[0])
                if not company:
                    QMessageBox.warning(
                        self, "発行不可",
                        "自社情報（会社設定）が未登録のため発行できません。\n"
                        "設定 → 会社情報 から登録してください。")
                    return
                filename = f"{issuances[0].doc_number}-{issuances[-1].doc_number}.pdf"
                merged_path = pdf_helpers.available_pdf_path(
                    pdf_helpers.get_pdf_output_dir(), filename)
                generate_receipt_originals_pdf(
                    issuances, company, merged_path, seal_image=seal)
                for iss in issuances:
                    iss.pdf_path = merged_path
                session.commit()
        except Exception as e:
            QMessageBox.critical(self, "発行エラー", str(e))
            return
        finally:
            session.close()

        if merged_path:
            open_pdf(merged_path)
        elif len(paths) == 1:
            open_pdf(paths[0])
        else:
            pdf_helpers.merge_and_open(paths, "簡易インボイス")

        if len(issued_numbers) == 1:
            self._issued_label.setText(f"{issued_numbers[0]} を発行しました")
        else:
            self._issued_label.setText(
                f"{issued_numbers[0]}〜{issued_numbers[-1]}"
                f"（{len(issued_numbers)}枚）を発行しました")

    def _issue(self):
        if self._simplified:
            self._issue_simplified()
            return
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
        lines_data = self._issuable_lines()
        if lines_data is None:
            return
        # 発行後も入力を残すので、うっかり同じ請求書を二重に発行しないよう確認する
        if (self._edit_issuance_id is None
                and self._last_issued_signature == self._input_signature()
                and QMessageBox.question(
                    self, "二重発行の確認",
                    "直前に発行したものと同じ内容です。\n"
                    "同じ内容でもう1枚発行しますか？"
                ) != QMessageBox.StandardButton.Yes):
            return
        total = sum(int(l["unit_price"]) * int(l["quantity"]) for l in lines_data)
        if total == 0 and QMessageBox.question(
                self, "合計0円の確認",
                "合計が0円です。このまま発行しますか？"
        ) != QMessageBox.StandardButton.Yes:
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
        due_date = None
        if doc_type == "invoice":
            qd = self._due_date.date()
            due_date = date(qd.year(), qd.month(), qd.day())
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
                    recipient_email        = email,
                    company_settings_id   = issuer_company_id,
                    bank_account_id       = bank_account_id,
                    seal_image_id         = seal_image_id,
                    show_recipient_person = show_recipient_person,
                    due_date              = due_date,
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
                    recipient_email        = email,
                    company_settings_id   = issuer_company_id,
                    bank_account_id       = bank_account_id,
                    seal_image_id         = seal_image_id,
                    show_recipient_person = show_recipient_person,
                    due_date              = due_date,
                )
                _add_log(session, "発行", "issuance", iss.id,
                         f"{label} {iss.doc_number} 宛先：{iss.recipient_organization or iss.recipient_name}")
            issued_no = iss.doc_number   # セッションを閉じた後も表示に使う
            from app.utils import pdf_helpers
            _delivery_text = self._delivery.currentText()
            window_envelope = False
            postal_code = address1 = address2 = ""
            if doc_type == "invoice":
                window_envelope = self._window_envelope_chk.isChecked()
                if window_envelope:
                    postal_code = self._postal_code_edit.text().strip()
                    address1    = self._address1_edit.text().strip()
                    address2    = self._address2_edit.text().strip()
            pdf_opts = dict(
                due_date=due_date,
                window_envelope=window_envelope,
                recipient_postal_code=postal_code,
                recipient_address=address1,
                recipient_address2=address2,
                project=get_project_by_id(session, iss.project_id),
            )
            if _delivery_text == "メール送付":
                # メール添付用に生成（ビューアで開かない）
                pdf_helpers.generate_and_open(
                    iss, session, open_file=False,
                    receipt_include_copy=doc_type != "receipt", **pdf_opts)
            else:
                outputted = self._save_print_pdf(session, iss, pdf_opts)
            if _delivery_text == "メール送付":
                from app.services.email_service import (
                    get_issuance_email_context,
                    prepare_issuance_email,
                )
                from app.services.operation_log_service import add_log
                from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog
                mail_sent = False
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
                        template_kind=iss.doc_type,
                        template_context=get_issuance_email_context(
                            session, iss),
                    )
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        to_recipients = dlg.to_recipients()
                        cc_recipients = dlg.cc_recipients()
                        bcc_recipients = dlg.bcc_recipients()
                        subject = dlg.subject()
                        body_html = dlg.body_html()
                        to_addr = to_recipients[0]
                        # 確認画面で変更した主宛先も再発行用に保持する。
                        iss.recipient_email = to_addr
                        session.commit()
                        ok, err_msg = self._send_via_m365(
                            to_recipients, subject, body_html, pdf_path,
                            cc_recipients=cc_recipients,
                            bcc_recipients=bcc_recipients)
                        if ok:
                            from datetime import datetime
                            iss.mail_subject = subject
                            iss.mail_sent_at = datetime.now()
                            iss.mail_delivery_status = "pending"
                            iss.mail_delivery_message = "Microsoft 365の配信結果を確認してください。"
                            iss.mail_delivery_checked_at = None
                            session.commit()
                            add_log(session, "メール送信", "issuance",
                                    iss.id,
                                    f"{iss.doc_number} → "
                                    f"{', '.join(to_recipients)}")
                            mail_sent = True
                            QMessageBox.information(
                                self, "メール送信",
                                f"{', '.join(to_recipients)} "
                                "にメールを送信しました。")
                        elif err_msg:   # None は設定不備（表示済み）
                            add_log(session, "メール送信失敗", "issuance",
                                    iss.id,
                                    f"{iss.doc_number}：{err_msg}")
                            QMessageBox.critical(
                                self, "メール送信エラー", err_msg)
                # キャンセル・設定不備・送信失敗のいずれでも、送れなかったら印刷を提案する
                outputted = mail_sent or self._offer_switch_to_print(session, iss, pdf_opts)
            if not outputted and self._handle_no_output(session, iss):
                return   # 取り消した。入力は残っているので、そのまま発行し直せる
        except Exception as e:
            QMessageBox.critical(self, "発行エラー", str(e))
            return
        finally:
            session.close()

        if self._edit_issuance_id is not None:
            self.edit_completed.emit()
        else:
            # 連続して作成できるよう入力は残す。消すときは「クリア」ボタン
            self._last_issued_signature = self._input_signature()
            self._issued_label.setText(f"{issued_no} を発行しました")

    def _send_via_m365(self, to_recipients: list[str], subject: str,
                       body_html: str, pdf_path: str | None,
                       cc_recipients: list[str] | None = None,
                       bcc_recipients: list[str] | None = None
                       ) -> tuple[bool, str | None]:
        """Microsoft 365 でメールを送り、終わるまで待つ。

        戻り値は (成功したか, エラーメッセージ)。設定が未入力のときは
        ここで設定エラーを表示し、(False, None) を返す。"""
        from PyQt6.QtWidgets import QApplication, QProgressDialog
        from app.ui.m365_mail_worker import M365MailWorker
        from app.utils.app_config import get_m365_client_id, get_m365_tenant_id
        client_id = get_m365_client_id()
        tenant_id = get_m365_tenant_id()
        if not client_id or not tenant_id:
            QMessageBox.critical(
                self, "設定エラー",
                "Microsoft 365 の Client ID / Tenant ID が"
                "設定されていません。\n"
                "設定 → メール送信設定から入力してください。")
            return False, None
        thread = QThread(self)
        worker = M365MailWorker(
            client_id, tenant_id, to_recipients,
            subject, body_html, pdf_path,
            cc_recipients=cc_recipients or None,
            bcc_recipients=bcc_recipients or None)
        worker.moveToThread(thread)
        prog = QProgressDialog("Microsoft 365 でメール送信中…", None, 0, 0, self)
        prog.setWindowTitle("メール送信")
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.show()
        result: dict = {}

        def _on_done(r):
            result["ok"] = r
            thread.quit()

        def _on_err(msg):
            result["err"] = msg
            thread.quit()
        worker.finished.connect(_on_done)
        worker.failed.connect(_on_err)
        thread.started.connect(worker.run)
        thread.finished.connect(prog.close)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        # 待ち画面（WindowModal）の間はメイン画面を閉じられないので、
        # スレッドが動作中に破棄されることはない
        while thread.isRunning():
            QApplication.processEvents()
        if "ok" in result:
            return True, None
        return False, result.get("err", "不明なエラー")

    def _test_send(self):
        """番号を使わずに、指定したアドレスへ「見本」の請求書メールを試し送信する。

        DB への記録・採番・送信記録は一切しない。本番の確認画面（CC・BCC を
        編集できる）は使わず、宛先は聞いた1件だけにする（お客様への誤送信防止）。"""
        iss, kwargs = self._build_preview()
        if iss is None:
            return
        from PyQt6.QtWidgets import QInputDialog
        from app.services.email_service import build_test_issuance_email, validate_email_addr
        from app.utils.app_config import get_m365_test_recipient
        addr, ok = QInputDialog.getText(
            self, "テスト送信",
            "テストメールの送信先（自分のアドレス）：",
            text=get_m365_test_recipient())
        if not ok or not addr.strip():
            return
        try:
            addr = validate_email_addr(addr.strip())
        except ValueError as e:
            QMessageBox.warning(self, "入力エラー", str(e))
            return

        from app.utils import pdf_helpers
        session = get_session()
        try:
            pdf_path = pdf_helpers.generate_preview_pdf(session, iss, **kwargs)
            if not pdf_path:
                QMessageBox.warning(
                    self, "テスト送信不可",
                    "自社情報（会社設定）が未登録のため作成できません。\n"
                    "設定 → 会社情報 から登録してください。")
                return
            subject, body_html = build_test_issuance_email(
                session, iss, project_name=kwargs.get("subject", ""))
        except Exception as e:
            _log.warning("テスト送信の準備に失敗", exc_info=True)
            QMessageBox.critical(self, "テスト送信エラー", str(e))
            return
        finally:
            session.close()

        sent, err_msg = self._send_via_m365([addr], subject, body_html, pdf_path)
        if sent:
            QMessageBox.information(
                self, "テスト送信",
                f"{addr} にテストメールを送信しました。\n"
                "（請求書は発行されていません）")
        elif err_msg:
            QMessageBox.critical(self, "テスト送信エラー", err_msg)

    def _save_print_pdf(self, session, iss, pdf_opts: dict) -> bool:
        """保存先を選ばせて印刷用 PDF を作り、ビューアで開く。保存したら True。"""
        from PyQt6.QtWidgets import QFileDialog
        from app.utils import pdf_helpers
        default_name = os.path.join(pdf_helpers.get_pdf_output_dir(),
                                    pdf_helpers.build_pdf_filename(iss))
        save_path, _ = QFileDialog.getSaveFileName(
            self, "PDFの保存先を選択", default_name, "PDF ファイル (*.pdf)")
        if not save_path:
            return False
        pdf_helpers.generate_and_open(iss, session, save_path=save_path, **pdf_opts)
        return True

    def _offer_switch_to_print(self, session, iss, pdf_opts: dict) -> bool:
        """メールで送らなかったとき、同じ番号のまま印刷に切り替えるか聞く。

        画面の発行方法を変えて発行し直すと、番号の違う2枚目ができてしまうため。
        印刷用 PDF を保存したら True。"""
        if QMessageBox.question(
                self, "印刷に切り替え",
                f"{iss.doc_number} はメールで送信されていません。\n"
                "同じ番号のまま印刷に切り替えますか？"
        ) != QMessageBox.StandardButton.Yes:
            return False
        from app.services.issuance_service import switch_to_print
        switch_to_print(session, iss)
        return self._save_print_pdf(session, iss, pdf_opts)

    def _handle_no_output(self, session, iss) -> bool:
        """印刷もメール送信もされなかったときの後始末。発行を取り消したら True。

        新規発行は取り消す（何も出力していないので）。修正・再発行は元の発行を
        消せないので、記録は残して再発行タブからの出力を案内する。"""
        if self._edit_issuance_id is not None:
            QMessageBox.information(
                self, "保存キャンセル",
                "発行は記録されましたが、PDFは保存されませんでした。\n"
                "再発行タブから出力できます。")
            return False
        from app.services.issuance_service import cancel_unoutput_issuance
        number = iss.doc_number
        cancel_unoutput_issuance(session, iss)
        QMessageBox.information(
            self, "発行を取り消しました",
            f"印刷もメール送信もされなかったため、{number} の発行を取り消しました。\n"
            "（この番号は欠番になります。入力内容はそのまま残っています）")
        return True

    def _input_signature(self) -> tuple:
        """発行内容を決める入力値すべて。前回の発行と同じ内容かの判定に使う。"""
        fields = [
            self._member_number_edit.text(), self._org_name.text(),
            self._kana_edit.text(), self._dept_edit.text(),
            self._rep_name_edit.text(), self._rep_kana_edit.text(),
            self._phone_edit.text(), self._email.text(),
            self._delivery.currentText(),
            self._issuer_combo.currentData(), self._seal_combo.currentData(),
        ]
        if self._doc_type_str == "invoice":
            fields += [
                self._bank_combo.currentData(), self._show_person_chk.isChecked(),
                self._due_date.date().toString("yyyyMMdd"),
                self._window_envelope_chk.isChecked(),
                self._postal_code_edit.text(), self._address1_edit.text(),
                self._address2_edit.text(),
            ]
        lines = tuple(tuple(sorted(l.items())) for l in self._collect_lines_data())
        return tuple(fields) + (lines,)

    def _clear_all(self):
        """入力をすべて消して、新しい発行を始められる状態にする。"""
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
        self._last_issued_signature = None
        self._issued_label.setText("")
