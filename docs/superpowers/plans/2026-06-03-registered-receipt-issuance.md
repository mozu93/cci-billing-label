# 登録済発行の作り直し（窓口での入金記録＋領収書発行）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 窓口発行＞「登録済発行」を、事業所を検索して発行済み・未入金の請求書を選び、入金記録と同時に領収書を発行する画面に作り直す。

**Architecture:** サービス層に「請求書から領収書を発行（＋入金記録）」する関数と「未入金請求書の検索」関数を追加し、UI（`IssuanceCrossMemberWidget`）を検索→未入金一覧→入金ダイアログ→領収書発行の流れに置き換える。入金と領収書発行は1トランザクションでセット実行する。

**Tech Stack:** Python, PyQt6, SQLAlchemy, pytest（既存の `db_session` / `memory_db` / `qtbot` フィクスチャを利用）。

参照spec: `docs/superpowers/specs/2026-06-03-registered-receipt-issuance-design.md`

---

## File Structure

- Modify: `app/services/issuance_service.py` — 関数 `issue_receipt_for_invoice` と `search_unpaid_invoices` を追加。
- Modify: `app/ui/payment_dialog.py` — `PaymentDialog` に「入金情報の収集のみ（自動記録しない）」モードと `values()` を追加。
- Rewrite: `app/ui/issuance_cross_member.py` — `IssuanceCrossMemberWidget` を新仕様に作り直し。
- Modify: `tests/test_issuance_service.py` — サービス層の新関数テストを追加。
- Modify: `tests/test_counter_issuance_tab.py` — 登録済発行UIのテストを追加。

---

## Task 1: サービス層 `issue_receipt_for_invoice`

発行済み請求書から、同明細・同額・同宛名の領収書を発行し、同時に入金（`Payment`）を記録して請求書を「支払済み」にする。

**Files:**
- Modify: `app/services/issuance_service.py`（末尾に関数追加。既存 import の `Issuance, IssuanceLine, Payment` を利用）
- Test: `tests/test_issuance_service.py`

- [ ] **Step 1: Write the failing test**

`tests/test_issuance_service.py` の末尾に追記する（`_setup` は同ファイル先頭の既存ヘルパ）。

```python
def test_issue_receipt_for_invoice(db_session):
    from app.services.issuance_service import (
        create_issuance_for_member, mark_as_issued, issue_receipt_for_invoice,
    )
    from app.database.models import Payment, Issuance
    from datetime import date
    proj, tmpl, pm = _setup(db_session)
    invoice = create_issuance_for_member(
        db_session, proj.id, pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5,
    )
    mark_as_issued(db_session, invoice.id, None, "田中", "窓口手渡し")

    receipt = issue_receipt_for_invoice(
        db_session, invoice_id=invoice.id,
        payment_date=date(2026, 5, 30),
        payment_method="現金", notes="窓口入金",
        staff_id=None, staff_name="田中",
    )

    # 領収書は元請求書の明細・金額・宛名を引き継ぐ
    assert receipt.doc_type == "receipt"
    assert receipt.doc_number.startswith("RCP-")
    assert receipt.status == "支払済み"
    assert int(receipt.amount) == int(invoice.amount)
    assert receipt.recipient_organization == invoice.recipient_organization
    assert len(receipt.lines) == len(invoice.lines)
    assert int(receipt.lines[0].unit_price) == int(invoice.lines[0].unit_price)
    assert receipt.id != invoice.id

    # 元請求書は支払済みになり、Payment が1件記録される
    db_session.refresh(invoice)
    assert invoice.status == "支払済み"
    payments = db_session.query(Payment).filter_by(issuance_id=invoice.id).all()
    assert len(payments) == 1
    assert int(payments[0].amount) == int(invoice.amount)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_issuance_service.py::test_issue_receipt_for_invoice -v`
Expected: FAIL（`ImportError` または `cannot import name 'issue_receipt_for_invoice'`）

- [ ] **Step 3: Write minimal implementation**

`app/services/issuance_service.py` の末尾に追加する。

```python
def issue_receipt_for_invoice(session: Session, invoice_id: int,
                              payment_date: date,
                              payment_method: str = "現金",
                              notes: str = "",
                              staff_id: int | None = None,
                              staff_name: str = "") -> Issuance:
    """発行済み請求書から領収書を発行し、入金を記録して請求書を支払済みにする。

    領収書は元請求書の明細・金額・宛名をそのまま引き継ぐ。
    入金額は請求書の全額固定。全体を1トランザクションで実行する。
    """
    invoice = session.get(Issuance, invoice_id)
    if invoice is None:
        raise ValueError("請求書が見つかりません。")
    if invoice.doc_type != "invoice":
        raise ValueError("請求書ではありません。")

    today = date.today()
    doc_number = get_next_doc_number(session, "receipt", today.year, today.month)
    receipt = Issuance(
        project_id=invoice.project_id,
        project_member_id=invoice.project_member_id,
        recipient_organization=invoice.recipient_organization,
        recipient_name=invoice.recipient_name,
        doc_type="receipt",
        doc_number=doc_number,
        status="支払済み",
        amount=invoice.amount,
        issued_at=datetime.now(),
        staff_id=staff_id,
        staff_name=staff_name,
        delivery_method="窓口手渡し",
    )
    session.add(receipt)
    session.flush()
    for line in invoice.lines:
        session.add(IssuanceLine(
            issuance_id=receipt.id,
            item_template_id=line.item_template_id,
            item_name=line.item_name,
            quantity=line.quantity,
            unit=line.unit,
            unit_price=line.unit_price,
            tax_rate=line.tax_rate,
            line_total=line.line_total,
        ))

    payment = Payment(
        issuance_id=invoice.id,
        payment_date=payment_date,
        amount=invoice.amount,
        payment_method=payment_method,
        staff_id=staff_id,
        staff_name=staff_name,
        notes=notes,
    )
    session.add(payment)
    invoice.status = "支払済み"
    session.commit()
    session.refresh(receipt)
    return receipt
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_issuance_service.py::test_issue_receipt_for_invoice -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/issuance_service.py tests/test_issuance_service.py
git commit -m "feat: 請求書から領収書を発行し入金を記録する issue_receipt_for_invoice を追加"
```

---

## Task 2: サービス層 `search_unpaid_invoices`

検索語（事業所名・代表者名・フリガナ）にマッチする、発行済み・未入金の請求書を返す。

**Files:**
- Modify: `app/services/issuance_service.py`（末尾に関数追加。`ProjectMember` は既存 import 済み）
- Test: `tests/test_issuance_service.py`

- [ ] **Step 1: Write the failing test**

`tests/test_issuance_service.py` の末尾に追記する。

```python
def test_search_unpaid_invoices(db_session):
    from app.services.issuance_service import (
        create_issuance_for_member, mark_as_issued, record_payment,
        search_unpaid_invoices,
    )
    from datetime import date
    proj, tmpl, pm = _setup(db_session)

    inv = create_issuance_for_member(
        db_session, proj.id, pm.id,
        recipient_organization=pm.organization_name,
        recipient_name=pm.representative_name,
        doc_type="invoice", fiscal_year=2026, month=5,
    )
    mark_as_issued(db_session, inv.id, None, "田中", "窓口手渡し")

    # 発行済み・未入金なのでヒットする
    hits = search_unpaid_invoices(db_session, "○○商事")
    assert len(hits) == 1
    assert hits[0].id == inv.id

    # マッチしない検索語では出ない
    assert search_unpaid_invoices(db_session, "存在しない名前") == []

    # 支払済みになると一覧から外れる
    record_payment(db_session, inv.id, payment_date=date(2026, 5, 30),
                   amount=int(inv.amount), payment_method="現金", staff_name="田中")
    assert search_unpaid_invoices(db_session, "○○商事") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_issuance_service.py::test_search_unpaid_invoices -v`
Expected: FAIL（`cannot import name 'search_unpaid_invoices'`）

- [ ] **Step 3: Write minimal implementation**

`app/services/issuance_service.py` の末尾に追加する。

```python
def search_unpaid_invoices(session: Session, query: str,
                           limit: int = 50) -> list[Issuance]:
    """検索語にマッチする、発行済み・未入金（status="発行済み"）の請求書を返す。

    検索対象: 宛先事業所名・宛先代表者名・名簿会員のフリガナ。
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    invoices = (session.query(Issuance)
                .filter(Issuance.doc_type == "invoice",
                        Issuance.status == "発行済み")
                .order_by(Issuance.issued_at.desc())
                .all())
    results = []
    for iss in invoices:
        parts = [iss.recipient_organization or "", iss.recipient_name or ""]
        if iss.project_member_id:
            pm = session.get(ProjectMember, iss.project_member_id)
            if pm:
                parts.append(pm.organization_kana or "")
        if q in " ".join(parts).lower():
            results.append(iss)
            if len(results) >= limit:
                break
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_issuance_service.py::test_search_unpaid_invoices -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/issuance_service.py tests/test_issuance_service.py
git commit -m "feat: 未入金の発行済み請求書を検索する search_unpaid_invoices を追加"
```

---

## Task 3: `PaymentDialog` に入金情報の収集モードを追加

登録済発行では入金記録と領収書発行を1関数（Task 1）で行うため、`PaymentDialog` を「入金情報を収集するだけで自動記録しない」モードで使えるようにする。既存の入金管理タブからの利用（`auto_record=True`）は従来通り。

**Files:**
- Modify: `app/ui/payment_dialog.py:101-158`（`PaymentDialog` の `__init__` と `_save`、`values()` 追加）
- Test: `tests/test_counter_issuance_tab.py`

- [ ] **Step 1: Write the failing test**

`tests/test_counter_issuance_tab.py` の末尾に追記する。

```python
def test_payment_dialog_collect_only_mode(qtbot, memory_db):
    """auto_record=False では record_payment を呼ばず値だけ返す。"""
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import (
        create_issuance_for_member, mark_as_issued,
    )
    from app.ui.payment_dialog import PaymentDialog
    from app.database.models import Payment

    s = get_session()
    cat = create_category(s, "青年部")
    tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(s, "2026 青年部", cat.id, 2026, "list")
    add_template_to_project(s, proj.id, tmpl.id)
    add_roster_entries(s, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(s, proj.id)[0]
    inv = create_issuance_for_member(s, proj.id, pm.id, "○○商事", "",
                                     "invoice", 2026, 5)
    mark_as_issued(s, inv.id, None, "田中", "窓口手渡し")
    inv_id = inv.id
    s.close()

    dlg = PaymentDialog(inv_id, auto_record=False)
    qtbot.addWidget(dlg)
    v = dlg.values()
    assert set(v.keys()) == {"payment_date", "amount", "payment_method", "notes"}

    dlg._save()  # accept のみ。record_payment は呼ばれない
    s = get_session()
    assert s.query(Payment).filter_by(issuance_id=inv_id).count() == 0
    s.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_counter_issuance_tab.py::test_payment_dialog_collect_only_mode -v`
Expected: FAIL（`PaymentDialog.__init__() got an unexpected keyword argument 'auto_record'`）

- [ ] **Step 3: Write minimal implementation**

`app/ui/payment_dialog.py` の `PaymentDialog.__init__` を変更する。

変更前（`:102-107`）:
```python
    def __init__(self, issuance_id: int, parent=None):
        super().__init__(parent)
        self._issuance_id = issuance_id
        self.setWindowTitle("入金記録")
        self.setFixedSize(360, 260)
        self._build()
```

変更後:
```python
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
```

`_save`（`:141-158`）を変更する。

変更前:
```python
    def _save(self):
        qd = self._date.date()
        payment_date = date(qd.year(), qd.month(), qd.day())
        session = get_session()
        try:
            record_payment(
                session,
                issuance_id=self._issuance_id,
                payment_date=payment_date,
                amount=self._amount.value(),
                payment_method=self._method.currentText(),
                staff_id=current_user.get_id(),
                staff_name=current_user.get_name(),
                notes=self._notes.text().strip()
            )
        finally:
            session.close()
        self.accept()
```

変更後:
```python
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
        finally:
            session.close()
        self.accept()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_counter_issuance_tab.py::test_payment_dialog_collect_only_mode -v`
Expected: PASS

既存の入金管理テストが壊れていないことも確認する。
Run: `python -m pytest tests/ -k payment -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/payment_dialog.py tests/test_counter_issuance_tab.py
git commit -m "feat: PaymentDialog に入金情報の収集のみモード(auto_record=False)を追加"
```

---

## Task 4: `IssuanceCrossMemberWidget` を作り直し

検索→未入金請求書一覧→入金ダイアログ→領収書発行の画面に置き換える。

**Files:**
- Rewrite: `app/ui/issuance_cross_member.py`（全置換）
- Test: `tests/test_counter_issuance_tab.py`

- [ ] **Step 1: Write the failing test**

`tests/test_counter_issuance_tab.py` の末尾に追記する。

```python
def test_registered_issue_lists_unpaid_invoices(qtbot, memory_db):
    """検索すると発行済み・未入金の請求書が一覧に出る。支払済みは出ない。"""
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import (
        create_issuance_for_member, mark_as_issued, record_payment,
    )
    from app.ui.issuance_cross_member import IssuanceCrossMemberWidget
    from datetime import date

    s = get_session()
    cat = create_category(s, "青年部")
    tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(s, "2026 青年部会費", cat.id, 2026, "list")
    add_template_to_project(s, proj.id, tmpl.id)
    add_roster_entries(s, proj.id, [
        {"organization_name": "○○商事"},
        {"organization_name": "△△工業"},
    ])
    pms = get_project_members(s, proj.id)
    inv1 = create_issuance_for_member(s, proj.id, pms[0].id, "○○商事", "",
                                      "invoice", 2026, 5)
    mark_as_issued(s, inv1.id, None, "田中", "窓口手渡し")
    inv2 = create_issuance_for_member(s, proj.id, pms[1].id, "△△工業", "",
                                      "invoice", 2026, 5)
    mark_as_issued(s, inv2.id, None, "田中", "窓口手渡し")
    # △△工業は支払済み → 一覧に出ない
    record_payment(s, inv2.id, payment_date=date(2026, 5, 30),
                   amount=int(inv2.amount), payment_method="現金", staff_name="田中")
    s.close()

    w = IssuanceCrossMemberWidget()
    qtbot.addWidget(w)
    w._search.setText("商事")
    w._search_member()
    assert w._result_table.rowCount() == 1

    w._search.setText("△△工業")
    w._search_member()
    assert w._result_table.rowCount() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_counter_issuance_tab.py::test_registered_issue_lists_unpaid_invoices -v`
Expected: FAIL（旧実装には `_result_table` が無いため `AttributeError`）

- [ ] **Step 3: Write minimal implementation**

`app/ui/issuance_cross_member.py` を以下で全置換する。

```python
# app/ui/issuance_cross_member.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView,
    QDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from app.database.connection import get_session
from app.services.issuance_service import (
    search_unpaid_invoices, issue_receipt_for_invoice
)
from app.services.project_service import get_project_by_id
from app.ui.payment_dialog import PaymentDialog
from app.utils import current_user


class IssuanceCrossMemberWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "事業所を検索すると、発行済みで未入金の請求書が一覧に出ます。\n"
            "行を選んで入金を記録すると、その請求書の領収書を発行します。"
        ))

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("事業所名・フリガナ・代表者名")
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._search_member)
        self._search.textChanged.connect(lambda: self._timer.start(300))
        search_row.addWidget(QLabel("検索："))
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        layout.addWidget(QLabel("発行済み・未入金の請求書："))
        self._result_table = QTableWidget(0, 5)
        self._result_table.setHorizontalHeaderLabels(
            ["事業所名", "件名", "請求書番号", "金額", "発行日"])
        self._result_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._result_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._result_table)

        btn_row = QHBoxLayout()
        btn_issue = QPushButton("入金を記録して領収書を発行")
        btn_issue.clicked.connect(self._issue_receipt)
        btn_row.addWidget(btn_issue)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _search_member(self):
        query = self._search.text().strip()
        self._result_table.setRowCount(0)
        if not query:
            return
        session = get_session()
        try:
            invoices = search_unpaid_invoices(session, query)
            for iss in invoices:
                proj = get_project_by_id(session, iss.project_id)
                row = self._result_table.rowCount()
                self._result_table.insertRow(row)
                issued = iss.issued_at.strftime("%Y/%m/%d") if iss.issued_at else ""
                values = [
                    iss.recipient_organization or iss.recipient_name or "",
                    proj.name if proj else "",
                    iss.doc_number,
                    f"¥{int(iss.amount):,}",
                    issued,
                ]
                for col, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    item.setData(Qt.ItemDataRole.UserRole, iss.id)
                    self._result_table.setItem(row, col, item)
        finally:
            session.close()

    def _selected_invoice_id(self) -> int | None:
        row = self._result_table.currentRow()
        if row < 0:
            return None
        return self._result_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _issue_receipt(self):
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            QMessageBox.warning(self, "未選択", "請求書を選択してください。")
            return
        dlg = PaymentDialog(invoice_id, self, auto_record=False)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        session = get_session()
        try:
            from app.utils.pdf_helpers import generate_and_open
            receipt = issue_receipt_for_invoice(
                session, invoice_id=invoice_id,
                payment_date=v["payment_date"],
                payment_method=v["payment_method"],
                notes=v["notes"],
                staff_id=current_user.get_id(),
                staff_name=current_user.get_name(),
            )
            generate_and_open(receipt, session)
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
        finally:
            session.close()
        self._search_member()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_counter_issuance_tab.py::test_registered_issue_lists_unpaid_invoices -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS（全テスト。既存のサブタブ名テスト `["フリー発行", "登録済発行"]` も維持される）

- [ ] **Step 6: Commit**

```bash
git add app/ui/issuance_cross_member.py tests/test_counter_issuance_tab.py
git commit -m "feat: 登録済発行を検索→未入金請求書→入金記録＋領収書発行に作り直し"
```

---

## Task 5: 手動確認

- [ ] **Step 1: アプリを起動して動作確認**

Run: `python -m app.main`（または既存の起動手順）
確認手順:
1. まとめて発行＞登録データから発行で、ある事業所に請求書を発行する（発行済みになる）。
2. 窓口発行＞登録済発行を開く。
3. その事業所名で検索し、未入金の請求書が一覧に出ることを確認。
4. 行を選び「入金を記録して領収書を発行」→ 入金ダイアログ → OK。
5. 領収書PDFが開き、再検索すると当該請求書が一覧から消える（支払済みになった）ことを確認。
6. まとめて発行＞入金管理で、当該請求書が「支払済み」になっていることを確認。

---

## Self-Review

- **Spec coverage:**
  - 画面（検索→未入金一覧→入金＋領収書発行）→ Task 4。
  - 「未入金の請求書」定義（発行済みinvoice）→ Task 2 の `search_unpaid_invoices`、Task 1 の doc_type ガード。
  - サービス層 `issue_receipt_for_invoice`（明細コピー・採番・入金記録・支払済み化・1トランザクション）→ Task 1。
  - 既存入金ダイアログ流用 → Task 3。
  - スコープ外（入金管理・登録データから発行・フリー発行）→ 変更なし（触れていない）。
- **Placeholder scan:** プレースホルダなし。全ステップに実コード/実コマンドを記載。
- **Type consistency:** `issue_receipt_for_invoice(session, invoice_id, payment_date, payment_method, notes, staff_id, staff_name)`、`search_unpaid_invoices(session, query, limit)`、`PaymentDialog(issuance_id, parent, auto_record)` と `values()`、UI の `_search`/`_search_member`/`_result_table`/`_issue_receipt` は全タスクで一貫。
