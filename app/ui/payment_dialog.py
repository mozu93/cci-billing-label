# app/ui/payment_dialog.py
from datetime import date
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QDateEdit, QSpinBox, QComboBox, QLineEdit, QTextEdit,
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
    ("支払期限",  90),   # 2
    ("状態",      80),   # 3
    ("会員番号",  90),   # 4
    ("宛先",     200),   # 5
    ("フリガナ", 160),   # 6
    ("金額",      90),   # 7
    ("発行日",    90),   # 8
    ("メール",   180),   # 9
]


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

        # ── ボタン行（テーブルの下） ─────────────────────────────────
        btn_row = QHBoxLayout()
        btn_pay_checked = QPushButton("チェックした行を支払済みに更新")
        btn_pay_checked.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 2px 12px; }"
            "QPushButton:hover { background: #1D4ED8; }")
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
            from app.database.models import ProjectMember, Project as _Proj
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
                email_addr = ""
                if iss.project_member_id:
                    pm = session.get(ProjectMember, iss.project_member_id)
                    if pm:
                        member_number = pm.member_number or ""
                        org_kana = pm.organization_kana or ""
                        email_addr = (pm.email or "").strip()
                proj = session.get(_Proj, iss.project_id)
                due_str = proj.due_date.strftime("%Y/%m/%d") if (proj and proj.due_date) else ""
                for col, val in enumerate([
                    iss.doc_number, due_str, iss.status, member_number, recipient,
                    org_kana, f"¥{int(iss.amount):,}", issued,
                    email_addr,
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
        checked_ids = self._checked_issuance_ids()
        project_id  = self._proj_combo.currentData()
        session = get_session()
        try:
            from app.database.models import Project, ProjectMember, Issuance
            today = date.today()
            targets = []

            if checked_ids:
                # チェック行を直接対象にする（二度手間なし）
                for iss_id in checked_ids:
                    iss = session.get(Issuance, iss_id)
                    if iss is None or iss.doc_type != "invoice":
                        continue
                    proj = session.get(Project, iss.project_id)
                    due  = proj.due_date if proj else None
                    email = ""
                    if iss.project_member_id:
                        pm = session.get(ProjectMember, iss.project_member_id)
                        email = (pm.email or "").strip() if pm else ""
                    recipient = iss.recipient_organization or iss.recipient_name or ""
                    targets.append((iss.id, iss.doc_number, recipient,
                                    int(iss.amount), email, due))
            elif project_id is None:
                # チェックなし＋「すべて」→ 全名簿の期限超過を収集
                for proj in get_projects(session):
                    due = proj.due_date
                    if not due or due >= today:
                        continue
                    for iss in get_project_issuances(session, proj.id, "発行済み"):
                        if iss.doc_type != "invoice":
                            continue
                        email = ""
                        if iss.project_member_id:
                            pm = session.get(ProjectMember, iss.project_member_id)
                            email = (pm.email or "").strip() if pm else ""
                        recipient = iss.recipient_organization or iss.recipient_name or ""
                        targets.append((iss.id, iss.doc_number, recipient,
                                        int(iss.amount), email, due))
            else:
                # チェックなし＋名簿指定 → その名簿の期限超過を全件収集
                proj = session.get(Project, project_id)
                if proj is None:
                    return
                due = proj.due_date
                if due is None:
                    QMessageBox.information(
                        self, "支払期限未設定",
                        "この名簿には支払期限が設定されていません。\n"
                        "「請求・領収書データ」タブで請求書を発行してください。")
                    return
                if due >= today:
                    QMessageBox.information(
                        self, "対象なし",
                        f"支払期限（{due.strftime('%Y/%m/%d')}）を"
                        "まだ過ぎていません。")
                    return
                for iss in get_project_issuances(session, project_id, "発行済み"):
                    if iss.doc_type != "invoice":
                        continue
                    email = ""
                    if iss.project_member_id:
                        pm = session.get(ProjectMember, iss.project_member_id)
                        email = (pm.email or "").strip() if pm else ""
                    recipient = iss.recipient_organization or iss.recipient_name or ""
                    targets.append((iss.id, iss.doc_number, recipient,
                                    int(iss.amount), email, due))
        finally:
            session.close()

        if not targets:
            QMessageBox.information(
                self, "対象なし", "期限超過・未入金の請求書はありません。")
            return
        _ReminderDialog(targets, self).exec()


class _ReminderDialog(QDialog):
    """期限超過・未入金の請求書に督促メールを一括送信するダイアログ。"""

    _COLS = [("", 30), ("発行番号", 120), ("支払期限", 90), ("宛先", 200),
             ("金額", 90), ("メール", 180), ("結果", 80)]

    _COL_RESULT = 6

    def __init__(self, targets: list[tuple], parent=None):
        # targets: [(issuance_id, doc_number, recipient, amount, email, due_date)]
        super().__init__(parent)
        self._targets = targets
        # iss_id -> due_date のマップ（送信時に参照）
        self._due_map = {t[0]: t[5] for t in targets}
        self.setWindowTitle("督促メール送信")
        self.resize(820, 480)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"支払期限を過ぎた未入金の請求書：{len(targets)}件\n"
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
        for iss_id, doc_number, recipient, amount, email, due_date in targets:
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
            due_str = due_date.strftime("%Y/%m/%d") if due_date else ""
            for col, val in enumerate([
                doc_number, due_str, recipient, f"¥{amount:,}",
                email or "（アドレス未登録）", "",
            ], start=1):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, iss_id)
                self._table.setItem(row, col, item)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("閉じる")
        btn_cancel.clicked.connect(self.reject)
        self._btn_send = QPushButton("チェックした行に督促メールを送信")
        self._btn_send.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 2px 12px; }"
            "QPushButton:hover { background: #1D4ED8; }")
        self._btn_send.clicked.connect(self._send)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_send)
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

    def _row_for_iss_id(self, iss_id: int) -> int | None:
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == iss_id:
                return r
        return None

    def _set_row_result(self, row: int, text: str, success: bool):
        from PyQt6.QtGui import QColor
        color = QColor("#16A34A") if success else QColor("#DC2626")
        bg    = QColor("#F0FDF4") if success else QColor("#FEF2F2")
        result_item = QTableWidgetItem(text)
        result_item.setForeground(color)
        self._table.setItem(row, self._COL_RESULT, result_item)
        for col in range(self._table.columnCount()):
            it = self._table.item(row, col)
            if it:
                it.setBackground(bg)
        if success:
            chk = self._table.item(row, 0)
            if chk:
                chk.setCheckState(Qt.CheckState.Unchecked)

    def _send(self):
        ids = self._checked_ids()
        if not ids:
            QMessageBox.information(self, "未選択",
                                    "送信する行にチェックを入れてください。")
            return

        # メール内容の確認・編集ダイアログ
        from app.services.email_service import get_email_template, PLACEHOLDER_KEYS
        tmpl_subject, tmpl_body = get_email_template("reminder")
        preview_dlg = _ReminderPreviewDialog(
            len(ids), tmpl_subject, tmpl_body, self)
        if preview_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        custom_subject = preview_dlg.subject()
        custom_body    = preview_dlg.body()

        from app.services.email_service import prepare_reminder_email
        from app.services.operation_log_service import add_log
        from app.database.models import Issuance
        from app.utils.app_config import get_m365_client_id, get_m365_tenant_id
        from app.ui.m365_mail_worker import M365ReminderBatchWorker
        from PyQt6.QtCore import QThread
        from PyQt6.QtWidgets import QApplication

        client_id = get_m365_client_id()
        tenant_id = get_m365_tenant_id()
        if not client_id or not tenant_id:
            QMessageBox.critical(
                self, "設定エラー",
                "Microsoft 365 の Client ID / Tenant ID が設定されていません。\n"
                "設定 → メール設定から入力してください。")
            return

        # 送信データを事前に組み立て
        session = get_session()
        items      = []
        pre_errors = []  # [(iss_id, message)]
        try:
            for iss_id in ids:
                iss = session.get(Issuance, iss_id)
                if iss is None:
                    continue
                try:
                    to_addr, subject, body_html, pdf_path = prepare_reminder_email(
                        session, iss, self._due_map.get(iss.id),
                        custom_subject=custom_subject,
                        custom_body=custom_body)
                    items.append({
                        "to": to_addr, "subject": subject,
                        "body_html": body_html, "pdf_path": pdf_path,
                        "doc_number": iss.doc_number or str(iss_id),
                        "iss_id": iss.id,
                    })
                except Exception as e:
                    pre_errors.append((iss.id, str(e)))
                    add_log(session, "督促メール送信失敗", "issuance",
                            iss.id, f"{iss.doc_number}：{e}")
        finally:
            session.close()

        # 事前エラー行を結果列に反映
        for iss_id, msg in pre_errors:
            r = self._row_for_iss_id(iss_id)
            if r is not None:
                self._set_row_result(r, "失敗", success=False)

        if not items:
            QMessageBox.warning(self, "督促メール", "送信対象がありませんでした。")
            return

        # M365でバックグラウンド送信
        self._btn_send.setEnabled(False)
        progress = QProgressDialog(
            "督促メールを送信中…", None, 0, len(items), self)
        progress.setWindowTitle("督促メール")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        thread = QThread(self)
        worker = M365ReminderBatchWorker(client_id, tenant_id, items)
        worker.moveToThread(thread)
        worker.progress.connect(lambda cur, _tot: progress.setValue(cur))
        _result: dict = {}
        def _on_done(sent, errors, _r=_result, _t=thread):
            _r["sent"]   = sent
            _r["errors"] = errors
            _t.quit()
        worker.done.connect(_on_done)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        while thread.isRunning():
            QApplication.processEvents()
        progress.setValue(len(items))
        self._btn_send.setEnabled(True)

        # 操作ログ & 結果列の更新
        sent   = _result.get("sent", 0)
        w_errors = _result.get("errors", [])
        session2 = get_session()
        try:
            for i, item in enumerate(items):
                iss_id = item["iss_id"]
                r = self._row_for_iss_id(iss_id)
                if i < sent:
                    add_log(session2, "督促メール送信", "issuance", iss_id,
                            f"{item['doc_number']} → {item['to']}")
                    if r is not None:
                        self._set_row_result(r, "送信済み", success=True)
                else:
                    err_msg = w_errors[i - sent] if (i - sent) < len(w_errors) else "失敗"
                    add_log(session2, "督促メール送信失敗", "issuance", iss_id,
                            f"{item['doc_number']}：{err_msg}")
                    if r is not None:
                        self._set_row_result(r, "失敗", success=False)
        finally:
            session2.close()

        all_errors = [msg for _, msg in pre_errors] + w_errors
        msg = f"{sent}件の督促メールを送信しました。"
        if all_errors:
            shown = "\n".join(all_errors[:10])
            more = f"\n…ほか{len(all_errors) - 10}件" if len(all_errors) > 10 else ""
            QMessageBox.warning(self, "督促メール",
                                f"{msg}\n\n失敗した行はチェックが残っています。\n"
                                f"内容を確認後、再送できます。\n\n{shown}{more}")
        else:
            QMessageBox.information(self, "督促メール", msg)


class _ReminderPreviewDialog(QDialog):
    """督促メールの件名・本文を確認・編集してから送信するダイアログ。"""

    def __init__(self, count: int, tmpl_subject: str, tmpl_body: str,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("メール内容の確認・編集")
        self.resize(620, 500)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"{count}件に以下の内容で督促メールを送信します。\n"
            "差し込みタグ（{宛名} {会社名} {文書番号} {金額} {支払期限} 等）は"
            "送信時に各宛先の情報に置き換えられます。"))

        form = QFormLayout()
        form.setVerticalSpacing(6)
        self._subject = QLineEdit(tmpl_subject)
        form.addRow("件名", self._subject)
        layout.addLayout(form)

        layout.addWidget(QLabel("本文："))
        self._body = QTextEdit()
        self._body.setAcceptRichText(False)
        self._body.setPlainText(tmpl_body)
        self._body.setMinimumHeight(280)
        layout.addWidget(self._body)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_save_tmpl = QPushButton("テンプレートとして保存")
        btn_save_tmpl.setToolTip("編集内容をメール設定のテンプレートに上書き保存します")
        btn_save_tmpl.clicked.connect(self._save_template)
        btn_send = QPushButton("この内容で送信")
        btn_send.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 2px 12px; }"
            "QPushButton:hover { background: #1D4ED8; }")
        btn_send.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save_tmpl)
        btn_row.addStretch()
        btn_row.addWidget(btn_send)
        layout.addLayout(btn_row)

    def subject(self) -> str:
        return self._subject.text().strip()

    def body(self) -> str:
        return self._body.toPlainText()

    def _save_template(self):
        from app.utils.app_config import get_config, save_config
        config = get_config()
        config.setdefault("email_templates", {}).setdefault("reminder", {})
        config["email_templates"]["reminder"]["subject"] = self.subject()
        config["email_templates"]["reminder"]["body"]    = self.body()
        save_config(config)
        QMessageBox.information(self, "保存完了",
                                "督促メールのテンプレートを保存しました。\n"
                                "次回以降、この内容がデフォルトで表示されます。")


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
        btn_ok.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 2px 12px; }"
            "QPushButton:hover { background: #1D4ED8; }")
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
        btn_ok.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 4px;"
            " font-weight: bold; padding: 2px 12px; }"
            "QPushButton:hover { background: #1D4ED8; }")
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
