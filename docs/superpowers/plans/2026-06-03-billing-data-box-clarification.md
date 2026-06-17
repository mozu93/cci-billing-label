# 「請求・領収書データ」中心化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「まとめて発行」を「請求・領収書データ（箱）」中心の用語・操作に整理し、件名（必須）・宛先空プレビュー・名簿エントリの登録日（新しい順・並べ替え可）を追加する。

**Architecture:** 既存の PyQt6 + SQLAlchemy(SQLite) 構成。`Project.name` を「件名」に転用（業務名は `category_id` で継続）。`ProjectMember` に `created_at` を1列追加（軽いマイグレーション）。プレビューは DB 非保存の一時 `Issuance` を組み立てて既存 PDF ジェネレータで生成する。UI 文言とテーブル列を変更。

**Tech Stack:** Python, PyQt6, SQLAlchemy, pytest / pytest-qt（`qtbot`・`memory_db`・`db_session` フィクスチャは `tests/conftest.py` 済み）。

参照仕様書：`docs/superpowers/specs/2026-06-03-billing-data-box-clarification-design.md`

---

## ファイル構成

| ファイル | 役割／変更 |
|---------|-----------|
| `app/database/models.py` | `ProjectMember.created_at` 追加 |
| `app/database/connection.py` | `_migrate` に `project_members.created_at` 追加 |
| `app/services/project_service.py` | `get_project_members(..., newest_first=False)` 追加 |
| `app/utils/pdf_helpers.py` | `build_preview_issuance` / `generate_preview` 追加 |
| `app/ui/project_form.py` | 件名フィールド（必須）、保存で `name=件名`、プレビュー（種別切替） |
| `app/ui/project_tab.py` | 一覧に「業務名」「件名」列 |
| `app/ui/batch_issuance_tab.py` | タブ名称変更 |
| `app/ui/project_member_panel.py` | 「登録日」列＋新しい順既定＋並べ替え |
| `app/ui/report_tab.py` / `app/ui/reissue_tab.py` | ヘッダ「名簿名」→「件名」 |

---

## Task 1: ProjectMember に登録日（created_at）を追加

**Files:**
- Modify: `app/database/models.py:138-152`
- Modify: `app/database/connection.py:13-26`
- Test: `tests/test_project_service.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_service.py` の末尾に追記：

```python
def test_roster_member_has_created_at(db_session):
    """名簿エントリに登録日時(created_at)が自動で入る。"""
    from app.services.project_service import create_project, add_roster_entries, get_project_members
    from datetime import datetime
    proj = create_project(db_session, name="2026 視察研修", category_id=None,
                          fiscal_year=2026, project_type="list")
    add_roster_entries(db_session, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(db_session, proj.id)[0]
    assert isinstance(pm.created_at, datetime)
```

- [ ] **Step 2: 失敗を確認**

Run: `python -m pytest tests/test_project_service.py::test_roster_member_has_created_at -v`
Expected: FAIL（`pm.created_at` が `None` または属性なし → AssertionError）

- [ ] **Step 3: モデルに列を追加**

`app/database/models.py` の `ProjectMember` の `sort_order` 行の直後（152行目付近）に追加：

```python
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
```

（`DateTime` と `datetime` は同ファイルで既に import 済み）

- [ ] **Step 4: 既存DB用マイグレーションを追加**

`app/database/connection.py` の `_migrate` 内、`project_members` の department 追加ブロックの直後に追記：

```python
        pm_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(project_members)"))}
        if "department" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN department VARCHAR(100) DEFAULT ''"))
            conn.commit()
        if "created_at" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN created_at DATETIME"))
            conn.commit()
```

- [ ] **Step 5: テストが通ることを確認**

Run: `python -m pytest tests/test_project_service.py::test_roster_member_has_created_at -v`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add app/database/models.py app/database/connection.py tests/test_project_service.py
git commit -m "feat: 名簿エントリに登録日(created_at)を追加"
```

---

## Task 2: get_project_members に「新しい順」オプションを追加

**Files:**
- Modify: `app/services/project_service.py:125-129`
- Test: `tests/test_project_service.py`

> 既定の並び順（sort_order）は既存テスト・発行処理が依存するため変更しない。新しい順は `newest_first=True` で明示する。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_service.py` に追記：

```python
def test_get_project_members_newest_first(db_session):
    """newest_first=True で登録日の新しい順に並ぶ。"""
    from datetime import datetime
    from app.services.project_service import create_project, get_project_members
    from app.database.models import ProjectMember
    proj = create_project(db_session, name="2026 視察研修", category_id=None,
                          fiscal_year=2026, project_type="list")
    old = ProjectMember(project_id=proj.id, organization_name="先に登録",
                        sort_order=0, created_at=datetime(2026, 6, 1, 9, 0, 0))
    new = ProjectMember(project_id=proj.id, organization_name="後で登録",
                        sort_order=1, created_at=datetime(2026, 6, 3, 9, 0, 0))
    db_session.add_all([old, new])
    db_session.commit()
    members = get_project_members(db_session, proj.id, newest_first=True)
    assert members[0].organization_name == "後で登録"
    assert members[1].organization_name == "先に登録"
```

- [ ] **Step 2: 失敗を確認**

Run: `python -m pytest tests/test_project_service.py::test_get_project_members_newest_first -v`
Expected: FAIL（`newest_first` 引数が無く TypeError、または順序が逆）

- [ ] **Step 3: 実装**

`app/services/project_service.py` の `get_project_members` を置き換え：

```python
def get_project_members(session: Session, project_id: int,
                        newest_first: bool = False) -> list[ProjectMember]:
    q = session.query(ProjectMember).filter_by(project_id=project_id)
    if newest_first:
        return q.order_by(ProjectMember.created_at.desc()).all()
    return q.order_by(ProjectMember.sort_order).all()
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python -m pytest tests/test_project_service.py::test_get_project_members_newest_first -v`
Expected: PASS

- [ ] **Step 5: 既存テストの回帰確認**

Run: `python -m pytest tests/test_project_service.py tests/test_report_service.py tests/test_issuance_service.py -q`
Expected: 全て PASS（既定順は不変）

- [ ] **Step 6: コミット**

```bash
git add app/services/project_service.py tests/test_project_service.py
git commit -m "feat: get_project_members に newest_first（新しい順）オプションを追加"
```

---

## Task 3: 宛先空プレビュー用の Issuance 生成（DB非保存）

**Files:**
- Modify: `app/utils/pdf_helpers.py`（末尾に追加）
- Test: `tests/test_pdf_preview.py`（新規）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pdf_preview.py` を新規作成：

```python
def test_build_preview_issuance(db_session):
    """プレビュー用Issuanceは宛先空・明細合計を持ち、DBに保存されない。"""
    from app.utils.pdf_helpers import build_preview_issuance
    from app.database.models import Issuance
    lines = [{"item_template_id": None, "item_name": "会費",
              "quantity": 2, "unit": "口", "unit_price": 3000, "tax_rate": 0}]
    iss = build_preview_issuance(lines, "invoice")
    assert iss.recipient_organization == ""
    assert iss.recipient_name == ""
    assert iss.doc_type == "invoice"
    assert int(iss.amount) == 6000
    assert len(iss.lines) == 1
    assert iss.lines[0].item_name == "会費"
    # セッションに追加していない＝永続化されていない
    assert db_session.query(Issuance).count() == 0
```

- [ ] **Step 2: 失敗を確認**

Run: `python -m pytest tests/test_pdf_preview.py::test_build_preview_issuance -v`
Expected: FAIL（`build_preview_issuance` が未定義 → ImportError）

- [ ] **Step 3: 実装**

`app/utils/pdf_helpers.py` の末尾に追加：

```python
def build_preview_issuance(lines_data: list[dict], doc_type: str):
    """宛先空のプレビュー用 Issuance（セッション未追加・非永続）を組み立てる。"""
    from datetime import datetime
    from app.database.models import Issuance, IssuanceLine
    lines = []
    total = 0
    for ld in lines_data:
        line_total = int(ld["unit_price"]) * int(ld["quantity"])
        total += line_total
        lines.append(IssuanceLine(
            item_template_id=ld.get("item_template_id"),
            item_name=ld["item_name"],
            quantity=ld["quantity"],
            unit=ld["unit"],
            unit_price=ld["unit_price"],
            tax_rate=ld["tax_rate"],
            line_total=line_total,
        ))
    return Issuance(
        project_id=None, project_member_id=None,
        recipient_organization="", recipient_name="",
        doc_type=doc_type, doc_number="（プレビュー）",
        status="プレビュー", amount=total,
        issued_at=datetime.now(), lines=lines,
    )


def generate_preview(lines_data: list[dict], doc_type: str, session) -> str | None:
    """プレビュー用PDFを一時ファイルに生成して開く（DBには書き込まない）。"""
    import os
    company, bank = get_company_and_bank(session)
    if not company:
        return None
    seal = get_default_seal(session, company)
    output_dir = get_pdf_output_dir()
    path = os.path.join(output_dir, "_preview.pdf")
    issuance = build_preview_issuance(lines_data, doc_type)
    if doc_type == "invoice":
        from app.services.pdf.invoice_pdf import generate_invoice_pdf
        generate_invoice_pdf(issuance, company, path, bank, seal_image=seal)
    else:
        from app.services.pdf.receipt_pdf import generate_receipt_pdf
        generate_receipt_pdf(issuance, company, path, seal_image=seal)
    from app.services.print_service import open_pdf
    open_pdf(path)
    return path
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python -m pytest tests/test_pdf_preview.py::test_build_preview_issuance -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add app/utils/pdf_helpers.py tests/test_pdf_preview.py
git commit -m "feat: 宛先空プレビュー用のIssuance生成とPDFプレビューを追加"
```

---

## Task 4: 請求・領収書データ登録に「件名」（必須）を追加

**Files:**
- Modify: `app/ui/project_form.py:29-50`（フォーム）, `:163-219`（load/save）
- Test: `tests/test_project_form.py`（新規）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_form.py` を新規作成：

```python
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidgetItem


def _seed_category_and_template():
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    s = get_session()
    cat = create_category(s, "不動産部会")
    t = create_item_template(s, cat.id, "視察研修会参加費", 5000, "人", 0, "receipt", "")
    ids = (cat.id, t.id)
    s.close()
    return ids


def _select_category(dlg, cat_id):
    idx = next(i for i in range(dlg._category.count())
               if dlg._category.itemData(i) == cat_id)
    dlg._category.setCurrentIndex(idx)


def _add_template(dlg, tmpl_id):
    item = QListWidgetItem("x")
    item.setData(Qt.ItemDataRole.UserRole, tmpl_id)
    dlg._selected_list.addItem(item)


def test_project_form_saves_title_as_name(qtbot, memory_db):
    cat_id, t_id = _seed_category_and_template()
    from app.ui.project_form import ProjectFormDialog
    dlg = ProjectFormDialog()
    qtbot.addWidget(dlg)
    _select_category(dlg, cat_id)
    dlg._title.setText("2026 視察研修会参加費")
    _add_template(dlg, t_id)
    dlg._save()

    from app.database.connection import get_session
    from app.services.project_service import get_projects
    s = get_session()
    names = [p.name for p in get_projects(s)]
    s.close()
    assert "2026 視察研修会参加費" in names


def test_project_form_requires_title(qtbot, memory_db, monkeypatch):
    cat_id, t_id = _seed_category_and_template()
    import app.ui.project_form as pf
    monkeypatch.setattr(pf.QMessageBox, "warning", lambda *a, **k: None)
    dlg = pf.ProjectFormDialog()
    qtbot.addWidget(dlg)
    _select_category(dlg, cat_id)
    _add_template(dlg, t_id)
    # 件名は空のまま
    dlg._save()

    from app.database.connection import get_session
    from app.services.project_service import get_projects
    s = get_session()
    count = len(get_projects(s))
    s.close()
    assert count == 0  # 件名未入力なので作成されない
```

- [ ] **Step 2: 失敗を確認**

Run: `python -m pytest tests/test_project_form.py -v`
Expected: FAIL（`dlg._title` が無く AttributeError）

- [ ] **Step 3: 件名フィールドを追加**

`app/ui/project_form.py` の `_build` 内、`self._category` 関連を組み立てている箇所に件名を追加。`form.addRow("業務名", cat_row)` の直後に挿入：

```python
        form.addRow("業務名", cat_row)
        self._title = QLineEdit()
        self._title.setPlaceholderText("件名（例：2026 視察研修会参加費）")
        form.addRow("件名", self._title)
        form.addRow("年度", self._fiscal_year)
```

（`QLineEdit` は既に import 済み）

- [ ] **Step 4: load で件名を表示**

`_load` 内、`self._fiscal_year.setValue(proj.fiscal_year)` の直前に追加：

```python
            self._title.setText(proj.name or "")
            self._fiscal_year.setValue(proj.fiscal_year)
```

- [ ] **Step 5: save で件名を必須化し name に保存**

`_save` の冒頭バリデーション部を置き換え：

```python
    def _save(self):
        cat_id = self._category.currentData()
        business = self._category.currentText().strip()
        title = self._title.text().strip()
        if not business or cat_id is None:
            QMessageBox.warning(self, "入力エラー", "業務名を選択してください。")
            return
        if not title:
            QMessageBox.warning(self, "入力エラー", "件名を入力してください。")
            return
        if self._selected_list.count() == 0:
            QMessageBox.warning(self, "入力エラー", "テンプレートを1つ以上選択してください。")
            return
        session = get_session()
        try:
            if self._project_id is None:
                proj = create_project(
                    session, name=title,
                    category_id=cat_id,
                    fiscal_year=self._fiscal_year.value(),
                    project_type="list",
                    notes=self._notes.toPlainText().strip()
                )
                for i in range(self._selected_list.count()):
                    tmpl_id = self._selected_list.item(i).data(Qt.ItemDataRole.UserRole)
                    add_template_to_project(session, proj.id, tmpl_id, sort_order=i)
            else:
                proj = get_project_by_id(session, self._project_id)
                proj.name = title
                proj.category_id = cat_id
                proj.fiscal_year = self._fiscal_year.value()
                proj.notes = self._notes.toPlainText().strip()
                from app.database.models import ProjectTemplate
                session.query(ProjectTemplate).filter_by(project_id=proj.id).delete()
                session.commit()
                for i in range(self._selected_list.count()):
                    tmpl_id = self._selected_list.item(i).data(Qt.ItemDataRole.UserRole)
                    add_template_to_project(session, proj.id, tmpl_id, sort_order=i)
        finally:
            session.close()
        self.accept()
```

- [ ] **Step 6: ダイアログ表題を更新**

`__init__` の `setWindowTitle` を変更：

```python
        self.setWindowTitle("請求・領収書データの登録" if project_id is None
                            else "請求・領収書データの編集")
```

- [ ] **Step 7: テストが通ることを確認**

Run: `python -m pytest tests/test_project_form.py -v`
Expected: PASS（2件）

- [ ] **Step 8: コミット**

```bash
git add app/ui/project_form.py tests/test_project_form.py
git commit -m "feat: 請求・領収書データ登録に件名(必須)を追加しnameに保存"
```

---

## Task 5: 登録ダイアログに宛先空プレビュー（種別切替）を追加

**Files:**
- Modify: `app/ui/project_form.py`（_build にプレビュー行、メソッド `_preview` 追加）
- Test: `tests/test_project_form.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_form.py` に追記：

```python
def test_project_form_preview_uses_selected_templates(qtbot, memory_db, monkeypatch):
    cat_id, t_id = _seed_category_and_template()
    captured = {}
    import app.utils.pdf_helpers as ph
    monkeypatch.setattr(ph, "generate_preview",
                        lambda lines, doc_type, session: captured.update(
                            lines=lines, doc_type=doc_type) or "ok")
    from app.ui.project_form import ProjectFormDialog
    dlg = ProjectFormDialog()
    qtbot.addWidget(dlg)
    _select_category(dlg, cat_id)
    _add_template(dlg, t_id)
    # 種別＝領収書を選ぶ
    ridx = next(i for i in range(dlg._doc_type.count())
                if dlg._doc_type.itemData(i) == "receipt")
    dlg._doc_type.setCurrentIndex(ridx)
    dlg._preview()

    assert captured["doc_type"] == "receipt"
    assert len(captured["lines"]) == 1
    assert captured["lines"][0]["item_name"] == "視察研修会参加費"
    assert int(captured["lines"][0]["unit_price"]) == 5000
```

- [ ] **Step 2: 失敗を確認**

Run: `python -m pytest tests/test_project_form.py::test_project_form_preview_uses_selected_templates -v`
Expected: FAIL（`dlg._doc_type` / `dlg._preview` が無い）

- [ ] **Step 3: プレビュー行を UI に追加**

`app/ui/project_form.py` の `_build` 内、保存ボタン行（`btn_row = QHBoxLayout()`）の直前に追加：

```python
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
```

（`QComboBox`・`QLabel`・`QPushButton` は既に import 済み）

- [ ] **Step 4: `_preview` メソッドを追加**

`_save` メソッドの直前に追加：

```python
    def _preview(self):
        if self._selected_list.count() == 0:
            QMessageBox.warning(self, "プレビュー不可",
                                "請求項目テンプレートを1つ以上選択してください。")
            return
        from app.database.models import ItemTemplate
        from app.utils import pdf_helpers
        session = get_session()
        try:
            lines_data = []
            for i in range(self._selected_list.count()):
                tmpl_id = self._selected_list.item(i).data(Qt.ItemDataRole.UserRole)
                t = session.get(ItemTemplate, tmpl_id)
                if t is None:
                    continue
                lines_data.append({
                    "item_template_id": t.id,
                    "item_name": t.name,
                    "quantity": 1,
                    "unit": t.unit,
                    "unit_price": int(t.unit_price),
                    "tax_rate": t.tax_rate,
                })
            try:
                pdf_helpers.generate_preview(
                    lines_data, self._doc_type.currentData(), session)
            except Exception as e:
                QMessageBox.critical(self, "プレビューエラー", str(e))
        finally:
            session.close()
```

- [ ] **Step 5: テストが通ることを確認**

Run: `python -m pytest tests/test_project_form.py -v`
Expected: PASS（3件）

- [ ] **Step 6: コミット**

```bash
git add app/ui/project_form.py tests/test_project_form.py
git commit -m "feat: 請求・領収書データ登録に宛先空プレビュー(種別切替)を追加"
```

---

## Task 6: 一覧に「業務名」「件名」列を表示

**Files:**
- Modify: `app/ui/project_tab.py:56-99`
- Test: `tests/test_project_tab.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_tab.py` に追記：

```python
def test_project_tab_shows_business_and_title_columns(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.project_service import create_project
    s = get_session()
    cat = create_category(s, "不動産部会")
    create_project(s, name="2026 視察研修会参加費", category_id=cat.id,
                   fiscal_year=2026, project_type="list")
    s.close()

    from app.ui.project_tab import ProjectTab
    w = ProjectTab()
    qtbot.addWidget(w)
    headers = [w._table.horizontalHeaderItem(i).text()
               for i in range(w._table.columnCount())]
    assert headers[0] == "業務名"
    assert headers[1] == "件名"

    cells = []
    for r in range(w._table.rowCount()):
        cells.append((w._table.item(r, 0).text(), w._table.item(r, 1).text()))
    assert ("不動産部会", "2026 視察研修会参加費") in cells
```

- [ ] **Step 2: 失敗を確認**

Run: `python -m pytest tests/test_project_tab.py::test_project_tab_shows_business_and_title_columns -v`
Expected: FAIL（列が5つで「業務名」ヘッダが無い）

- [ ] **Step 3: テーブル定義を変更**

`app/ui/project_tab.py` の `_build` 内、テーブル生成部を置き換え：

```python
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["業務名", "件名", "状態", "全件", "発行済", "未発行"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
```

- [ ] **Step 4: 行データに業務名を加える**

`_load` を置き換え：

```python
    def _load(self):
        year = self._year_combo.currentData()
        status = self._status_combo.currentData()
        session = get_session()
        try:
            from app.database.models import Category
            cat_name = {c.id: c.name for c in session.query(Category).all()}
            projects = get_projects(session, fiscal_year=year, status=status)
            self._table.setRowCount(0)
            for proj in projects:
                p = get_project_progress(session, proj.id)
                row = self._table.rowCount()
                self._table.insertRow(row)
                for col, val in enumerate([
                    cat_name.get(proj.category_id, ""), proj.name, proj.status,
                    str(p["total"]), str(p["issued"]), str(p["pending"])
                ]):
                    item = QTableWidgetItem(val)
                    item.setData(Qt.ItemDataRole.UserRole, proj.id)
                    self._table.setItem(row, col, item)
        finally:
            session.close()
```

（`_on_select` と `_selected_project_id` は `item(row, 0)` の UserRole を読むが、列0にも project_id を入れているため変更不要）

- [ ] **Step 5: 新規登録ボタンの名称を変更**

`app/ui/project_tab.py` の `_build` 内、`btn_add = QPushButton("＋ 新規名簿登録")` を変更：

```python
        btn_add = QPushButton("＋ 新規 請求・領収書データ")
```

- [ ] **Step 6: テストが通ることを確認**

Run: `python -m pytest tests/test_project_tab.py -v`
Expected: PASS

- [ ] **Step 7: コミット**

```bash
git add app/ui/project_tab.py tests/test_project_tab.py
git commit -m "feat: 請求・領収書データ一覧に業務名・件名列とボタン名変更"
```

---

## Task 7: 「まとめて発行」のタブ名称を変更

**Files:**
- Modify: `app/ui/batch_issuance_tab.py:15-17`
- Test: `tests/test_batch_issuance_tab.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_batch_issuance_tab.py` を確認し、末尾に追記（既存テストの形式に合わせる）：

```python
def test_batch_issuance_tab_titles_renamed(qtbot, memory_db):
    from PyQt6.QtWidgets import QTabWidget
    from app.ui.batch_issuance_tab import BatchIssuanceTab
    w = BatchIssuanceTab()
    qtbot.addWidget(w)
    inner = w.findChild(QTabWidget)
    titles = [inner.tabText(i) for i in range(inner.count())]
    assert "請求・領収書データ" in titles
    assert "登録データから発行" in titles
    assert "名簿登録" not in titles
```

- [ ] **Step 2: 失敗を確認**

Run: `python -m pytest tests/test_batch_issuance_tab.py::test_batch_issuance_tab_titles_renamed -v`
Expected: FAIL（旧タブ名のまま）

- [ ] **Step 3: タブ名を変更**

`app/ui/batch_issuance_tab.py` の `addTab` 3行を置き換え：

```python
        inner.addTab(ProjectTab(), "請求・領収書データ")
        inner.addTab(IssuanceFromProjectWidget(), "登録データから発行")
        inner.addTab(PaymentManagementWidget(), "入金管理")
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python -m pytest tests/test_batch_issuance_tab.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add app/ui/batch_issuance_tab.py tests/test_batch_issuance_tab.py
git commit -m "feat: まとめて発行のタブ名を請求・領収書データ基準に変更"
```

---

## Task 8: 名簿パネルに「登録日」列・新しい順・並べ替え

**Files:**
- Modify: `app/ui/project_member_panel.py:143-174`
- Test: `tests/test_project_member_panel.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_member_panel.py` に追記：

```python
def test_member_panel_has_registration_date_column(qtbot, memory_db):
    from app.ui.project_member_panel import ProjectMemberPanel
    from app.services.project_service import create_project, add_roster_entries
    from app.database.connection import get_session
    s = get_session()
    proj = create_project(s, name="2026 視察研修", category_id=None,
                          fiscal_year=2026, project_type="list")
    add_roster_entries(s, proj.id, [{"organization_name": "○○商事"}])
    pid = proj.id
    s.close()

    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    headers = [panel._table.horizontalHeaderItem(i).text()
               for i in range(panel._table.columnCount())]
    assert "登録日" in headers
    assert panel._table.isSortingEnabled()
```

- [ ] **Step 2: 失敗を確認**

Run: `python -m pytest tests/test_project_member_panel.py::test_member_panel_has_registration_date_column -v`
Expected: FAIL（「登録日」列なし）

- [ ] **Step 3: テーブル定義を変更**

`app/ui/project_member_panel.py` の `_build` 内、テーブル生成部を置き換え：

```python
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["事業所名", "代表者名", "メール", "電話", "登録日"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._edit_entry)
```

- [ ] **Step 4: `_load` を新しい順＋登録日表示に変更**

`_load` を置き換え：

```python
    def _load(self):
        session = get_session()
        try:
            pms = get_project_members(session, self._project_id, newest_first=True)
        finally:
            session.close()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for pm in pms:
            row = self._table.rowCount()
            self._table.insertRow(row)
            reg = pm.created_at.strftime("%Y/%m/%d") if pm.created_at else ""
            vals = [
                pm.organization_name or "",
                pm.representative_name or "",
                pm.email or "",
                pm.phone or "",
                reg,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, pm.id)
                self._table.setItem(row, col, item)
        self._table.setSortingEnabled(True)
        self._count_label.setText(f"{len(pms)} 件")
```

（`QHeaderView` は既に import 済み。登録日は `YYYY/MM/DD` 形式で辞書順＝日付順に一致するため列クリックで正しく並ぶ）

- [ ] **Step 5: テストが通ることを確認**

Run: `python -m pytest tests/test_project_member_panel.py -v`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add app/ui/project_member_panel.py tests/test_project_member_panel.py
git commit -m "feat: 名簿パネルに登録日列・新しい順・並べ替えを追加"
```

---

## Task 9: レポート／再発行のヘッダ「名簿名」→「件名」

**Files:**
- Modify: `app/ui/report_tab.py:113-141`, `app/ui/reissue_tab.py:60-62`
- Test: `tests/test_report_header.py`（新規）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_report_header.py` を新規作成：

```python
def test_report_widgets_use_kenmei_header(qtbot, memory_db):
    from app.ui.report_tab import (
        UnpaidReportWidget, PaymentReportWidget, ProjectSummaryWidget)
    for cls in (UnpaidReportWidget, PaymentReportWidget, ProjectSummaryWidget):
        w = cls()
        qtbot.addWidget(w)
        assert "件名" in w.HEADERS
        assert "名簿名" not in w.HEADERS


def test_reissue_tab_uses_kenmei_header(qtbot, memory_db):
    from app.ui.reissue_tab import ReissueWidget
    w = ReissueWidget()
    qtbot.addWidget(w)
    headers = [w._table.horizontalHeaderItem(i).text()
               for i in range(w._table.columnCount())]
    assert "件名" in headers
    assert "名簿名" not in headers
```

- [ ] **Step 2: 失敗を確認**

Run: `python -m pytest tests/test_report_header.py -v`
Expected: FAIL（ヘッダが「名簿名」のまま）

- [ ] **Step 3: report_tab のヘッダを変更**

`app/ui/report_tab.py` の3クラスの `HEADERS` を以下に変更（`"名簿名"`→`"件名"`、`KEYS` は変更しない）：

```python
# UnpaidReportWidget
    HEADERS = ["発行番号", "件名", "年度", "事業所名", "代表者名", "品目",
               "会員番号", "金額", "状態"]

# PaymentReportWidget
    HEADERS = ["入金日", "発行番号", "件名", "年度", "宛先", "但し書き",
               "入金額", "入金方法", "担当者"]

# ProjectSummaryWidget
    HEADERS = ["年度", "件名", "全件", "発行済", "支払済", "未発行", "総額", "入金額"]
```

- [ ] **Step 4: reissue_tab のヘッダを変更**

`app/ui/reissue_tab.py` の `_build` 内、`setHorizontalHeaderLabels` を変更：

```python
        self._table.setHorizontalHeaderLabels(
            ["発行番号", "件名", "宛先", "金額", "種別", "状態", "発行日"])
```

- [ ] **Step 5: テストが通ることを確認**

Run: `python -m pytest tests/test_report_header.py -v`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add app/ui/report_tab.py app/ui/reissue_tab.py tests/test_report_header.py
git commit -m "feat: レポート・再発行のヘッダを名簿名から件名に変更"
```

---

## 最終確認

- [ ] **全テスト実行**

Run: `python -m pytest -q`
Expected: 全て PASS

- [ ] **アプリ起動スモーク（任意）**

「まとめて発行」→「請求・領収書データ」で新規登録（件名必須・プレビュー）→ 名簿に宛先を追加し登録日が新しい順で並ぶことを目視確認。
