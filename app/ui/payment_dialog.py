# app/ui/payment_dialog.py
from datetime import date
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QDateEdit, QSpinBox, QComboBox, QLineEdit,
    QPushButton, QLabel, QWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QProgressDialog
)
from PyQt6.QtCore import Qt, QDate, QTimer
from app.database.connection import get_session
from app.services.issuance_service import record_payment, get_project_issuances
from app.services.project_service import get_projects
from app.utils import current_user


_COL_CHK = 0

_PAY_COLS = [
    ("",          30),   # 0: チェックボックス
    ("発行番号", 120),   # 1
    ("書類種別",  70),   # 2
    ("状態",      80),   # 3
    ("会員番号",  90),   # 4
    ("宛先",     200),   # 5
    ("フリガナ", 160),   # 6
    ("金額",      90),   # 7
    ("発行日",    90),   # 8
]

_DOC_TYPE_LABEL = {"invoice": "請求書", "receipt": "領収書"}


class PaymentManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load_projects()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("発行済み書類の支払管理"))

        # ── フィルタ行 ──────────────────────────────────────────────
        filter_row = QHBoxLayout()
        self._proj_combo = QComboBox()
        self._proj_combo.setMinimumWidth(300)
        self._proj_combo.currentIndexChanged.connect(self._load)

        self._doctype_combo = QComboBox()
        self._doctype_combo.addItems(["請求書のみ", "すべて"])
        self._doctype_combo.currentIndexChanged.connect(self._load)

        self._status_combo = QComboBox()
        self._status_combo.addItems(["発行済み", "支払済み", "すべて"])
        self._status_combo.currentIndexChanged.connect(self._load)

        filter_row.addWidget(QLabel("名簿："))
        filter_row.addWidget(self._proj_combo)
        filter_row.addWidget(QLabel("種別："))
        filter_row.addWidget(self._doctype_combo)
        filter_row.addWidget(QLabel("状態："))
        filter_row.addWidget(self._status_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("事業所名・会員番号・フリガナで絞り込み")
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._apply_search)
        self._search.textChanged.connect(lambda: self._search_timer.start(300))
        search_row.addWidget(QLabel("検索："))
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        # ── ボタン行（テーブルの上） ─────────────────────────────────
        btn_row = QHBoxLayout()
        btn_pay_checked = QPushButton("チェックした行を支払済みに更新")
        btn_pay_checked.clicked.connect(self._mark_paid_checked)
        btn_row.addWidget(btn_pay_checked)
        btn_reminder = QPushButton("期限超過の督促メール…")
        btn_reminder.setToolTip(
            "支払期限を過ぎても未入金の請求書について、\n"
            "名簿のメールアドレス宛に督促メールを一括送信します。")
        btn_reminder.clicked.connect(self._open_reminder_dialog)
        btn_row.addWidget(btn_reminder)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── テーブル ────────────────────────────────────────────────
        self._table = QTableWidget(0, len(_PAY_COLS))
        self._table.setHorizontalHeaderLabels([c[0] for c in _PAY_COLS])
        hdr = self._table.horizontalHeader()
        hdr.setSortIndicatorShown(True)
        hdr.sectionClicked.connect(self._on_header_clicked)
        for i, (_, w) in enumerate(_PAY_COLS):
            hdr.setSectionResizeMode(
                i,
                QHeaderView.ResizeMode.Fixed if i == _COL_CHK
                else QHeaderView.ResizeMode.Interactive
            )
            self._table.setColumnWidth(i, w)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table)

    def _apply_search(self):
        q = self._search.text().strip().lower()
        for r in range(self._table.rowCount()):
            if not q:
                self._table.setRowHidden(r, False)
                continue
            targets = []
            for col in (2, 4, 5, 6):  # 書類種別, 会員番号, 宛先, フリガナ
                it = self._table.item(r, col)
                if it:
                    targets.append(it.text().lower())
            self._table.setRowHidden(r, not any(q in t for t in targets))

    # ── ヘッダーチェックで全選択／全解除 ─────────────────────────────

    def _on_header_clicked(self, col: int):
        if col != _COL_CHK:
            return
        hdr_item = self._table.horizontalHeaderItem(_COL_CHK)
        if hdr_item is None:
            return
        new_state = (Qt.CheckState.Unchecked
                     if hdr_item.checkState() == Qt.CheckState.Checked
                     else Qt.CheckState.Checked)
        hdr_item.setCheckState(new_state)
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            it = self._table.item(r, _COL_CHK)
            if it:
                it.setCheckState(new_state)
        self._table.blockSignals(False)

    # ── データ読み込み ─────────────────────────────────────────────

    def _load_projects(self):
        session = get_session()
        try:
            projects = get_projects(session, status="active")
        finally:
            session.close()
        self._proj_combo.clear()
        self._proj_combo.addItem("すべて", None)
        for p in projects:
            self._proj_combo.addItem(p.name, p.id)
        self._load()

    def _load(self):
        project_id = self._proj_combo.currentData()
        status_text = self._status_combo.currentText()
        status = None if status_text == "すべて" else status_text
        invoice_only = self._doctype_combo.currentText() == "請求書のみ"

        session = get_session()
        try:
            if project_id is None:
                from app.database.models import Issuance as _Iss
                q = session.query(_Iss)
                if status:
                    q = q.filter(_Iss.status == status)
                issuances = q.order_by(_Iss.created_at.desc()).all()
            else:
                issuances = get_project_issuances(session, project_id, status)
            from app.database.models import ProjectMember
            self._table.setSortingEnabled(False)
            self._table.setRowCount(0)

            # チェックボックスヘッダーを初期化
            hdr_chk = QTableWidgetItem()
            hdr_chk.setCheckState(Qt.CheckState.Unchecked)
            self._table.setHorizontalHeaderItem(_COL_CHK, hdr_chk)

            for iss in issuances:
                if invoice_only and iss.doc_type != "invoice":
                    continue
                row = self._table.rowCount()
                self._table.insertRow(row)

                # チェックボックス列
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Unchecked)
                self._table.setItem(row, _COL_CHK, chk)

                recipient = iss.recipient_organization or iss.recipient_name or ""
                issued = iss.issued_at.strftime("%Y/%m/%d") if iss.issued_at else ""
                member_number = ""
                org_kana = ""
                if iss.project_member_id:
                    pm = session.get(ProjectMember, iss.project_member_id)
                    if pm:
                        member_number = pm.member_number or ""
                        org_kana = pm.organization_kana or ""
                doc_label = _DOC_TYPE_LABEL.get(iss.doc_type, iss.doc_type)
                for col, val in enumerate([
                    iss.doc_number, doc_label, iss.status, member_number, recipient,
                    org_kana, f"¥{int(iss.amount):,}", issued,
                ], start=1):
                    item = QTableWidgetItem(val)
                    item.setData(Qt.ItemDataRole.UserRole, iss.id)
                    self._table.setItem(row, col, item)
        finally:
            session.close()
        self._table.setSortingEnabled(True)
        self._apply_search()

    # ── 支払済み更新 ───────────────────────────────────────────────

    def _checked_issuance_ids(self) -> list[int]:
        ids = []
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, _COL_CHK)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                data_item = self._table.item(r, 1)  # 発行番号列
                if data_item:
                    ids.append(data_item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _mark_paid_checked(self):
        ids = self._checked_issuance_ids()
        if not ids:
            QMessageBox.information(self, "未選択",
                                    "チェックボックスにチェックを入れてください。")
            return
        dlg = _BatchPaymentDialog(len(ids), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        session = get_session()
        try:
            from app.database.models import Issuance
            from app.services.operation_log_service import add_log
            for iss_id in ids:
                iss = session.get(Issuance, iss_id)
                if iss and iss.status != "支払済み":
                    record_payment(
                        session,
                        issuance_id=iss_id,
                        payment_date=v["payment_date"],
                        amount=int(iss.amount),
                        payment_method=v["payment_method"],
                        staff_id=current_user.get_id(),
                        staff_name=current_user.get_name(),
                        notes=v["notes"],
                    )
                    add_log(session, "入金記録", "issuance", iss_id,
                            f"{iss.doc_number} ¥{int(iss.amount):,} {v['payment_method']}")
        finally:
            session.close()
        self._load()

    # ── 督促メール ─────────────────────────────────────────────────

    def _open_reminder_dialog(self):
        project_id = self._proj_combo.currentData()
        if project_id is None:
            return
        session = get_session()
        try:
            from app.database.models import Project, ProjectMember
            proj = session.get(Project, project_id)
            if proj is None:
                return
            due = proj.due_date
            if due is None:
                QMessageBox.information(
                    self, "支払期限未設定",
                    "この名簿には支払期限が設定されていないため、\n"
                    "期限超過を判定できません。\n"
                    "「請求・領収書データ」タブで支払期限を設定してください。")
                return
            if due >= date.today():
                QMessageBox.information(
                    self, "対象なし",
                    f"支払期限（{due.strftime('%Y/%m/%d')}）を"
                    "まだ過ぎていません。")
                return
            targets = []
            for iss in get_project_issuances(session, project_id, "発行済み"):
                if iss.doc_type != "invoice":
                    continue
                email = ""
                if iss.project_member_id:
                    pm = session.get(ProjectMember, iss.project_member_id)
                    email = (pm.email or "").strip() if pm else ""
                recipient = (iss.recipient_organization
                             or iss.recipient_name or "")
                targets.append((iss.id, iss.doc_number, recipient,
                                int(iss.amount), email))
        finally:
            session.close()

        if not targets:
            QMessageBox.information(
                self, "対象なし", "期限超過・未入金の請求書はありません。")
            return
        _ReminderDialog(targets, due, self).exec()


class _ReminderDialog(QDialog):
    """期限超過・未入金の請求書に督促メールを一括送信するダイアログ。"""

    _COLS = [("", 30), ("発行番号", 120), ("宛先", 220),
             ("金額", 90), ("メール", 180)]

    def __init__(self, targets: list[tuple], due_date, parent=None):
        # targets: [(issuance_id, doc_number, recipient, amount, email)]
        super().__init__(parent)
        self._targets = targets
        self._due_date = due_date
        self.setWindowTitle("督促メール送信")
        self.resize(680, 480)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"支払期限（{due_date.strftime('%Y/%m/%d')}）を過ぎた未入金の請求書："
            f"{len(targets)}件\n"
            "送信する行にチェックを入れてください"
            "（アドレス未登録の行は送信できません）。"))

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels([c[0] for c in self._COLS])
        hdr = self._table.horizontalHeader()
        for i, (_, w) in enumerate(self._COLS):
            hdr.setSectionResizeMode(
                i, QHeaderView.ResizeMode.Fixed if i == 0
                else QHeaderView.ResizeMode.Interactive)
            self._table.setColumnWidth(i, w)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for iss_id, doc_number, recipient, amount, email in targets:
            row = self._table.rowCount()
            self._table.insertRow(row)
            chk = QTableWidgetItem()
            if email:
                chk.setFlags(Qt.ItemFlag.ItemIsEnabled
                             | Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Checked)
            else:
                chk.setFlags(Qt.ItemFlag.NoItemFlags)
            self._table.setItem(row, 0, chk)
            for col, val in enumerate([
                doc_number, recipient, f"¥{amount:,}",
                email or "（アドレス未登録）",
            ], start=1):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, iss_id)
                self._table.setItem(row, col, item)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("閉じる")
        btn_cancel.clicked.connect(self.reject)
        btn_send = QPushButton("チェックした行に督促メールを送信")
        btn_send.clicked.connect(self._send)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(btn_send)
        layout.addLayout(btn_row)

    def _checked_ids(self) -> list[int]:
        ids = []
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                item = self._table.item(r, 1)
                if item:
                    ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _send(self):
        ids = self._checked_ids()
        if not ids:
            QMessageBox.information(self, "未選択",
                                    "送信する行にチェックを入れてください。")
            return
        box = QMessageBox(
            QMessageBox.Icon.Question, "送信確認",
            f"{len(ids)}件に督促メールを送信します。よろしいですか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            self)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        from app.services.email_service import SmtpSession, send_reminder_email
        from app.services.operation_log_service import add_log
        from app.database.models import Issuance

        progress = QProgressDialog(
            "督促メールを送信中…", "中止", 0, len(ids), self)
        progress.setWindowTitle("督促メール")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        session = get_session()
        sent = 0
        errors = []
        try:
            with SmtpSession() as smtp:
                for i, iss_id in enumerate(ids):
                    if progress.wasCanceled():
                        break
                    progress.setValue(i)
                    iss = session.get(Issuance, iss_id)
                    if iss is None:
                        continue
                    try:
                        addr = send_reminder_email(
                            session, iss, self._due_date, smtp=smtp)
                        sent += 1
                        add_log(session, "督促メール送信", "issuance", iss.id,
                                f"{iss.doc_number} → {addr}")
                    except Exception as e:
                        errors.append(str(e))
                        add_log(session, "督促メール送信失敗", "issuance",
                                iss.id, f"{iss.doc_number}：{e}")
        except Exception as e:
            errors.append(f"SMTP接続エラー：{e}")
        finally:
            progress.setValue(len(ids))
            session.close()

        msg = f"{sent}件の督促メールを送信しました。"
        if errors:
            shown = "\n".join(errors[:10])
            more = f"\n…ほか{len(errors) - 10}件" if len(errors) > 10 else ""
            QMessageBox.warning(self, "督促メール",
                                f"{msg}\n\n送信できなかったもの：\n{shown}{more}")
        else:
            QMessageBox.information(self, "督促メール", msg)
        self.accept()


class _BatchPaymentDialog(QDialog):
    """複数行一括入金記録用（金額は各行の請求額を使用）。"""

    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("一括入金記録")
        self.setFixedSize(360, 220)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{count} 件をまとめて支払済みにします。"))
        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._method = QComboBox()
        self._method.addItems(["現金", "振込", "その他"])
        self._notes = QLineEdit()
        form.addRow("入金日", self._date)
        form.addRow("入金方法", self._method)
        form.addRow("備考", self._notes)
        layout.addLayout(form)
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("支払済みにする")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def values(self) -> dict:
        qd = self._date.date()
        return {
            "payment_date": date(qd.year(), qd.month(), qd.day()),
            "payment_method": self._method.currentText(),
            "notes": self._notes.text().strip(),
        }


class PaymentDialog(QDialog):
    def __init__(self, issuance_id: int, parent=None, auto_record: bool = True):
        super().__init__(parent)
        self._issuance_id = issuance_id
        self._auto_record = auto_record
        self.setWindowTitle("入金記録")
        self.setFixedSize(360, 260)
        self._build()

    def values(self) -> dict:
        qd = self._date.date()
        return {
            "payment_date": date(qd.year(), qd.month(), qd.day()),
            "amount": self._amount.value(),
            "payment_method": self._method.currentText(),
            "notes": self._notes.text().strip(),
        }

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(3)
        form.setHorizontalSpacing(8)
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._amount = QSpinBox()
        self._amount.setRange(0, 99999999)
        session = get_session()
        try:
            from app.database.models import Issuance
            iss = session.get(Issuance, self._issuance_id)
            if iss:
                self._amount.setValue(int(iss.amount))
        finally:
            session.close()
        if not self._auto_record:
            self._amount.setReadOnly(True)
        self._method = QComboBox()
        self._method.addItems(["現金", "振込", "その他"])
        self._notes = QLineEdit()
        form.addRow("入金日", self._date)
        form.addRow("入金額（円）", self._amount)
        form.addRow("入金方法", self._method)
        form.addRow("備考", self._notes)
        layout.addLayout(form)
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("記録して支払済みにする")
        btn_ok.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _save(self):
        if not self._auto_record:
            self.accept()
            return
        v = self.values()
        session = get_session()
        try:
            record_payment(
                session,
                issuance_id=self._issuance_id,
                payment_date=v["payment_date"],
                amount=v["amount"],
                payment_method=v["payment_method"],
                staff_id=current_user.get_id(),
                staff_name=current_user.get_name(),
                notes=v["notes"],
            )
            from app.database.models import Issuance
            from app.services.operation_log_service import add_log
            iss = session.get(Issuance, self._issuance_id)
            add_log(session, "入金記録", "issuance", self._issuance_id,
                    f"{iss.doc_number if iss else ''} ¥{v['amount']:,} {v['payment_method']}")
        finally:
            session.close()
        self.accept()
