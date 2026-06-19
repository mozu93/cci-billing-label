# app/ui/company_settings.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QGroupBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView, QDialog,
    QFileDialog, QLabel, QCheckBox
)

from app.database.connection import get_session
from app.database.models import CompanySettings, BankAccount, SealImage


def _ask_label(parent, title: str, prompt: str, default: str = "") -> tuple[str, bool]:
    from PyQt6.QtWidgets import QInputDialog
    text, ok = QInputDialog.getText(parent, title, prompt, text=default)
    return text.strip() or default, ok


class CompanySettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._selected_company_id: int | None = None
        self._build()
        self._load_issuers()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── 発行元一覧 ─────────────────────────────────────────
        grp1 = QGroupBox("発行元一覧")
        grp1_layout = QVBoxLayout(grp1)
        grp1_layout.setSpacing(4)
        grp1_layout.setContentsMargins(6, 4, 6, 6)

        self._issuer_table = QTableWidget(0, 3)
        self._issuer_table.setHorizontalHeaderLabels(["名称", "住所", ""])
        self._issuer_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._issuer_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._issuer_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._issuer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._issuer_table.setFixedHeight(155)
        self._issuer_table.currentCellChanged.connect(
            lambda cur_row, _cc, prev_row, _pc: (
                self._on_issuer_selected(cur_row) if cur_row != prev_row else None))
        grp1_layout.addWidget(self._issuer_table)

        btn_row1 = QHBoxLayout()
        btn_add_issuer     = QPushButton("＋ 発行元追加")
        btn_edit_issuer    = QPushButton("編集")
        btn_default_issuer = QPushButton("★ デフォルトに設定")
        btn_del_issuer     = QPushButton("削除")
        btn_add_issuer.clicked.connect(self._add_issuer)
        btn_edit_issuer.clicked.connect(self._edit_issuer)
        btn_default_issuer.clicked.connect(self._set_default_issuer)
        btn_del_issuer.clicked.connect(self._del_issuer)
        btn_row1.addWidget(btn_add_issuer)
        btn_row1.addWidget(btn_edit_issuer)
        btn_row1.addWidget(btn_default_issuer)
        btn_row1.addWidget(btn_del_issuer)
        btn_row1.addStretch()
        grp1_layout.addLayout(btn_row1)
        root.addWidget(grp1)

        # ── 銀行口座 + 印鑑画像（選択中発行元） ────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        # 銀行口座
        grp2 = QGroupBox("銀行口座")
        bank_layout = QVBoxLayout(grp2)
        bank_layout.setSpacing(4)
        bank_layout.setContentsMargins(6, 4, 6, 6)
        self._bank_table = QTableWidget(0, 5)
        self._bank_table.setHorizontalHeaderLabels(
            ["ラベル", "銀行名", "支店名", "種別", "口座番号"])
        self._bank_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._bank_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._bank_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bank_table.setFixedHeight(155)
        bank_layout.addWidget(self._bank_table)

        bank_btn_row = QHBoxLayout()
        btn_add_bank = QPushButton("＋ 口座追加")
        btn_add_bank.clicked.connect(self._add_bank)
        btn_del_bank = QPushButton("削除")
        btn_del_bank.clicked.connect(self._del_bank)
        bank_btn_row.addWidget(btn_add_bank)
        bank_btn_row.addWidget(btn_del_bank)
        bank_btn_row.addStretch()
        bank_layout.addLayout(bank_btn_row)
        bottom.addWidget(grp2)

        # 印鑑画像
        grp3 = QGroupBox("印鑑画像")
        seal_layout = QVBoxLayout(grp3)
        seal_layout.setSpacing(4)
        seal_layout.setContentsMargins(6, 4, 6, 6)
        self._print_seal_chk = QCheckBox("印鑑を印字する（請求書・領収書共通）")
        self._print_seal_chk.setChecked(True)
        self._print_seal_chk.stateChanged.connect(self._save_seal_option)
        seal_layout.addWidget(self._print_seal_chk)
        seal_layout.addWidget(QLabel("PNG / JPG を登録。★デフォルトが印刷されます。"))

        self._seal_table = QTableWidget(0, 3)
        self._seal_table.setHorizontalHeaderLabels(["ラベル", "保存状態", ""])
        self._seal_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._seal_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._seal_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._seal_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._seal_table.setFixedHeight(155)
        seal_layout.addWidget(self._seal_table)

        seal_btn_row = QHBoxLayout()
        btn_add_seal     = QPushButton("＋ 画像を登録")
        btn_default_seal = QPushButton("★ デフォルトに設定")
        btn_del_seal     = QPushButton("削除")
        btn_add_seal.clicked.connect(self._add_seal)
        btn_default_seal.clicked.connect(self._set_default_seal)
        btn_del_seal.clicked.connect(self._del_seal)
        seal_btn_row.addWidget(btn_add_seal)
        seal_btn_row.addWidget(btn_default_seal)
        seal_btn_row.addWidget(btn_del_seal)
        seal_btn_row.addStretch()
        seal_layout.addLayout(seal_btn_row)
        bottom.addWidget(grp3)

        root.addLayout(bottom)
        root.addStretch()

    # ── 発行元一覧の読み込み ────────────────────────────────────

    def _load_issuers(self, select_id: int | None = None):
        session = get_session()
        try:
            issuers = session.query(CompanySettings).order_by(CompanySettings.id).all()
            self._issuer_table.setRowCount(0)
            for cs in issuers:
                row = self._issuer_table.rowCount()
                self._issuer_table.insertRow(row)
                default_mark = "★ デフォルト" if cs.is_default else ""
                for col, val in enumerate([cs.name, cs.address or "", default_mark]):
                    item = QTableWidgetItem(val)
                    item.setData(0x0100, cs.id)
                    self._issuer_table.setItem(row, col, item)
        finally:
            session.close()

        if select_id is not None:
            for r in range(self._issuer_table.rowCount()):
                if self._issuer_table.item(r, 0).data(0x0100) == select_id:
                    self._issuer_table.selectRow(r)
                    return
        if self._issuer_table.rowCount() > 0:
            self._issuer_table.selectRow(0)

    def _on_issuer_selected(self, row: int):
        if row < 0:
            self._selected_company_id = None
            self._bank_table.setRowCount(0)
            self._seal_table.setRowCount(0)
            return
        item = self._issuer_table.item(row, 0)
        if item:
            self._selected_company_id = item.data(0x0100)
            self._load_bank_seal()

    def _load_bank_seal(self):
        if self._selected_company_id is None:
            return
        session = get_session()
        try:
            cs = session.get(CompanySettings, self._selected_company_id)
            if not cs:
                return
            self._print_seal_chk.blockSignals(True)
            self._print_seal_chk.setChecked(
                bool(cs.print_seal) if cs.print_seal is not None else True)
            self._print_seal_chk.blockSignals(False)

            self._bank_table.setRowCount(0)
            for b in cs.bank_accounts:
                r = self._bank_table.rowCount()
                self._bank_table.insertRow(r)
                for col, val in enumerate([b.label, b.bank_name, b.bank_branch,
                                            b.bank_account_type, b.bank_account_number]):
                    item = QTableWidgetItem(val)
                    item.setData(0x0100, b.id)
                    self._bank_table.setItem(r, col, item)

            self._seal_table.setRowCount(0)
            for s in cs.seal_images:
                r = self._seal_table.rowCount()
                self._seal_table.insertRow(r)
                default_mark = "★ デフォルト" if s.is_default else ""
                if s.image_data:
                    status = "DB保存済"
                elif s.path:
                    status = f"ファイル: {s.path}"
                else:
                    status = "（未登録）"
                for col, val in enumerate([s.label, status, default_mark]):
                    item = QTableWidgetItem(val)
                    item.setData(0x0100, s.id)
                    self._seal_table.setItem(r, col, item)
                # 既存のファイルパスデータをBLOBに自動マイグレーション
                if not s.image_data and s.path:
                    import os as _os
                    if _os.path.exists(s.path):
                        try:
                            s.image_data = open(s.path, "rb").read()
                            session.commit()
                            self._seal_table.item(r, 1).setText("DB保存済")
                        except Exception:
                            pass
        finally:
            session.close()

    # ── 発行元の操作 ───────────────────────────────────────────

    def _add_issuer(self):
        dlg = IssuerEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_id = getattr(dlg, '_saved_id', None)
            session = get_session()
            try:
                count = session.query(CompanySettings).count()
                if count == 1 and new_id:
                    cs = session.get(CompanySettings, new_id)
                    if cs:
                        cs.is_default = True
                        session.commit()
            finally:
                session.close()
            self._load_issuers(select_id=new_id)

    def _edit_issuer(self):
        if self._selected_company_id is None:
            QMessageBox.warning(self, "未選択", "編集する発行元を選択してください。")
            return
        dlg = IssuerEditDialog(self, company_id=self._selected_company_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_issuers(select_id=self._selected_company_id)

    def _set_default_issuer(self):
        if self._selected_company_id is None:
            QMessageBox.warning(self, "未選択", "デフォルトにする発行元を選択してください。")
            return
        session = get_session()
        try:
            for cs in session.query(CompanySettings).all():
                cs.is_default = (cs.id == self._selected_company_id)
            session.commit()
        finally:
            session.close()
        self._load_issuers(select_id=self._selected_company_id)

    def _del_issuer(self):
        if self._selected_company_id is None:
            return
        session = get_session()
        try:
            total = session.query(CompanySettings).count()
            if total <= 1:
                QMessageBox.warning(self, "削除不可",
                                    "発行元が1件しかないため削除できません。")
                return
            cs = session.get(CompanySettings, self._selected_company_id)
            if cs and cs.is_default:
                QMessageBox.warning(self, "削除不可",
                                    "デフォルト発行元は削除できません。\n"
                                    "先に別の発行元をデフォルトに設定してください。")
                return
            name = cs.name if cs else ""
            if QMessageBox.question(
                    self, "削除の確認",
                    f"発行元「{name}」を削除します。\nよろしいですか？"
            ) != QMessageBox.StandardButton.Yes:
                return
            if cs:
                session.delete(cs)
                session.commit()
        finally:
            session.close()
        self._selected_company_id = None
        self._load_issuers()

    # ── 銀行口座の操作 ─────────────────────────────────────────

    def _add_bank(self):
        if self._selected_company_id is None:
            QMessageBox.warning(self, "未選択", "発行元を選択してから口座を追加してください。")
            return
        dlg = BankAccountDialog(self, company_id=self._selected_company_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_bank_seal()

    def _del_bank(self):
        row = self._bank_table.currentRow()
        if row < 0:
            return
        bank_id = self._bank_table.item(row, 0).data(0x0100)
        bank_name = self._bank_table.item(row, 1).text()
        if QMessageBox.question(
                self, "削除の確認",
                f"口座「{bank_name}」を削除します。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            b = session.get(BankAccount, bank_id)
            if b:
                session.delete(b)
                session.commit()
        finally:
            session.close()
        self._load_bank_seal()

    # ── 印鑑画像の操作 ─────────────────────────────────────────

    def _save_seal_option(self):
        if self._selected_company_id is None:
            return
        session = get_session()
        try:
            cs = session.get(CompanySettings, self._selected_company_id)
            if cs:
                cs.print_seal = self._print_seal_chk.isChecked()
                session.commit()
        finally:
            session.close()

    def _add_seal(self):
        if self._selected_company_id is None:
            QMessageBox.warning(self, "未選択", "発行元を選択してから印鑑を登録してください。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "印鑑画像を選択", "",
            "画像ファイル (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not path:
            return
        label, ok = _ask_label(self, "印鑑ラベル", "印鑑のラベルを入力してください：",
                                default="印鑑")
        if not ok:
            return
        try:
            image_bytes = open(path, "rb").read()
        except Exception as e:
            QMessageBox.critical(self, "読み込みエラー", f"画像の読み込みに失敗しました。\n{e}")
            return
        session = get_session()
        try:
            is_first = session.query(SealImage).filter_by(
                company_id=self._selected_company_id).count() == 0
            seal = SealImage(
                company_id=self._selected_company_id,
                label=label,
                path="",
                image_data=image_bytes,
                is_default=is_first,
            )
            session.add(seal)
            session.commit()
        finally:
            session.close()
        self._load_bank_seal()

    def _set_default_seal(self):
        row = self._seal_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "未選択", "デフォルトにする印鑑を選択してください。")
            return
        seal_id = self._seal_table.item(row, 0).data(0x0100)
        session = get_session()
        try:
            for s in session.query(SealImage).filter_by(
                    company_id=self._selected_company_id).all():
                s.is_default = (s.id == seal_id)
            session.commit()
        finally:
            session.close()
        self._load_bank_seal()

    def _del_seal(self):
        row = self._seal_table.currentRow()
        if row < 0:
            return
        seal_id = self._seal_table.item(row, 0).data(0x0100)
        label = self._seal_table.item(row, 0).text()
        if QMessageBox.question(
                self, "削除の確認",
                f"印鑑画像「{label}」を削除します。\nよろしいですか？"
        ) != QMessageBox.StandardButton.Yes:
            return
        session = get_session()
        try:
            s = session.get(SealImage, seal_id)
            if s:
                session.delete(s)
                session.commit()
        finally:
            session.close()
        self._load_bank_seal()


class IssuerEditDialog(QDialog):
    """発行元の追加・編集ダイアログ。"""

    def __init__(self, parent=None, company_id: int | None = None):
        super().__init__(parent)
        self._company_id = company_id
        self.setWindowTitle("発行元を編集" if company_id else "発行元を追加")
        self.setFixedSize(440, 290)
        self.setStyleSheet(
            "QLineEdit { border: 1px solid #b5b5b5; border-radius: 3px; "
            "padding: 3px 4px; background: white; }"
        )
        self._build()
        if company_id:
            self._load(company_id)

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._name    = QLineEdit()
        self._postal  = QLineEdit()
        self._postal.setMaximumWidth(120)
        self._address = QLineEdit()
        self._phone   = QLineEdit()
        self._fax     = QLineEdit()
        self._email   = QLineEdit()
        self._t_number = QLineEdit()
        self._t_number.setPlaceholderText("T1234567890123")
        self._print_seal = QCheckBox("印鑑を印字する（請求書・領収書共通）")
        self._print_seal.setChecked(True)
        form.addRow("名称 *",            self._name)
        form.addRow("郵便番号",          self._postal)
        form.addRow("住所",              self._address)
        form.addRow("電話",              self._phone)
        form.addRow("FAX",               self._fax)
        form.addRow("メール",            self._email)
        form.addRow("インボイス登録番号", self._t_number)
        form.addRow("",                  self._print_seal)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("保存")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _load(self, company_id: int):
        session = get_session()
        try:
            cs = session.get(CompanySettings, company_id)
            if cs:
                self._name.setText(cs.name)
                self._postal.setText(cs.postal_code)
                self._address.setText(cs.address)
                self._phone.setText(cs.phone)
                self._fax.setText(cs.fax)
                self._email.setText(cs.email)
                self._t_number.setText(cs.invoice_reg_number)
                self._print_seal.setChecked(
                    bool(cs.print_seal) if cs.print_seal is not None else True)
        finally:
            session.close()

    def _save(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "入力エラー", "名称を入力してください。")
            return
        session = get_session()
        try:
            if self._company_id:
                cs = session.get(CompanySettings, self._company_id)
            else:
                cs = CompanySettings()
                session.add(cs)
            cs.name               = self._name.text().strip()
            cs.postal_code        = self._postal.text().strip()
            cs.address            = self._address.text().strip()
            cs.phone              = self._phone.text().strip()
            cs.fax                = self._fax.text().strip()
            cs.email              = self._email.text().strip()
            cs.invoice_reg_number = self._t_number.text().strip()
            cs.print_seal         = self._print_seal.isChecked()
            session.commit()
            self._saved_id = cs.id
        finally:
            session.close()
        self.accept()


class BankAccountDialog(QDialog):
    def __init__(self, parent=None, company_id: int | None = None):
        super().__init__(parent)
        self._company_id = company_id
        self.setWindowTitle("銀行口座登録")
        self.setFixedSize(360, 260)
        self.setStyleSheet(
            "QLineEdit { border: 1px solid #b5b5b5; border-radius: 3px; "
            "padding: 3px 4px; background: white; }"
        )
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._label        = QLineEdit()
        self._label.setPlaceholderText("例：メイン口座")
        self._bank_name    = QLineEdit()
        self._branch       = QLineEdit()
        self._account_type = QLineEdit("普通")
        self._account_number = QLineEdit()
        self._account_name   = QLineEdit()
        form.addRow("ラベル",   self._label)
        form.addRow("銀行名",   self._bank_name)
        form.addRow("支店名",   self._branch)
        form.addRow("口座種別", self._account_type)
        form.addRow("口座番号", self._account_number)
        form.addRow("口座名義", self._account_name)
        layout.addLayout(form)
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("登録")
        btn_ok.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _save(self):
        if not self._label.text().strip():
            QMessageBox.warning(self, "入力エラー", "ラベルを入力してください。")
            return
        if self._company_id is None:
            QMessageBox.warning(self, "エラー", "発行元が指定されていません。")
            return
        session = get_session()
        try:
            b = BankAccount(
                company_id=self._company_id,
                label=self._label.text().strip(),
                bank_name=self._bank_name.text().strip(),
                bank_branch=self._branch.text().strip(),
                bank_account_type=self._account_type.text().strip(),
                bank_account_name=self._account_name.text().strip(),
                bank_account_number=self._account_number.text().strip(),
            )
            session.add(b)
            session.commit()
        finally:
            session.close()
        self.accept()
