# 領収書発行済みなら請求書を「無効」表示にする Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「登録データから発行」で、請求書が未発行かつ領収書が発行済みの事業所の請求書を「無効」と表示し、請求書の発行対象から外す。

**Architecture:** データは作らず、`inv（最新invoice）が無く rcp（最新receipt）がある` を「無効」と動的判定する。`app/ui/issuance_from_project.py` の表示・フィルタ・個別発行と、`app/services/pdf/batch_pdf.py` の全員発行に、この条件を反映する。

**Tech Stack:** Python, PyQt6, SQLAlchemy, pytest（`qtbot` / `memory_db` / `db_session` フィクスチャ）。

参照spec: `docs/superpowers/specs/2026-06-06-invoice-voided-when-receipt-issued-design.md`

---

## File Structure

- Modify: `app/ui/issuance_from_project.py` — `_load_members`（表示とフィルタ）、`_issue_checked`（個別発行のスキップ）。
- Modify: `app/services/pdf/batch_pdf.py` — `generate_batch_pdf`（全員発行のスキップ）。
- Modify: `tests/test_issuance_from_project.py` — UIテスト追加。
- Modify: `tests/test_batch_pdf.py` — サービステスト追加。

判定は全箇所で同一: 「請求書 invoice が無く、領収書 receipt がある」＝無効。

---

## Task 1: 請求書列に「無効」を表示する

**Files:**
- Modify: `app/ui/issuance_from_project.py`（`_load_members`）
- Test: `tests/test_issuance_from_project.py`

UIテストのseedヘルパ `_select_project` は既にこのファイルにある（前機能で追加済み）。Task 1 では新しいインラインseedを使う。

- [ ] **Step 1: Write the failing test**

`tests/test_issuance_from_project.py` 末尾に追記:

```python
def test_invoice_column_shows_voided_when_only_receipt(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued
    from app.ui.issuance_from_project import (
        IssuanceFromProjectWidget, COL_ORG, COL_INV,
    )
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
    # ○○商事：領収書のみ発行（請求書なし）→ 無効
    rcp = create_issuance_for_member(s, proj.id, pms[0].id, "○○商事", "",
                                     "receipt", 2026, 5)
    mark_as_issued(s, rcp.id, None, "田中", "窓口手渡し")
    # △△工業：請求書発行済み
    inv = create_issuance_for_member(s, proj.id, pms[1].id, "△△工業", "",
                                     "invoice", 2026, 5)
    mark_as_issued(s, inv.id, None, "田中", "窓口手渡し")
    proj_id = proj.id
    s.close()

    w = IssuanceFromProjectWidget()
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    w._filter_combo.setCurrentIndex(1)  # すべて
    w._load_members()

    rows = {}
    for r in range(w._table.rowCount()):
        rows[w._table.item(r, COL_ORG).text()] = w._table.item(r, COL_INV).text()
    assert rows["○○商事"] == "無効"          # 領収書のみ → 請求書は無効
    assert "発行済" in rows["△△工業"]        # 請求書発行済みは従来どおり
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_issuance_from_project.py::test_invoice_column_shows_voided_when_only_receipt -v`
Expected: FAIL（○○商事の請求書列が "未発行" のままで "無効" にならない）

- [ ] **Step 3: Implement**

`app/ui/issuance_from_project.py` の `_load_members` 内、member ループを編集する。

現在（該当部分、`_cell_text` 取得とフィルタ前後）:
```python
                # 「未発行のみ」は選択中の書類種別を基準にする
                sel = inv if doc_type == "invoice" else rcp
                sel_status = sel.status if sel else "未発行"
                if not show_all and sel_status in ("発行済み", "支払済み"):
                    continue
                if query:
                    targets = [
                        pm.organization_name or "",
                        pm.representative_name or "",
                        pm.organization_kana or "",
                    ]
                    if not any(query in t.lower() for t in targets):
                        continue
                pm_data.append((
                    pm.id, pm,
                    self._cell_text(inv), self._cell_text(rcp),
                    inv.id if inv else None, rcp.id if rcp else None,
                ))
```

新:
```python
                # 請求書未発行かつ領収書発行済み → 請求書は「無効」
                voided = inv is None and rcp is not None
                # 「未発行のみ」は選択中の書類種別を基準にする
                sel = inv if doc_type == "invoice" else rcp
                sel_status = sel.status if sel else "未発行"
                if not show_all and sel_status in ("発行済み", "支払済み"):
                    continue
                if query:
                    targets = [
                        pm.organization_name or "",
                        pm.representative_name or "",
                        pm.organization_kana or "",
                    ]
                    if not any(query in t.lower() for t in targets):
                        continue
                inv_text = "無効" if voided else self._cell_text(inv)
                pm_data.append((
                    pm.id, pm,
                    inv_text, self._cell_text(rcp),
                    inv.id if inv else None, rcp.id if rcp else None,
                ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_issuance_from_project.py::test_invoice_column_shows_voided_when_only_receipt -v`
Expected: PASS

- [ ] **Step 5: Run the file's full tests**

Run: `python -m pytest tests/test_issuance_from_project.py -v`
Expected: PASS（既存テストも緑）

- [ ] **Step 6: Commit**

```bash
git add app/ui/issuance_from_project.py tests/test_issuance_from_project.py
git commit -m "feat: 登録データから発行で領収書のみの事業所の請求書を無効表示"
```

---

## Task 2: 「未発行のみ」フィルタで無効の請求書を隠す

**Files:**
- Modify: `app/ui/issuance_from_project.py`（`_load_members` のフィルタ条件）
- Test: `tests/test_issuance_from_project.py`

Task 1 で `voided` 変数が `_load_members` のループ内に導入済み。本タスクはフィルタ条件にそれを足すだけ。

- [ ] **Step 1: Write the failing test**

`tests/test_issuance_from_project.py` 末尾に追記:

```python
def test_unissued_filter_hides_voided_invoice(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued
    from app.ui.issuance_from_project import IssuanceFromProjectWidget, COL_ORG
    s = get_session()
    cat = create_category(s, "青年部")
    tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(s, "2026 青年部会費", cat.id, 2026, "list")
    add_template_to_project(s, proj.id, tmpl.id)
    add_roster_entries(s, proj.id, [
        {"organization_name": "○○商事"},   # 領収書のみ → 請求書無効
        {"organization_name": "××物産"},   # 何も発行なし → 純粋に未発行
    ])
    pms = get_project_members(s, proj.id)
    rcp = create_issuance_for_member(s, proj.id, pms[0].id, "○○商事", "",
                                     "receipt", 2026, 5)
    mark_as_issued(s, rcp.id, None, "田中", "窓口手渡し")
    proj_id = proj.id
    s.close()

    w = IssuanceFromProjectWidget()
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    # 書類種別=請求書、未発行のみ
    idx_inv = next(i for i in range(w._doctype_combo.count())
                   if w._doctype_combo.itemData(i) == "invoice")
    w._filter_combo.setCurrentIndex(0)  # 未発行のみ
    w._doctype_combo.setCurrentIndex(idx_inv)
    w._load_members()

    orgs = [w._table.item(r, COL_ORG).text() for r in range(w._table.rowCount())]
    assert "○○商事" not in orgs   # 無効は対応不要なので出ない
    assert "××物産" in orgs       # 純粋な未発行は出る
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_issuance_from_project.py::test_unissued_filter_hides_voided_invoice -v`
Expected: FAIL（○○商事が「未発行のみ」に出てしまう）

- [ ] **Step 3: Implement**

`app/ui/issuance_from_project.py` の `_load_members` のフィルタ条件を変更する。

現在（Task 1 適用後）:
```python
                if not show_all and sel_status in ("発行済み", "支払済み"):
                    continue
```

新:
```python
                hide_issued = sel_status in ("発行済み", "支払済み")
                hide_voided = doc_type == "invoice" and voided
                if not show_all and (hide_issued or hide_voided):
                    continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_issuance_from_project.py::test_unissued_filter_hides_voided_invoice -v`
Expected: PASS

- [ ] **Step 5: Run the file's full tests**

Run: `python -m pytest tests/test_issuance_from_project.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/ui/issuance_from_project.py tests/test_issuance_from_project.py
git commit -m "feat: 未発行のみフィルタで無効の請求書を非表示にする"
```

---

## Task 3: 個別の請求書発行で無効の行をスキップ

**Files:**
- Modify: `app/ui/issuance_from_project.py`（`_issue_checked`）
- Test: `tests/test_issuance_from_project.py`

- [ ] **Step 1: Write the failing test**

`tests/test_issuance_from_project.py` 末尾に追記:

```python
def test_issue_checked_skips_voided_invoice(qtbot, memory_db):
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued
    from app.ui.issuance_from_project import IssuanceFromProjectWidget, COL_CHK
    from app.database.models import Issuance
    from PyQt6.QtCore import Qt
    s = get_session()
    cat = create_category(s, "青年部")
    tmpl = create_item_template(s, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(s, "2026 青年部会費", cat.id, 2026, "list")
    add_template_to_project(s, proj.id, tmpl.id)
    add_roster_entries(s, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(s, proj.id)[0]
    rcp = create_issuance_for_member(s, proj.id, pm.id, "○○商事", "",
                                     "receipt", 2026, 5)
    mark_as_issued(s, rcp.id, None, "田中", "窓口手渡し")
    proj_id, pm_id = proj.id, pm.id
    s.close()

    w = IssuanceFromProjectWidget()
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    # 書類種別=請求書、すべて表示で○○商事（無効）を出す
    idx_inv = next(i for i in range(w._doctype_combo.count())
                   if w._doctype_combo.itemData(i) == "invoice")
    w._doctype_combo.setCurrentIndex(idx_inv)
    w._filter_combo.setCurrentIndex(1)  # すべて
    w._load_members()
    assert w._table.rowCount() == 1
    # 行をチェックして請求書を発行
    w._table.item(0, COL_CHK).setCheckState(Qt.CheckState.Checked)
    w._issue_checked()

    # 無効なので請求書は作られない
    s = get_session()
    cnt = (s.query(Issuance)
           .filter_by(project_member_id=pm_id, doc_type="invoice")
           .count())
    s.close()
    assert cnt == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_issuance_from_project.py::test_issue_checked_skips_voided_invoice -v`
Expected: FAIL（請求書が新規作成され count == 1 になる）

- [ ] **Step 3: Implement**

`app/ui/issuance_from_project.py` の `_issue_checked` のループ先頭を変更する。

現在:
```python
            for pm_id, invoice_id, receipt_id in targets:
                issuance_id = invoice_id if doc_type == "invoice" else receipt_id
```

新:
```python
            for pm_id, invoice_id, receipt_id in targets:
                # 領収書発行済みで請求書未発行＝無効。請求書は発行しない
                if doc_type == "invoice" and invoice_id is None and receipt_id is not None:
                    continue
                issuance_id = invoice_id if doc_type == "invoice" else receipt_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_issuance_from_project.py::test_issue_checked_skips_voided_invoice -v`
Expected: PASS

- [ ] **Step 5: Run the file's full tests**

Run: `python -m pytest tests/test_issuance_from_project.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/ui/issuance_from_project.py tests/test_issuance_from_project.py
git commit -m "feat: 個別の請求書発行で無効の行をスキップ"
```

---

## Task 4: 全員に請求書を発行で無効の事業所をスキップ

**Files:**
- Modify: `app/services/pdf/batch_pdf.py`（`generate_batch_pdf`）
- Test: `tests/test_batch_pdf.py`

`generate_batch_pdf` は `_issue_all`（当画面）からのみ呼ばれる。

- [ ] **Step 1: Inspect existing test for company seeding**

`tests/test_batch_pdf.py` を読み、`generate_batch_pdf` を呼ぶ既存テスト（前機能で追加した `test_batch_pdf_invoice_not_reuse_existing_receipt` 等）が company / bank をどうseedし `tmp_path` をどう使うかを確認する。同じ方式を流用する。

- [ ] **Step 2: Write the failing test**

`tests/test_batch_pdf.py` 末尾に、既存テストと同じ company seed 方式で追記する（company/bank 生成は既存テストの書き方に合わせること）:

```python
def test_batch_pdf_invoice_skips_voided_member(db_session, tmp_path):
    """請求書未発行・領収書発行済みの事業所は請求書を作らずスキップする。"""
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued
    from app.services.pdf.batch_pdf import generate_batch_pdf
    from app.database.models import Issuance, CompanySettings

    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "会費", 5000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事"},   # 領収書のみ → 無効
        {"organization_name": "××物産"},   # 何もなし → 発行される
    ])
    pms = get_project_members(db_session, proj.id)
    rcp = create_issuance_for_member(db_session, proj.id, pms[0].id, "○○商事", "",
                                     "receipt", 2026, 5)
    mark_as_issued(db_session, rcp.id, None, "田中", "窓口手渡し")

    company = CompanySettings(name="テスト商工会")
    db_session.add(company)
    db_session.commit()

    generate_batch_pdf(db_session, proj.id, company, str(tmp_path),
                       None, doc_type="invoice")

    inv_void = (db_session.query(Issuance)
                .filter_by(project_member_id=pms[0].id, doc_type="invoice")
                .count())
    inv_normal = (db_session.query(Issuance)
                  .filter_by(project_member_id=pms[1].id, doc_type="invoice")
                  .count())
    assert inv_void == 0      # 無効の事業所は請求書を作らない
    assert inv_normal == 1    # 通常の事業所は請求書を作る
```

注: 上の `CompanySettings(name=...)` は最小例。`tests/test_batch_pdf.py` の既存テストが company を別の方法（必須カラムを埋める等）で作っているなら、その方式に合わせること（PDF生成が company の項目を参照するため）。

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_batch_pdf.py::test_batch_pdf_invoice_skips_voided_member -v`
Expected: FAIL（○○商事に請求書が作られ inv_void == 1 になる）

- [ ] **Step 4: Implement**

`app/services/pdf/batch_pdf.py` の `generate_batch_pdf` の member ループ、`iss is None` 分岐に「請求書発行時、領収書が既にあればスキップ」を追加する。

現在:
```python
    for pm in pms:
        iss = (session.query(Issuance)
               .filter_by(project_member_id=pm.id, doc_type=doc_type)
               .order_by(Issuance.created_at.desc())
               .first())
        is_new = False
        if iss is None:
            if not pm.organization_name and not pm.representative_name:
                continue
            iss = create_issuance_for_member(
                session, project_id=project_id,
                project_member_id=pm.id,
                recipient_organization=pm.organization_name,
                recipient_name=pm.representative_name,
                doc_type=doc_type,
                fiscal_year=today.year, month=today.month,
            )
            is_new = True
```

新:
```python
    for pm in pms:
        iss = (session.query(Issuance)
               .filter_by(project_member_id=pm.id, doc_type=doc_type)
               .order_by(Issuance.created_at.desc())
               .first())
        is_new = False
        if iss is None:
            if not pm.organization_name and not pm.representative_name:
                continue
            # 請求書発行時、領収書が既にある＝請求書は無効。スキップ
            if doc_type == "invoice":
                has_receipt = (session.query(Issuance)
                               .filter_by(project_member_id=pm.id,
                                          doc_type="receipt")
                               .first() is not None)
                if has_receipt:
                    continue
            iss = create_issuance_for_member(
                session, project_id=project_id,
                project_member_id=pm.id,
                recipient_organization=pm.organization_name,
                recipient_name=pm.representative_name,
                doc_type=doc_type,
                fiscal_year=today.year, month=today.month,
            )
            is_new = True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_batch_pdf.py::test_batch_pdf_invoice_skips_voided_member -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS（全テスト）

- [ ] **Step 7: Commit**

```bash
git add app/services/pdf/batch_pdf.py tests/test_batch_pdf.py
git commit -m "feat: 全員に請求書を発行で領収書発行済みの事業所をスキップ"
```

---

## Task 5: 手動確認

- [ ] **Step 1: アプリを起動して確認**

Run: `python -m app.main`（または既存の起動手順）
確認手順:
1. まとめて発行 ＞「登録データから発行」で、ある事業所に**領収書だけ**を発行する（請求書は出さない）。
2. 書類種別=請求書にして一覧を見ると、その事業所の請求書列が「無効」と表示される。
3. 書類種別=請求書・表示=「未発行のみ」にすると、その事業所が一覧に出ないことを確認。
4. その事業所をチェックして「選択行に請求書を発行」しても、請求書が発行されない（無効のまま）ことを確認。
5. 「全員に請求書を発行」しても、その事業所には請求書が作られないことを確認。

---

## Self-Review

- **Spec coverage:**
  - 判定（invなし & rcpあり）→ Task 1 の `voided`。全タスクで同条件を使用。
  - 請求書列「無効」表示 → Task 1。
  - 「未発行のみ」で無効を非表示 → Task 2。
  - 個別請求書発行のスキップ → Task 3。
  - 全員に請求書を発行のスキップ → Task 4。
  - 領収書側・他画面は変更なし（触れていない）。
- **Placeholder scan:** プレースホルダなし。全ステップに実コード・実コマンドあり。Task 4 Step 1/2 は既存テストの company seed 方式に合わせる指示を明示。
- **Type consistency:** `voided = inv is None and rcp is not None`（UI）と `has_receipt`（service）は同じ意味の条件。行データ `(pm_id, invoice_id, receipt_id)` と `_issue_checked` のスキップ条件 `invoice_id is None and receipt_id is not None` は整合。列定数 `COL_ORG`/`COL_INV`/`COL_CHK` は既存のまま使用。
