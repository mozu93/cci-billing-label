# app/ui/category_management.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel, QMessageBox, QSpinBox,
    QDialog, QFormLayout
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.database.models import Category
from app.services.category_service import (
    create_category, get_active_categories, deactivate_category,
    update_category
)


class CategoryManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        add_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("業務名（例：青年部）")
        self._order_input = QSpinBox()
        self._order_input.setRange(0, 999)
        btn_add = QPushButton("追加")
        btn_add.clicked.connect(self._add)
        add_row.addWidget(QLabel("名称："))
        add_row.addWidget(self._name_input)
        add_row.addWidget(QLabel("表示順："))
        add_row.addWidget(self._order_input)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _: self._edit())
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_edit = QPushButton("編集")
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton("削除（無効化）")
        btn_del.clicked.connect(self._deactivate)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _load(self):
        session = get_session()
        try:
            cats = get_active_categories(session)
        finally:
            session.close()
        self._list.clear()
        for c in cats:
            item = QListWidgetItem(f"{c.name}（表示順:{c.sort_order}）")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self._list.addItem(item)

    def _add(self):
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "入力エラー", "業務名を入力してください。")
            return
        session = get_session()
        try:
            create_category(session, name, self._order_input.value())
        finally:
            session.close()
        self._name_input.clear()
        self._load()

    def _edit(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, "未選択", "編集する業務名を選択してください。")
            return
        cat_id = item.data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            cat = session.get(Category, cat_id)
            if cat is None:
                return
            name, sort_order = cat.name, cat.sort_order
        finally:
            session.close()

        dlg = CategoryEditDialog(self, name=name, sort_order=sort_order)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name, new_order = dlg.values()
        if not new_name:
            QMessageBox.warning(self, "入力エラー", "業務名を入力してください。")
            return
        session = get_session()
        try:
            update_category(session, cat_id, new_name, new_order)
        finally:
            session.close()
        self._load()

    def _deactivate(self):
        item = self._list.currentItem()
        if not item:
            return
        cat_id = item.data(Qt.ItemDataRole.UserRole)
        name = item.text().rsplit("（表示順", 1)[0]
        if QMessageBox.question(
                self, "削除の確認",
                f"業務名「{name}」を削除（無効化）します。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            deactivate_category(session, cat_id)
        finally:
            session.close()
        self._load()


class CategoryEditDialog(QDialog):
    def __init__(self, parent=None, name: str = "", sort_order: int = 0,
                 title: str = "業務名の編集"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(320, 150)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._name = QLineEdit(name)
        self._order = QSpinBox()
        self._order.setRange(0, 999)
        self._order.setValue(sort_order)
        form.addRow("業務名", self._name)
        form.addRow("表示順", self._order)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("保存")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def values(self) -> tuple[str, int]:
        return self._name.text().strip(), self._order.value()
