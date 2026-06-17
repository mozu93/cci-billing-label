# app/ui/item_template_management.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QComboBox, QSpinBox, QDialog,
    QFormLayout, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.database.models import ItemTemplate
from app.services.category_service import get_active_categories
from app.services.item_template_service import (
    create_item_template, get_all_active_templates,
    deactivate_item_template, update_item_template
)

TAX_RATE_OPTIONS = [("消費税10%", 10), ("消費税8%", 8), ("非課税", 0), ("不課税", -1)]


class ItemTemplateManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("＋ 新規テンプレート")
        btn_add.clicked.connect(self._add)
        btn_edit = QPushButton("編集")
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton("無効化")
        btn_del.clicked.connect(self._deactivate)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["業務名", "項目名", "単価", "単位", "税区分"])
        hdr = self._table.horizontalHeader()
        for col in range(5):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.cellDoubleClicked.connect(lambda row, _: self._open_edit(row))
        layout.addWidget(self._table)

    def _load(self):
        session = get_session()
        try:
            templates = get_all_active_templates(session)
            rows = []
            for t in templates:
                cat_name = t.category.name if t.category else ""
                tax_label = next((l for l, v in TAX_RATE_OPTIONS if v == t.tax_rate), str(t.tax_rate))
                rows.append((t.id, cat_name, t.name, f"¥{int(t.unit_price):,}",
                              t.unit, tax_label))
        finally:
            session.close()
        self._table.setRowCount(0)
        for tmpl_id, *vals in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, tmpl_id)
                self._table.setItem(row, col, item)
        self._table.resizeColumnsToContents()

    def _add(self):
        dlg = ItemTemplateDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _edit(self):
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "未選択", "編集するテンプレートを選択してください。")
            return
        self._open_edit(row)

    def _open_edit(self, row: int):
        item = self._table.item(row, 0)
        if item is None:
            return
        tmpl_id = item.data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            tmpl = session.get(ItemTemplate, tmpl_id)
            if tmpl:
                session.expunge(tmpl)
        finally:
            session.close()
        if tmpl is None:
            return
        dlg = ItemTemplateDialog(self, template=tmpl)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _deactivate(self):
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "未選択", "無効化するテンプレートを選択してください。")
            return
        tmpl_id = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        name = self._table.item(row, 1).text()
        if QMessageBox.question(
                self, "無効化の確認",
                f"テンプレート「{name}」を無効化します。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            deactivate_item_template(session, tmpl_id)
        finally:
            session.close()
        self._load()


class ItemTemplateDialog(QDialog):
    def __init__(self, parent=None, template: ItemTemplate | None = None,
                 default_category_id: int | None = None,
                 default_name: str | None = None,
                 default_price: int | None = None):
        super().__init__(parent)
        self._template = template
        self.setWindowTitle("請求項目テンプレート編集" if template else "請求項目テンプレート登録")
        self.setFixedSize(400, 260)
        self.setStyleSheet(
            "QLineEdit, QSpinBox { border: 1px solid #b5b5b5; border-radius: 3px; "
            "padding: 3px 4px; background: white; }"
        )
        self._build()
        if template:
            self._populate(template)
        else:
            if default_category_id is not None:
                idx = self._category.findData(default_category_id)
                if idx >= 0:
                    self._category.setCurrentIndex(idx)
            if default_name:
                self._name.setText(default_name)
            if default_price is not None:
                self._unit_price.setValue(default_price)

    @property
    def result_name(self) -> str:
        return self._name.text().strip()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)

        self._category = QComboBox()
        session = get_session()
        try:
            for cat in get_active_categories(session):
                self._category.addItem(cat.name, cat.id)
        finally:
            session.close()

        self._name = QLineEdit()
        self._name.setPlaceholderText("例：青年部会費")
        self._unit_price = QSpinBox()
        self._unit_price.setRange(0, 9999999)
        self._unit = QLineEdit("式")
        self._tax_rate = QComboBox()
        for label, value in TAX_RATE_OPTIONS:
            self._tax_rate.addItem(label, value)

        form.addRow("業務名", self._category)
        form.addRow("項目名 / 但し書き", self._name)
        form.addRow("単価（円）", self._unit_price)
        form.addRow("単位", self._unit)
        form.addRow("税区分", self._tax_rate)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("保存" if self._template else "登録")
        btn_ok.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _populate(self, tmpl: ItemTemplate):
        idx = self._category.findData(tmpl.category_id)
        if idx >= 0:
            self._category.setCurrentIndex(idx)
        self._name.setText(tmpl.name or "")
        self._unit_price.setValue(int(tmpl.unit_price or 0))
        self._unit.setText(tmpl.unit or "式")
        idx = self._tax_rate.findData(tmpl.tax_rate)
        if idx >= 0:
            self._tax_rate.setCurrentIndex(idx)

    def _save(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "入力エラー", "項目名を入力してください。")
            return
        if self._category.currentData() is None:
            QMessageBox.warning(self, "入力エラー",
                                "業務名が選択されていません。\n"
                                "先に「設定→業務名」で業務名を登録してください。")
            return
        session = get_session()
        try:
            unit = self._unit.text().strip() or "式"
            if self._template:
                update_item_template(
                    session,
                    template_id=self._template.id,
                    category_id=self._category.currentData(),
                    name=name,
                    unit_price=self._unit_price.value(),
                    unit=unit,
                    tax_rate=self._tax_rate.currentData(),
                    doc_type="both",
                    description=name,
                )
            else:
                create_item_template(
                    session,
                    category_id=self._category.currentData(),
                    name=name,
                    unit_price=self._unit_price.value(),
                    unit=unit,
                    tax_rate=self._tax_rate.currentData(),
                    doc_type="both",
                    description=name,
                )
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", str(e))
            return
        finally:
            session.close()
        self.accept()
