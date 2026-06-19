# app/ui/reissue_tab.py
import os
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QComboBox, QLabel, QHeaderView, QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer
from app.database.connection import get_session
from app.database.models import Issuance, Project
from app.services.project_service import get_projects
from app.services.category_service import get_active_categories
from sqlalchemy.orm import joinedload

COL_NUM  = 0
COL_PROJ = 1
COL_DEST = 2
COL_AMT  = 3
COL_TYPE = 4
COL_STAT = 5
COL_DATE = 6

_TYPE_LABEL = {"invoice": "請求書", "receipt": "領収書"}


class ReissueWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._all_projects: list = []
        self._build()
        self._load_filter_data()

    def showEvent(self, event):
        super().showEvent(event)
        self._load_filter_data()

    def _build(self):
        layout = QVBoxLayout(self)

        # ── フィルタ行 ────────────────────────────────────────────────
        top = QHBoxLayout()

        top.addWidget(QLabel("年度："))
        self._year_combo = QComboBox()
        self._year_combo.setMinimumWidth(95)
        y = date.today().year
        self._year_combo.addItem("すべて", None)
        for yr in range(y + 1, y - 5, -1):
            self._year_combo.addItem(f"{yr}年度", yr)
        self._year_combo.setCurrentIndex(2)
        self._year_combo.currentIndexChanged.connect(self._on_year_cat_changed)
        top.addWidget(self._year_combo)

        top.addWidget(QLabel("業務区分："))
        self._cat_combo = QComboBox()
        self._cat_combo.setMinimumWidth(120)
        self._cat_combo.currentIndexChanged.connect(self._on_year_cat_changed)
        top.addWidget(self._cat_combo)

        top.addWidget(QLabel("件名："))
        self._proj_combo = QComboBox()
        self._proj_combo.setMinimumWidth(220)
        self._proj_combo.currentIndexChanged.connect(self._load)
        top.addWidget(self._proj_combo)

        top.addWidget(QLabel("種別："))
        self._type_combo = QComboBox()
        self._type_combo.addItem("すべて",  None)
        self._type_combo.addItem("請求書", "invoice")
        self._type_combo.addItem("領収書", "receipt")
        self._type_combo.currentIndexChanged.connect(self._load)
        top.addWidget(self._type_combo)

        top.addStretch()

        self._btn_edit = QPushButton("内容修正")
        self._btn_edit.setFixedHeight(36)
        self._btn_edit.setEnabled(False)
        self._btn_edit.setStyleSheet(
            "QPushButton { background:#0e7490; color:white; border-radius:4px;"
            " font-weight:bold; padding:0 16px; }"
            "QPushButton:hover { background:#0c6280; }"
            "QPushButton:disabled { background:#cccccc; color:#888; }"
        )
        self._btn_edit.clicked.connect(self._edit_issuance)
        top.addWidget(self._btn_edit)

        self._btn_reissue = QPushButton("再発行（PDF再出力）")
        self._btn_reissue.setFixedHeight(36)
        self._btn_reissue.setStyleSheet(
            "QPushButton { background:#1D4ED8; color:white; border-radius:4px;"
            " font-weight:bold; padding:0 16px; }"
            "QPushButton:hover { background:#1E40AF; }"
        )
        self._btn_reissue.clicked.connect(self._reissue)
        top.addWidget(self._btn_reissue)
        layout.addLayout(top)

        # ── 検索行 ───────────────────────────────────────────────────
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("宛先・件名で絞り込み")
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._apply_search)
        self._search.textChanged.connect(lambda: self._search_timer.start(300))
        search_row.addWidget(QLabel("検索："))
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        # ── テーブル ─────────────────────────────────────────────────
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["発行番号", "件名", "宛先", "金額", "種別", "状態", "発行日"])
        hdr = self._table.horizontalHeader()
        hdr.setSortIndicatorShown(True)
        hdr.setSectionResizeMode(COL_PROJ, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_DEST, QHeaderView.ResizeMode.Stretch)
        for col in (COL_NUM, COL_AMT, COL_TYPE, COL_STAT, COL_DATE):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setSortingEnabled(True)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color:#555; font-size:11px;")
        layout.addWidget(self._count_lbl)

    # ── フィルタデータ初期化 ──────────────────────────────────────────

    def _load_filter_data(self):
        session = get_session()
        try:
            self._all_projects = get_projects(session)   # counter除外・全ステータス
            cats = get_active_categories(session)
        finally:
            session.close()

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

        self._refresh_proj_combo()

    def _on_year_cat_changed(self):
        self._refresh_proj_combo()

    def _refresh_proj_combo(self):
        sel_year = self._year_combo.currentData()
        sel_cat  = self._cat_combo.currentData()
        current_id = self._proj_combo.currentData()

        self._proj_combo.blockSignals(True)
        self._proj_combo.clear()
        self._proj_combo.addItem("すべて", None)
        for p in self._all_projects:
            if sel_year is not None and p.fiscal_year != sel_year:
                continue
            if sel_cat is not None and p.category_id != sel_cat:
                continue
            self._proj_combo.addItem(p.name, p.id)
        for i in range(self._proj_combo.count()):
            if self._proj_combo.itemData(i) == current_id:
                self._proj_combo.setCurrentIndex(i)
                break
        self._proj_combo.blockSignals(False)
        self._load()

    # ── データ読み込み ────────────────────────────────────────────────

    def _load(self):
        year     = self._year_combo.currentData()
        proj_id  = self._proj_combo.currentData()
        doc_type = self._type_combo.currentData()

        session = get_session()
        try:
            from sqlalchemy import or_
            q = (session.query(Issuance, Project)
                 .join(Project, Issuance.project_id == Project.id)
                 .filter(or_(
                     Issuance.doc_type == "receipt",
                     Issuance.status == "発行済み",
                 )))
            if year:
                q = q.filter(Project.fiscal_year == year)
            if proj_id:
                q = q.filter(Issuance.project_id == proj_id)
            if doc_type:
                q = q.filter(Issuance.doc_type == doc_type)
            rows = q.order_by(Issuance.issued_at.desc()).all()
        finally:
            session.close()

        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for iss, proj in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            dest = (iss.recipient_organization or iss.recipient_name or "").strip()
            issued = iss.issued_at.strftime("%Y/%m/%d") if iss.issued_at else ""
            for col, val in [
                (COL_NUM,  iss.doc_number or ""),
                (COL_PROJ, proj.name or ""),
                (COL_DEST, dest),
                (COL_AMT,  f"¥{int(iss.amount):,}"),
                (COL_TYPE, _TYPE_LABEL.get(iss.doc_type, iss.doc_type)),
                (COL_STAT, iss.status),
                (COL_DATE, issued),
            ]:
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole,     iss.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, proj.project_type)
                item.setData(Qt.ItemDataRole.UserRole + 2, iss.status)
                item.setData(Qt.ItemDataRole.UserRole + 3, iss.doc_type)
                self._table.setItem(r, col, item)

        self._table.setSortingEnabled(True)
        self._count_lbl.setText(f"{len(rows)} 件")
        self._apply_search()

    # ── 検索（クライアント側フィルタ） ───────────────────────────────

    def _apply_search(self):
        q = self._search.text().strip().lower()
        total = 0
        for r in range(self._table.rowCount()):
            if not q:
                self._table.setRowHidden(r, False)
                total += 1
                continue
            targets = []
            for col in (COL_PROJ, COL_DEST):  # 件名, 宛先
                it = self._table.item(r, col)
                if it:
                    targets.append(it.text().lower())
            hidden = not any(q in t for t in targets)
            self._table.setRowHidden(r, hidden)
            if not hidden:
                total += 1
        self._count_lbl.setText(f"{total} 件")

    def _on_selection_changed(self):
        row = self._table.currentRow()
        if row < 0:
            self._btn_edit.setEnabled(False)
            return
        item = self._table.item(row, COL_NUM)
        proj_type = item.data(Qt.ItemDataRole.UserRole + 1) if item else None
        status    = item.data(Qt.ItemDataRole.UserRole + 2) if item else None
        self._btn_edit.setEnabled(status == "発行済み")

    # ── 内容修正 ─────────────────────────────────────────────────────

    def _edit_issuance(self):
        row = self._table.currentRow()
        if row < 0:
            return
        item     = self._table.item(row, COL_NUM)
        iss_id   = item.data(Qt.ItemDataRole.UserRole)
        doc_type = item.data(Qt.ItemDataRole.UserRole + 3)

        from PyQt6.QtWidgets import QDialog, QVBoxLayout
        from app.ui.issuance_counter import IssuanceCounterWidget

        dlg = QDialog(self)
        dlg.setWindowTitle("フリー発行の内容修正")
        dlg.setMinimumWidth(920)
        dlg.setMinimumHeight(600)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)

        widget = IssuanceCounterWidget(doc_type=doc_type, edit_issuance_id=iss_id)
        widget.edit_completed.connect(dlg.accept)
        layout.addWidget(widget)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    # ── 再発行 ───────────────────────────────────────────────────────

    def _reissue(self):
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "未選択",
                                    "再発行する行を選択してください。")
            return
        iss_id = self._table.item(row, COL_NUM).data(Qt.ItemDataRole.UserRole)

        session = get_session()
        try:
            iss = (session.query(Issuance)
                   .options(joinedload(Issuance.lines))
                   .filter_by(id=iss_id)
                   .first())
            if not iss:
                QMessageBox.critical(self, "エラー", "発行データが見つかりません。")
                return
            from app.utils.pdf_helpers import generate_and_open
            from app.services.operation_log_service import add_log
            due_date = None
            if iss.doc_type == "invoice":
                from app.ui.invoice_options_dialog import InvoiceOptionsDialog
                from PyQt6.QtWidgets import QDialog
                opts = InvoiceOptionsDialog(issued_at=iss.issued_at, parent=self)
                if opts.exec() != QDialog.DialogCode.Accepted:
                    return
                due_date = opts.due_date()
            from app.database.models import Project as _Project
            _proj = session.get(_Project, iss.project_id)
            from PyQt6.QtWidgets import QFileDialog
            from app.utils.pdf_helpers import get_pdf_output_dir
            _out_dir = get_pdf_output_dir()
            _default_name = os.path.join(_out_dir, f"{iss.doc_number}_再発行.pdf")
            _save_path, _ = QFileDialog.getSaveFileName(
                self, "PDFの保存先を選択", _default_name, "PDF ファイル (*.pdf)"
            )
            if not _save_path:
                return  # キャンセル時は何も変更せず終了
            generate_and_open(iss, session, reissue=True, due_date=due_date,
                              save_path=_save_path,
                              project=_proj)
            _lbl = "請求書" if iss.doc_type == "invoice" else "領収書"
            add_log(session, "再発行", "issuance", iss.id,
                    f"{_lbl} {iss.doc_number} 宛先：{iss.recipient_organization or iss.recipient_name}")

            ans = QMessageBox.question(
                self, "メール送信",
                f"再発行した{_lbl}をメールで送信しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Yes:
                self._send_reissue_email(session, iss, _save_path)
        except Exception as e:
            QMessageBox.critical(self, "再発行エラー", str(e))
        finally:
            session.close()

    def _send_reissue_email(self, session, iss, pdf_path: str):
        from PyQt6.QtCore import QThread
        from PyQt6.QtWidgets import QApplication, QDialog, QInputDialog, QProgressDialog
        from app.services.email_service import (
            prepare_issuance_email, validate_email_addr,
        )
        from app.services.operation_log_service import add_log
        from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog
        from app.ui.m365_mail_worker import M365MailWorker
        from app.utils.app_config import get_m365_client_id, get_m365_tenant_id

        client_id = get_m365_client_id()
        tenant_id = get_m365_tenant_id()
        if not client_id or not tenant_id:
            QMessageBox.critical(
                self, "設定エラー",
                "Microsoft 365 の Client ID / Tenant ID が設定されていません。\n"
                "設定 → メール設定から入力してください。")
            return

        _lbl = "請求書" if iss.doc_type == "invoice" else "領収書"

        # メールアドレスを取得（会員設定 → 手入力）
        to_addr = subject = body_html = ""
        try:
            to_addr, subject, body_html, _ = prepare_issuance_email(session, iss)
        except ValueError:
            pass

        if not to_addr:
            name = iss.recipient_organization or iss.recipient_name or ""
            text, ok = QInputDialog.getText(
                self, "送信先メールアドレス",
                f"{name} の送信先メールアドレスを入力してください：")
            if not ok or not text.strip():
                return
            try:
                to_addr = validate_email_addr(text.strip())
            except ValueError as e:
                QMessageBox.critical(self, "入力エラー", str(e))
                return
            try:
                _, subject, body_html, _ = prepare_issuance_email(
                    session, iss, to_addr=to_addr)
            except ValueError as e:
                QMessageBox.critical(self, "エラー", str(e))
                return

        dlg = InvoiceMailConfirmDialog(
            self,
            to_recipients=[to_addr],
            subject=subject,
            body_html=body_html,
            pdf_path=pdf_path,
            invoice_no=iss.doc_number,
            customer_name=(iss.recipient_organization or iss.recipient_name or ""),
            amount_text=f"¥{iss.amount:,}" if iss.amount else "",
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        thread = QThread(self)
        worker = M365MailWorker(
            client_id, tenant_id, [to_addr], subject, body_html, pdf_path)
        worker.moveToThread(thread)
        prog = QProgressDialog(f"送信中（{iss.doc_number}）…", None, 0, 0, self)
        prog.setWindowTitle("メール送信")
        prog.setWindowModality(Qt.WindowModality.WindowModal)
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
            add_log(session, "メール送信", "issuance", iss.id,
                    f"{_lbl} {iss.doc_number} 再発行 → {to_addr}")
            QMessageBox.information(
                self, "送信完了",
                f"{_lbl}（再発行）をメールで送信しました。\n宛先：{to_addr}")
        else:
            err_msg = _result.get("err", "不明なエラー")
            add_log(session, "メール送信失敗", "issuance", iss.id,
                    f"{_lbl} {iss.doc_number} 再発行：{err_msg}")
            QMessageBox.critical(self, "送信失敗",
                                 f"メール送信に失敗しました。\n{err_msg}")
