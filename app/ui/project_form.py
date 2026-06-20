# app/ui/project_form.py
from datetime import date
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QWidget, QLineEdit, QComboBox, QSpinBox, QTextEdit,
    QPushButton, QLabel, QMessageBox, QFrame,
    QScrollArea, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.category_service import get_active_categories, create_category
from app.services.item_template_service import (
    get_all_active_templates, get_templates_by_category, create_item_template
)
from app.services.project_service import (
    create_project, get_project_by_id,
    add_template_to_project, get_project_templates
)

TAX_RATE_OPTIONS = [("消費税10%", 10), ("消費税8%", 8), ("非課税", 0), ("不課税", -1)]


class _ItemRow(QFrame):
    """発行項目1行（項目名 / 単価 / 単位 / 税区分 / テンプレ登録 / 削除）"""

    def __init__(self, dialog: "ProjectFormDialog"):
        super().__init__()
        self._dialog = dialog
        self.setStyleSheet(
            "QFrame { border-bottom: 1px solid #e2e2e2; background: white; }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(6)

        self.name_combo = QComboBox()
        self.name_combo.setEditable(True)
        self.name_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.name_combo.addItem("（項目を選択または入力）", None)
        self.name_combo.lineEdit().setPlaceholderText("（項目を選択または入力）")

        self.price_spin = QSpinBox()
        self.price_spin.setRange(0, 9_999_999)
        self.price_spin.setFixedWidth(110)
        self.price_spin.setGroupSeparatorShown(True)

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 9999)
        self.qty_spin.setValue(1)
        self.qty_spin.setFixedWidth(64)

        self.unit_edit = QLineEdit("式")
        self.unit_edit.setFixedWidth(48)
        self.unit_edit.setPlaceholderText("式")

        self.tax_combo = QComboBox()
        self.tax_combo.setFixedWidth(110)
        for label, value in TAX_RATE_OPTIONS:
            self.tax_combo.addItem(label, value)

        self.btn_save_tmpl = QPushButton("テンプレ登録")
        self.btn_save_tmpl.setFixedWidth(80)
        self.btn_save_tmpl.setEnabled(False)
        self.btn_save_tmpl.setToolTip("品目名と単価をテンプレートマスタに登録します")
        self.btn_save_tmpl.setStyleSheet(
            "QPushButton { font-size: 10px; color: #1565c0;"
            " border: 1px solid #1565c0; border-radius: 3px;"
            " padding: 1px 3px; background: transparent; }"
            "QPushButton:hover { background: #e3f2fd; }"
            "QPushButton:disabled { color: #bbb; border-color: #ccc; }")

        self.btn_del = QPushButton("✕")
        self.btn_del.setFixedSize(28, 26)
        self.btn_del.setStyleSheet(
            "QPushButton { color: #cc4444; border: none;"
            " background: transparent; font-weight: bold; }"
            "QPushButton:hover { color: #ff0000; }")

        lay.addWidget(self.name_combo, 1)
        lay.addWidget(QLabel("単価"))
        lay.addWidget(self.price_spin)
        lay.addWidget(QLabel("数量"))
        lay.addWidget(self.qty_spin)
        lay.addWidget(QLabel("単位"))
        lay.addWidget(self.unit_edit)
        lay.addWidget(QLabel("税"))
        lay.addWidget(self.tax_combo)
        lay.addWidget(self.btn_save_tmpl)
        lay.addWidget(self.btn_del)

        self.name_combo.currentIndexChanged.connect(self._on_name_changed)
        self.name_combo.lineEdit().textChanged.connect(self._update_save_btn)
        self.btn_del.clicked.connect(lambda: dialog._remove_row(self))
        self.btn_save_tmpl.clicked.connect(lambda: dialog._save_row_as_template(self))

    def _on_name_changed(self):
        tmpl_id = self.name_combo.currentData()
        if tmpl_id is not None:
            tmpl = next((t for t in self._dialog._templates if t.id == tmpl_id), None)
            if tmpl:
                self.price_spin.blockSignals(True)
                self.price_spin.setValue(int(tmpl.unit_price))
                self.price_spin.blockSignals(False)
                self.unit_edit.setText(tmpl.unit or "式")
                idx = self.tax_combo.findData(tmpl.tax_rate)
                if idx >= 0:
                    self.tax_combo.setCurrentIndex(idx)
        self._update_save_btn()

    def _update_save_btn(self):
        _PH = "（項目を選択または入力）"
        is_direct = self.name_combo.currentData() is None
        text = self.name_combo.currentText().strip()
        self.btn_save_tmpl.setEnabled(is_direct and bool(text) and text != _PH)

    def refresh_combo(self, templates: list):
        cur_id = self.name_combo.currentData()
        cur_text = self.name_combo.currentText()
        self.name_combo.blockSignals(True)
        self.name_combo.clear()
        self.name_combo.addItem("（項目を選択または入力）", None)
        for t in templates:
            self.name_combo.addItem(f"{t.name}（¥{int(t.unit_price):,}）", t.id)
        if cur_id is not None:
            for i in range(self.name_combo.count()):
                if self.name_combo.itemData(i) == cur_id:
                    self.name_combo.setCurrentIndex(i)
                    break
            else:
                self.name_combo.setCurrentIndex(0)
        else:
            self.name_combo.setCurrentIndex(0)
            _PH = "（項目を選択または入力）"
            if cur_text and cur_text != _PH:
                self.name_combo.setEditText(cur_text)
        self.name_combo.blockSignals(False)
        self._update_save_btn()

    def item_name(self) -> str:
        return self.name_combo.currentText().strip()

    def template_id(self) -> int | None:
        return self.name_combo.currentData()


class ProjectFormDialog(QDialog):
    def __init__(self, project_id: int | None = None, parent=None):
        super().__init__(parent)
        self._project_id = project_id
        self._templates: list = []
        self._rows: list[_ItemRow] = []
        self.setWindowTitle("請求・領収書データの登録" if project_id is None
                            else "請求・領収書データの編集")
        self.resize(780, 560)
        self.setStyleSheet(
            "QLineEdit, QComboBox, QSpinBox { "
            "border: 1px solid #b5b5b5; border-radius: 3px; "
            "padding: 3px 4px; background: white; }"
            "QTextEdit { border: 1px solid #b5b5b5; border-radius: 3px; "
            "background: white; }"
        )
        self._build()
        if project_id:
            self._load(project_id)
        else:
            self._add_row()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # ── 2カラムフォーム ──────────────────────────────────
        top_cols = QHBoxLayout()
        top_cols.setSpacing(0)

        # 左カラム：基本情報
        left_w = QWidget()
        left_outer = QVBoxLayout(left_w)
        left_outer.setContentsMargins(0, 0, 12, 0)
        left_outer.setSpacing(0)

        left_form = QFormLayout()
        left_form.setVerticalSpacing(3)
        left_form.setHorizontalSpacing(8)
        left_form.setContentsMargins(0, 0, 0, 0)

        self._fiscal_year = QSpinBox()
        self._fiscal_year.setRange(2000, 2099)
        self._fiscal_year.setValue(date.today().year)
        self._fiscal_year.setMaximumWidth(80)

        self._category = QComboBox()
        self._category.currentIndexChanged.connect(self._on_category_change)
        cat_row_w = QWidget()
        cat_lay = QHBoxLayout(cat_row_w)
        cat_lay.setContentsMargins(0, 0, 0, 0)
        cat_lay.setSpacing(4)
        cat_lay.addWidget(self._category, 1)
        btn_new_cat = QPushButton("＋ 新規業務名…")
        btn_new_cat.setFixedWidth(120)
        btn_new_cat.clicked.connect(self._add_category_master)
        cat_lay.addWidget(btn_new_cat)

        self._title = QLineEdit()
        self._title.setPlaceholderText("件名（例：2026 視察研修会参加費）")

        self._notes = QTextEdit()
        self._notes.setFixedHeight(44)

        left_form.addRow("年度",   self._fiscal_year)
        left_form.addRow("業務名", cat_row_w)
        left_form.addRow("件名",   self._title)
        left_form.addRow("備考",   self._notes)

        left_outer.addLayout(left_form)
        left_outer.addStretch()
        left_w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        top_cols.addWidget(left_w, 6)

        # 縦区切り線
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("QFrame { color: #d0d0d0; }")
        top_cols.addWidget(sep)

        # 右カラム：発行設定
        right_w = QWidget()
        right_vbox = QVBoxLayout(right_w)
        right_vbox.setContentsMargins(12, 0, 0, 0)
        right_vbox.setSpacing(0)

        right_form = QFormLayout()
        right_form.setVerticalSpacing(3)
        right_form.setHorizontalSpacing(8)
        right_form.setContentsMargins(0, 0, 0, 0)

        self._issuer_combo = QComboBox()
        self._bank_combo   = QComboBox()
        self._seal_combo   = QComboBox()
        self._issuer_combo.currentIndexChanged.connect(self._on_issuer_changed)

        right_form.addRow("発行元",   self._issuer_combo)
        right_form.addRow("銀行口座", self._bank_combo)
        right_form.addRow("印鑑",     self._seal_combo)

        right_vbox.addLayout(right_form)
        right_vbox.addStretch()
        right_w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        top_cols.addWidget(right_w, 4)

        self._reload_issuers()
        layout.addLayout(top_cols)

        grp = QGroupBox("発行項目（1つ以上必須）")
        grp_vbox = QVBoxLayout(grp)
        grp_vbox.setContentsMargins(8, 8, 8, 8)
        grp_vbox.setSpacing(2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(190)
        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: white;")
        self._rows_vbox = QVBoxLayout(self._rows_container)
        self._rows_vbox.setContentsMargins(0, 0, 0, 2)
        self._rows_vbox.setSpacing(0)
        self._rows_vbox.addStretch()
        scroll.setWidget(self._rows_container)
        grp_vbox.addWidget(scroll)

        add_row = QHBoxLayout()
        btn_add = QPushButton("＋ 行追加")
        btn_add.clicked.connect(self._add_row)
        add_row.addWidget(btn_add)
        btn_new_tmpl = QPushButton("＋ 新規テンプレート…")
        btn_new_tmpl.clicked.connect(self._add_template_master)
        add_row.addWidget(btn_new_tmpl)
        add_row.addStretch()
        grp_vbox.addLayout(add_row)
        layout.addWidget(grp, 1)

        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("プレビュー種別："))
        self._doc_type = QComboBox()
        self._doc_type.addItem("請求書", "invoice")
        self._doc_type.addItem("領収書", "receipt")
        preview_row.addWidget(self._doc_type)
        btn_preview = QPushButton("プレビュー（宛先空）")
        btn_preview.clicked.connect(self._preview)
        preview_row.addWidget(btn_preview)
        preview_row.addStretch()
        layout.addLayout(preview_row)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("保存")
        btn_ok.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 2px 12px; }"
            "QPushButton:hover { background: #1D4ED8; }")
        btn_ok.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        self._reload_categories()

    # ── マスタ読み込み ────────────────────────────────────────

    def _load_templates(self):
        cat_id = self._category.currentData()
        session = get_session()
        try:
            self._templates = (get_templates_by_category(session, cat_id)
                               if cat_id is not None
                               else get_all_active_templates(session))
        finally:
            session.close()
        for row in self._rows:
            row.refresh_combo(self._templates)

    def _reload_categories(self, select_id: int | None = None):
        self._category.blockSignals(True)
        self._category.clear()
        session = get_session()
        try:
            for cat in get_active_categories(session):
                self._category.addItem(cat.name, cat.id)
        finally:
            session.close()
        if select_id is not None:
            for i in range(self._category.count()):
                if self._category.itemData(i) == select_id:
                    self._category.setCurrentIndex(i)
                    break
        self._category.blockSignals(False)
        self._load_templates()

    def _add_category_master(self):
        from app.ui.category_management import CategoryEditDialog
        dlg = CategoryEditDialog(self)
        dlg.setWindowTitle("業務名の新規追加")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, sort_order = dlg.values()
        if not name:
            QMessageBox.warning(self, "入力エラー", "業務名を入力してください。")
            return
        session = get_session()
        try:
            cat = create_category(session, name, sort_order)
            new_id = cat.id
        finally:
            session.close()
        self._reload_categories(select_id=new_id)

    def _on_category_change(self, _):
        self._load_templates()

    def _reload_issuers(self, select_company_id: int | None = None,
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
        self._reload_bank_seal(select_bank_id=select_bank_id,
                               select_seal_id=select_seal_id)

    def _reload_bank_seal(self, select_bank_id: int | None = None,
                          select_seal_id: int | None = None):
        from app.database.models import BankAccount, SealImage
        company_id = self._issuer_combo.currentData()
        session = get_session()
        try:
            self._bank_combo.blockSignals(True)
            self._bank_combo.clear()
            self._bank_combo.addItem("（なし）", None)
            if company_id:
                banks = session.query(BankAccount).filter_by(
                    company_id=company_id).all()
                for b in banks:
                    label = f"{'★ ' if b.is_default else ''}{b.label} {b.bank_name}"
                    self._bank_combo.addItem(label, b.id)
            self._bank_combo.blockSignals(False)

            self._seal_combo.blockSignals(True)
            self._seal_combo.clear()
            self._seal_combo.addItem("（なし）", None)
            if company_id:
                seals = session.query(SealImage).filter_by(
                    company_id=company_id).all()
                for s in seals:
                    label = f"{'★ ' if s.is_default else ''}{s.label}"
                    self._seal_combo.addItem(label, s.id)
            self._seal_combo.blockSignals(False)

            if select_bank_id is not None:
                for i in range(self._bank_combo.count()):
                    if self._bank_combo.itemData(i) == select_bank_id:
                        self._bank_combo.setCurrentIndex(i)
                        break
            else:
                for i in range(self._bank_combo.count()):
                    if self._bank_combo.itemData(i) is not None:
                        bank_obj = session.get(BankAccount, self._bank_combo.itemData(i))
                        if bank_obj and bank_obj.is_default:
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
                        seal_obj = session.get(SealImage, self._seal_combo.itemData(i))
                        if seal_obj and seal_obj.is_default:
                            self._seal_combo.setCurrentIndex(i)
                            break
        finally:
            session.close()

    def _on_issuer_changed(self, _):
        self._reload_bank_seal()

    # ── 行操作 ───────────────────────────────────────────────

    def _add_row(self):
        row = _ItemRow(self)
        row.refresh_combo(self._templates)
        self._rows_vbox.insertWidget(self._rows_vbox.count() - 1, row)
        self._rows.append(row)

    def _remove_row(self, row: _ItemRow):
        if row not in self._rows:
            return
        self._rows.remove(row)
        self._rows_vbox.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def _save_row_as_template(self, row: _ItemRow):
        from app.ui.item_template_management import ItemTemplateDialog
        _PH = "（項目を選択または入力）"
        name = row.item_name()
        if not name or name == _PH:
            QMessageBox.warning(self, "未入力", "項目名を入力してください。")
            return
        dlg = ItemTemplateDialog(
            self,
            default_category_id=self._category.currentData(),
            default_name=name,
            default_price=row.price_spin.value(),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        saved_name = dlg.result_name
        self._load_templates()
        new_tmpl = next((t for t in self._templates if t.name == saved_name), None)
        if new_tmpl:
            row.name_combo.blockSignals(True)
            for i in range(row.name_combo.count()):
                if row.name_combo.itemData(i) == new_tmpl.id:
                    row.name_combo.setCurrentIndex(i)
                    break
            row.name_combo.blockSignals(False)
            row._update_save_btn()

    def _add_template_master(self):
        from app.ui.item_template_management import ItemTemplateDialog
        dlg = ItemTemplateDialog(self, default_category_id=self._category.currentData())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_templates()

    # ── 編集モード読み込み ────────────────────────────────────

    def _load(self, project_id: int):
        session = get_session()
        try:
            proj = get_project_by_id(session, project_id)
            if not proj:
                return
            self._title.setText(proj.name or "")
            self._fiscal_year.setValue(proj.fiscal_year)
            self._notes.setPlainText(proj.notes or "")
            for i in range(self._category.count()):
                if self._category.itemData(i) == proj.category_id:
                    self._category.setCurrentIndex(i)
                    break
            pts = get_project_templates(session, project_id)
            tmpl_data = [
                (pt.item_template.id, int(pt.unit_price_override or pt.item_template.unit_price),
                 pt.item_template.unit,
                 pt.tax_rate_override if pt.tax_rate_override is not None else pt.item_template.tax_rate,
                 int(pt.default_quantity) if pt.default_quantity else 1)
                for pt in pts
            ]
            company_settings_id = proj.company_settings_id
            bank_account_id     = proj.bank_account_id
            seal_image_id       = proj.seal_image_id
        finally:
            session.close()
        for tmpl_id, price, unit, tax_rate, qty in tmpl_data:
            self._add_row()
            row = self._rows[-1]
            row.name_combo.blockSignals(True)
            for i in range(row.name_combo.count()):
                if row.name_combo.itemData(i) == tmpl_id:
                    row.name_combo.setCurrentIndex(i)
                    break
            row.name_combo.blockSignals(False)
            row.price_spin.setValue(price)
            row.qty_spin.setValue(qty)
            row.unit_edit.setText(unit or "式")
            idx = row.tax_combo.findData(tax_rate)
            if idx >= 0:
                row.tax_combo.setCurrentIndex(idx)
            row._update_save_btn()
        self._reload_issuers(
            select_company_id=company_settings_id,
            select_bank_id=bank_account_id,
            select_seal_id=seal_image_id,
        )

    # ── プレビュー ────────────────────────────────────────────

    def _preview(self):
        _PH = "（項目を選択または入力）"
        lines_data = []
        session = get_session()
        try:
            for row in self._rows:
                name = row.item_name()
                if not name or name == _PH:
                    continue
                tmpl_id = row.template_id()
                if tmpl_id is not None:
                    from app.database.models import ItemTemplate
                    t = session.get(ItemTemplate, tmpl_id)
                    if t:
                        lines_data.append({
                            "item_template_id": t.id,
                            "item_name": t.name,
                            "quantity": row.qty_spin.value(),
                            "unit": t.unit,
                            "unit_price": int(t.unit_price),
                            "tax_rate": t.tax_rate,
                        })
                else:
                    lines_data.append({
                        "item_template_id": None,
                        "item_name": name,
                        "quantity": row.qty_spin.value(),
                        "unit": row.unit_edit.text().strip() or "式",
                        "unit_price": row.price_spin.value(),
                        "tax_rate": row.tax_combo.currentData(),
                    })
            if not lines_data:
                QMessageBox.warning(self, "プレビュー不可", "有効な項目がありません。")
                return
            from app.utils import pdf_helpers
            try:
                result = pdf_helpers.generate_preview(
                    lines_data, self._doc_type.currentData(), session)
                if result is None:
                    QMessageBox.warning(
                        self, "プレビュー不可",
                        "自社情報（会社設定）が未登録のためプレビューできません。\n"
                        "設定 → 会社情報 から登録してください。")
            except Exception as e:
                QMessageBox.critical(self, "プレビューエラー", str(e))
        finally:
            session.close()

    # ── 保存 ────────────────────────────────────────────────

    def _save(self):
        cat_id = self._category.currentData()
        title = self._title.text().strip()
        if cat_id is None:
            QMessageBox.warning(self, "入力エラー", "業務名を選択してください。")
            return
        if not title:
            QMessageBox.warning(self, "入力エラー", "件名を入力してください。")
            return

        _PH = "（項目を選択または入力）"
        seen_names: set[str] = set()
        for row in self._rows:
            name = row.item_name()
            if not name or name == _PH:
                continue
            if name in seen_names:
                QMessageBox.warning(
                    self, "入力エラー",
                    f"品目名「{name}」が重複しています。\n品目名を変えてください。")
                return
            seen_names.add(name)

        session = get_session()
        try:
            tmpl_qty_list: list[tuple[int, int, int | None]] = []
            for row in self._rows:
                name = row.item_name()
                if not name or name == _PH:
                    continue
                qty = row.qty_spin.value()
                tmpl_id = row.template_id()
                selected_tax_rate = row.tax_combo.currentData()
                if tmpl_id is not None:
                    tmpl = next((t for t in self._templates if t.id == tmpl_id), None)
                    # テンプレートの税率と異なる場合のみ override として保存
                    override_tax = selected_tax_rate if (tmpl is None or selected_tax_rate != tmpl.tax_rate) else None
                    tmpl_qty_list.append((tmpl_id, qty, override_tax))
                else:
                    # 同名テンプレートを検索、なければ自動作成
                    from app.database.models import ItemTemplate
                    existing = session.query(ItemTemplate).filter_by(
                        name=name, is_active=True).first()
                    if existing:
                        override_tax = selected_tax_rate if selected_tax_rate != existing.tax_rate else None
                        tmpl_qty_list.append((existing.id, qty, override_tax))
                    else:
                        new_tmpl = create_item_template(
                            session,
                            category_id=cat_id,
                            name=name,
                            unit_price=row.price_spin.value(),
                            unit=row.unit_edit.text().strip() or "式",
                            tax_rate=selected_tax_rate,
                            doc_type="both",
                            description=name,
                        )
                        tmpl_qty_list.append((new_tmpl.id, qty, None))

            if not tmpl_qty_list:
                QMessageBox.warning(self, "入力エラー",
                                    "発行項目を1つ以上入力してください。")
                return

            if self._project_id is None:
                proj = create_project(
                    session, name=title,
                    category_id=cat_id,
                    fiscal_year=self._fiscal_year.value(),
                    project_type="list",
                    notes=self._notes.toPlainText().strip(),
                    company_settings_id=self._issuer_combo.currentData(),
                    bank_account_id=self._bank_combo.currentData(),
                    seal_image_id=self._seal_combo.currentData(),
                )
                for i, (tid, qty, tax_ovr) in enumerate(tmpl_qty_list):
                    add_template_to_project(session, proj.id, tid, sort_order=i,
                                            default_quantity=qty,
                                            tax_rate_override=tax_ovr)
            else:
                proj = get_project_by_id(session, self._project_id)
                proj.name = title
                proj.category_id = cat_id
                proj.fiscal_year = self._fiscal_year.value()
                proj.notes = self._notes.toPlainText().strip()
                proj.company_settings_id = self._issuer_combo.currentData()
                proj.bank_account_id     = self._bank_combo.currentData()
                proj.seal_image_id       = self._seal_combo.currentData()
                from app.database.models import ProjectTemplate
                session.query(ProjectTemplate).filter_by(
                    project_id=proj.id).delete()
                session.commit()
                for i, (tid, qty, tax_ovr) in enumerate(tmpl_qty_list):
                    add_template_to_project(session, proj.id, tid, sort_order=i,
                                            default_quantity=qty,
                                            tax_rate_override=tax_ovr)
        finally:
            session.close()
        self.accept()
