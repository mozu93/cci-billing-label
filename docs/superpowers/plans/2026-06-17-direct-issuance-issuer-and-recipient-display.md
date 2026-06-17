# 単発発行（請求書）の発行元選択・宛名表示設定 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 単発発行（請求書タブ）の「発行設定」に発行元・銀行口座・印鑑の選択コンボと、宛名に役職・氏名を印字するかのチェックボックスを追加し、発行ごとに個別保存できるようにする。

**Architecture:** `Issuance` に4カラム（company_settings_id, bank_account_id, seal_image_id, show_recipient_person）を追加し、PDF生成時の発行元解決ロジック（`get_issuer_for_project`）で project 設定より優先させる。UI側は `project_form.py` の発行元選択パターンを `issuance_counter.py` に移植する。

**Tech Stack:** Python, PyQt6, SQLAlchemy, pytest, pytest-qt, reportlab

設計書: `docs/superpowers/specs/2026-06-17-direct-issuance-issuer-and-recipient-display-design.md`

---

### Task 1: Issuance モデルへのカラム追加とPDF発行元解決の優先順位変更

**Files:**
- Modify: `app/database/models.py:169-194`（Issuanceクラス）
- Modify: `app/database/connection.py:53-63`（`_migrate()` の issuances カラム追加部分）
- Modify: `app/utils/pdf_helpers.py:44-104`（`get_issuer_for_project`, `generate_and_open`）
- Test: `tests/test_pdf_helpers.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_pdf_helpers.py` の末尾に追加：

```python
def test_get_issuer_for_project_issuance_overrides_project(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project
    from app.database.models import Issuance

    cs_proj = CompanySettings(name="プロジェクト発行元", is_default=True)
    cs_iss  = CompanySettings(name="発行ごとの発行元",   is_default=False)
    db_session.add_all([cs_proj, cs_iss])
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="counter",
                   company_settings_id=cs_proj.id)
    db_session.add(proj)
    db_session.commit()

    iss = Issuance(doc_number="INV-001", doc_type="invoice",
                   recipient_organization="テスト", status="発行済み",
                   project_id=proj.id, amount=1000,
                   company_settings_id=cs_iss.id)
    db_session.add(iss)
    db_session.commit()

    company, _, _ = get_issuer_for_project(db_session, proj, issuance=iss)
    assert company.id == cs_iss.id


def test_get_issuer_for_project_issuance_dangling_reference_falls_back(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project
    from app.database.models import Issuance

    cs = CompanySettings(name="デフォルト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="counter")
    db_session.add(proj)
    db_session.commit()

    iss = Issuance(doc_number="INV-002", doc_type="invoice",
                   recipient_organization="テスト", status="発行済み",
                   project_id=proj.id, amount=1000,
                   company_settings_id=99999)  # 存在しないID
    db_session.add(iss)
    db_session.commit()

    company, _, _ = get_issuer_for_project(db_session, proj, issuance=iss)
    assert company.id == cs.id  # フォールバックでデフォルト発行元
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `python -m pytest tests/test_pdf_helpers.py -q`
Expected: 2件が `TypeError: 'company_settings_id' is an invalid keyword argument for Issuance` で FAIL（既存テストはそのままPASS）

- [ ] **Step 3: Issuance モデルにカラムを追加する**

`app/database/models.py` の `Issuance` クラス内、`staff_name = Column(String(100), default="")` の直後に追加：

```python
    company_settings_id = Column(Integer, ForeignKey("company_settings.id"), nullable=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=True)
    seal_image_id = Column(Integer, ForeignKey("seal_images.id"), nullable=True)
    show_recipient_person = Column(Boolean, default=True)
```

- [ ] **Step 4: 既存DB向けのマイグレーションを追加する**

`app/database/connection.py` の `_migrate()` 内、`issuances` テーブルの既存ループ（`for col, ddl in [...]:` の対象がissuancesになっている箇所）に4つのタプルを追加する：

変更前：
```python
        iss_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(issuances)"))}
        for col, ddl in [
            ("member_number",        "VARCHAR(50) DEFAULT ''"),
            ("recipient_kana",       "VARCHAR(200) DEFAULT ''"),
            ("recipient_department", "VARCHAR(100) DEFAULT ''"),
            ("recipient_name_kana",  "VARCHAR(100) DEFAULT ''"),
            ("recipient_phone",      "VARCHAR(50) DEFAULT ''"),
        ]:
```

変更後：
```python
        iss_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(issuances)"))}
        for col, ddl in [
            ("member_number",        "VARCHAR(50) DEFAULT ''"),
            ("recipient_kana",       "VARCHAR(200) DEFAULT ''"),
            ("recipient_department", "VARCHAR(100) DEFAULT ''"),
            ("recipient_name_kana",  "VARCHAR(100) DEFAULT ''"),
            ("recipient_phone",      "VARCHAR(50) DEFAULT ''"),
            ("company_settings_id",   "INTEGER REFERENCES company_settings(id)"),
            ("bank_account_id",       "INTEGER REFERENCES bank_accounts(id)"),
            ("seal_image_id",          "INTEGER REFERENCES seal_images(id)"),
            ("show_recipient_person", "BOOLEAN DEFAULT 1"),
        ]:
```

- [ ] **Step 5: `get_issuer_for_project` に issuance 優先解決を追加する**

`app/utils/pdf_helpers.py` の `get_issuer_for_project` 全体を以下に置き換える：

```python
def get_issuer_for_project(session, project, issuance=None) -> tuple:
    """発行（issuance）個別設定 → プロジェクト設定 → 発行元デフォルト → システムデフォルトの順に解決する。

    issuance に company_settings_id 等が設定されていない、または参照先が
    削除済み（None）の場合は次の優先度にフォールバックする。

    戻り値: (CompanySettings | None, BankAccount | None, SealImage | None)
    """
    from app.database.models import SealImage

    # 1. 発行元を解決
    company = None
    if issuance is not None and getattr(issuance, "company_settings_id", None):
        company = session.get(CompanySettings, issuance.company_settings_id)
    if company is None and project is not None and getattr(project, "company_settings_id", None):
        company = session.get(CompanySettings, project.company_settings_id)
    if company is None:
        company = (session.query(CompanySettings).filter_by(is_default=True).first()
                   or session.query(CompanySettings).first())
    if company is None:
        return None, None, None

    # 2. 銀行口座を解決
    bank = None
    if issuance is not None and getattr(issuance, "bank_account_id", None):
        bank = session.get(BankAccount, issuance.bank_account_id)
    if bank is None and project is not None and getattr(project, "bank_account_id", None):
        bank = session.get(BankAccount, project.bank_account_id)
    if bank is None:
        bank = (session.query(BankAccount)
                .filter_by(company_id=company.id, is_default=True).first()
                or session.query(BankAccount)
                .filter_by(company_id=company.id).first())

    # 3. 印鑑を解決（print_seal=False なら常に None）
    seal = None
    if getattr(company, "print_seal", True):
        if issuance is not None and getattr(issuance, "seal_image_id", None):
            seal = session.get(SealImage, issuance.seal_image_id)
        if seal is None and project is not None and getattr(project, "seal_image_id", None):
            seal = session.get(SealImage, project.seal_image_id)
        if seal is None:
            seal = (session.query(SealImage)
                    .filter_by(company_id=company.id, is_default=True).first()
                    or session.query(SealImage)
                    .filter_by(company_id=company.id).first())

    return company, bank, seal
```

- [ ] **Step 6: `generate_and_open` の呼び出しを統一する**

`app/utils/pdf_helpers.py` の `generate_and_open` 内、以下を変更：

変更前：
```python
    if project is not None:
        company, bank, seal = get_issuer_for_project(session, project)
    else:
        company, bank = get_company_and_bank(session)
        seal = get_default_seal(session, company)
    if not company:
        return None
```

変更後：
```python
    company, bank, seal = get_issuer_for_project(session, project, issuance=issuance)
    if not company:
        return None
```

- [ ] **Step 7: テストを実行して成功を確認する**

Run: `python -m pytest tests/test_pdf_helpers.py -q`
Expected: 全件PASS

- [ ] **Step 8: 関連する既存テストへの回帰がないか確認する**

Run: `python -m pytest tests/test_invoice_pdf.py tests/test_issuance_service.py tests/test_issuance_from_project.py -q`
Expected: 全件PASS

- [ ] **Step 9: コミット**

```bash
git add app/database/models.py app/database/connection.py app/utils/pdf_helpers.py tests/test_pdf_helpers.py
git commit -m "feat: Issuanceに発行元・銀行口座・印鑑カラムを追加し解決優先度をissuance>project>デフォルトに変更"
```

---

### Task 2: 請求書PDFの宛名に役職・氏名を印字するかのオプション追加

**Files:**
- Modify: `app/services/pdf/invoice_pdf.py:114-165`（`generate_invoice_pdf`）, `:245-301`（`_build_client_block`）
- Test: `tests/test_invoice_pdf.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_invoice_pdf.py` の末尾に追加：

```python
def test_build_client_block_hides_person_when_disabled():
    from app.services.pdf.invoice_pdf import _build_client_block
    from app.database.models import Issuance

    iss = Issuance(
        doc_number="INV-003", doc_type="invoice",
        recipient_organization="○○商事株式会社",
        recipient_department="営業部",
        recipient_name="田中太郎",
    )
    parts = _build_client_block(iss, show_recipient_person=False)
    texts = [p.text for p in parts if hasattr(p, "text")]
    assert any("御中" in t for t in texts)
    assert not any("田中太郎" in t for t in texts)
    assert not any("営業部" in t for t in texts)


def test_build_client_block_shows_person_by_default():
    """show_recipient_person を指定しない場合は既存どおり氏名・役職を表示する（回帰防止）。"""
    from app.services.pdf.invoice_pdf import _build_client_block
    from app.database.models import Issuance

    iss = Issuance(
        doc_number="INV-004", doc_type="invoice",
        recipient_organization="○○商事株式会社",
        recipient_department="営業部",
        recipient_name="田中太郎",
    )
    parts = _build_client_block(iss)
    texts = [p.text for p in parts if hasattr(p, "text")]
    assert any("田中太郎" in t for t in texts)
    assert any("営業部" in t for t in texts)
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `python -m pytest tests/test_invoice_pdf.py -q`
Expected: `test_build_client_block_hides_person_when_disabled` が `TypeError: _build_client_block() got an unexpected keyword argument 'show_recipient_person'` で FAIL。`test_build_client_block_shows_person_by_default` は新キーワード未使用なので既に PASS する（既存挙動の回帰防止テストとして機能）。

- [ ] **Step 3: `_build_client_block` にオプションを追加する**

`app/services/pdf/invoice_pdf.py` の `_build_client_block` 関数定義と冒頭を変更：

変更前：
```python
def _build_client_block(issuance, subject: str = "",
                         window_envelope: bool = False,
                         recipient_postal_code: str = "",
                         recipient_address: str = "",
                         recipient_address2: str = "") -> list:
    parts = []
    org    = issuance.recipient_organization or ""
    dept   = getattr(issuance, "recipient_department", "") or ""
    person = issuance.recipient_name or ""
```

変更後：
```python
def _build_client_block(issuance, subject: str = "",
                         window_envelope: bool = False,
                         recipient_postal_code: str = "",
                         recipient_address: str = "",
                         recipient_address2: str = "",
                         show_recipient_person: bool = True) -> list:
    parts = []
    org    = issuance.recipient_organization or ""
    dept   = (getattr(issuance, "recipient_department", "") or "") if show_recipient_person else ""
    person = (issuance.recipient_name or "") if show_recipient_person else ""
```

- [ ] **Step 4: `generate_invoice_pdf` から渡すようにする**

`app/services/pdf/invoice_pdf.py` の `generate_invoice_pdf` 内、`client_block = _build_client_block(...)` 呼び出しを変更：

変更前：
```python
    client_block = _build_client_block(
        issuance, subject=subject,
        window_envelope=window_envelope,
        recipient_postal_code=recipient_postal_code,
        recipient_address=recipient_address,
        recipient_address2=recipient_address2,
    )
```

変更後：
```python
    client_block = _build_client_block(
        issuance, subject=subject,
        window_envelope=window_envelope,
        recipient_postal_code=recipient_postal_code,
        recipient_address=recipient_address,
        recipient_address2=recipient_address2,
        show_recipient_person=bool(getattr(issuance, "show_recipient_person", True)),
    )
```

- [ ] **Step 5: テストを実行して成功を確認する**

Run: `python -m pytest tests/test_invoice_pdf.py -q`
Expected: 全件PASS

- [ ] **Step 6: コミット**

```bash
git add app/services/pdf/invoice_pdf.py tests/test_invoice_pdf.py
git commit -m "feat: 請求書PDFの宛名に役職・氏名を印字するかをissuance単位で切り替え可能にする"
```

---

### Task 3: サービス層（create_direct_issuance / update_direct_issuance）の対応

**Files:**
- Modify: `app/services/issuance_service.py:212-284`（`create_direct_issuance`）, `:287-332`（`update_direct_issuance`）
- Test: `tests/test_issuance_service.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_issuance_service.py` の `test_create_direct_issuance_invoice_no_payment` の直後に追加：

```python
def test_create_direct_issuance_stores_issuer_and_display_settings(db_session):
    """単発発行で選んだ発行元・銀行口座・印鑑・宛名表示設定が Issuance に保存される。"""
    from app.services.issuance_service import create_direct_issuance
    from app.database.models import CompanySettings, BankAccount, SealImage

    cs = CompanySettings(name="テスト発行元")
    db_session.add(cs)
    db_session.commit()
    bank = BankAccount(company_id=cs.id, label="口座", bank_name="○○銀行")
    seal = SealImage(company_id=cs.id, label="印鑑", path="/tmp/seal.png")
    db_session.add_all([bank, seal])
    db_session.commit()

    lines = [{"item_template_id": None, "item_name": "会費",
              "quantity": 1, "unit": "式", "unit_price": 5000, "tax_rate": 0}]
    iss = create_direct_issuance(
        db_session, lines_data=lines,
        recipient_organization="○○商事", recipient_name="",
        doc_type="invoice", fiscal_year=2026, month=6,
        company_settings_id=cs.id, bank_account_id=bank.id,
        seal_image_id=seal.id, show_recipient_person=False,
    )
    assert iss.company_settings_id == cs.id
    assert iss.bank_account_id == bank.id
    assert iss.seal_image_id == seal.id
    assert iss.show_recipient_person is False


def test_update_direct_issuance_updates_issuer_and_display_settings(db_session):
    """内容修正で発行元・宛名表示設定を変更できる。"""
    from app.services.issuance_service import create_direct_issuance, update_direct_issuance
    from app.database.models import CompanySettings

    cs1 = CompanySettings(name="発行元A")
    cs2 = CompanySettings(name="発行元B")
    db_session.add_all([cs1, cs2])
    db_session.commit()

    lines = [{"item_template_id": None, "item_name": "会費",
              "quantity": 1, "unit": "式", "unit_price": 5000, "tax_rate": 0}]
    iss = create_direct_issuance(
        db_session, lines_data=lines,
        recipient_organization="○○商事", recipient_name="",
        doc_type="invoice", fiscal_year=2026, month=6,
        company_settings_id=cs1.id, show_recipient_person=True,
    )

    updated = update_direct_issuance(
        db_session, issuance_id=iss.id, lines_data=lines,
        recipient_organization="○○商事", recipient_name="",
        delivery_method="窓口手渡し",
        company_settings_id=cs2.id, show_recipient_person=False,
    )
    assert updated.company_settings_id == cs2.id
    assert updated.show_recipient_person is False
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `python -m pytest tests/test_issuance_service.py -q`
Expected: 2件が `TypeError: create_direct_issuance() got an unexpected keyword argument 'company_settings_id'`（および `update_direct_issuance` 側も同様）で FAIL

- [ ] **Step 3: `create_direct_issuance` にパラメータを追加する**

`app/services/issuance_service.py` の `create_direct_issuance` 定義を変更：

変更前：
```python
def create_direct_issuance(session: Session, lines_data: list[dict],
                            recipient_organization: str, recipient_name: str,
                            doc_type: str, fiscal_year: int, month: int,
                            staff_id: int | None = None, staff_name: str = "",
                            delivery_method: str = "窓口手渡し",
                            project_name: str = "直接発行",
                            member_number: str = "",
                            recipient_kana: str = "",
                            recipient_department: str = "",
                            recipient_name_kana: str = "",
                            recipient_phone: str = "") -> Issuance:
```

変更後：
```python
def create_direct_issuance(session: Session, lines_data: list[dict],
                            recipient_organization: str, recipient_name: str,
                            doc_type: str, fiscal_year: int, month: int,
                            staff_id: int | None = None, staff_name: str = "",
                            delivery_method: str = "窓口手渡し",
                            project_name: str = "直接発行",
                            member_number: str = "",
                            recipient_kana: str = "",
                            recipient_department: str = "",
                            recipient_name_kana: str = "",
                            recipient_phone: str = "",
                            company_settings_id: int | None = None,
                            bank_account_id: int | None = None,
                            seal_image_id: int | None = None,
                            show_recipient_person: bool = True) -> Issuance:
```

同関数内、`Issuance(...)` 構築部分の `delivery_method=delivery_method,` の直後に追加：

```python
        company_settings_id=company_settings_id,
        bank_account_id=bank_account_id,
        seal_image_id=seal_image_id,
        show_recipient_person=show_recipient_person,
```

- [ ] **Step 4: `update_direct_issuance` にパラメータを追加する**

`app/services/issuance_service.py` の `update_direct_issuance` 定義を変更：

変更前：
```python
def update_direct_issuance(session: Session, issuance_id: int,
                            lines_data: list[dict],
                            recipient_organization: str, recipient_name: str,
                            delivery_method: str,
                            staff_id: int | None = None,
                            staff_name: str = "",
                            member_number: str = "",
                            recipient_kana: str = "",
                            recipient_department: str = "",
                            recipient_name_kana: str = "",
                            recipient_phone: str = "") -> Issuance:
```

変更後：
```python
def update_direct_issuance(session: Session, issuance_id: int,
                            lines_data: list[dict],
                            recipient_organization: str, recipient_name: str,
                            delivery_method: str,
                            staff_id: int | None = None,
                            staff_name: str = "",
                            member_number: str = "",
                            recipient_kana: str = "",
                            recipient_department: str = "",
                            recipient_name_kana: str = "",
                            recipient_phone: str = "",
                            company_settings_id: int | None = None,
                            bank_account_id: int | None = None,
                            seal_image_id: int | None = None,
                            show_recipient_person: bool = True) -> Issuance:
```

同関数内、`issuance.recipient_phone = recipient_phone` の直後に追加：

```python
    issuance.company_settings_id = company_settings_id
    issuance.bank_account_id = bank_account_id
    issuance.seal_image_id = seal_image_id
    issuance.show_recipient_person = show_recipient_person
```

- [ ] **Step 5: テストを実行して成功を確認する**

Run: `python -m pytest tests/test_issuance_service.py -q`
Expected: 全件PASS

- [ ] **Step 6: コミット**

```bash
git add app/services/issuance_service.py tests/test_issuance_service.py
git commit -m "feat: create_direct_issuance/update_direct_issuanceに発行元・宛名表示設定の引数を追加"
```

---

### Task 4: 単発発行UI（請求書タブ）に発行元・銀行口座・印鑑コンボと宛名表示チェックボックスを追加

**Files:**
- Modify: `app/ui/issuance_counter.py`（`_build()` 内、`grp_opts` セクション）
- Test: `tests/test_counter_issuance_tab.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_counter_issuance_tab.py` の末尾に追加：

```python
def test_issuer_combo_changing_resets_bank_and_seal(qtbot, memory_db):
    """発行元コンボを変更すると、銀行口座・印鑑コンボがその発行元のデフォルトにリセットされる。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings, BankAccount, SealImage
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    cs1 = CompanySettings(name="発行元A", is_default=True)
    cs2 = CompanySettings(name="発行元B", is_default=False)
    s.add_all([cs1, cs2])
    s.commit()
    bank2 = BankAccount(company_id=cs2.id, label="B口座", bank_name="△△銀行", is_default=True)
    seal2 = SealImage(company_id=cs2.id, label="B印鑑", path="/tmp/b.png", is_default=True)
    s.add_all([bank2, seal2])
    s.commit()
    cs2_id, bank2_id, seal2_id = cs2.id, bank2.id, seal2.id
    s.close()

    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)

    idx = next(i for i in range(w._issuer_combo.count())
               if w._issuer_combo.itemData(i) == cs2_id)
    w._issuer_combo.setCurrentIndex(idx)

    assert w._bank_combo.currentData() == bank2_id
    assert w._seal_combo.currentData() == seal2_id


def test_show_person_checkbox_defaults_to_true_when_unset(qtbot, memory_db, monkeypatch):
    """recipient_person_last が未設定の場合はチェック済み（既存挙動）になる。

    app_config はホームディレクトリの実ファイルを読むため、開発機に残った
    過去の設定値に依存しないよう get_config をその場でモックする。
    """
    import app.utils.app_config as cfg_mod
    monkeypatch.setattr(cfg_mod, "get_config", lambda: {})
    from app.ui.issuance_counter import IssuanceCounterWidget
    w = IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    assert w._show_person_chk.isChecked() is True
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `python -m pytest tests/test_counter_issuance_tab.py -q`
Expected: 2件が `AttributeError: 'IssuanceCounterWidget' object has no attribute '_issuer_combo'` で FAIL

- [ ] **Step 3: `_build()` に発行設定コンボを追加する**

`app/ui/issuance_counter.py` の `_build()` 内、以下を変更：

変更前：
```python
        if self._doc_type_str == "invoice":
            y, m = (date.today().year, date.today().month + 1) if date.today().month < 12 else (date.today().year + 1, 1)
            default_due = date(y, m, calendar.monthrange(y, m)[1])
```

変更後：
```python
        if self._doc_type_str == "invoice":
            self._issuer_combo = QComboBox()
            self._bank_combo   = QComboBox()
            self._seal_combo   = QComboBox()
            self._issuer_combo.currentIndexChanged.connect(self._on_issuer_combo_changed)
            opts_form.addRow("発行元",   self._issuer_combo)
            opts_form.addRow("銀行口座", self._bank_combo)
            opts_form.addRow("印鑑",     self._seal_combo)

            from app.utils.app_config import get_config as _get_cfg
            self._show_person_chk = QCheckBox("宛名に役職・氏名を印字する")
            self._show_person_chk.setChecked(_get_cfg().get("recipient_person_last", True))
            opts_form.addRow(self._show_person_chk)

            self._reload_issuer_combo()

            y, m = (date.today().year, date.today().month + 1) if date.today().month < 12 else (date.today().year + 1, 1)
            default_due = date(y, m, calendar.monthrange(y, m)[1])
```

- [ ] **Step 4: 発行元・銀行口座・印鑑の読み込みメソッドを追加する**

`app/ui/issuance_counter.py` の `_reload_master` メソッド定義の直後（`_load_edit_data` の直前）に追加：

```python
    def _reload_issuer_combo(self, select_company_id: int | None = None,
                             select_bank_id: int | None = None,
                             select_seal_id: int | None = None):
        from app.database.models import CompanySettings
        session = get_session()
        try:
            issuers = session.query(CompanySettings).order_by(CompanySettings.id).all()
            self._issuer_combo.blockSignals(True)
            self._issuer_combo.clear()
            default_idx = 0
            for i, cs in enumerate(issuers):
                label = f"{'★ ' if cs.is_default else ''}{cs.name}"
                self._issuer_combo.addItem(label, cs.id)
                if cs.is_default and select_company_id is None:
                    default_idx = i
            self._issuer_combo.blockSignals(False)

            if select_company_id is not None:
                for i in range(self._issuer_combo.count()):
                    if self._issuer_combo.itemData(i) == select_company_id:
                        self._issuer_combo.setCurrentIndex(i)
                        break
            else:
                self._issuer_combo.setCurrentIndex(default_idx)
        finally:
            session.close()
        self._reload_bank_seal_combo(select_bank_id=select_bank_id,
                                     select_seal_id=select_seal_id)

    def _reload_bank_seal_combo(self, select_bank_id: int | None = None,
                                select_seal_id: int | None = None):
        from app.database.models import BankAccount, SealImage
        company_id = self._issuer_combo.currentData()
        session = get_session()
        try:
            self._bank_combo.blockSignals(True)
            self._bank_combo.clear()
            self._bank_combo.addItem("（なし）", None)
            if company_id:
                banks = session.query(BankAccount).filter_by(company_id=company_id).all()
                for b in banks:
                    label = f"{'★ ' if b.is_default else ''}{b.label} {b.bank_name}"
                    self._bank_combo.addItem(label, b.id)
            self._bank_combo.blockSignals(False)

            self._seal_combo.blockSignals(True)
            self._seal_combo.clear()
            self._seal_combo.addItem("（なし）", None)
            if company_id:
                seals = session.query(SealImage).filter_by(company_id=company_id).all()
                for s in seals:
                    label = f"{'★ ' if s.is_default else ''}{s.label}"
                    self._seal_combo.addItem(label, s.id)
            self._seal_combo.blockSignals(False)

            if select_bank_id is not None:
                for i in range(self._bank_combo.count()):
                    if self._bank_combo.itemData(i) == select_bank_id:
                        self._bank_combo.setCurrentIndex(i)
                        break
            else:
                for i in range(self._bank_combo.count()):
                    if self._bank_combo.itemData(i) is not None:
                        b = session.get(BankAccount, self._bank_combo.itemData(i))
                        if b and b.is_default:
                            self._bank_combo.setCurrentIndex(i)
                            break

            if select_seal_id is not None:
                for i in range(self._seal_combo.count()):
                    if self._seal_combo.itemData(i) == select_seal_id:
                        self._seal_combo.setCurrentIndex(i)
                        break
            else:
                for i in range(self._seal_combo.count()):
                    if self._seal_combo.itemData(i) is not None:
                        s = session.get(SealImage, self._seal_combo.itemData(i))
                        if s and s.is_default:
                            self._seal_combo.setCurrentIndex(i)
                            break
        finally:
            session.close()

    def _on_issuer_combo_changed(self, _):
        self._reload_bank_seal_combo()
```

- [ ] **Step 5: テストを実行して成功を確認する**

Run: `python -m pytest tests/test_counter_issuance_tab.py -q`
Expected: 全件PASS

- [ ] **Step 6: コミット**

```bash
git add app/ui/issuance_counter.py tests/test_counter_issuance_tab.py
git commit -m "feat: 単発発行（請求書）の発行設定に発行元・銀行口座・印鑑コンボと宛名表示チェックボックスを追加"
```

---

### Task 5: 発行・編集フローへの配線

**Files:**
- Modify: `app/ui/issuance_counter.py`（`_issue()`, `_load_edit_data()`）
- Test: `tests/test_counter_issuance_tab.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_counter_issuance_tab.py` の末尾に追加：

```python
def test_issue_invoice_persists_selected_issuer_and_display_setting(qtbot, memory_db, monkeypatch):
    """単発発行（請求書）で選んだ発行元・宛名表示設定が Issuance に保存される。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings, Issuance
    from app.services.category_service import create_category
    from app.services.item_template_service import create_item_template
    import app.ui.issuance_counter as ic
    from PyQt6.QtWidgets import QFileDialog

    # app_config は実ファイル（~/.cci-billing/config.json）を読み書きするため、
    # テストで開発機の実ファイルを汚さないようインメモリの辞書に差し替える。
    import app.utils.app_config as cfg_mod
    _fake_cfg: dict = {}
    monkeypatch.setattr(cfg_mod, "get_config", lambda: _fake_cfg)
    monkeypatch.setattr(cfg_mod, "save_config", lambda c: _fake_cfg.update(c))

    s = get_session()
    cs1 = CompanySettings(name="発行元A", is_default=True)
    cs2 = CompanySettings(name="発行元B", is_default=False)
    s.add_all([cs1, cs2])
    s.commit()
    cat = create_category(s, "不動産部会")
    create_item_template(s, cat.id, "視察研修会参加費", 5000, "人", 0, "invoice", "")
    cs2_id = cs2.id
    s.close()

    monkeypatch.setattr(ic.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    w = ic.IssuanceCounterWidget("invoice")
    qtbot.addWidget(w)
    w._reload_master()
    w._org_name.setText("テスト株式会社")
    row = w._rows[0]
    idx = next(i for i in range(row.tmpl_combo.count()) if row.tmpl_combo.itemData(i) is not None)
    row.tmpl_combo.setCurrentIndex(idx)

    issuer_idx = next(i for i in range(w._issuer_combo.count())
                      if w._issuer_combo.itemData(i) == cs2_id)
    w._issuer_combo.setCurrentIndex(issuer_idx)
    w._show_person_chk.setChecked(False)

    w._issue()

    s = get_session()
    iss = s.query(Issuance).order_by(Issuance.id.desc()).first()
    assert iss.company_settings_id == cs2_id
    assert iss.show_recipient_person is False
    s.close()
    assert _fake_cfg["recipient_person_last"] is False  # 次回デフォルト用に記憶される


def test_edit_issuance_restores_issuer_and_display_setting(qtbot, memory_db):
    """内容修正で開くと、保存済みの発行元・宛名表示設定が復元される。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings
    from app.services.issuance_service import create_direct_issuance
    import app.ui.issuance_counter as ic

    s = get_session()
    cs1 = CompanySettings(name="発行元A", is_default=True)
    cs2 = CompanySettings(name="発行元B", is_default=False)
    s.add_all([cs1, cs2])
    s.commit()
    lines = [{"item_template_id": None, "item_name": "会費",
              "quantity": 1, "unit": "式", "unit_price": 5000, "tax_rate": 0}]
    iss = create_direct_issuance(
        s, lines_data=lines,
        recipient_organization="○○商事", recipient_name="",
        doc_type="invoice", fiscal_year=2026, month=6,
        company_settings_id=cs2.id, show_recipient_person=False,
    )
    iss_id, cs2_id = iss.id, cs2.id
    s.close()

    w = ic.IssuanceCounterWidget("invoice", edit_issuance_id=iss_id)
    qtbot.addWidget(w)
    w._reload_master()
    w._load_edit_data()

    assert w._issuer_combo.currentData() == cs2_id
    assert w._show_person_chk.isChecked() is False
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `python -m pytest tests/test_counter_issuance_tab.py -q`
Expected: 2件が `AssertionError`（保存・復元されていないため `None`/デフォルト値のまま）で FAIL

- [ ] **Step 3: `_issue()` で選択値を渡すようにする**

`app/ui/issuance_counter.py` の `_issue()` 内、`doc_type = self._doc_type_str` の直前に追加：

```python
        issuer_company_id = bank_account_id = seal_image_id = None
        show_recipient_person = True
        if self._doc_type_str == "invoice":
            issuer_company_id     = self._issuer_combo.currentData()
            bank_account_id       = self._bank_combo.currentData()
            seal_image_id         = self._seal_combo.currentData()
            show_recipient_person = self._show_person_chk.isChecked()
            from app.utils.app_config import get_config as _get_cfg, save_config as _save_cfg
            _cfg = _get_cfg()
            _cfg["recipient_person_last"] = show_recipient_person
            _save_cfg(_cfg)

```

`update_direct_issuance(...)` 呼び出しの `recipient_phone = phone,` の直後に追加：

```python
                    company_settings_id   = issuer_company_id,
                    bank_account_id       = bank_account_id,
                    seal_image_id         = seal_image_id,
                    show_recipient_person = show_recipient_person,
```

`create_direct_issuance(...)` 呼び出しの `recipient_phone = phone,` の直後にも同様に追加：

```python
                    company_settings_id   = issuer_company_id,
                    bank_account_id       = bank_account_id,
                    seal_image_id         = seal_image_id,
                    show_recipient_person = show_recipient_person,
```

- [ ] **Step 4: `_load_edit_data()` で復元するようにする**

`app/ui/issuance_counter.py` の `_load_edit_data()` 内、以下を変更：

変更前：
```python
            idx = self._delivery.findText(iss.delivery_method or "")
            if idx >= 0:
                self._delivery.setCurrentIndex(idx)
```

変更後：
```python
            idx = self._delivery.findText(iss.delivery_method or "")
            if idx >= 0:
                self._delivery.setCurrentIndex(idx)
            if self._doc_type_str == "invoice":
                if iss.company_settings_id is not None:
                    self._reload_issuer_combo(
                        select_company_id=iss.company_settings_id,
                        select_bank_id=iss.bank_account_id,
                        select_seal_id=iss.seal_image_id,
                    )
                self._show_person_chk.setChecked(
                    iss.show_recipient_person if iss.show_recipient_person is not None else True)
```

- [ ] **Step 5: テストを実行して成功を確認する**

Run: `python -m pytest tests/test_counter_issuance_tab.py -q`
Expected: 全件PASS

- [ ] **Step 6: コミット**

```bash
git add app/ui/issuance_counter.py tests/test_counter_issuance_tab.py
git commit -m "feat: 単発発行の発行・内容修正フローに発行元・宛名表示設定の保存・復元を配線"
```

---

### Task 6: 全体回帰確認

**Files:** なし（確認のみ）

- [ ] **Step 1: 全テストスイートを実行する**

Run: `python -m pytest -q --ignore=tests/test_main_window_tabs.py`
Expected: 全件PASS（`test_main_window_tabs.py` は既知の断続的ネイティブクラッシュのため除外。`docs/.../memory/project_test_main_window_crash.md` 参照）

- [ ] **Step 2: 実際のDBに対して既存DBマイグレーションが安全に動くことを確認する**

Run:
```bash
python -c "
from app.database.connection import init_db, get_session
init_db()
from app.database.models import Issuance
s = get_session()
i = s.query(Issuance).first()
print('company_settings_id:', i.company_settings_id if i else 'N/A')
print('show_recipient_person:', i.show_recipient_person if i else 'N/A')
s.close()
"
```
Expected: エラーなく実行でき、既存レコードは `company_settings_id=None`、`show_recipient_person=True`（既存挙動を維持）

- [ ] **Step 3: アプリを起動して単発発行（請求書）タブを目視確認する**

Run: `python main.py`
Expected: 「単発発行」→「請求書」タブの「発行設定」に「発行元」「銀行口座」「印鑑」コンボと「宛名に役職・氏名を印字する」チェックボックスが表示される。発行元を変更すると銀行口座・印鑑が切り替わる。実際に1件発行し、PDFの宛名表示がチェックボックスの状態と一致することを確認する。
