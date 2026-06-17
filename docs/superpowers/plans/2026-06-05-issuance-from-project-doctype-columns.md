# 登録データから発行の2列化・発行種別明示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「登録データから発行」タブで、発行する書類種別をボタンに明示し、一覧で請求書・領収書それぞれの発行状態を同時に表示する。

**Architecture:** 単一ウィジェット `IssuanceFromProjectWidget`（`app/ui/issuance_from_project.py`）の改修。発行ボタン文言を書類種別コンボに連動させ、一覧の状態列を請求書／領収書の2列に分割し、各 project_member の種別別最新発行を表示する。「未発行のみ」フィルタは選択中の書類種別を基準にする。

**Tech Stack:** Python, PyQt6, SQLAlchemy, pytest（`qtbot` / `memory_db` フィクスチャ）。

参照spec: `docs/superpowers/specs/2026-06-05-issuance-from-project-doctype-columns-design.md`

---

## File Structure

- Modify: `app/ui/issuance_from_project.py` — 列定数・`_build`・`_load_members`・`_checked_rows`・`_issue_checked` の改修、`_update_issue_button_labels` / `_cell_text` の追加。
- Modify: `tests/test_issuance_from_project.py` — ボタン文言テストの更新と、新規UIテストの追加。

全タスクが同じ2ファイルを触る。タスクは振る舞い単位で分割し、各タスク完了時点でテストが緑になるようにする。

---

## Task 1: 発行ボタンの文言を書類種別に連動させる

**Files:**
- Modify: `app/ui/issuance_from_project.py`（`_build` のボタン生成部、`_update_issue_button_labels` 追加）
- Test: `tests/test_issuance_from_project.py`

- [ ] **Step 1: Update the existing button-text test and add a new one**

`tests/test_issuance_from_project.py` の `test_widget_has_issue_and_batch_buttons` を次に置き換える（ボタン文言が種別連動になるため固定文字列を変更）:

```python
def test_widget_has_issue_and_batch_buttons(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    w = IssuanceFromProjectWidget()
    qtbot.addWidget(w)
    texts = _texts(w)
    # 初期は請求書。種別が文言に含まれる
    assert "選択行に請求書を発行" in texts
    assert "全員に請求書を発行" in texts
    # 旧2段階ボタンが無い
    assert "準備（採番）" not in texts
```

同ファイル末尾に追記:

```python
def test_issue_button_labels_follow_doctype(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    w = IssuanceFromProjectWidget()
    qtbot.addWidget(w)
    idx_inv = next(i for i in range(w._doctype_combo.count())
                   if w._doctype_combo.itemData(i) == "invoice")
    w._doctype_combo.setCurrentIndex(idx_inv)
    assert w._btn_issue.text() == "選択行に請求書を発行"
    assert w._btn_issue_all.text() == "全員に請求書を発行"
    idx_rcp = next(i for i in range(w._doctype_combo.count())
                   if w._doctype_combo.itemData(i) == "receipt")
    w._doctype_combo.setCurrentIndex(idx_rcp)
    assert w._btn_issue.text() == "選択行に領収書を発行"
    assert w._btn_issue_all.text() == "全員に領収書を発行"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_issuance_from_project.py -v`
Expected: FAIL（`test_widget_has_issue_and_batch_buttons` は新文言が無く失敗、`test_issue_button_labels_follow_doctype` は `w._btn_issue` 属性が無く AttributeError）

- [ ] **Step 3: Implement**

`app/ui/issuance_from_project.py` の `_build` 内、ボタン生成部分を変更する。

現在（`:113-125`）:
```python
        btn_row = QHBoxLayout()
        btn_issue = QPushButton("選択した行を発行")
        btn_issue.clicked.connect(self._issue_checked)
        btn_issue_all = QPushButton("全員まとめて発行")
        btn_issue_all.clicked.connect(self._issue_all)
        self._delivery_combo = QComboBox()
        self._delivery_combo.addItems(["窓口手渡し", "郵送", "メール送付", "その他"])
        btn_row.addWidget(btn_issue)
        btn_row.addWidget(btn_issue_all)
        btn_row.addWidget(QLabel("配付方法："))
        btn_row.addWidget(self._delivery_combo)
        btn_row.addStretch()
        layout.addLayout(btn_row)
```

新:
```python
        btn_row = QHBoxLayout()
        self._btn_issue = QPushButton("選択行に請求書を発行")
        self._btn_issue.clicked.connect(self._issue_checked)
        self._btn_issue_all = QPushButton("全員に請求書を発行")
        self._btn_issue_all.clicked.connect(self._issue_all)
        self._delivery_combo = QComboBox()
        self._delivery_combo.addItems(["窓口手渡し", "郵送", "メール送付", "その他"])
        btn_row.addWidget(self._btn_issue)
        btn_row.addWidget(self._btn_issue_all)
        btn_row.addWidget(QLabel("配付方法："))
        btn_row.addWidget(self._delivery_combo)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 書類種別の変更でボタン文言を更新（ボタン生成後に接続）
        self._doctype_combo.currentIndexChanged.connect(self._update_issue_button_labels)
        self._update_issue_button_labels()
```

`_build` の後（`_on_header_clicked` の手前あたり）にメソッドを追加:
```python
    def _update_issue_button_labels(self):
        label = self._doctype_combo.currentText()
        self._btn_issue.setText(f"選択行に{label}を発行")
        self._btn_issue_all.setText(f"全員に{label}を発行")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_issuance_from_project.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/issuance_from_project.py tests/test_issuance_from_project.py
git commit -m "feat: 登録データから発行の発行ボタン文言を書類種別に連動"
```

---

## Task 2: 一覧を請求書・領収書の2列に分ける

**Files:**
- Modify: `app/ui/issuance_from_project.py`（列定数、`_build` のヘッダー、`_load_members`、`_checked_rows`、`_issue_checked`、`_cell_text` 追加）
- Test: `tests/test_issuance_from_project.py`

- [ ] **Step 1: Write the failing test**

`tests/test_issuance_from_project.py` 末尾に追記:

```python
def _seed_two_members_with_issuances():
    """○○商事=請求書のみ発行済み / △△工業=請求書も領収書も発行済み。proj_id を返す。"""
    from app.database.connection import get_session
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    from app.services.project_service import (
        create_project, add_template_to_project, add_roster_entries,
        get_project_members,
    )
    from app.services.issuance_service import create_issuance_for_member, mark_as_issued
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
    rcp2 = create_issuance_for_member(s, proj.id, pms[1].id, "△△工業", "",
                                      "receipt", 2026, 5)
    mark_as_issued(s, rcp2.id, None, "田中", "窓口手渡し")
    proj_id = proj.id
    s.close()
    return proj_id


def _select_project(w, proj_id):
    for i in range(w._proj_combo.count()):
        if w._proj_combo.itemData(i) == proj_id:
            w._proj_combo.setCurrentIndex(i)
            return


def test_two_columns_show_invoice_and_receipt_status(qtbot, memory_db):
    from app.ui.issuance_from_project import (
        IssuanceFromProjectWidget, COL_ORG, COL_INV, COL_RCP,
    )
    proj_id = _seed_two_members_with_issuances()
    w = IssuanceFromProjectWidget()
    qtbot.addWidget(w)
    _select_project(w, proj_id)
    w._filter_combo.setCurrentIndex(1)  # すべて
    w._load_members()

    assert w._table.rowCount() == 2
    rows = {}
    for r in range(w._table.rowCount()):
        org = w._table.item(r, COL_ORG).text()
        rows[org] = (w._table.item(r, COL_INV).text(),
                     w._table.item(r, COL_RCP).text())
    # ○○商事：請求書発行済み・領収書未発行
    assert "発行済" in rows["○○商事"][0]
    assert "INV-" in rows["○○商事"][0]
    assert rows["○○商事"][1] == "未発行"
    # △△工業：請求書・領収書とも発行済み（古い方が消えない）
    assert "発行済" in rows["△△工業"][0]
    assert "INV-" in rows["△△工業"][0]
    assert "発行済" in rows["△△工業"][1]
    assert "RCP-" in rows["△△工業"][1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_issuance_from_project.py::test_two_columns_show_invoice_and_receipt_status -v`
Expected: FAIL（`COL_INV` / `COL_RCP` が未定義で ImportError、または列内容が一致しない）

- [ ] **Step 3: Implement**

(3a) 列定数を変更する。現在（`:15-19`）:
```python
COL_CHK = 0
COL_ORG = 1
COL_REP = 2
COL_STA = 3
COL_NUM = 4
```
新:
```python
COL_CHK = 0
COL_ORG = 1
COL_REP = 2
COL_INV = 3
COL_RCP = 4
```

(3b) `_build` のヘッダーラベルを変更する。現在（`:95-97`）:
```python
        self._table = _CheckableTable(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["", "事業所名", "代表者名", "ステータス", "発行番号"])
```
新:
```python
        self._table = _CheckableTable(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["", "事業所名", "代表者名", "請求書", "領収書"])
```

(3c) `_cell_text` ヘルパとステータス短縮表をクラスに追加する（`_load_members` の手前）:
```python
    _STATUS_SHORT = {"発行済み": "発行済", "支払済み": "支払済", "準備中": "準備中"}

    def _cell_text(self, iss) -> str:
        if iss is None:
            return "未発行"
        short = self._STATUS_SHORT.get(iss.status, iss.status)
        return f"{short} {iss.doc_number}".strip()
```

(3d) `_load_members` を全面的に置き換える。現在（`:190-249`）の本体を次に置き換える:
```python
    def _load_members(self):
        project_id = self._proj_combo.currentData()
        if project_id is None:
            self._table.setRowCount(0)
            return
        query = self._search.text().strip().lower()
        show_all = self._filter_combo.currentIndex() == 1
        doc_type = self._doctype_combo.currentData()
        session = get_session()
        try:
            pms = get_project_members(session, project_id)
            from app.database.models import Issuance
            pm_data = []
            for pm in pms:
                inv = (session.query(Issuance)
                       .filter_by(project_member_id=pm.id, doc_type="invoice")
                       .order_by(Issuance.created_at.desc())
                       .first())
                rcp = (session.query(Issuance)
                       .filter_by(project_member_id=pm.id, doc_type="receipt")
                       .order_by(Issuance.created_at.desc())
                       .first())
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
        finally:
            session.close()

        # テーブル再構築：チェック状態・範囲選択をリセット
        self._table._last_checked_row = -1
        hdr = self._table.horizontalHeaderItem(COL_CHK)
        if hdr:
            hdr.setCheckState(Qt.CheckState.Unchecked)

        self._table.setRowCount(0)
        for pm_id, pm, inv_text, rcp_text, inv_id, rcp_id in pm_data:
            row = self._table.rowCount()
            self._table.insertRow(row)

            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(row, COL_CHK, chk_item)

            row_data = (pm_id, inv_id, rcp_id)
            for col, val in [
                (COL_ORG, pm.organization_name or ""),
                (COL_REP, pm.representative_name or ""),
                (COL_INV, inv_text),
                (COL_RCP, rcp_text),
            ]:
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, row_data)
                self._table.setItem(row, col, item)

        self._status_label.setText(f"{len(pm_data)} 件表示")
```

(3e) `_checked_rows` を、行データが3要素になったことに合わせる。現在（`:253-261`）:
```python
    def _checked_rows(self) -> list[tuple[int, int | None]]:
        result = []
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, COL_CHK)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                data_item = self._table.item(r, COL_ORG)
                if data_item:
                    result.append(data_item.data(Qt.ItemDataRole.UserRole))
        return result
```
新:
```python
    def _checked_rows(self) -> list[tuple[int, int | None, int | None]]:
        result = []
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, COL_CHK)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                data_item = self._table.item(r, COL_ORG)
                if data_item:
                    result.append(data_item.data(Qt.ItemDataRole.UserRole))
        return result
```

(3f) `_issue_checked` の対象ループを、選択種別に応じて id を引くよう変更する。現在（`:289`）:
```python
            for pm_id, issuance_id in targets:
```
新:
```python
            for pm_id, invoice_id, receipt_id in targets:
                issuance_id = invoice_id if doc_type == "invoice" else receipt_id
```
（`doc_type` は同メソッド `:280` で既に `doc_type = self._doctype_combo.currentData()` として定義済み。ループ本体の以降のロジックはそのまま。`issuance_id is None` の新規採番分岐も既存のまま動く。）

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_issuance_from_project.py::test_two_columns_show_invoice_and_receipt_status -v`
Expected: PASS

- [ ] **Step 5: Run the file's full tests**

Run: `python -m pytest tests/test_issuance_from_project.py -v`
Expected: PASS（Task 1 のテストも引き続き緑）

- [ ] **Step 6: Commit**

```bash
git add app/ui/issuance_from_project.py tests/test_issuance_from_project.py
git commit -m "feat: 登録データから発行の一覧を請求書・領収書の2列表示に変更"
```

---

## Task 3: 「未発行のみ」フィルタを選択種別基準にし、種別変更で再読込

Task 2 の `_load_members` は既に「選択中の書類種別」を未発行判定に使う。残るは、書類種別コンボを変えたときに一覧が再読込されるよう接続することと、その振る舞いのテスト。

**Files:**
- Modify: `app/ui/issuance_from_project.py`（`_build` で `_doctype_combo.currentIndexChanged` に `_load_members` を接続）
- Test: `tests/test_issuance_from_project.py`

- [ ] **Step 1: Write the failing test**

`tests/test_issuance_from_project.py` 末尾に追記:

```python
def test_unissued_filter_is_per_doctype(qtbot, memory_db):
    from app.ui.issuance_from_project import IssuanceFromProjectWidget
    proj_id = _seed_two_members_with_issuances()
    # ○○商事=請求書発行済み/領収書未発行、△△工業=両方発行済み
    w = IssuanceFromProjectWidget()
    qtbot.addWidget(w)
    _select_project(w, proj_id)

    # 書類種別=請求書、未発行のみ → 両者とも請求書発行済みなので0件
    idx_inv = next(i for i in range(w._doctype_combo.count())
                   if w._doctype_combo.itemData(i) == "invoice")
    w._filter_combo.setCurrentIndex(0)  # 未発行のみ
    w._doctype_combo.setCurrentIndex(idx_inv)
    w._load_members()
    assert w._table.rowCount() == 0

    # 書類種別=領収書に切替 → 切替だけで再読込され、領収書未発行の○○商事が出る
    idx_rcp = next(i for i in range(w._doctype_combo.count())
                   if w._doctype_combo.itemData(i) == "receipt")
    w._doctype_combo.setCurrentIndex(idx_rcp)  # currentIndexChanged で再読込
    orgs = [w._table.item(r, 1).text() for r in range(w._table.rowCount())]
    assert "○○商事" in orgs       # 領収書未発行
    assert "△△工業" not in orgs   # 領収書発行済み
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_issuance_from_project.py::test_unissued_filter_is_per_doctype -v`
Expected: FAIL（種別を領収書に変えても自動再読込されず、テーブルが請求書基準のまま＝`○○商事` が出ない）

- [ ] **Step 3: Implement**

`app/ui/issuance_from_project.py` の `_build` 末尾、Task 1 で追加した接続の直後に `_load_members` への接続を追加する。

Task 1 後の該当箇所:
```python
        # 書類種別の変更でボタン文言を更新（ボタン生成後に接続）
        self._doctype_combo.currentIndexChanged.connect(self._update_issue_button_labels)
        self._update_issue_button_labels()
```
新:
```python
        # 書類種別の変更でボタン文言を更新し、一覧も再読込する（ボタン生成後に接続）
        self._doctype_combo.currentIndexChanged.connect(self._update_issue_button_labels)
        self._doctype_combo.currentIndexChanged.connect(self._load_members)
        self._update_issue_button_labels()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_issuance_from_project.py::test_unissued_filter_is_per_doctype -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS（全テスト。`_on_project_changed` 内の `setCurrentIndex` による種別自動判定は `_load_members` を二重に呼ぶ可能性があるが、冪等なので問題ない）

- [ ] **Step 6: Commit**

```bash
git add app/ui/issuance_from_project.py tests/test_issuance_from_project.py
git commit -m "feat: 登録データから発行の未発行フィルタを書類種別基準にし種別変更で再読込"
```

---

## Task 4: 手動確認

- [ ] **Step 1: アプリを起動して確認**

Run: `python -m app.main`（または既存の起動手順）
確認手順:
1. まとめて発行 ＞「登録データから発行」を開く。
2. 名簿を選び、一覧に「請求書」「領収書」の2列が出て、それぞれの状態（未発行／発行済 番号）が表示されることを確認。
3. 上部「書類種別」を請求書↔領収書で切り替えると、発行ボタンの文言が「選択行に請求書を発行」↔「…領収書を発行」と変わり、「未発行のみ」表示の対象も切り替わることを確認。
4. 請求書を発行 → 一覧の請求書列が「発行済 INV-...」になる。続けて同じ事業所に領収書を発行 → 領収書列が「発行済 RCP-...」になり、請求書列の表示は消えないことを確認。

---

## Self-Review

- **Spec coverage:**
  - 2列（請求書／領収書）表示・種別別最新取得 → Task 2。
  - セル表記（未発行／状態+番号、状態短縮）→ Task 2 の `_cell_text`。
  - 行データ `(pm_id, invoice_id, receipt_id)` と発行対象引き当て → Task 2 の `_load_members` / `_checked_rows` / `_issue_checked`。
  - 発行ボタンの種別連動 → Task 1。
  - 「未発行のみ」を選択種別基準＋種別変更で再読込 → Task 2（判定）＋ Task 3（再読込接続）。
  - スコープ外（サービス層・PDF・Shift範囲選択・`_get_doc_type`）→ 変更していない。
- **Placeholder scan:** プレースホルダなし。全ステップに実コード・実コマンドあり。
- **Type consistency:** 列定数 `COL_INV`/`COL_RCP`、行データ3要素 `(pm_id, invoice_id, receipt_id)`、`_cell_text(iss)`、`_update_issue_button_labels()`、ボタン属性 `self._btn_issue`/`self._btn_issue_all` は全タスクで一貫。`_issue_checked` のループ変数 unpack（3要素）も Task 2 で更新済み。
