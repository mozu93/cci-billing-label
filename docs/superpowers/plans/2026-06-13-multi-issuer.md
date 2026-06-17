# 複数発行元管理機能 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 複数の発行元（CompanySettings）を登録・管理し、プロジェクトごとに使用する発行元・銀行口座・印鑑を選択できるようにする。

**Architecture:** CompanySettings に `is_default` フラグを追加してマルチレコード化する。Project に `company_settings_id`・`bank_account_id`・`seal_image_id` の FK を追加し、PDF生成時に「プロジェクト設定 → 発行元デフォルト → システムデフォルト」の順でフォールバックする。既存データは変更なし。

**Tech Stack:** SQLAlchemy (SQLite/PostgreSQL), PyQt6, ReportLab

---

## ファイル構成

| ファイル | 変更内容 |
|---|---|
| `app/database/models.py` | CompanySettings に `is_default` 追加、Project に3FK追加 |
| `app/database/connection.py` | `_migrate()` に新カラム追加処理を追記 |
| `app/utils/pdf_helpers.py` | `get_issuer_for_project()` 追加、`generate_and_open()` に `project` 引数追加 |
| `app/services/project_service.py` | `create_project()` に新FK引数を追加 |
| `app/ui/company_settings.py` | 発行元一覧UI・`IssuerEditDialog` を追加、既存UIを再構成 |
| `app/ui/project_form.py` | 発行元・口座・印鑑のコンボボックスを追加 |
| `app/ui/issuance_from_project.py` | `generate_and_open()` 呼び出しに `project=` を追加 |
| `app/ui/issuance_counter.py` | 同上 |
| `app/ui/reissue_tab.py` | 同上 |
| `tests/test_models.py` | 新カラムのテストを追加 |
| `tests/test_pdf_helpers.py` | 新規作成：`get_issuer_for_project()` のテスト |
| `tests/test_project_service.py` | `create_project` の新引数テストを追加 |

---

## Task 1: DB モデルの変更とマイグレーション

**Files:**
- Modify: `app/database/models.py`
- Modify: `app/database/connection.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_models.py` に以下を追加する：

```python
def test_company_settings_has_is_default(db_session):
    from app.database.models import CompanySettings
    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()
    db_session.refresh(cs)
    assert cs.is_default is True


def test_project_has_issuer_fks(db_session):
    from app.database.models import CompanySettings, BankAccount, Project
    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    bank = BankAccount(company_id=cs.id, label="メイン", bank_name="テスト銀行",
                       is_default=True)
    db_session.add(bank)
    db_session.commit()

    proj = Project(name="テストPJ", fiscal_year=2026, project_type="list",
                   company_settings_id=cs.id, bank_account_id=bank.id)
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    assert proj.company_settings_id == cs.id
    assert proj.bank_account_id == bank.id
    assert proj.seal_image_id is None
    assert proj.issuer.name == "テスト会社"
    assert proj.bank_account.bank_name == "テスト銀行"
```

- [ ] **Step 2: テストが失敗することを確認する**

```
pytest tests/test_models.py::test_company_settings_has_is_default tests/test_models.py::test_project_has_issuer_fks -v
```

期待: AttributeError（`is_default` / `company_settings_id` が未定義）

- [ ] **Step 3: models.py を修正する**

`app/database/models.py` の `CompanySettings` クラスに1行追加：

```python
class CompanySettings(Base):
    __tablename__ = "company_settings"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, default="")
    postal_code = Column(String(10), default="")
    address = Column(String(300), default="")
    phone = Column(String(50), default="")
    fax = Column(String(50), default="")
    email = Column(String(200), default="")
    invoice_reg_number = Column(String(20), default="")
    logo_path = Column(String(500), default="")
    print_seal = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)          # ← 追加
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    bank_accounts = relationship("BankAccount", back_populates="company",
                                 cascade="all, delete-orphan")
    seal_images = relationship("SealImage", back_populates="company",
                               cascade="all, delete-orphan")
```

`Project` クラスに FK と relationship を追加：

```python
class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    fiscal_year = Column(Integer, nullable=False)
    project_type = Column(String(20), default="list")
    status = Column(String(20), default="draft")
    issue_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    notes = Column(Text, default="")
    company_settings_id = Column(Integer, ForeignKey("company_settings.id"), nullable=True)  # ← 追加
    bank_account_id     = Column(Integer, ForeignKey("bank_accounts.id"),    nullable=True)  # ← 追加
    seal_image_id       = Column(Integer, ForeignKey("seal_images.id"),      nullable=True)  # ← 追加
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    issuer       = relationship("CompanySettings", foreign_keys=[company_settings_id])  # ← 追加
    bank_account = relationship("BankAccount",     foreign_keys=[bank_account_id])      # ← 追加
    seal_image   = relationship("SealImage",       foreign_keys=[seal_image_id])        # ← 追加
```

- [ ] **Step 4: connection.py の `_migrate()` に追記する**

`app/database/connection.py` の `_migrate()` 関数末尾に以下を追加する：

```python
        cs_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(company_settings)"))}
        if "is_default" not in cs_cols:
            conn.execute(text(
                "ALTER TABLE company_settings ADD COLUMN is_default BOOLEAN DEFAULT 0"))
            # 既存の最初のレコードをデフォルトに設定
            conn.execute(text(
                "UPDATE company_settings SET is_default = 1 "
                "WHERE id = (SELECT MIN(id) FROM company_settings)"))
            conn.commit()

        proj_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(projects)"))}
        for col, ddl in [
            ("company_settings_id", "INTEGER REFERENCES company_settings(id)"),
            ("bank_account_id",     "INTEGER REFERENCES bank_accounts(id)"),
            ("seal_image_id",       "INTEGER REFERENCES seal_images(id)"),
        ]:
            if col not in proj_cols:
                conn.execute(text(f"ALTER TABLE projects ADD COLUMN {col} {ddl}"))
                conn.commit()
```

- [ ] **Step 5: テストが通ることを確認する**

```
pytest tests/test_models.py -v
```

期待: すべて PASS

- [ ] **Step 6: コミットする**

```bash
git add app/database/models.py app/database/connection.py tests/test_models.py
git commit -m "feat: CompanySettingsにis_defaultを追加、ProjectにIssuerFKを追加"
```

---

## Task 2: pdf_helpers — get_issuer_for_project() 追加

**Files:**
- Modify: `app/utils/pdf_helpers.py`
- Create: `tests/test_pdf_helpers.py`

- [ ] **Step 1: テストファイルを作成する**

`tests/test_pdf_helpers.py` を新規作成：

```python
# tests/test_pdf_helpers.py
from app.database.models import CompanySettings, BankAccount, SealImage, Project


def test_get_issuer_for_project_uses_project_company(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project

    cs_default = CompanySettings(name="デフォルト会社", is_default=True)
    cs_other   = CompanySettings(name="別会社",         is_default=False)
    db_session.add_all([cs_default, cs_other])
    db_session.commit()

    bank = BankAccount(company_id=cs_other.id, label="口座A",
                       bank_name="○○銀行", is_default=True)
    db_session.add(bank)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="list",
                   company_settings_id=cs_other.id, bank_account_id=bank.id)
    db_session.add(proj)
    db_session.commit()

    company, ba, seal = get_issuer_for_project(db_session, proj)
    assert company.id == cs_other.id
    assert ba.id == bank.id
    assert seal is None


def test_get_issuer_for_project_falls_back_to_default(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project

    cs = CompanySettings(name="デフォルト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    bank = BankAccount(company_id=cs.id, label="口座A",
                       bank_name="○○銀行", is_default=True)
    db_session.add(bank)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="list")
    db_session.add(proj)
    db_session.commit()

    company, ba, seal = get_issuer_for_project(db_session, proj)
    assert company.id == cs.id
    assert ba.id == bank.id


def test_get_issuer_for_project_respects_print_seal_false(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project

    cs = CompanySettings(name="会社", is_default=True, print_seal=False)
    db_session.add(cs)
    db_session.commit()

    seal_img = SealImage(company_id=cs.id, label="印鑑", path="/tmp/seal.png",
                         is_default=True)
    db_session.add(seal_img)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="list",
                   seal_image_id=seal_img.id)
    db_session.add(proj)
    db_session.commit()

    _, _, seal = get_issuer_for_project(db_session, proj)
    assert seal is None  # print_seal=False なので常に None


def test_get_issuer_for_project_project_none_falls_back(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project

    cs = CompanySettings(name="会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    company, _, _ = get_issuer_for_project(db_session, None)
    assert company.id == cs.id
```

- [ ] **Step 2: テストが失敗することを確認する**

```
pytest tests/test_pdf_helpers.py -v
```

期待: ImportError か AttributeError（`get_issuer_for_project` 未定義）

- [ ] **Step 3: pdf_helpers.py に `get_issuer_for_project()` を追加する**

`app/utils/pdf_helpers.py` の `get_default_seal()` の直後に追加：

```python
def get_issuer_for_project(session, project) -> tuple:
    """プロジェクト設定 → 発行元デフォルト → システムデフォルトの順に解決する。

    戻り値: (CompanySettings | None, BankAccount | None, SealImage | None)
    """
    from app.database.models import CompanySettings, BankAccount, SealImage

    # 1. 発行元を解決
    company = None
    if project is not None and getattr(project, "company_settings_id", None):
        company = session.get(CompanySettings, project.company_settings_id)
    if company is None:
        company = (session.query(CompanySettings).filter_by(is_default=True).first()
                   or session.query(CompanySettings).first())
    if company is None:
        return None, None, None

    # 2. 銀行口座を解決
    bank = None
    if project is not None and getattr(project, "bank_account_id", None):
        bank = session.get(BankAccount, project.bank_account_id)
    if bank is None:
        bank = (session.query(BankAccount)
                .filter_by(company_id=company.id, is_default=True).first()
                or session.query(BankAccount)
                .filter_by(company_id=company.id).first())

    # 3. 印鑑を解決（print_seal=False なら常に None）
    seal = None
    if getattr(company, "print_seal", True):
        if project is not None and getattr(project, "seal_image_id", None):
            seal = session.get(SealImage, project.seal_image_id)
        if seal is None:
            seal = (session.query(SealImage)
                    .filter_by(company_id=company.id, is_default=True).first()
                    or session.query(SealImage)
                    .filter_by(company_id=company.id).first())

    return company, bank, seal
```

- [ ] **Step 4: `generate_and_open()` に `project` 引数を追加する**

`app/utils/pdf_helpers.py` の `generate_and_open()` のシグネチャと冒頭を変更する：

```python
def generate_and_open(issuance, session, reissue: bool = False,
                      due_date=None, open_file: bool = True,
                      window_envelope: bool = False,
                      recipient_postal_code: str = "",
                      recipient_address: str = "",
                      recipient_address2: str = "",
                      project=None) -> str | None:
    """発行データのPDFを生成し、open_file=True ならビューアで開く。

    project を渡すとそのプロジェクトの発行元・口座・印鑑を使う。
    """
    if project is not None:
        company, bank, seal = get_issuer_for_project(session, project)
    else:
        company, bank = get_company_and_bank(session)
        seal = get_default_seal(session, company)

    if not company:
        return None
    output_dir = get_pdf_output_dir()
    # ここから先は既存コードと同じ（company/bank/seal 変数を使う）
```

既存の `generate_and_open` 内の `company, bank = get_company_and_bank(session)` と `if not company:` と `seal = get_default_seal(session, company)` の3行を上記の if/else ブロックに置き換えるだけでよい。

- [ ] **Step 5: テストが通ることを確認する**

```
pytest tests/test_pdf_helpers.py -v
```

期待: すべて PASS

- [ ] **Step 6: コミットする**

```bash
git add app/utils/pdf_helpers.py tests/test_pdf_helpers.py
git commit -m "feat: pdf_helpersにget_issuer_for_project()を追加し発行元をプロジェクトから解決"
```

---

## Task 3: project_service — create_project に新引数を追加

**Files:**
- Modify: `app/services/project_service.py`
- Modify: `tests/test_project_service.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_service.py` に以下を追加する：

```python
def test_create_project_with_issuer(db_session):
    from app.database.models import CompanySettings, BankAccount
    from app.services.category_service import create_category

    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    bank = BankAccount(company_id=1, label="口座", bank_name="○○銀行", is_default=True)
    db_session.add(bank)
    db_session.commit()

    cat = create_category(db_session, "青年部")
    proj = create_project(db_session, name="テストPJ",
                          category_id=cat.id, fiscal_year=2026,
                          project_type="list",
                          company_settings_id=cs.id,
                          bank_account_id=bank.id)
    assert proj.company_settings_id == cs.id
    assert proj.bank_account_id == bank.id
    assert proj.seal_image_id is None
```

- [ ] **Step 2: テストが失敗することを確認する**

```
pytest tests/test_project_service.py::test_create_project_with_issuer -v
```

期待: TypeError（`create_project` が `company_settings_id` を受け付けない）

- [ ] **Step 3: project_service.py を修正する**

`app/services/project_service.py` の `create_project` を以下に置き換える：

```python
def create_project(session: Session, name: str, category_id: int,
                   fiscal_year: int, project_type: str,
                   notes: str = "",
                   company_settings_id: int | None = None,
                   bank_account_id: int | None = None,
                   seal_image_id: int | None = None) -> Project:
    proj = Project(
        name=name, category_id=category_id,
        fiscal_year=fiscal_year, project_type=project_type,
        status="active", notes=notes,
        company_settings_id=company_settings_id,
        bank_account_id=bank_account_id,
        seal_image_id=seal_image_id,
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return proj
```

- [ ] **Step 4: テストが通ることを確認する**

```
pytest tests/test_project_service.py -v
```

期待: すべて PASS

- [ ] **Step 5: コミットする**

```bash
git add app/services/project_service.py tests/test_project_service.py
git commit -m "feat: create_projectにcompany_settings_id/bank_account_id/seal_image_id引数を追加"
```

---

## Task 4: company_settings UI — 複数発行元対応

**Files:**
- Modify: `app/ui/company_settings.py`

このタスクは `company_settings.py` を全面的に再構成する。UIテストはスモークテストのみ。

- [ ] **Step 1: `app/ui/company_settings.py` を以下の内容に置き換える**

```python
# app/ui/company_settings.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QGroupBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView, QDialog,
    QFileDialog, QLabel, QCheckBox
)
from PyQt6.QtCore import Qt
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
        root.setSpacing(10)

        # ── 発行元一覧 ─────────────────────────────────────────
        grp1 = QGroupBox("発行元一覧")
        grp1_layout = QVBoxLayout(grp1)
        grp1_layout.setSpacing(6)

        self._issuer_table = QTableWidget(0, 3)
        self._issuer_table.setHorizontalHeaderLabels(["名称", "住所", ""])
        self._issuer_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._issuer_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._issuer_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._issuer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._issuer_table.setMaximumHeight(160)
        self._issuer_table.currentRowChanged.connect(self._on_issuer_selected)
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
        bottom.setSpacing(12)

        # 銀行口座
        grp2 = QGroupBox("銀行口座")
        bank_layout = QVBoxLayout(grp2)
        bank_layout.setSpacing(6)
        self._bank_table = QTableWidget(0, 5)
        self._bank_table.setHorizontalHeaderLabels(
            ["ラベル", "銀行名", "支店名", "種別", "口座番号"])
        self._bank_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._bank_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._bank_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._bank_table.setMaximumHeight(150)
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
        seal_layout.setSpacing(6)
        self._print_seal_chk = QCheckBox("印鑑を印字する（請求書・領収書共通）")
        self._print_seal_chk.setChecked(True)
        self._print_seal_chk.stateChanged.connect(self._save_seal_option)
        seal_layout.addWidget(self._print_seal_chk)
        seal_layout.addWidget(QLabel("PNG / JPG を登録。★デフォルトが印刷されます。"))

        self._seal_table = QTableWidget(0, 3)
        self._seal_table.setHorizontalHeaderLabels(["ラベル", "ファイルパス", ""])
        self._seal_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._seal_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._seal_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._seal_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._seal_table.setMaximumHeight(150)
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
                    self._issuer_table.setCurrentRow(r)
                    return
        if self._issuer_table.rowCount() > 0:
            self._issuer_table.setCurrentRow(0)

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
                for col, val in enumerate([s.label, s.path, default_mark]):
                    item = QTableWidgetItem(val)
                    item.setData(0x0100, s.id)
                    self._seal_table.setItem(r, col, item)
        finally:
            session.close()

    # ── 発行元の操作 ───────────────────────────────────────────

    def _add_issuer(self):
        dlg = IssuerEditDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # 1件目なら自動的にデフォルト設定
            session = get_session()
            try:
                count = session.query(CompanySettings).count()
                if count == 1:
                    cs = session.query(CompanySettings).first()
                    cs.is_default = True
                    session.commit()
                    new_id = cs.id
                else:
                    cs = session.query(CompanySettings).order_by(
                        CompanySettings.id.desc()).first()
                    new_id = cs.id if cs else None
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
        session = get_session()
        try:
            is_first = session.query(SealImage).filter_by(
                company_id=self._selected_company_id).count() == 0
            seal = SealImage(
                company_id=self._selected_company_id,
                label=label, path=path, is_default=is_first,
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
        self.setFixedSize(440, 330)
        self._build()
        if company_id:
            self._load(company_id)

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(6)
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
        finally:
            session.close()
        self.accept()


class BankAccountDialog(QDialog):
    def __init__(self, parent=None, company_id: int | None = None):
        super().__init__(parent)
        self._company_id = company_id
        self.setWindowTitle("銀行口座登録")
        self.setFixedSize(360, 300)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
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
                bank_account_number=self._account_number.text().strip(),
                bank_account_name=self._account_name.text().strip(),
            )
            session.add(b)
            session.commit()
        finally:
            session.close()
        self.accept()
```

- [ ] **Step 2: スモークテストを実行する**

```
pytest tests/ -k "company_settings or settings_tab" -v
```

既存テストが引き続き PASS することを確認する。

- [ ] **Step 3: コミットする**

```bash
git add app/ui/company_settings.py
git commit -m "feat: company_settingsUIを複数発行元対応に再構成・IssuerEditDialogを追加"
```

---

## Task 5: project_form UI — 発行元・口座・印鑑の選択

**Files:**
- Modify: `app/ui/project_form.py`

- [ ] **Step 1: `project_form.py` の `_build()` メソッドに発行元コンボを追加する**

`ProjectFormDialog._build()` の `form.addRow("備考", self._notes)` の直後に以下を追加する：

```python
        # ── 発行元・口座・印鑑 ──────────────────────────────────
        self._issuer_combo = QComboBox()
        self._bank_combo   = QComboBox()
        self._seal_combo   = QComboBox()
        self._issuer_combo.currentIndexChanged.connect(self._on_issuer_changed)
        form.addRow("発行元", self._issuer_combo)
        form.addRow("銀行口座", self._bank_combo)
        form.addRow("印鑑", self._seal_combo)
        self._reload_issuers()
```

- [ ] **Step 2: `_reload_issuers()` メソッドを追加する**

`ProjectFormDialog` クラスに以下のメソッドを追加する（`_reload_categories()` の近くに置く）：

```python
    def _reload_issuers(self, select_company_id: int | None = None,
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
        self._reload_bank_seal(select_bank_id=select_bank_id,
                               select_seal_id=select_seal_id)

    def _reload_bank_seal(self, select_bank_id: int | None = None,
                          select_seal_id: int | None = None):
        from app.database.models import CompanySettings, BankAccount, SealImage
        company_id = self._issuer_combo.currentData()
        session = get_session()
        try:
            self._bank_combo.blockSignals(True)
            self._bank_combo.clear()
            self._bank_combo.addItem("（なし）", None)
            if company_id:
                banks = session.query(BankAccount).filter_by(
                    company_id=company_id).all()
                for b in banks:
                    label = f"{'★ ' if b.is_default else ''}{b.label} {b.bank_name}"
                    self._bank_combo.addItem(label, b.id)
            self._bank_combo.blockSignals(False)

            self._seal_combo.blockSignals(True)
            self._seal_combo.clear()
            self._seal_combo.addItem("（なし）", None)
            if company_id:
                seals = session.query(SealImage).filter_by(
                    company_id=company_id).all()
                for s in seals:
                    label = f"{'★ ' if s.is_default else ''}{s.label}"
                    self._seal_combo.addItem(label, s.id)
            self._seal_combo.blockSignals(False)

            # デフォルト値をセット
            if select_bank_id is not None:
                for i in range(self._bank_combo.count()):
                    if self._bank_combo.itemData(i) == select_bank_id:
                        self._bank_combo.setCurrentIndex(i)
                        break
            else:
                for i in range(self._bank_combo.count()):
                    if self._bank_combo.itemData(i) is not None:
                        bank_obj = session.get(BankAccount, self._bank_combo.itemData(i))
                        if bank_obj and bank_obj.is_default:
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
                        seal_obj = session.get(SealImage, self._seal_combo.itemData(i))
                        if seal_obj and seal_obj.is_default:
                            self._seal_combo.setCurrentIndex(i)
                            break
        finally:
            session.close()

    def _on_issuer_changed(self, _):
        self._reload_bank_seal()
```

- [ ] **Step 3: `_load()` メソッドに発行元・口座・印鑑の読み込みを追加する**

`ProjectFormDialog._load()` の `session.close()` 前（`tmpl_data` 取得の後）に以下を追加する：

```python
            company_settings_id = proj.company_settings_id
            bank_account_id     = proj.bank_account_id
            seal_image_id       = proj.seal_image_id
```

`finally: session.close()` の後に以下を追加する：

```python
        self._reload_issuers(
            select_company_id=company_settings_id,
            select_bank_id=bank_account_id,
            select_seal_id=seal_image_id,
        )
```

- [ ] **Step 4: `_save()` メソッドに発行元・口座・印鑑の保存を追加する**

`ProjectFormDialog._save()` の新規作成パス（`if self._project_id is None:` ブロック）で `create_project()` 呼び出しを以下に変更する：

```python
                proj = create_project(
                    session, name=title,
                    category_id=cat_id,
                    fiscal_year=self._fiscal_year.value(),
                    project_type="list",
                    notes=self._notes.toPlainText().strip(),
                    company_settings_id=self._issuer_combo.currentData(),
                    bank_account_id=self._bank_combo.currentData(),
                    seal_image_id=self._seal_combo.currentData(),
                )
```

編集パス（`else:` ブロック）の `proj.notes = ...` の直後に追加する：

```python
                proj.company_settings_id = self._issuer_combo.currentData()
                proj.bank_account_id     = self._bank_combo.currentData()
                proj.seal_image_id       = self._seal_combo.currentData()
```

- [ ] **Step 5: テストを実行する**

```
pytest tests/test_project_form.py tests/test_project_service.py -v
```

既存テストが PASS することを確認する。

- [ ] **Step 6: コミットする**

```bash
git add app/ui/project_form.py
git commit -m "feat: project_formに発行元・口座・印鑑の選択コンボを追加"
```

---

## Task 6: generate_and_open の呼び出し元にプロジェクトを渡す

**Files:**
- Modify: `app/ui/issuance_from_project.py`
- Modify: `app/ui/issuance_counter.py`
- Modify: `app/ui/reissue_tab.py`

### issuance_from_project.py

- [ ] **Step 1: issuance_from_project.py の generate_and_open 呼び出しを修正する**

`app/ui/issuance_from_project.py` の `generate_and_open(iss, session, ...)` 呼び出し（行831付近）を以下に変更する：

```python
                        from app.database.models import Project as _Project
                        _proj = session.get(_Project, iss.project_id)
                        path = generate_and_open(iss, session, due_date=due_date,
                                                 open_file=open_each,
                                                 window_envelope=window_envelope,
                                                 project=_proj)
```

### issuance_counter.py

- [ ] **Step 2: issuance_counter.py の generate_and_open 呼び出しを修正する**

`app/ui/issuance_counter.py` の `generate_and_open(iss, session, ...)` 呼び出し（行935付近）を以下に変更する：

```python
            from app.database.models import Project as _Project
            _proj = session.get(_Project, iss.project_id)
            generate_and_open(iss, session, due_date=due_date,
                              window_envelope=window_envelope,
                              recipient_postal_code=postal_code,
                              recipient_address=address1,
                              recipient_address2=address2,
                              project=_proj)
```

（`postal_code`, `address1`, `address2` の変数名は実際のコードに合わせる）

### reissue_tab.py

- [ ] **Step 3: reissue_tab.py の generate_and_open 呼び出しを修正する**

`app/ui/reissue_tab.py` の `generate_and_open(iss, session, reissue=True, ...)` 呼び出し（行322付近）を以下に変更する：

```python
            from app.database.models import Project as _Project
            _proj = session.get(_Project, iss.project_id)
            generate_and_open(iss, session, reissue=True, due_date=due_date,
                              project=_proj)
```

### 動作確認

- [ ] **Step 4: 全テストを実行する**

```
pytest tests/ -v
```

期待: すべて PASS

- [ ] **Step 5: コミットする**

```bash
git add app/ui/issuance_from_project.py app/ui/issuance_counter.py app/ui/reissue_tab.py
git commit -m "feat: 発行UI全体でプロジェクトの発行元情報をPDF生成に反映"
```

---

## 完了確認チェックリスト

- [ ] `pytest tests/ -v` が全て PASS
- [ ] アプリ起動後、設定タブ→発行元情報に複数発行元を追加できる
- [ ] 発行元を選択すると銀行口座・印鑑が切り替わる
- [ ] ★デフォルト設定が正しく反映される
- [ ] プロジェクト作成/編集フォームに発行元・口座・印鑑のコンボが表示される
- [ ] プロジェクト保存後、再編集で正しい値が復元される
- [ ] 発行PDF（請求書・領収書）にプロジェクト設定の発行元情報が反映される
- [ ] 既存プロジェクト（NULL値）はデフォルト発行元でPDF生成される
