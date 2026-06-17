# 商工会議所請求書・領収書発行システム — Plan 1: 基盤・マスタ管理

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `cci-billing` プロジェクトの基盤（DB・設定・スタッフ管理・カテゴリ・請求項目テンプレート・会員マスタ）を構築し、データの登録・管理ができる状態にする。

**Architecture:** Python + PyQt6デスクトップアプリ。DBはPostgreSQL（本番）/ SQLite（開発・テスト）をSQLAlchemyで抽象化。設定ファイル（`~/.cci-billing/config.json`）でDB接続先を管理。サービス層（`app/services/`）がDB操作を担い、UI層（`app/ui/`）はサービスを呼び出す構造。

**Tech Stack:** Python 3.11+, PyQt6 6.6+, SQLAlchemy 2.0, PostgreSQL 15+ / SQLite（テスト用）, openpyxl 3.1+, pytest 8+

---

## ファイル構成

```
cci-billing/
├── main.py
├── requirements.txt
├── requirements-dev.txt
├── app/
│   ├── __init__.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py          # 全テーブル定義
│   │   └── connection.py      # エンジン・セッション管理
│   ├── services/
│   │   ├── __init__.py
│   │   ├── staff_service.py
│   │   ├── category_service.py
│   │   ├── item_template_service.py
│   │   └── member_service.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── theme.py
│   │   ├── main_window.py
│   │   ├── login_dialog.py
│   │   ├── first_run_wizard.py
│   │   ├── settings_tab.py
│   │   ├── staff_management.py
│   │   ├── category_management.py
│   │   ├── item_template_management.py
│   │   ├── member_list.py
│   │   ├── member_form.py
│   │   └── member_import.py
│   └── utils/
│       ├── __init__.py
│       ├── app_config.py      # config.json 読み書き
│       ├── current_user.py    # ログイン中スタッフ保持
│       └── excel_utils.py     # Excel・クリップボード取込
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_staff_service.py
│   ├── test_category_service.py
│   ├── test_item_template_service.py
│   ├── test_member_service.py
│   └── test_excel_utils.py
└── docs/
    └── setup.md
```

---

## Task 1: プロジェクト初期化

**Files:**
- Create: `C:\Users\taka\Documents\Gemini\0030Business\cci-billing\` (ディレクトリ)
- Create: `requirements.txt`
- Create: `requirements-dev.txt`

- [ ] **Step 1: ディレクトリ作成とgit初期化**

```powershell
New-Item -ItemType Directory -Path "C:\Users\taka\Documents\Gemini\0030Business\cci-billing"
cd "C:\Users\taka\Documents\Gemini\0030Business\cci-billing"
git init
```

- [ ] **Step 2: requirements.txt を作成**

```
PyQt6>=6.6.0
SQLAlchemy>=2.0.0
psycopg2-binary>=2.9.0
reportlab>=4.0.0
openpyxl>=3.1.0
```

- [ ] **Step 3: requirements-dev.txt を作成**

```
pytest>=8.0.0
pytest-qt>=4.4.0
```

- [ ] **Step 4: パッケージインストール**

```powershell
pip install -r requirements.txt -r requirements-dev.txt
```

期待出力: `Successfully installed ...`

- [ ] **Step 5: ディレクトリ構造を作成**

```powershell
$dirs = @(
  "app", "app\database", "app\services", "app\ui", "app\utils",
  "tests", "docs"
)
foreach ($d in $dirs) {
  New-Item -ItemType Directory -Path $d -Force
  New-Item -ItemType File -Path "$d\__init__.py" -Force
}
```

- [ ] **Step 6: .gitignore を作成**

```
__pycache__/
*.pyc
*.db
*.db-shm
*.db-wal
.env
~/.cci-billing/
dist/
build/
*.spec
```

- [ ] **Step 7: コミット**

```powershell
git add .
git commit -m "chore: プロジェクト初期化"
```

---

## Task 2: 設定ファイル管理 (app_config.py / current_user.py)

**Files:**
- Create: `app/utils/app_config.py`
- Create: `app/utils/current_user.py`

- [ ] **Step 1: app_config.py を作成**

```python
# app/utils/app_config.py
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".cci-billing"
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_first_run() -> bool:
    return not CONFIG_FILE.exists() or not get_config().get("db_configured")


def get_db_url() -> str:
    config = get_config()
    if config.get("db_type") == "postgresql":
        host = config["host"]
        port = config.get("port", 5432)
        database = config["database"]
        user = config["user"]
        password = config["password"]
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return "sqlite:///cci_billing.db"
```

- [ ] **Step 2: current_user.py を作成**

```python
# app/utils/current_user.py
_staff_id: int | None = None
_staff_name: str = ""


def set_current(staff_id: int, staff_name: str) -> None:
    global _staff_id, _staff_name
    _staff_id = staff_id
    _staff_name = staff_name


def get_id() -> int | None:
    return _staff_id


def get_name() -> str:
    return _staff_name


def clear() -> None:
    global _staff_id, _staff_name
    _staff_id = None
    _staff_name = ""


def is_logged_in() -> bool:
    return _staff_id is not None
```

- [ ] **Step 3: コミット**

```powershell
git add app/utils/app_config.py app/utils/current_user.py
git commit -m "feat: 設定ファイル管理・ログインユーザー状態管理を追加"
```

---

## Task 3: DB接続管理 (connection.py)

**Files:**
- Create: `app/database/connection.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_models.py
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database.models import Base


def test_create_all_tables():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # テーブルが存在することを確認
    result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    tables = {row[0] for row in result}
    assert "staff" in tables
    assert "categories" in tables
    assert "item_templates" in tables
    assert "members_master" in tables
    assert "company_settings" in tables
    session.close()
```

- [ ] **Step 2: テストを実行して失敗を確認**

```powershell
pytest tests/test_models.py -v
```

期待出力: `ImportError` または `ModuleNotFoundError`（モデル未定義）

- [ ] **Step 3: connection.py を作成**

```python
# app/database/connection.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.utils.app_config import get_db_url

_SessionFactory = None


def get_engine(url: str | None = None):
    return create_engine(url or get_db_url(), echo=False)


def init_db(url: str | None = None):
    global _SessionFactory
    from app.database.models import Base
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    _SessionFactory = sessionmaker(bind=engine)


def get_session() -> Session:
    if _SessionFactory is None:
        init_db()
    return _SessionFactory()
```

---

## Task 4: 全モデル定義 (models.py)

**Files:**
- Create: `app/database/models.py`

- [ ] **Step 1: models.py を作成**

```python
# app/database/models.py
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime,
    Numeric, Boolean, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Staff(Base):
    __tablename__ = "staff"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


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
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    bank_accounts = relationship("BankAccount", back_populates="company",
                                 cascade="all, delete-orphan")
    seal_images = relationship("SealImage", back_populates="company",
                               cascade="all, delete-orphan")


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company_settings.id"), nullable=False)
    label = Column(String(100), nullable=False, default="")
    bank_name = Column(String(100), default="")
    bank_branch = Column(String(100), default="")
    bank_account_type = Column(String(20), default="普通")
    bank_account_number = Column(String(20), default="")
    bank_account_name = Column(String(100), default="")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    company = relationship("CompanySettings", back_populates="bank_accounts")


class SealImage(Base):
    __tablename__ = "seal_images"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company_settings.id"), nullable=False)
    label = Column(String(100), nullable=False, default="")
    path = Column(String(500), default="")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    company = relationship("CompanySettings", back_populates="seal_images")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    item_templates = relationship("ItemTemplate", back_populates="category")


class ItemTemplate(Base):
    __tablename__ = "item_templates"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String(200), nullable=False)
    unit_price = Column(Numeric(15, 0), default=0)
    unit = Column(String(20), default="式")
    # 10=消費税10%, 8=消費税8%, 0=非課税, -1=不課税
    tax_rate = Column(Integer, default=10)
    # "invoice"=請求書のみ, "receipt"=領収書のみ, "both"=両方
    doc_type = Column(String(20), default="both")
    description = Column(String(300), default="")
    notes = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    category = relationship("Category", back_populates="item_templates")


class Member(Base):
    __tablename__ = "members_master"
    id = Column(Integer, primary_key=True)
    member_number = Column(String(50), nullable=True, unique=True)
    organization_name = Column(String(200), default="")
    organization_kana = Column(String(200), default="")
    representative_name = Column(String(100), default="")
    representative_kana = Column(String(100), default="")
    postal_code = Column(String(10), default="")
    address = Column(String(300), default="")
    phone = Column(String(50), default="")
    email = Column(String(200), default="")
    is_member = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    name_history = relationship("MemberNameHistory", back_populates="member",
                                cascade="all, delete-orphan")


class MemberNameHistory(Base):
    __tablename__ = "member_name_history"
    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("members_master.id"), nullable=False)
    organization_name = Column(String(200), default="")
    representative_name = Column(String(100), default="")
    changed_at = Column(DateTime, default=datetime.now)
    reason = Column(String(200), default="")

    member = relationship("Member", back_populates="name_history")


class OperationLog(Base):
    __tablename__ = "operation_logs"
    id = Column(Integer, primary_key=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    staff_name = Column(String(100), default="")
    action = Column(String(100), nullable=False)
    target_type = Column(String(50), default="")
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


# ── Plan 2 以降で使用するテーブル（先行定義）──────────────────────

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    fiscal_year = Column(Integer, nullable=False)
    project_type = Column(String(20), default="list")  # "list" or "counter"
    status = Column(String(20), default="draft")  # draft/active/closed/archived
    issue_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ProjectTemplate(Base):
    __tablename__ = "project_templates"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    item_template_id = Column(Integer, ForeignKey("item_templates.id"), nullable=False)
    sort_order = Column(Integer, default=0)
    unit_price_override = Column(Numeric(15, 0), nullable=True)


class ProjectMember(Base):
    __tablename__ = "project_members"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members_master.id"), nullable=True)
    sort_order = Column(Integer, default=0)


class Issuance(Base):
    __tablename__ = "issuances"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    project_member_id = Column(Integer, ForeignKey("project_members.id"), nullable=True)
    recipient_organization = Column(String(200), default="")
    recipient_name = Column(String(100), default="")
    doc_type = Column(String(20), nullable=False)  # invoice / receipt
    doc_number = Column(String(50), default="")
    status = Column(String(20), default="準備中")  # 準備中/発行済み/支払済み
    delivery_method = Column(String(20), default="窓口手渡し")
    amount = Column(Numeric(15, 0), default=0)
    pdf_path = Column(String(500), default="")
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    staff_name = Column(String(100), default="")
    issued_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    lines = relationship("IssuanceLine", back_populates="issuance",
                         cascade="all, delete-orphan")


class IssuanceLine(Base):
    __tablename__ = "issuance_lines"
    id = Column(Integer, primary_key=True)
    issuance_id = Column(Integer, ForeignKey("issuances.id"), nullable=False)
    item_template_id = Column(Integer, ForeignKey("item_templates.id"), nullable=True)
    item_name = Column(String(300), nullable=False)
    quantity = Column(Numeric(10, 2), default=1)
    unit = Column(String(20), default="式")
    unit_price = Column(Numeric(15, 0), default=0)
    tax_rate = Column(Integer, default=10)
    line_total = Column(Numeric(15, 0), default=0)

    issuance = relationship("Issuance", back_populates="lines")


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    issuance_id = Column(Integer, ForeignKey("issuances.id"), nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(15, 0), nullable=False)
    payment_method = Column(String(20), default="現金")  # 現金/振込/その他
    notes = Column(String(200), default="")
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    staff_name = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.now)


class EmailTemplate(Base):
    __tablename__ = "email_templates"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    subject = Column(String(200), nullable=False)
    body = Column(Text, default="")
    template_type = Column(String(20), default="invoice")  # invoice/receipt/reminder
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
```

- [ ] **Step 2: conftest.py を作成**

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
```

- [ ] **Step 3: テストを実行してパスを確認**

```powershell
pytest tests/test_models.py -v
```

期待出力: `PASSED`

- [ ] **Step 4: コミット**

```powershell
git add app/database/ tests/conftest.py tests/test_models.py
git commit -m "feat: DBモデル全定義・接続管理を追加"
```

---

## Task 5: スタッフサービス

**Files:**
- Create: `app/services/staff_service.py`
- Create: `tests/test_staff_service.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_staff_service.py
from app.database.models import Staff
from app.services.staff_service import (
    create_staff, get_active_staff, deactivate_staff
)


def test_create_staff(db_session):
    staff = create_staff(db_session, "田中 太郎")
    assert staff.id is not None
    assert staff.name == "田中 太郎"
    assert staff.is_active is True


def test_get_active_staff(db_session):
    create_staff(db_session, "田中 太郎")
    create_staff(db_session, "鈴木 花子")
    result = get_active_staff(db_session)
    assert len(result) == 2


def test_deactivate_staff(db_session):
    staff = create_staff(db_session, "田中 太郎")
    deactivate_staff(db_session, staff.id)
    result = get_active_staff(db_session)
    assert len(result) == 0


def test_duplicate_name_raises(db_session):
    create_staff(db_session, "田中 太郎")
    import pytest
    with pytest.raises(Exception):
        create_staff(db_session, "田中 太郎")
```

- [ ] **Step 2: テスト実行→失敗確認**

```powershell
pytest tests/test_staff_service.py -v
```

期待出力: `ImportError`

- [ ] **Step 3: staff_service.py を作成**

```python
# app/services/staff_service.py
from sqlalchemy.orm import Session
from app.database.models import Staff


def create_staff(session: Session, name: str) -> Staff:
    staff = Staff(name=name)
    session.add(staff)
    session.commit()
    session.refresh(staff)
    return staff


def get_active_staff(session: Session) -> list[Staff]:
    return session.query(Staff).filter_by(is_active=True).order_by(Staff.name).all()


def get_all_staff(session: Session) -> list[Staff]:
    return session.query(Staff).order_by(Staff.name).all()


def deactivate_staff(session: Session, staff_id: int) -> None:
    staff = session.get(Staff, staff_id)
    if staff:
        staff.is_active = False
        session.commit()


def reactivate_staff(session: Session, staff_id: int) -> None:
    staff = session.get(Staff, staff_id)
    if staff:
        staff.is_active = True
        session.commit()


def update_staff_name(session: Session, staff_id: int, name: str) -> Staff:
    staff = session.get(Staff, staff_id)
    staff.name = name
    session.commit()
    return staff
```

- [ ] **Step 4: テスト実行→パス確認**

```powershell
pytest tests/test_staff_service.py -v
```

期待出力: `4 passed`

- [ ] **Step 5: コミット**

```powershell
git add app/services/staff_service.py tests/test_staff_service.py
git commit -m "feat: スタッフサービスを追加"
```

---

## Task 6: カテゴリサービス

**Files:**
- Create: `app/services/category_service.py`
- Create: `tests/test_category_service.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_category_service.py
from app.services.category_service import (
    create_category, get_active_categories, update_category, deactivate_category
)


def test_create_category(db_session):
    cat = create_category(db_session, "青年部", sort_order=0)
    assert cat.id is not None
    assert cat.name == "青年部"


def test_get_active_categories_sorted(db_session):
    create_category(db_session, "青年部", sort_order=1)
    create_category(db_session, "女性部", sort_order=0)
    cats = get_active_categories(db_session)
    assert cats[0].name == "女性部"
    assert cats[1].name == "青年部"


def test_deactivate_category(db_session):
    cat = create_category(db_session, "青年部")
    deactivate_category(db_session, cat.id)
    assert get_active_categories(db_session) == []
```

- [ ] **Step 2: テスト実行→失敗確認**

```powershell
pytest tests/test_category_service.py -v
```

- [ ] **Step 3: category_service.py を作成**

```python
# app/services/category_service.py
from sqlalchemy.orm import Session
from app.database.models import Category


def create_category(session: Session, name: str, sort_order: int = 0) -> Category:
    cat = Category(name=name, sort_order=sort_order)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat


def get_active_categories(session: Session) -> list[Category]:
    return (session.query(Category)
            .filter_by(is_active=True)
            .order_by(Category.sort_order, Category.name)
            .all())


def update_category(session: Session, category_id: int,
                    name: str, sort_order: int) -> Category:
    cat = session.get(Category, category_id)
    cat.name = name
    cat.sort_order = sort_order
    session.commit()
    return cat


def deactivate_category(session: Session, category_id: int) -> None:
    cat = session.get(Category, category_id)
    if cat:
        cat.is_active = False
        session.commit()
```

- [ ] **Step 4: テスト→パス確認**

```powershell
pytest tests/test_category_service.py -v
```

期待出力: `3 passed`

- [ ] **Step 5: コミット**

```powershell
git add app/services/category_service.py tests/test_category_service.py
git commit -m "feat: カテゴリサービスを追加"
```

---

## Task 7: 請求項目テンプレートサービス

**Files:**
- Create: `app/services/item_template_service.py`
- Create: `tests/test_item_template_service.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_item_template_service.py
from app.services.category_service import create_category
from app.services.item_template_service import (
    create_item_template, get_templates_by_category, get_all_active_templates,
    update_item_template, deactivate_item_template
)


def test_create_template(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(
        db_session,
        category_id=cat.id,
        name="青年部会費",
        unit_price=10000,
        unit="式",
        tax_rate=0,
        doc_type="invoice",
        description=""
    )
    assert tmpl.id is not None
    assert tmpl.unit_price == 10000


def test_get_templates_by_category(db_session):
    cat1 = create_category(db_session, "青年部")
    cat2 = create_category(db_session, "検定")
    create_item_template(db_session, cat1.id, "青年部会費", 10000, "式", 0, "invoice", "")
    create_item_template(db_session, cat2.id, "珠算検定受験料", 3000, "人", 0, "receipt", "珠算検定受験料として")
    result = get_templates_by_category(db_session, cat1.id)
    assert len(result) == 1
    assert result[0].name == "青年部会費"


def test_deactivate_template(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費", 10000, "式", 0, "invoice", "")
    deactivate_item_template(db_session, tmpl.id)
    assert get_all_active_templates(db_session) == []
```

- [ ] **Step 2: テスト実行→失敗確認**

```powershell
pytest tests/test_item_template_service.py -v
```

- [ ] **Step 3: item_template_service.py を作成**

```python
# app/services/item_template_service.py
from sqlalchemy.orm import Session
from app.database.models import ItemTemplate


def create_item_template(session: Session, category_id: int, name: str,
                          unit_price: int, unit: str, tax_rate: int,
                          doc_type: str, description: str) -> ItemTemplate:
    tmpl = ItemTemplate(
        category_id=category_id, name=name, unit_price=unit_price,
        unit=unit, tax_rate=tax_rate, doc_type=doc_type, description=description
    )
    session.add(tmpl)
    session.commit()
    session.refresh(tmpl)
    return tmpl


def get_templates_by_category(session: Session, category_id: int) -> list[ItemTemplate]:
    return (session.query(ItemTemplate)
            .filter_by(category_id=category_id, is_active=True)
            .order_by(ItemTemplate.name)
            .all())


def get_all_active_templates(session: Session) -> list[ItemTemplate]:
    return (session.query(ItemTemplate)
            .filter_by(is_active=True)
            .order_by(ItemTemplate.category_id, ItemTemplate.name)
            .all())


def update_item_template(session: Session, template_id: int, **kwargs) -> ItemTemplate:
    tmpl = session.get(ItemTemplate, template_id)
    for key, value in kwargs.items():
        setattr(tmpl, key, value)
    session.commit()
    return tmpl


def deactivate_item_template(session: Session, template_id: int) -> None:
    tmpl = session.get(ItemTemplate, template_id)
    if tmpl:
        tmpl.is_active = False
        session.commit()
```

- [ ] **Step 4: テスト→パス確認**

```powershell
pytest tests/test_item_template_service.py -v
```

期待出力: `3 passed`

- [ ] **Step 5: コミット**

```powershell
git add app/services/item_template_service.py tests/test_item_template_service.py
git commit -m "feat: 請求項目テンプレートサービスを追加"
```

---

## Task 8: 会員サービス（CRUD・検索・名称変更）

**Files:**
- Create: `app/services/member_service.py`
- Create: `tests/test_member_service.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_member_service.py
from app.services.member_service import (
    create_member, search_members, update_member_name, get_member_by_id
)


def test_create_member(db_session):
    m = create_member(db_session, member_number="A-001",
                      organization_name="○○商事", organization_kana="マルマルショウジ",
                      representative_name="田中 太郎", representative_kana="タナカ タロウ")
    assert m.id is not None
    assert m.member_number == "A-001"


def test_search_by_organization_name(db_session):
    create_member(db_session, member_number="A-001", organization_name="○○商事",
                  organization_kana="マルマルショウジ")
    create_member(db_session, member_number="A-002", organization_name="△△産業",
                  organization_kana="サンカクサンカクサンギョウ")
    result = search_members(db_session, "商事")
    assert len(result) == 1
    assert result[0].organization_name == "○○商事"


def test_search_by_member_number(db_session):
    create_member(db_session, member_number="A-001", organization_name="○○商事",
                  organization_kana="マルマルショウジ")
    result = search_members(db_session, "A-001")
    assert len(result) == 1


def test_search_by_kana(db_session):
    create_member(db_session, member_number="A-001", organization_name="○○商事",
                  organization_kana="マルマルショウジ")
    result = search_members(db_session, "マルマル")
    assert len(result) == 1


def test_update_name_creates_history(db_session):
    m = create_member(db_session, member_number="A-001",
                      organization_name="旧社名", organization_kana="キュウシャメイ")
    update_member_name(db_session, m.id, new_organization_name="新社名",
                       new_organization_kana="シンシャメイ", reason="商号変更")
    updated = get_member_by_id(db_session, m.id)
    assert updated.organization_name == "新社名"
    assert len(updated.name_history) == 1
    assert updated.name_history[0].organization_name == "旧社名"
```

- [ ] **Step 2: テスト実行→失敗確認**

```powershell
pytest tests/test_member_service.py -v
```

- [ ] **Step 3: member_service.py を作成**

```python
# app/services/member_service.py
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.database.models import Member, MemberNameHistory


def create_member(session: Session, member_number: str | None = None,
                  organization_name: str = "", organization_kana: str = "",
                  representative_name: str = "", representative_kana: str = "",
                  postal_code: str = "", address: str = "",
                  phone: str = "", email: str = "",
                  is_member: bool = True, notes: str = "") -> Member:
    m = Member(
        member_number=member_number or None,
        organization_name=organization_name,
        organization_kana=organization_kana,
        representative_name=representative_name,
        representative_kana=representative_kana,
        postal_code=postal_code, address=address,
        phone=phone, email=email,
        is_member=is_member, notes=notes
    )
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def get_member_by_id(session: Session, member_id: int) -> Member | None:
    return session.get(Member, member_id)


def search_members(session: Session, query: str,
                   active_only: bool = True) -> list[Member]:
    q = session.query(Member)
    if active_only:
        q = q.filter(Member.is_active.is_(True))
    if query:
        like = f"%{query}%"
        q = q.filter(or_(
            Member.member_number.ilike(f"{query}%"),
            Member.organization_name.ilike(like),
            Member.organization_kana.ilike(f"{query}%"),
            Member.representative_name.ilike(like),
            Member.representative_kana.ilike(f"{query}%"),
        ))
    return q.order_by(Member.organization_kana, Member.organization_name).all()


def update_member_name(session: Session, member_id: int,
                       new_organization_name: str | None = None,
                       new_organization_kana: str | None = None,
                       new_representative_name: str | None = None,
                       new_representative_kana: str | None = None,
                       reason: str = "") -> Member:
    m = session.get(Member, member_id)
    history = MemberNameHistory(
        member_id=m.id,
        organization_name=m.organization_name,
        representative_name=m.representative_name,
        changed_at=datetime.now(),
        reason=reason
    )
    session.add(history)
    if new_organization_name is not None:
        m.organization_name = new_organization_name
    if new_organization_kana is not None:
        m.organization_kana = new_organization_kana
    if new_representative_name is not None:
        m.representative_name = new_representative_name
    if new_representative_kana is not None:
        m.representative_kana = new_representative_kana
    session.commit()
    session.refresh(m)
    return m


def deactivate_member(session: Session, member_id: int) -> None:
    m = session.get(Member, member_id)
    if m:
        m.is_active = False
        session.commit()


def get_recipient_label(member: Member) -> str:
    if member.organization_name and member.representative_name:
        return f"{member.organization_name} {member.representative_name} 様"
    elif member.organization_name:
        return f"{member.organization_name} 御中"
    else:
        return f"{member.representative_name} 様"
```

- [ ] **Step 4: テスト→パス確認**

```powershell
pytest tests/test_member_service.py -v
```

期待出力: `5 passed`

- [ ] **Step 5: コミット**

```powershell
git add app/services/member_service.py tests/test_member_service.py
git commit -m "feat: 会員サービス（CRUD・検索・名称変更履歴）を追加"
```

---

## Task 9: Excel・クリップボード取込ユーティリティ

**Files:**
- Create: `app/utils/excel_utils.py`
- Create: `tests/test_excel_utils.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_excel_utils.py
from app.utils.excel_utils import parse_tsv_text, MEMBER_COLUMNS


def test_parse_tsv_basic():
    tsv = "A-001\t○○商事\tマルマルショウジ\t田中 太郎\tタナカ タロウ\t123-4567\t東京都\t03-1234-5678\ttest@example.com"
    rows = parse_tsv_text(tsv)
    assert len(rows) == 1
    assert rows[0]["member_number"] == "A-001"
    assert rows[0]["organization_name"] == "○○商事"
    assert rows[0]["representative_name"] == "田中 太郎"


def test_parse_tsv_multiple_rows():
    tsv = "A-001\t○○商事\t\t\t\t\t\t\t\nA-002\t△△産業\t\t\t\t\t\t\t"
    rows = parse_tsv_text(tsv)
    assert len(rows) == 2


def test_parse_tsv_skips_empty_rows():
    tsv = "A-001\t○○商事\t\t\t\t\t\t\t\n\n\n"
    rows = parse_tsv_text(tsv)
    assert len(rows) == 1


def test_required_field_validation():
    # 事業所名も代表者名もない行はスキップ
    tsv = "A-001\t\t\t\t\t\t\t\t"
    rows = parse_tsv_text(tsv)
    assert len(rows) == 0
```

- [ ] **Step 2: テスト実行→失敗確認**

```powershell
pytest tests/test_excel_utils.py -v
```

- [ ] **Step 3: excel_utils.py を作成**

```python
# app/utils/excel_utils.py
from pathlib import Path
import openpyxl

# Excelの列順（この順番でTSVも貼り付ける）
MEMBER_COLUMNS = [
    "member_number",       # 会員番号
    "organization_name",   # 事業所名
    "organization_kana",   # 事業所名フリガナ
    "representative_name", # 代表者名
    "representative_kana", # 代表者名フリガナ
    "postal_code",         # 郵便番号
    "address",             # 住所
    "phone",               # 電話
    "email",               # メール
]


def parse_tsv_text(text: str) -> list[dict]:
    """ExcelからコピーしたTSVテキストを会員データのリストに変換する"""
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cells = line.split("\t")
        # 列数が足りない場合は空文字で補完
        while len(cells) < len(MEMBER_COLUMNS):
            cells.append("")
        row = {col: cells[i].strip() for i, col in enumerate(MEMBER_COLUMNS)}
        # 事業所名または代表者名のどちらかが必須
        if not row["organization_name"] and not row["representative_name"]:
            continue
        rows.append(row)
    return rows


def parse_excel_file(file_path: str, sheet_name: str | None = None,
                     header_row: int = 1) -> list[dict]:
    """Excelファイルを読み込んで会員データのリストに変換する"""
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < header_row:
            continue
        cells = [str(c).strip() if c is not None else "" for c in row]
        while len(cells) < len(MEMBER_COLUMNS):
            cells.append("")
        data = {col: cells[i] for i, col in enumerate(MEMBER_COLUMNS)}
        if not data["organization_name"] and not data["representative_name"]:
            continue
        rows.append(data)
    wb.close()
    return rows
```

- [ ] **Step 4: テスト→パス確認**

```powershell
pytest tests/test_excel_utils.py -v
```

期待出力: `4 passed`

- [ ] **Step 5: コミット**

```powershell
git add app/utils/excel_utils.py tests/test_excel_utils.py
git commit -m "feat: Excel・クリップボード取込ユーティリティを追加"
```

---

## Task 10: テーマ・メインウィンドウ基盤 (UI)

**Files:**
- Create: `app/ui/theme.py`
- Create: `app/ui/main_window.py`
- Create: `main.py`

- [ ] **Step 1: theme.py を作成（既存アプリのデザイントークンを流用）**

```python
# app/ui/theme.py
STYLESHEET = """
QGroupBox {
    border: 1px solid #E2E8F0; border-radius: 8px;
    margin-top: 12px; padding: 14px 10px 10px 10px;
    background: white; font-family: "Meiryo UI";
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: #2563EB; font-weight: bold; font-size: 12px;
}
QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox {
    border: 1px solid #CBD5E1; border-radius: 5px;
    padding: 5px 10px; background: white; color: #1E293B;
    font-family: "Meiryo UI"; font-size: 12px; min-height: 28px;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {
    border: 1.5px solid #3B82F6; background: #F8FAFF;
}
QTableWidget {
    border: 1px solid #E2E8F0; border-radius: 6px;
    gridline-color: #F1F5F9; background: white;
    font-family: "Meiryo UI"; font-size: 12px;
    selection-background-color: #DBEAFE; selection-color: #1E293B;
}
QTableWidget::item { padding: 4px 6px; }
QTableWidget::item:selected { background: #DBEAFE; color: #1E293B; }
QHeaderView::section {
    background: #F8FAFC; border: none;
    border-right: 1px solid #E2E8F0;
    border-bottom: 2px solid #3B82F6;
    padding: 7px 8px; font-weight: bold;
    font-size: 11px; color: #475569; font-family: "Meiryo UI";
}
QPushButton { font-family: "Meiryo UI"; font-size: 12px; }
QLabel { font-family: "Meiryo UI"; color: #1E293B; }
QTabBar::tab {
    padding: 8px 18px; border: 1px solid #E2E8F0;
    border-bottom: none; border-radius: 6px 6px 0 0;
    background: #F1F5F9; color: #64748B;
    font-family: "Meiryo UI"; font-size: 12px; margin-right: 2px;
}
QTabBar::tab:selected {
    background: white; color: #2563EB;
    font-weight: bold; border-bottom: 2px solid white;
}
QScrollBar:vertical { width: 6px; background: transparent; }
QScrollBar::handle:vertical {
    background: #CBD5E1; border-radius: 3px; min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

PRIMARY = "#2563EB"
DANGER  = "#DC2626"
SUCCESS = "#16A34A"
```

- [ ] **Step 2: main_window.py を作成（タブの骨格のみ）**

```python
# app/ui/main_window.py
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QLabel
from PyQt6.QtCore import pyqtSignal


class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("商工会議所請求書・領収書発行システム")
        self.resize(1200, 800)
        self._build_tabs()

    def _build_tabs(self):
        tabs = QTabWidget()
        # Plan 1 で実装するタブ
        tabs.addTab(QLabel("ダッシュボード（Plan 2で実装）"), "ダッシュボード")
        tabs.addTab(QLabel("事業管理（Plan 2で実装）"), "事業管理")
        tabs.addTab(QLabel("発行（Plan 2で実装）"), "発行")
        tabs.addTab(QLabel("レポート（Plan 4で実装）"), "レポート")

        from app.ui.settings_tab import SettingsTab
        tabs.addTab(SettingsTab(), "設定")

        self.setCentralWidget(tabs)
```

- [ ] **Step 3: settings_tab.py を作成（骨格）**

```python
# app/ui/settings_tab.py
from PyQt6.QtWidgets import QWidget, QTabWidget, QLabel, QVBoxLayout


class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        inner = QTabWidget()

        from app.ui.company_settings import CompanySettingsWidget
        from app.ui.staff_management import StaffManagementWidget
        from app.ui.category_management import CategoryManagementWidget
        from app.ui.item_template_management import ItemTemplateManagementWidget
        from app.ui.member_list import MemberListWidget

        inner.addTab(CompanySettingsWidget(), "発行元情報")
        inner.addTab(StaffManagementWidget(), "スタッフ管理")
        inner.addTab(CategoryManagementWidget(), "カテゴリ")
        inner.addTab(ItemTemplateManagementWidget(), "請求項目テンプレート")
        inner.addTab(MemberListWidget(), "会員マスタ")
        layout.addWidget(inner)
```

- [ ] **Step 4: コミット（UIスタブ）**

```powershell
git add app/ui/theme.py app/ui/main_window.py app/ui/settings_tab.py
git commit -m "feat: テーマ・メインウィンドウ・設定タブの骨格を追加"
```

---

## Task 11: 初回設定ウィザード (first_run_wizard.py)

**Files:**
- Create: `app/ui/first_run_wizard.py`

- [ ] **Step 1: first_run_wizard.py を作成**

```python
# app/ui/first_run_wizard.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QMessageBox, QFormLayout
)
from PyQt6.QtCore import Qt
from app.utils.app_config import save_config, get_db_url


class FirstRunWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("初期設定")
        self.setFixedSize(480, 340)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("データベースの接続先を設定してください。"))

        self._db_type = QComboBox()
        self._db_type.addItems(["PostgreSQL（複数人共有）", "SQLite（個人使用）"])
        self._db_type.currentIndexChanged.connect(self._on_type_change)

        form = QFormLayout()
        self._host = QLineEdit("localhost")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(5432)
        self._database = QLineEdit("cci_billing")
        self._user = QLineEdit("postgres")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("DB種別", self._db_type)
        form.addRow("ホスト", self._host)
        form.addRow("ポート", self._port)
        form.addRow("データベース名", self._database)
        form.addRow("ユーザー名", self._user)
        form.addRow("パスワード", self._password)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_test = QPushButton("接続テスト")
        btn_test.clicked.connect(self._test_connection)
        btn_ok = QPushButton("保存して開始")
        btn_ok.clicked.connect(self._save)
        btn_row.addWidget(btn_test)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _on_type_change(self, index):
        is_pg = index == 0
        for w in [self._host, self._port, self._database, self._user, self._password]:
            w.setEnabled(is_pg)

    def _build_config(self) -> dict:
        if self._db_type.currentIndex() == 0:
            return {
                "db_type": "postgresql",
                "host": self._host.text().strip(),
                "port": self._port.value(),
                "database": self._database.text().strip(),
                "user": self._user.text().strip(),
                "password": self._password.text(),
                "db_configured": True,
            }
        return {"db_type": "sqlite", "db_configured": True}

    def _test_connection(self):
        config = self._build_config()
        save_config(config)
        try:
            from app.database.connection import init_db
            init_db()
            QMessageBox.information(self, "成功", "接続に成功しました。")
        except Exception as e:
            QMessageBox.critical(self, "接続エラー", str(e))

    def _save(self):
        config = self._build_config()
        save_config(config)
        try:
            from app.database.connection import init_db
            init_db()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"DB初期化に失敗しました：\n{e}")
```

- [ ] **Step 2: コミット**

```powershell
git add app/ui/first_run_wizard.py
git commit -m "feat: 初回DB接続設定ウィザードを追加"
```

---

## Task 12: ログイン画面 (login_dialog.py)

**Files:**
- Create: `app/ui/login_dialog.py`

- [ ] **Step 1: login_dialog.py を作成**

```python
# app/ui/login_dialog.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.staff_service import get_active_staff
from app.utils import current_user


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ログイン")
        self.setFixedSize(320, 400)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("担当者を選択してください"))

        self._list = QListWidget()
        session = get_session()
        try:
            for staff in get_active_staff(session):
                item = QListWidgetItem(staff.name)
                item.setData(Qt.ItemDataRole.UserRole, (staff.id, staff.name))
                self._list.addItem(item)
        finally:
            session.close()

        self._list.itemDoubleClicked.connect(self._login)
        layout.addWidget(self._list)

        btn = QPushButton("ログイン")
        btn.clicked.connect(self._login)
        layout.addWidget(btn)

    def _login(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.warning(self, "選択エラー", "担当者を選択してください。")
            return
        staff_id, staff_name = item.data(Qt.ItemDataRole.UserRole)
        current_user.set_current(staff_id, staff_name)
        self.accept()
```

- [ ] **Step 2: コミット**

```powershell
git add app/ui/login_dialog.py
git commit -m "feat: スタッフログイン画面を追加"
```

---

## Task 13: スタッフ管理UI (staff_management.py)

**Files:**
- Create: `app/ui/staff_management.py`

- [ ] **Step 1: staff_management.py を作成**

```python
# app/ui/staff_management.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.staff_service import (
    create_staff, get_all_staff, deactivate_staff, reactivate_staff
)


class StaffManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        add_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("スタッフ名を入力")
        btn_add = QPushButton("追加")
        btn_add.clicked.connect(self._add)
        add_row.addWidget(QLabel("氏名："))
        add_row.addWidget(self._name_input)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["ID", "氏名", "状態"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_deact = QPushButton("無効化")
        btn_deact.clicked.connect(self._deactivate)
        btn_react = QPushButton("有効化")
        btn_react.clicked.connect(self._reactivate)
        btn_row.addWidget(btn_deact)
        btn_row.addWidget(btn_react)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _load(self):
        session = get_session()
        try:
            staff_list = get_all_staff(session)
        finally:
            session.close()
        self._table.setRowCount(0)
        for s in staff_list:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self._table.setItem(row, 1, QTableWidgetItem(s.name))
            status = "有効" if s.is_active else "無効"
            self._table.setItem(row, 2, QTableWidgetItem(status))

    def _add(self):
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "入力エラー", "氏名を入力してください。")
            return
        session = get_session()
        try:
            create_staff(session, name)
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
            return
        finally:
            session.close()
        self._name_input.clear()
        self._load()

    def _selected_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        return int(self._table.item(row, 0).text())

    def _deactivate(self):
        staff_id = self._selected_id()
        if staff_id is None:
            return
        session = get_session()
        try:
            deactivate_staff(session, staff_id)
        finally:
            session.close()
        self._load()

    def _reactivate(self):
        staff_id = self._selected_id()
        if staff_id is None:
            return
        session = get_session()
        try:
            reactivate_staff(session, staff_id)
        finally:
            session.close()
        self._load()
```

- [ ] **Step 2: コミット**

```powershell
git add app/ui/staff_management.py
git commit -m "feat: スタッフ管理UIを追加"
```

---

## Task 14: カテゴリ・テンプレート管理UI

**Files:**
- Create: `app/ui/category_management.py`
- Create: `app/ui/item_template_management.py`

- [ ] **Step 1: category_management.py を作成**

```python
# app/ui/category_management.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel, QMessageBox, QSpinBox
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.category_service import (
    create_category, get_active_categories, update_category, deactivate_category
)


class CategoryManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        add_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("カテゴリ名（例：青年部）")
        self._order_input = QSpinBox()
        self._order_input.setRange(0, 999)
        btn_add = QPushButton("追加")
        btn_add.clicked.connect(self._add)
        add_row.addWidget(QLabel("名称："))
        add_row.addWidget(self._name_input)
        add_row.addWidget(QLabel("表示順："))
        add_row.addWidget(self._order_input)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        self._list = QListWidget()
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_del = QPushButton("削除（無効化）")
        btn_del.clicked.connect(self._deactivate)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _load(self):
        session = get_session()
        try:
            cats = get_active_categories(session)
        finally:
            session.close()
        self._list.clear()
        for c in cats:
            item = QListWidgetItem(f"{c.name}（表示順:{c.sort_order}）")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self._list.addItem(item)

    def _add(self):
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "入力エラー", "カテゴリ名を入力してください。")
            return
        session = get_session()
        try:
            create_category(session, name, self._order_input.value())
        finally:
            session.close()
        self._name_input.clear()
        self._load()

    def _deactivate(self):
        item = self._list.currentItem()
        if not item:
            return
        cat_id = item.data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            deactivate_category(session, cat_id)
        finally:
            session.close()
        self._load()
```

- [ ] **Step 2: item_template_management.py を作成**

```python
# app/ui/item_template_management.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QComboBox, QSpinBox, QDialog,
    QFormLayout, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.category_service import get_active_categories
from app.services.item_template_service import (
    create_item_template, get_all_active_templates, deactivate_item_template
)

TAX_RATE_OPTIONS = [("消費税10%", 10), ("消費税8%", 8), ("非課税", 0), ("不課税", -1)]
DOC_TYPE_OPTIONS = [("請求書・領収書両方", "both"), ("請求書のみ", "invoice"), ("領収書のみ", "receipt")]


class ItemTemplateManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("＋ 新規テンプレート")
        btn_add.clicked.connect(self._add)
        btn_del = QPushButton("無効化")
        btn_del.clicked.connect(self._deactivate)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["カテゴリ", "項目名", "単価", "単位", "税区分", "書類種別"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

    def _load(self):
        session = get_session()
        try:
            templates = get_all_active_templates(session)
        finally:
            session.close()
        self._table.setRowCount(0)
        for t in templates:
            row = self._table.rowCount()
            self._table.insertRow(row)
            cat_name = t.category.name if t.category else ""
            tax_label = next((l for l, v in TAX_RATE_OPTIONS if v == t.tax_rate), str(t.tax_rate))
            doc_label = next((l for l, v in DOC_TYPE_OPTIONS if v == t.doc_type), t.doc_type)
            for col, val in enumerate([cat_name, t.name, f"¥{int(t.unit_price):,}",
                                        t.unit, tax_label, doc_label]):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, t.id)
                self._table.setItem(row, col, item)

    def _add(self):
        dlg = ItemTemplateDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _deactivate(self):
        row = self._table.currentRow()
        if row < 0:
            return
        tmpl_id = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            deactivate_item_template(session, tmpl_id)
        finally:
            session.close()
        self._load()


class ItemTemplateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("請求項目テンプレート登録")
        self.setFixedSize(400, 360)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._category = QComboBox()
        session = get_session()
        try:
            for cat in get_active_categories(session):
                self._category.addItem(cat.name, cat.id)
        finally:
            session.close()

        self._name = QLineEdit()
        self._name.setPlaceholderText("例：青年部会費")
        self._unit_price = QSpinBox()
        self._unit_price.setRange(0, 9999999)
        self._unit = QLineEdit("式")
        self._tax_rate = QComboBox()
        for label, value in TAX_RATE_OPTIONS:
            self._tax_rate.addItem(label, value)
        self._doc_type = QComboBox()
        for label, value in DOC_TYPE_OPTIONS:
            self._doc_type.addItem(label, value)
        self._description = QLineEdit()
        self._description.setPlaceholderText("但し書き（領収書に使用）")

        form.addRow("カテゴリ", self._category)
        form.addRow("項目名", self._name)
        form.addRow("単価（円）", self._unit_price)
        form.addRow("単位", self._unit)
        form.addRow("税区分", self._tax_rate)
        form.addRow("書類種別", self._doc_type)
        form.addRow("但し書き", self._description)
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
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "入力エラー", "項目名を入力してください。")
            return
        session = get_session()
        try:
            create_item_template(
                session,
                category_id=self._category.currentData(),
                name=name,
                unit_price=self._unit_price.value(),
                unit=self._unit.text().strip() or "式",
                tax_rate=self._tax_rate.currentData(),
                doc_type=self._doc_type.currentData(),
                description=self._description.text().strip()
            )
        finally:
            session.close()
        self.accept()
```

- [ ] **Step 3: コミット**

```powershell
git add app/ui/category_management.py app/ui/item_template_management.py
git commit -m "feat: カテゴリ・請求項目テンプレート管理UIを追加"
```

---

## Task 15: 会員マスタUI（一覧・登録・編集・インポート）

**Files:**
- Create: `app/ui/member_list.py`
- Create: `app/ui/member_form.py`
- Create: `app/ui/member_import.py`

- [ ] **Step 1: member_form.py を作成**

```python
# app/ui/member_form.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QCheckBox, QTextEdit, QPushButton, QLabel, QMessageBox
)
from app.database.connection import get_session
from app.database.models import Member
from app.services.member_service import create_member, update_member_name, get_member_by_id


class MemberFormDialog(QDialog):
    def __init__(self, member_id: int | None = None, parent=None):
        super().__init__(parent)
        self._member_id = member_id
        self.setWindowTitle("会員登録" if member_id is None else "会員編集")
        self.setFixedSize(480, 480)
        self._build()
        if member_id:
            self._load(member_id)

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._member_number = QLineEdit()
        self._member_number.setPlaceholderText("例：A-001（任意）")
        self._org_name = QLineEdit()
        self._org_kana = QLineEdit()
        self._rep_name = QLineEdit()
        self._rep_kana = QLineEdit()
        self._postal = QLineEdit()
        self._address = QLineEdit()
        self._phone = QLineEdit()
        self._email = QLineEdit()
        self._is_member = QCheckBox("会員")
        self._is_member.setChecked(True)
        self._notes = QTextEdit()
        self._notes.setFixedHeight(60)

        form.addRow("会員番号", self._member_number)
        form.addRow("事業所名 *", self._org_name)
        form.addRow("事業所名フリガナ", self._org_kana)
        form.addRow("代表者名", self._rep_name)
        form.addRow("代表者名フリガナ", self._rep_kana)
        form.addRow("郵便番号", self._postal)
        form.addRow("住所", self._address)
        form.addRow("電話", self._phone)
        form.addRow("メール", self._email)
        form.addRow("区分", self._is_member)
        form.addRow("備考", self._notes)
        layout.addWidget(QLabel("※ 事業所名または代表者名のどちらか一方は必須"))
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("保存")
        btn_ok.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _load(self, member_id: int):
        session = get_session()
        try:
            m = get_member_by_id(session, member_id)
            if m:
                self._member_number.setText(m.member_number or "")
                self._org_name.setText(m.organization_name)
                self._org_kana.setText(m.organization_kana)
                self._rep_name.setText(m.representative_name)
                self._rep_kana.setText(m.representative_kana)
                self._postal.setText(m.postal_code)
                self._address.setText(m.address)
                self._phone.setText(m.phone)
                self._email.setText(m.email)
                self._is_member.setChecked(m.is_member)
                self._notes.setPlainText(m.notes)
        finally:
            session.close()

    def _save(self):
        org = self._org_name.text().strip()
        rep = self._rep_name.text().strip()
        if not org and not rep:
            QMessageBox.warning(self, "入力エラー", "事業所名または代表者名を入力してください。")
            return
        session = get_session()
        try:
            if self._member_id is None:
                create_member(
                    session,
                    member_number=self._member_number.text().strip() or None,
                    organization_name=org,
                    organization_kana=self._org_kana.text().strip(),
                    representative_name=rep,
                    representative_kana=self._rep_kana.text().strip(),
                    postal_code=self._postal.text().strip(),
                    address=self._address.text().strip(),
                    phone=self._phone.text().strip(),
                    email=self._email.text().strip(),
                    is_member=self._is_member.isChecked(),
                    notes=self._notes.toPlainText().strip()
                )
            else:
                update_member_name(
                    session, self._member_id,
                    new_organization_name=org,
                    new_organization_kana=self._org_kana.text().strip(),
                    new_representative_name=rep,
                    new_representative_kana=self._rep_kana.text().strip(),
                    reason="手動編集"
                )
        finally:
            session.close()
        self.accept()
```

- [ ] **Step 2: member_import.py を作成**

```python
# app/ui/member_import.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QHeaderView
)
from app.database.connection import get_session
from app.services.member_service import create_member
from app.utils.excel_utils import parse_tsv_text, parse_excel_file, MEMBER_COLUMNS

HEADERS = ["会員番号", "事業所名", "フリガナ", "代表者名", "代表者フリガナ",
           "郵便番号", "住所", "電話", "メール"]


class MemberImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("会員インポート")
        self.resize(800, 600)
        self._rows: list[dict] = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Excelからコピーして下の欄に貼り付けるか、Excelファイルを選択してください。\n"
            "列順：会員番号 / 事業所名 / フリガナ / 代表者名 / 代表者フリガナ / 郵便番号 / 住所 / 電話 / メール"
        ))

        self._paste_area = QTextEdit()
        self._paste_area.setPlaceholderText("ここにExcelの内容を貼り付け（Ctrl+V）")
        self._paste_area.setFixedHeight(100)
        layout.addWidget(self._paste_area)

        btn_row1 = QHBoxLayout()
        btn_parse = QPushButton("貼り付け内容を解析")
        btn_parse.clicked.connect(self._parse_paste)
        btn_file = QPushButton("Excelファイルを選択")
        btn_file.clicked.connect(self._open_file)
        btn_row1.addWidget(btn_parse)
        btn_row1.addWidget(btn_file)
        btn_row1.addStretch()
        layout.addLayout(btn_row1)

        self._table = QTableWidget(0, len(HEADERS))
        self._table.setHorizontalHeaderLabels(HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        btn_row2 = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        self._btn_import = QPushButton("インポート実行")
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._import)
        btn_row2.addWidget(btn_cancel)
        btn_row2.addStretch()
        btn_row2.addWidget(self._btn_import)
        layout.addLayout(btn_row2)

    def _show_rows(self, rows: list[dict]):
        self._rows = rows
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            for c, col in enumerate(MEMBER_COLUMNS):
                self._table.setItem(r, c, QTableWidgetItem(row.get(col, "")))
        self._status_label.setText(f"{len(rows)} 件を読み込みました")
        self._btn_import.setEnabled(len(rows) > 0)

    def _parse_paste(self):
        text = self._paste_area.toPlainText()
        rows = parse_tsv_text(text)
        if not rows:
            QMessageBox.warning(self, "解析エラー", "データが見つかりませんでした。")
            return
        self._show_rows(rows)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Excelファイルを選択", "", "Excel (*.xlsx *.xls)")
        if not path:
            return
        try:
            rows = parse_excel_file(path)
            self._show_rows(rows)
        except Exception as e:
            QMessageBox.critical(self, "読込エラー", str(e))

    def _import(self):
        session = get_session()
        imported = 0
        errors = []
        try:
            for row in self._rows:
                try:
                    create_member(session, **row)
                    imported += 1
                except Exception as e:
                    errors.append(f"{row.get('organization_name', '?')}: {e}")
        finally:
            session.close()
        msg = f"{imported} 件をインポートしました。"
        if errors:
            msg += f"\n失敗 {len(errors)} 件：\n" + "\n".join(errors[:5])
        QMessageBox.information(self, "インポート完了", msg)
        self.accept()
```

- [ ] **Step 3: member_list.py を作成**

```python
# app/ui/member_list.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QLabel, QDialog, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer
from app.database.connection import get_session
from app.services.member_service import search_members, deactivate_member
from app.ui.member_form import MemberFormDialog
from app.ui.member_import import MemberImportDialog


class MemberListWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load("")

    def _build(self):
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("会員番号・事業所名・フリガナ・代表者名で検索")
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(lambda: self._load(self._search.text()))
        self._search.textChanged.connect(lambda: self._search_timer.start(300))
        search_row.addWidget(QLabel("検索："))
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("＋ 新規登録")
        btn_add.clicked.connect(self._add)
        btn_edit = QPushButton("編集")
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton("無効化")
        btn_del.clicked.connect(self._deactivate)
        btn_import = QPushButton("Excelインポート")
        btn_import.clicked.connect(self._import)
        for b in [btn_add, btn_edit, btn_del, btn_import]:
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["会員番号", "事業所名", "代表者名", "電話", "区分"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemDoubleClicked.connect(self._edit)
        layout.addWidget(self._table)

        self._count_label = QLabel("")
        layout.addWidget(self._count_label)

    def _load(self, query: str):
        session = get_session()
        try:
            members = search_members(session, query)
        finally:
            session.close()
        self._table.setRowCount(0)
        for m in members:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, val in enumerate([
                m.member_number or "",
                m.organization_name,
                m.representative_name,
                m.phone,
                "会員" if m.is_member else "非会員"
            ]):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, m.id)
                self._table.setItem(row, col, item)
        self._count_label.setText(f"{len(members)} 件")

    def _selected_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        return self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _add(self):
        dlg = MemberFormDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load(self._search.text())

    def _edit(self):
        member_id = self._selected_id()
        if member_id is None:
            return
        dlg = MemberFormDialog(member_id=member_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load(self._search.text())

    def _deactivate(self):
        member_id = self._selected_id()
        if member_id is None:
            return
        session = get_session()
        try:
            deactivate_member(session, member_id)
        finally:
            session.close()
        self._load(self._search.text())

    def _import(self):
        dlg = MemberImportDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load(self._search.text())
```

- [ ] **Step 4: コミット**

```powershell
git add app/ui/member_list.py app/ui/member_form.py app/ui/member_import.py
git commit -m "feat: 会員マスタUI（一覧・登録・編集・インポート）を追加"
```

---

## Task 16: 発行元情報・銀行口座設定UI

**Files:**
- Create: `app/ui/company_settings.py`

- [ ] **Step 1: company_settings.py を作成**

```python
# app/ui/company_settings.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QGroupBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView, QDialog
)
from app.database.connection import get_session
from app.database.models import CompanySettings, BankAccount


def _get_or_create_settings(session) -> CompanySettings:
    cs = session.query(CompanySettings).first()
    if not cs:
        cs = CompanySettings()
        session.add(cs)
        session.commit()
    return cs


class CompanySettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        grp = QGroupBox("発行元情報")
        form = QFormLayout(grp)
        self._name = QLineEdit()
        self._postal = QLineEdit()
        self._address = QLineEdit()
        self._phone = QLineEdit()
        self._fax = QLineEdit()
        self._email = QLineEdit()
        self._t_number = QLineEdit()
        self._t_number.setPlaceholderText("T1234567890123")
        form.addRow("名称", self._name)
        form.addRow("郵便番号", self._postal)
        form.addRow("住所", self._address)
        form.addRow("電話", self._phone)
        form.addRow("FAX", self._fax)
        form.addRow("メール", self._email)
        form.addRow("インボイス登録番号", self._t_number)
        layout.addWidget(grp)

        btn_save = QPushButton("発行元情報を保存")
        btn_save.clicked.connect(self._save)
        layout.addWidget(btn_save)

        grp2 = QGroupBox("銀行口座")
        bank_layout = QVBoxLayout(grp2)
        self._bank_table = QTableWidget(0, 5)
        self._bank_table.setHorizontalHeaderLabels(
            ["ラベル", "銀行名", "支店名", "口座種別", "口座番号"])
        self._bank_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._bank_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
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
        layout.addWidget(grp2)

    def _load(self):
        session = get_session()
        try:
            cs = _get_or_create_settings(session)
            self._name.setText(cs.name)
            self._postal.setText(cs.postal_code)
            self._address.setText(cs.address)
            self._phone.setText(cs.phone)
            self._fax.setText(cs.fax)
            self._email.setText(cs.email)
            self._t_number.setText(cs.invoice_reg_number)
            self._bank_table.setRowCount(0)
            for b in cs.bank_accounts:
                row = self._bank_table.rowCount()
                self._bank_table.insertRow(row)
                for col, val in enumerate([b.label, b.bank_name, b.bank_branch,
                                            b.bank_account_type, b.bank_account_number]):
                    item = QTableWidgetItem(val)
                    item.setData(0x0100, b.id)
                    self._bank_table.setItem(row, col, item)
        finally:
            session.close()

    def _save(self):
        session = get_session()
        try:
            cs = _get_or_create_settings(session)
            cs.name = self._name.text().strip()
            cs.postal_code = self._postal.text().strip()
            cs.address = self._address.text().strip()
            cs.phone = self._phone.text().strip()
            cs.fax = self._fax.text().strip()
            cs.email = self._email.text().strip()
            cs.invoice_reg_number = self._t_number.text().strip()
            session.commit()
        finally:
            session.close()
        QMessageBox.information(self, "保存", "発行元情報を保存しました。")

    def _add_bank(self):
        dlg = BankAccountDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _del_bank(self):
        row = self._bank_table.currentRow()
        if row < 0:
            return
        bank_id = self._bank_table.item(row, 0).data(0x0100)
        session = get_session()
        try:
            b = session.get(BankAccount, bank_id)
            if b:
                session.delete(b)
                session.commit()
        finally:
            session.close()
        self._load()


class BankAccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("銀行口座登録")
        self.setFixedSize(360, 300)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._label = QLineEdit()
        self._label.setPlaceholderText("例：メイン口座")
        self._bank_name = QLineEdit()
        self._branch = QLineEdit()
        self._account_type = QLineEdit("普通")
        self._account_number = QLineEdit()
        self._account_name = QLineEdit()
        form.addRow("ラベル", self._label)
        form.addRow("銀行名", self._bank_name)
        form.addRow("支店名", self._branch)
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
        session = get_session()
        try:
            cs = _get_or_create_settings(session)
            b = BankAccount(
                company_id=cs.id,
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

- [ ] **Step 2: コミット**

```powershell
git add app/ui/company_settings.py
git commit -m "feat: 発行元情報・銀行口座設定UIを追加"
```

---

## Task 17: エントリポイント完成・全体統合

**Files:**
- Create: `main.py`

- [ ] **Step 1: main.py を作成**

```python
# main.py
import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QFont, QPalette, QColor
from app.ui.theme import STYLESHEET


def _excepthook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(msg, file=sys.stderr)
    try:
        QMessageBox.critical(None, "予期しないエラー", str(exc_value))
    except Exception:
        pass


def main():
    sys.excepthook = _excepthook
    app = QApplication(sys.argv)
    app.setApplicationName("商工会議所請求書・領収書発行システム")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    font = QFont("Meiryo UI", 10)
    app.setFont(font)

    from app.utils.app_config import is_first_run
    if is_first_run():
        from app.ui.first_run_wizard import FirstRunWizard
        wiz = FirstRunWizard()
        if wiz.exec() != FirstRunWizard.DialogCode.Accepted:
            sys.exit(0)

    from app.database.connection import init_db
    init_db()

    from app.services.staff_service import get_active_staff
    from app.database.connection import get_session
    session = get_session()
    try:
        has_staff = bool(get_active_staff(session))
    finally:
        session.close()

    if not has_staff:
        from app.ui.staff_management import StaffManagementWidget
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel
        dlg = QDialog()
        dlg.setWindowTitle("スタッフ登録")
        dlg.setFixedSize(600, 400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("最初にスタッフを登録してください。"))
        layout.addWidget(StaffManagementWidget())
        from PyQt6.QtWidgets import QPushButton
        btn = QPushButton("完了")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec()

    from app.ui.login_dialog import LoginDialog
    dlg = LoginDialog()
    if dlg.exec() != LoginDialog.DialogCode.Accepted:
        sys.exit(0)

    from app.ui.main_window import MainWindow
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: アプリを起動して動作確認**

```powershell
python main.py
```

期待動作：
1. 初回起動時は DB接続設定ウィザードが表示される
2. スタッフ未登録時はスタッフ登録ダイアログが表示される
3. ログイン画面でスタッフを選択するとメインウィンドウが開く
4. 設定タブ→「会員マスタ」「スタッフ管理」「カテゴリ」「請求項目テンプレート」「発行元情報」が表示される

- [ ] **Step 3: 全テストをパスすることを確認**

```powershell
pytest tests/ -v
```

期待出力: 全テストが `PASSED`

- [ ] **Step 4: 最終コミット**

```powershell
git add main.py
git commit -m "feat: エントリポイント完成・Plan 1 完了"
```

---

## Plan 1 完了チェックリスト

- [ ] `pytest tests/ -v` で全テストがパス
- [ ] `python main.py` でアプリが起動する
- [ ] DB接続設定ウィザードが動作する
- [ ] スタッフの登録・無効化ができる
- [ ] ログインできる
- [ ] カテゴリの追加・削除ができる
- [ ] 請求項目テンプレートの追加・無効化ができる
- [ ] 会員の登録・検索・編集ができる
- [ ] ExcelからのコピーペーストでインポートできΡ
- [ ] Excelファイルからインポートできる
- [ ] 発行元情報・銀行口座を登録できる

---

**次のステップ：** Plan 2「事業管理・発行コア」
