# 商工会議所請求書・領収書発行システム — Plan 2: 事業管理・発行コア

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 事業（project）の作成・会員割当・発行の3フロー（事業から/人起点横断/窓口型）・支払管理・ダッシュボードを実装し、実際に請求書・領収書を発行できる状態にする。

**Architecture:** Plan 1の基盤の上に構築。project_service / issuance_service のサービス層を追加し、UIは event_tab（事業管理）・issuance_tab（発行）・dashboard（ダッシュボード）で構成する。発行番号は `INV-YYYYMM-NNNN`（請求書）/ `RCP-YYYYMM-NNNN`（領収書）形式で連番採番。

**Tech Stack:** Python 3.11+, PyQt6, SQLAlchemy 2.0, SQLite（開発）/ PostgreSQL（本番）, pytest

---

## ファイル構成（新規作成）

```
app/
  services/
    project_service.py       # 事業CRUD・会員割当・進捗集計
    issuance_service.py      # 発行番号採番・発行レコード作成・ステータス更新
  ui/
    dashboard.py             # ダッシュボードタブ（年度別進捗）
    project_tab.py           # 事業管理タブ
    project_form.py          # 事業登録・編集ダイアログ
    project_member_panel.py  # リスト型事業の会員割当パネル
    issuance_tab.py          # 発行タブ（3フロー入口）
    issuance_from_project.py # フロー①：事業から発行
    issuance_cross_member.py # フロー②：人を起点に横断合算発行
    issuance_counter.py      # フロー③：窓口型その場入力発行
    payment_dialog.py        # 支払済み更新・入金消込ダイアログ
tests/
  test_project_service.py
  test_issuance_service.py
```

---

## Task 1: プロジェクトサービス

**Files:**
- Create: `app/services/project_service.py`
- Create: `tests/test_project_service.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_project_service.py
import pytest
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.member_service import create_member
from app.services.project_service import (
    create_project, get_projects, activate_project, close_project,
    add_template_to_project, add_members_to_project,
    get_project_members, get_project_progress
)


def test_create_project(db_session):
    cat = create_category(db_session, "青年部")
    proj = create_project(db_session, name="2026年度 青年部会費",
                          category_id=cat.id, fiscal_year=2026,
                          project_type="list")
    assert proj.id is not None
    assert proj.status == "draft"
    assert proj.fiscal_year == 2026


def test_activate_project(db_session):
    cat = create_category(db_session, "青年部")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    activate_project(db_session, proj.id)
    db_session.refresh(proj)
    assert proj.status == "active"


def test_get_projects_by_year(db_session):
    cat = create_category(db_session, "青年部")
    create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    create_project(db_session, "2025年度 青年部会費", cat.id, 2025, "list")
    result = get_projects(db_session, fiscal_year=2026)
    assert len(result) == 1
    assert result[0].fiscal_year == 2026


def test_add_template_to_project(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費", 10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    db_session.refresh(proj)
    from app.database.models import ProjectTemplate
    pts = db_session.query(ProjectTemplate).filter_by(project_id=proj.id).all()
    assert len(pts) == 1
    assert pts[0].item_template_id == tmpl.id


def test_add_members_to_project(db_session):
    cat = create_category(db_session, "青年部")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    m1 = create_member(db_session, member_number="A-001", organization_name="○○商事",
                       organization_kana="マルマルショウジ")
    m2 = create_member(db_session, member_number="A-002", organization_name="△△産業",
                       organization_kana="サンカクサンギョウ")
    add_members_to_project(db_session, proj.id, [m1.id, m2.id])
    members = get_project_members(db_session, proj.id)
    assert len(members) == 2


def test_get_project_progress(db_session):
    cat = create_category(db_session, "青年部")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    m1 = create_member(db_session, member_number="A-001", organization_name="○○商事",
                       organization_kana="マルマルショウジ")
    m2 = create_member(db_session, member_number="A-002", organization_name="△△産業",
                       organization_kana="サンカクサンギョウ")
    add_members_to_project(db_session, proj.id, [m1.id, m2.id])
    progress = get_project_progress(db_session, proj.id)
    assert progress["total"] == 2
    assert progress["issued"] == 0
    assert progress["paid"] == 0
    assert progress["pending"] == 2
```

- [ ] **Step 2: テスト実行→失敗確認**

```bash
cd C:\Users\taka\Documents\Gemini\0030Business\cci-billing
python -m pytest tests/test_project_service.py -v
```

期待: `ImportError`（project_service未定義）

- [ ] **Step 3: project_service.py を作成**

```python
# app/services/project_service.py
from sqlalchemy.orm import Session
from app.database.models import Project, ProjectTemplate, ProjectMember, Issuance


def create_project(session: Session, name: str, category_id: int,
                   fiscal_year: int, project_type: str,
                   notes: str = "") -> Project:
    proj = Project(
        name=name, category_id=category_id,
        fiscal_year=fiscal_year, project_type=project_type,
        status="draft", notes=notes
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return proj


def get_projects(session: Session, fiscal_year: int | None = None,
                 status: str | None = None) -> list[Project]:
    q = session.query(Project)
    if fiscal_year is not None:
        q = q.filter(Project.fiscal_year == fiscal_year)
    if status is not None:
        q = q.filter(Project.status == status)
    return q.order_by(Project.name).all()


def get_project_by_id(session: Session, project_id: int) -> Project | None:
    return session.get(Project, project_id)


def activate_project(session: Session, project_id: int) -> None:
    proj = session.get(Project, project_id)
    if proj:
        proj.status = "active"
        session.commit()


def close_project(session: Session, project_id: int) -> None:
    proj = session.get(Project, project_id)
    if proj:
        proj.status = "closed"
        session.commit()


def archive_project(session: Session, project_id: int) -> None:
    proj = session.get(Project, project_id)
    if proj:
        proj.status = "archived"
        session.commit()


def add_template_to_project(session: Session, project_id: int,
                             template_id: int,
                             unit_price_override: int | None = None,
                             sort_order: int = 0) -> ProjectTemplate:
    pt = ProjectTemplate(
        project_id=project_id,
        item_template_id=template_id,
        sort_order=sort_order,
        unit_price_override=unit_price_override
    )
    session.add(pt)
    session.commit()
    return pt


def remove_template_from_project(session: Session, project_id: int,
                                  template_id: int) -> None:
    pt = (session.query(ProjectTemplate)
          .filter_by(project_id=project_id, item_template_id=template_id)
          .first())
    if pt:
        session.delete(pt)
        session.commit()


def get_project_templates(session: Session, project_id: int) -> list[ProjectTemplate]:
    return (session.query(ProjectTemplate)
            .filter_by(project_id=project_id)
            .order_by(ProjectTemplate.sort_order)
            .all())


def add_members_to_project(session: Session, project_id: int,
                            member_ids: list[int]) -> list[ProjectMember]:
    existing = {pm.member_id for pm in
                session.query(ProjectMember).filter_by(project_id=project_id).all()}
    pms = []
    for i, mid in enumerate(member_ids):
        if mid in existing:
            continue
        pm = ProjectMember(project_id=project_id, member_id=mid, sort_order=i)
        session.add(pm)
        pms.append(pm)
    session.commit()
    return pms


def get_project_members(session: Session, project_id: int) -> list[ProjectMember]:
    return (session.query(ProjectMember)
            .filter_by(project_id=project_id)
            .order_by(ProjectMember.sort_order)
            .all())


def remove_member_from_project(session: Session, project_member_id: int) -> None:
    pm = session.get(ProjectMember, project_member_id)
    if pm:
        session.delete(pm)
        session.commit()


def get_project_progress(session: Session, project_id: int) -> dict:
    members = get_project_members(session, project_id)
    total = len(members)
    pm_ids = [pm.id for pm in members]
    if not pm_ids:
        return {"total": 0, "issued": 0, "paid": 0, "pending": 0}
    issued_pms = set(
        row[0] for row in
        session.query(Issuance.project_member_id)
        .filter(
            Issuance.project_member_id.in_(pm_ids),
            Issuance.status.in_(["発行済み", "支払済み"])
        ).all()
    )
    paid_pms = set(
        row[0] for row in
        session.query(Issuance.project_member_id)
        .filter(
            Issuance.project_member_id.in_(pm_ids),
            Issuance.status == "支払済み"
        ).all()
    )
    issued = len(issued_pms)
    paid = len(paid_pms)
    return {"total": total, "issued": issued, "paid": paid,
            "pending": total - issued}
```

- [ ] **Step 4: テスト→パス確認**

```bash
python -m pytest tests/test_project_service.py -v
```

期待: `6 passed`

- [ ] **Step 5: コミット**

```bash
git add app/services/project_service.py tests/test_project_service.py
git commit -m "feat: プロジェクトサービスを追加"
```

---

## Task 2: 発行サービス

**Files:**
- Create: `app/services/issuance_service.py`
- Create: `tests/test_issuance_service.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_issuance_service.py
from datetime import date
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.member_service import create_member
from app.services.project_service import (
    create_project, add_template_to_project, add_members_to_project,
    get_project_members
)
from app.services.issuance_service import (
    get_next_doc_number, create_issuance_for_member,
    create_counter_issuance, mark_as_issued, record_payment,
    get_pending_issuances_for_member, get_project_issuances
)


def _setup(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費",
                          cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    m = create_member(db_session, member_number="A-001",
                      organization_name="○○商事",
                      organization_kana="マルマルショウジ")
    add_members_to_project(db_session, proj.id, [m.id])
    pm = get_project_members(db_session, proj.id)[0]
    return proj, tmpl, m, pm


def test_get_next_doc_number(db_session):
    n1 = get_next_doc_number(db_session, "invoice", 2026, 5)
    n2 = get_next_doc_number(db_session, "invoice", 2026, 5)
    assert n1 == "INV-202605-0001"
    assert n2 == "INV-202605-0002"


def test_get_next_doc_number_receipt(db_session):
    n = get_next_doc_number(db_session, "receipt", 2026, 5)
    assert n == "RCP-202605-0001"


def test_create_issuance_for_member(db_session):
    proj, tmpl, m, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, project_id=proj.id, project_member_id=pm.id,
        member=m, doc_type="invoice", fiscal_year=2026, month=5
    )
    assert issuance.id is not None
    assert issuance.status == "準備中"
    assert issuance.doc_number.startswith("INV-")
    assert len(issuance.lines) == 1
    assert int(issuance.lines[0].unit_price) == 10000


def test_mark_as_issued(db_session):
    proj, tmpl, m, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, proj.id, pm.id, m, "invoice", 2026, 5
    )
    mark_as_issued(db_session, issuance.id, staff_id=None,
                   staff_name="田中", delivery_method="窓口手渡し")
    db_session.refresh(issuance)
    assert issuance.status == "発行済み"
    assert issuance.staff_name == "田中"


def test_record_payment(db_session):
    proj, tmpl, m, pm = _setup(db_session)
    issuance = create_issuance_for_member(
        db_session, proj.id, pm.id, m, "invoice", 2026, 5
    )
    mark_as_issued(db_session, issuance.id, None, "田中", "窓口手渡し")
    record_payment(db_session, issuance.id,
                   payment_date=date(2026, 5, 30),
                   amount=10000, payment_method="現金",
                   staff_name="田中")
    db_session.refresh(issuance)
    assert issuance.status == "支払済み"


def test_get_pending_for_member(db_session):
    proj, tmpl, m, pm = _setup(db_session)
    create_issuance_for_member(db_session, proj.id, pm.id, m, "invoice", 2026, 5)
    pending = get_pending_issuances_for_member(db_session, m.id)
    assert len(pending) == 1
    assert pending[0].status == "準備中"


def test_create_counter_issuance(db_session):
    cat = create_category(db_session, "検定")
    tmpl = create_item_template(db_session, cat.id, "珠算検定受験料",
                                3000, "人", 0, "receipt", "珠算検定受験料として")
    proj = create_project(db_session, "珠算検定", cat.id, 2026, "counter")
    add_template_to_project(db_session, proj.id, tmpl.id)
    issuance = create_counter_issuance(
        db_session, project_id=proj.id,
        recipient_organization="△△そろばん教室",
        recipient_name="",
        doc_type="receipt", quantity=3,
        fiscal_year=2026, month=5
    )
    assert issuance.id is not None
    assert issuance.status == "発行済み"
    assert int(issuance.lines[0].quantity) == 3
    assert int(issuance.amount) == 9000
```

- [ ] **Step 2: テスト実行→失敗確認**

```bash
python -m pytest tests/test_issuance_service.py -v
```

- [ ] **Step 3: issuance_service.py を作成**

```python
# app/services/issuance_service.py
from datetime import datetime, date
from sqlalchemy.orm import Session
from app.database.models import (
    Issuance, IssuanceLine, Payment, ProjectTemplate, ProjectMember, Member
)


def get_next_doc_number(session: Session, doc_type: str,
                         fiscal_year: int, month: int) -> str:
    prefix = "INV" if doc_type == "invoice" else "RCP"
    ym = f"{fiscal_year}{month:02d}"
    pattern = f"{prefix}-{ym}-%"
    last = (session.query(Issuance)
            .filter(Issuance.doc_number.like(pattern))
            .order_by(Issuance.doc_number.desc())
            .first())
    if last:
        seq = int(last.doc_number.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}-{ym}-{seq:04d}"


def _build_lines_from_project(session: Session, project_id: int,
                               quantity: int = 1) -> tuple[list[dict], int]:
    pts = (session.query(ProjectTemplate)
           .filter_by(project_id=project_id)
           .order_by(ProjectTemplate.sort_order)
           .all())
    lines = []
    total = 0
    for pt in pts:
        tmpl = pt.item_template
        price = int(pt.unit_price_override or tmpl.unit_price)
        line_total = price * quantity
        total += line_total
        lines.append({
            "item_template_id": tmpl.id,
            "item_name": tmpl.name,
            "quantity": quantity,
            "unit": tmpl.unit,
            "unit_price": price,
            "tax_rate": tmpl.tax_rate,
            "line_total": line_total,
        })
    return lines, total


def create_issuance_for_member(session: Session, project_id: int,
                                project_member_id: int, member: Member,
                                doc_type: str, fiscal_year: int,
                                month: int) -> Issuance:
    doc_number = get_next_doc_number(session, doc_type, fiscal_year, month)
    lines, total = _build_lines_from_project(session, project_id)

    issuance = Issuance(
        project_id=project_id,
        project_member_id=project_member_id,
        recipient_organization=member.organization_name,
        recipient_name=member.representative_name,
        doc_type=doc_type,
        doc_number=doc_number,
        status="準備中",
        amount=total,
    )
    session.add(issuance)
    session.flush()
    for line_data in lines:
        session.add(IssuanceLine(issuance_id=issuance.id, **line_data))
    session.commit()
    session.refresh(issuance)
    return issuance


def create_counter_issuance(session: Session, project_id: int,
                             recipient_organization: str,
                             recipient_name: str,
                             doc_type: str, quantity: int,
                             fiscal_year: int, month: int) -> Issuance:
    doc_number = get_next_doc_number(session, doc_type, fiscal_year, month)
    lines, total = _build_lines_from_project(session, project_id, quantity)
    now = datetime.now()
    issuance = Issuance(
        project_id=project_id,
        project_member_id=None,
        recipient_organization=recipient_organization,
        recipient_name=recipient_name,
        doc_type=doc_type,
        doc_number=doc_number,
        status="発行済み",
        amount=total,
        issued_at=now,
    )
    session.add(issuance)
    session.flush()
    for line_data in lines:
        session.add(IssuanceLine(issuance_id=issuance.id, **line_data))
    session.commit()
    session.refresh(issuance)
    return issuance


def create_combined_issuance(session: Session,
                              issuances_data: list[dict],
                              doc_type: str,
                              recipient_organization: str,
                              recipient_name: str,
                              fiscal_year: int, month: int,
                              staff_id: int | None,
                              staff_name: str,
                              delivery_method: str) -> Issuance:
    """複数事業の項目を1枚に合算発行する（フロー②用）"""
    doc_number = get_next_doc_number(session, doc_type, fiscal_year, month)
    all_lines = []
    total = 0
    project_ids = set()
    for data in issuances_data:
        lines, sub_total = _build_lines_from_project(
            session, data["project_id"], data.get("quantity", 1))
        all_lines.extend(lines)
        total += sub_total
        project_ids.add(data["project_id"])
    now = datetime.now()
    # 代表プロジェクトIDは最初の事業
    primary_project_id = issuances_data[0]["project_id"] if issuances_data else None
    issuance = Issuance(
        project_id=primary_project_id,
        project_member_id=None,
        recipient_organization=recipient_organization,
        recipient_name=recipient_name,
        doc_type=doc_type,
        doc_number=doc_number,
        status="発行済み",
        amount=total,
        issued_at=now,
        staff_id=staff_id,
        staff_name=staff_name,
        delivery_method=delivery_method,
    )
    session.add(issuance)
    session.flush()
    for line_data in all_lines:
        session.add(IssuanceLine(issuance_id=issuance.id, **line_data))
    # 各事業のProjectMemberのステータスを更新するため、
    # 合算対象のproject_member_idを発行済みにマーク
    for data in issuances_data:
        pm_id = data.get("project_member_id")
        if pm_id:
            prep = (session.query(Issuance)
                    .filter_by(project_member_id=pm_id, status="準備中")
                    .first())
            if prep:
                prep.status = "発行済み"
                prep.issued_at = now
                prep.staff_name = staff_name
    session.commit()
    session.refresh(issuance)
    return issuance


def mark_as_issued(session: Session, issuance_id: int,
                   staff_id: int | None, staff_name: str,
                   delivery_method: str = "窓口手渡し") -> None:
    issuance = session.get(Issuance, issuance_id)
    if issuance:
        issuance.status = "発行済み"
        issuance.issued_at = datetime.now()
        issuance.staff_id = staff_id
        issuance.staff_name = staff_name
        issuance.delivery_method = delivery_method
        session.commit()


def record_payment(session: Session, issuance_id: int,
                   payment_date: date, amount: int,
                   payment_method: str = "現金",
                   staff_id: int | None = None,
                   staff_name: str = "",
                   notes: str = "") -> None:
    issuance = session.get(Issuance, issuance_id)
    if not issuance:
        return
    payment = Payment(
        issuance_id=issuance_id,
        payment_date=payment_date,
        amount=amount,
        payment_method=payment_method,
        staff_id=staff_id,
        staff_name=staff_name,
        notes=notes,
    )
    session.add(payment)
    issuance.status = "支払済み"
    session.commit()


def get_pending_issuances_for_member(session: Session,
                                     member_id: int) -> list[Issuance]:
    pm_ids = [pm.id for pm in
              session.query(ProjectMember).filter_by(member_id=member_id).all()]
    if not pm_ids:
        return []
    return (session.query(Issuance)
            .filter(Issuance.project_member_id.in_(pm_ids),
                    Issuance.status == "準備中")
            .all())


def get_project_issuances(session: Session, project_id: int,
                           status: str | None = None) -> list[Issuance]:
    q = session.query(Issuance).filter_by(project_id=project_id)
    if status:
        q = q.filter(Issuance.status == status)
    return q.order_by(Issuance.created_at.desc()).all()
```

- [ ] **Step 4: テスト→パス確認**

```bash
python -m pytest tests/test_issuance_service.py -v
```

期待: `7 passed`

- [ ] **Step 5: コミット**

```bash
git add app/services/issuance_service.py tests/test_issuance_service.py
git commit -m "feat: 発行サービス（番号採番・発行・入金消込）を追加"
```

---

## Task 3: ダッシュボード

**Files:**
- Create: `app/ui/dashboard.py`

- [ ] **Step 1: dashboard.py を作成**

```python
# app/ui/dashboard.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from app.database.connection import get_session
from app.services.project_service import get_projects, get_project_progress, activate_project


class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        # 年度フィルター
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("年度："))
        self._year_combo = QComboBox()
        from datetime import date
        current_year = date.today().year
        for y in range(current_year + 1, current_year - 5, -1):
            self._year_combo.addItem(f"{y}年度", y)
        self._year_combo.setCurrentIndex(1)
        self._year_combo.currentIndexChanged.connect(self._load)
        top_row.addWidget(self._year_combo)
        btn_refresh = QPushButton("更新")
        btn_refresh.clicked.connect(self._load)
        top_row.addWidget(btn_refresh)
        top_row.addStretch()
        layout.addLayout(top_row)

        # 進捗テーブル（active事業）
        self._label_active = QLabel("■ 受付中の事業")
        layout.addWidget(self._label_active)
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["事業名", "種別", "全件", "発行済", "支払済", "未発行"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        # 下書き事業
        self._label_draft = QLabel("■ 準備中の事業（draft）")
        layout.addWidget(self._label_draft)
        self._draft_table = QTableWidget(0, 3)
        self._draft_table.setHorizontalHeaderLabels(["事業名", "種別", "操作"])
        self._draft_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._draft_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._draft_table)

    def _load(self):
        year = self._year_combo.currentData()
        session = get_session()
        try:
            active = get_projects(session, fiscal_year=year, status="active")
            draft = get_projects(session, fiscal_year=year, status="draft")

            self._table.setRowCount(0)
            for proj in active:
                p = get_project_progress(session, proj.id)
                row = self._table.rowCount()
                self._table.insertRow(row)
                type_label = "リスト型" if proj.project_type == "list" else "窓口型"
                pending = p["pending"]
                for col, val in enumerate([
                    proj.name, type_label,
                    str(p["total"]), str(p["issued"]),
                    str(p["paid"]), str(pending)
                ]):
                    item = QTableWidgetItem(val)
                    item.setData(Qt.ItemDataRole.UserRole, proj.id)
                    if col == 5 and pending > 0:
                        item.setForeground(QColor("#DC2626"))
                    self._table.setItem(row, col, item)

            self._draft_table.setRowCount(0)
            for proj in draft:
                row = self._draft_table.rowCount()
                self._draft_table.insertRow(row)
                type_label = "リスト型" if proj.project_type == "list" else "窓口型"
                self._draft_table.setItem(row, 0, QTableWidgetItem(proj.name))
                self._draft_table.setItem(row, 1, QTableWidgetItem(type_label))
                btn = QPushButton("受付開始")
                btn.setProperty("project_id", proj.id)
                btn.clicked.connect(self._activate)
                self._draft_table.setCellWidget(row, 2, btn)
        finally:
            session.close()

    def _activate(self):
        btn = self.sender()
        project_id = btn.property("project_id")
        session = get_session()
        try:
            activate_project(session, project_id)
        finally:
            session.close()
        self._load()
```

- [ ] **Step 2: コミット**

```bash
git add app/ui/dashboard.py
git commit -m "feat: ダッシュボード（年度別進捗）を追加"
```

---

## Task 4: 事業管理UI

**Files:**
- Create: `app/ui/project_tab.py`
- Create: `app/ui/project_form.py`
- Create: `app/ui/project_member_panel.py`

- [ ] **Step 1: project_form.py を作成**

```python
# app/ui/project_form.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QSpinBox, QTextEdit,
    QPushButton, QLabel, QMessageBox, QListWidget,
    QListWidgetItem, QGroupBox
)
from PyQt6.QtCore import Qt
from datetime import date
from app.database.connection import get_session
from app.services.category_service import get_active_categories
from app.services.item_template_service import get_templates_by_category, get_all_active_templates
from app.services.project_service import (
    create_project, get_project_by_id,
    add_template_to_project, remove_template_from_project,
    get_project_templates
)
from app.database.models import ItemTemplate


class ProjectFormDialog(QDialog):
    def __init__(self, project_id: int | None = None, parent=None):
        super().__init__(parent)
        self._project_id = project_id
        self.setWindowTitle("事業登録" if project_id is None else "事業編集")
        self.resize(560, 580)
        self._build()
        if project_id:
            self._load(project_id)

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name = QLineEdit()
        self._name.setPlaceholderText("例：2026年度 青年部会費")
        self._category = QComboBox()
        self._category.currentIndexChanged.connect(self._on_category_change)
        self._fiscal_year = QSpinBox()
        self._fiscal_year.setRange(2000, 2099)
        self._fiscal_year.setValue(date.today().year)
        self._project_type = QComboBox()
        self._project_type.addItems(["リスト型（会員名簿あり）", "窓口型（その場入力）"])
        self._notes = QTextEdit()
        self._notes.setFixedHeight(60)

        form.addRow("事業名", self._name)
        form.addRow("カテゴリ", self._category)
        form.addRow("年度", self._fiscal_year)
        form.addRow("種別", self._project_type)
        form.addRow("備考", self._notes)
        layout.addLayout(form)

        # テンプレート選択
        grp = QGroupBox("請求項目テンプレート（1つ以上必須）")
        grp_layout = QHBoxLayout(grp)

        left = QVBoxLayout()
        left.addWidget(QLabel("利用可能なテンプレート："))
        self._avail_list = QListWidget()
        left.addWidget(self._avail_list)
        btn_add_tmpl = QPushButton("→ 追加")
        btn_add_tmpl.clicked.connect(self._add_template)
        left.addWidget(btn_add_tmpl)

        right = QVBoxLayout()
        right.addWidget(QLabel("この事業で使用するテンプレート："))
        self._selected_list = QListWidget()
        right.addWidget(self._selected_list)
        btn_del_tmpl = QPushButton("← 削除")
        btn_del_tmpl.clicked.connect(self._remove_template)
        right.addWidget(btn_del_tmpl)

        grp_layout.addLayout(left)
        grp_layout.addLayout(right)
        layout.addWidget(grp)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("保存")
        btn_ok.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        session = get_session()
        try:
            for cat in get_active_categories(session):
                self._category.addItem(cat.name, cat.id)
        finally:
            session.close()

    def _on_category_change(self, _):
        cat_id = self._category.currentData()
        if cat_id is None:
            return
        session = get_session()
        try:
            templates = get_templates_by_category(session, cat_id)
        finally:
            session.close()
        self._avail_list.clear()
        for t in templates:
            item = QListWidgetItem(f"{t.name}（¥{int(t.unit_price):,}）")
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            self._avail_list.addItem(item)

    def _add_template(self):
        item = self._avail_list.currentItem()
        if not item:
            return
        tmpl_id = item.data(Qt.ItemDataRole.UserRole)
        for i in range(self._selected_list.count()):
            if self._selected_list.item(i).data(Qt.ItemDataRole.UserRole) == tmpl_id:
                return
        new_item = QListWidgetItem(item.text())
        new_item.setData(Qt.ItemDataRole.UserRole, tmpl_id)
        self._selected_list.addItem(new_item)

    def _remove_template(self):
        row = self._selected_list.currentRow()
        if row >= 0:
            self._selected_list.takeItem(row)

    def _load(self, project_id: int):
        session = get_session()
        try:
            proj = get_project_by_id(session, project_id)
            if not proj:
                return
            self._name.setText(proj.name)
            self._fiscal_year.setValue(proj.fiscal_year)
            idx = 0 if proj.project_type == "list" else 1
            self._project_type.setCurrentIndex(idx)
            self._notes.setPlainText(proj.notes or "")
            for i in range(self._category.count()):
                if self._category.itemData(i) == proj.category_id:
                    self._category.setCurrentIndex(i)
                    break
            for pt in get_project_templates(session, project_id):
                tmpl = pt.item_template
                item = QListWidgetItem(f"{tmpl.name}（¥{int(tmpl.unit_price):,}）")
                item.setData(Qt.ItemDataRole.UserRole, tmpl.id)
                self._selected_list.addItem(item)
        finally:
            session.close()

    def _save(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "入力エラー", "事業名を入力してください。")
            return
        if self._selected_list.count() == 0:
            QMessageBox.warning(self, "入力エラー", "テンプレートを1つ以上選択してください。")
            return
        session = get_session()
        try:
            if self._project_id is None:
                proj = create_project(
                    session,
                    name=name,
                    category_id=self._category.currentData(),
                    fiscal_year=self._fiscal_year.value(),
                    project_type="list" if self._project_type.currentIndex() == 0 else "counter",
                    notes=self._notes.toPlainText().strip()
                )
                for i in range(self._selected_list.count()):
                    tmpl_id = self._selected_list.item(i).data(Qt.ItemDataRole.UserRole)
                    add_template_to_project(session, proj.id, tmpl_id, sort_order=i)
            else:
                proj = get_project_by_id(session, self._project_id)
                proj.name = name
                proj.category_id = self._category.currentData()
                proj.fiscal_year = self._fiscal_year.value()
                proj.project_type = "list" if self._project_type.currentIndex() == 0 else "counter"
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

- [ ] **Step 2: project_member_panel.py を作成**

```python
# app/ui/project_member_panel.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.project_service import (
    get_project_members, add_members_to_project, remove_member_from_project
)
from app.services.member_service import search_members
from app.utils.excel_utils import parse_tsv_text, parse_excel_file
from PyQt6.QtWidgets import QTextEdit, QFileDialog


class ProjectMemberPanel(QWidget):
    def __init__(self, project_id: int):
        super().__init__()
        self._project_id = project_id
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("会員リスト（リスト型事業）"))

        btn_row = QHBoxLayout()
        btn_import = QPushButton("Excelインポート")
        btn_import.clicked.connect(self._import)
        btn_paste = QPushButton("貼り付けインポート")
        btn_paste.clicked.connect(self._paste_import)
        btn_del = QPushButton("削除")
        btn_del.clicked.connect(self._remove)
        for b in [btn_import, btn_paste, btn_del]:
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["会員番号", "事業所名", "代表者名", "ステータス"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)
        self._count_label = QLabel("")
        layout.addWidget(self._count_label)

    def _load(self):
        session = get_session()
        try:
            pms = get_project_members(session, self._project_id)
            from app.database.models import Issuance
            pm_status = {}
            for pm in pms:
                iss = (session.query(Issuance)
                       .filter_by(project_member_id=pm.id)
                       .order_by(Issuance.created_at.desc())
                       .first())
                pm_status[pm.id] = iss.status if iss else "準備中"
        finally:
            session.close()
        self._table.setRowCount(0)
        for pm in pms:
            m = pm.member
            row = self._table.rowCount()
            self._table.insertRow(row)
            vals = [
                m.member_number or "" if m else "",
                m.organization_name if m else "",
                m.representative_name if m else "",
                pm_status.get(pm.id, "準備中")
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, pm.id)
                self._table.setItem(row, col, item)
        self._count_label.setText(f"{len(pms)} 件")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Excelを選択", "", "Excel (*.xlsx *.xls)")
        if not path:
            return
        try:
            rows = parse_excel_file(path)
            self._register_rows(rows)
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))

    def _paste_import(self):
        from PyQt6.QtWidgets import QDialog as D, QVBoxLayout as VL
        dlg = D(self)
        dlg.setWindowTitle("貼り付けインポート")
        dlg.resize(600, 200)
        vl = VL(dlg)
        te = QTextEdit()
        te.setPlaceholderText("ExcelからコピーしてCtrl+Vで貼り付け")
        vl.addWidget(te)
        btn = QPushButton("インポート")
        btn.clicked.connect(dlg.accept)
        vl.addWidget(btn)
        if dlg.exec() == D.DialogCode.Accepted:
            rows = parse_tsv_text(te.toPlainText())
            self._register_rows(rows)

    def _register_rows(self, rows: list[dict]):
        session = get_session()
        added = 0
        try:
            for row in rows:
                members = search_members(session, row.get("member_number", "") or
                                         row.get("organization_name", ""))
                if members:
                    add_members_to_project(session, self._project_id, [members[0].id])
                    added += 1
        finally:
            session.close()
        QMessageBox.information(self, "完了", f"{added} 件を追加しました。")
        self._load()

    def _remove(self):
        row = self._table.currentRow()
        if row < 0:
            return
        pm_id = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            remove_member_from_project(session, pm_id)
        finally:
            session.close()
        self._load()
```

- [ ] **Step 3: project_tab.py を作成**

```python
# app/ui/project_tab.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QComboBox, QLabel, QHeaderView, QDialog, QSplitter,
    QMessageBox
)
from PyQt6.QtCore import Qt
from datetime import date
from app.database.connection import get_session
from app.services.project_service import (
    get_projects, activate_project, close_project, archive_project,
    get_project_progress
)
from app.ui.project_form import ProjectFormDialog
from app.ui.project_member_panel import ProjectMemberPanel


class ProjectTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("年度："))
        self._year_combo = QComboBox()
        current_year = date.today().year
        for y in range(current_year + 1, current_year - 5, -1):
            self._year_combo.addItem(f"{y}年度", y)
        self._year_combo.setCurrentIndex(1)
        self._year_combo.currentIndexChanged.connect(self._load)
        top_row.addWidget(self._year_combo)

        btn_add = QPushButton("＋ 新規事業")
        btn_add.clicked.connect(self._add)
        btn_edit = QPushButton("編集")
        btn_edit.clicked.connect(self._edit)
        top_row.addWidget(btn_add)
        top_row.addWidget(btn_edit)
        top_row.addStretch()

        self._status_combo = QComboBox()
        self._status_combo.addItems(["すべて", "draft", "active", "closed", "archived"])
        self._status_combo.currentIndexChanged.connect(self._load)
        top_row.addWidget(QLabel("状態："))
        top_row.addWidget(self._status_combo)
        layout.addLayout(top_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["事業名", "種別", "状態", "全件", "発行済", "未発行"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.currentCellChanged.connect(self._on_select)
        splitter.addWidget(self._table)

        self._member_panel_container = QWidget()
        self._member_panel_layout = QVBoxLayout(self._member_panel_container)
        splitter.addWidget(self._member_panel_container)
        splitter.setSizes([300, 300])

        layout.addWidget(splitter)

        btn_row2 = QHBoxLayout()
        btn_activate = QPushButton("受付開始（active）")
        btn_activate.clicked.connect(self._activate)
        btn_close = QPushButton("終了（closed）")
        btn_close.clicked.connect(self._close)
        btn_archive = QPushButton("アーカイブ")
        btn_archive.clicked.connect(self._archive)
        for b in [btn_activate, btn_close, btn_archive]:
            btn_row2.addWidget(b)
        btn_row2.addStretch()
        layout.addLayout(btn_row2)

    def _load(self):
        year = self._year_combo.currentData()
        status_text = self._status_combo.currentText()
        status = None if status_text == "すべて" else status_text
        session = get_session()
        try:
            projects = get_projects(session, fiscal_year=year, status=status)
            self._table.setRowCount(0)
            for proj in projects:
                p = get_project_progress(session, proj.id)
                row = self._table.rowCount()
                self._table.insertRow(row)
                type_label = "リスト型" if proj.project_type == "list" else "窓口型"
                for col, val in enumerate([
                    proj.name, type_label, proj.status,
                    str(p["total"]), str(p["issued"]), str(p["pending"])
                ]):
                    item = QTableWidgetItem(val)
                    item.setData(Qt.ItemDataRole.UserRole, proj.id)
                    self._table.setItem(row, col, item)
        finally:
            session.close()

    def _on_select(self, row, *_):
        if row < 0:
            return
        project_id = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            from app.services.project_service import get_project_by_id
            proj = get_project_by_id(session, project_id)
            project_type = proj.project_type if proj else "list"
        finally:
            session.close()
        for i in reversed(range(self._member_panel_layout.count())):
            self._member_panel_layout.itemAt(i).widget().deleteLater()
        if project_type == "list":
            panel = ProjectMemberPanel(project_id)
            self._member_panel_layout.addWidget(panel)

    def _selected_project_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        return self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _add(self):
        dlg = ProjectFormDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _edit(self):
        pid = self._selected_project_id()
        if pid is None:
            return
        dlg = ProjectFormDialog(project_id=pid, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _activate(self):
        pid = self._selected_project_id()
        if pid is None:
            return
        session = get_session()
        try:
            activate_project(session, pid)
        finally:
            session.close()
        self._load()

    def _close(self):
        pid = self._selected_project_id()
        if pid is None:
            return
        session = get_session()
        try:
            close_project(session, pid)
        finally:
            session.close()
        self._load()

    def _archive(self):
        pid = self._selected_project_id()
        if pid is None:
            return
        session = get_session()
        try:
            archive_project(session, pid)
        finally:
            session.close()
        self._load()
```

- [ ] **Step 4: コミット**

```bash
git add app/ui/project_form.py app/ui/project_member_panel.py app/ui/project_tab.py
git commit -m "feat: 事業管理UI（登録・会員割当・ステータス管理）を追加"
```

---

## Task 5: 発行フロー①（事業から発行）

**Files:**
- Create: `app/ui/issuance_from_project.py`

- [ ] **Step 1: issuance_from_project.py を作成**

```python
# app/ui/issuance_from_project.py
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QComboBox, QLineEdit, QDialog,
    QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from app.database.connection import get_session
from app.services.project_service import get_projects, get_project_members, get_project_by_id
from app.services.issuance_service import (
    create_issuance_for_member, mark_as_issued, get_project_issuances
)
from app.utils import current_user


class IssuanceFromProjectWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load_projects()

    def _build(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("事業："))
        self._proj_combo = QComboBox()
        self._proj_combo.setMinimumWidth(300)
        self._proj_combo.currentIndexChanged.connect(self._load_members)
        top.addWidget(self._proj_combo)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["未発行のみ", "すべて"])
        self._filter_combo.currentIndexChanged.connect(self._load_members)
        top.addWidget(QLabel("表示："))
        top.addWidget(self._filter_combo)
        top.addStretch()
        layout.addLayout(top)

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("名前・会員番号で絞り込み")
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._load_members)
        self._search.textChanged.connect(lambda: self._timer.start(300))
        search_row.addWidget(QLabel("検索："))
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["会員番号", "事業所名", "代表者名", "ステータス", "発行番号"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_prepare = QPushButton("準備（採番）")
        btn_prepare.clicked.connect(self._prepare)
        btn_issue = QPushButton("発行する")
        btn_issue.clicked.connect(self._issue)
        self._delivery_combo = QComboBox()
        self._delivery_combo.addItems(["窓口手渡し", "郵送", "メール送付", "その他"])
        btn_row.addWidget(btn_prepare)
        btn_row.addWidget(btn_issue)
        btn_row.addWidget(QLabel("配付方法："))
        btn_row.addWidget(self._delivery_combo)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    def _load_projects(self):
        session = get_session()
        try:
            projects = get_projects(session, status="active")
        finally:
            session.close()
        self._proj_combo.clear()
        for p in projects:
            self._proj_combo.addItem(p.name, p.id)
        self._load_members()

    def _load_members(self):
        project_id = self._proj_combo.currentData()
        if project_id is None:
            return
        query = self._search.text().strip().lower()
        show_all = self._filter_combo.currentIndex() == 1
        session = get_session()
        try:
            pms = get_project_members(session, project_id)
            from app.database.models import Issuance
            pm_data = []
            for pm in pms:
                m = pm.member
                iss = (session.query(Issuance)
                       .filter_by(project_member_id=pm.id)
                       .order_by(Issuance.created_at.desc())
                       .first())
                status = iss.status if iss else "未準備"
                doc_number = iss.doc_number if iss else ""
                issuance_id = iss.id if iss else None
                if not show_all and status in ("発行済み", "支払済み"):
                    continue
                if query:
                    search_targets = [
                        m.member_number or "",
                        m.organization_name,
                        m.representative_name,
                        m.organization_kana,
                    ]
                    if not any(query in t.lower() for t in search_targets):
                        continue
                pm_data.append((pm.id, m, status, doc_number, issuance_id))
        finally:
            session.close()

        self._table.setRowCount(0)
        for pm_id, m, status, doc_number, issuance_id in pm_data:
            row = self._table.rowCount()
            self._table.insertRow(row)
            for col, val in enumerate([
                m.member_number or "",
                m.organization_name,
                m.representative_name,
                status,
                doc_number
            ]):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, (pm_id, issuance_id))
                self._table.setItem(row, col, item)
        self._status_label.setText(f"{len(pm_data)} 件表示")

    def _selected_pm(self) -> tuple[int, int | None] | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        return self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _prepare(self):
        sel = self._selected_pm()
        if sel is None:
            return
        pm_id, issuance_id = sel
        if issuance_id is not None:
            QMessageBox.information(self, "情報", "既に採番済みです。")
            return
        project_id = self._proj_combo.currentData()
        session = get_session()
        try:
            proj = get_project_by_id(session, project_id)
            from app.database.models import ProjectMember
            pm = session.get(ProjectMember, pm_id)
            m = pm.member
            today = date.today()
            pt = get_projects(session, fiscal_year=proj.fiscal_year)
            doc_type = "invoice"
            for pt_item in (session.query(__import__('app.database.models', fromlist=['ProjectTemplate']).ProjectTemplate)
                           .filter_by(project_id=project_id).all()):
                if pt_item.item_template.doc_type == "receipt":
                    doc_type = "receipt"
                    break
            create_issuance_for_member(
                session, project_id=project_id,
                project_member_id=pm_id,
                member=m, doc_type=doc_type,
                fiscal_year=today.year, month=today.month
            )
        finally:
            session.close()
        self._load_members()

    def _issue(self):
        sel = self._selected_pm()
        if sel is None:
            return
        pm_id, issuance_id = sel
        if issuance_id is None:
            QMessageBox.warning(self, "エラー", "先に「準備（採番）」を行ってください。")
            return
        delivery = self._delivery_combo.currentText()
        session = get_session()
        try:
            from app.database.models import Issuance
            iss = session.get(Issuance, issuance_id)
            if iss and iss.status == "発行済み":
                QMessageBox.information(self, "情報", "既に発行済みです。")
                return
            mark_as_issued(session, issuance_id,
                           staff_id=current_user.get_id(),
                           staff_name=current_user.get_name(),
                           delivery_method=delivery)
        finally:
            session.close()
        QMessageBox.information(self, "発行完了",
                                f"発行しました。（{delivery}）\n印刷はPlan 3で実装されます。")
        self._load_members()
```

- [ ] **Step 2: コミット**

```bash
git add app/ui/issuance_from_project.py
git commit -m "feat: 発行フロー①（事業から発行）を追加"
```

---

## Task 6: 発行フロー②③ + 支払ダイアログ

**Files:**
- Create: `app/ui/issuance_cross_member.py`
- Create: `app/ui/issuance_counter.py`
- Create: `app/ui/payment_dialog.py`

- [ ] **Step 1: issuance_cross_member.py を作成**

```python
# app/ui/issuance_cross_member.py
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView,
    QComboBox, QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from app.database.connection import get_session
from app.services.member_service import search_members
from app.services.issuance_service import (
    get_pending_issuances_for_member, create_combined_issuance
)
from app.services.project_service import get_project_by_id
from app.utils import current_user


class IssuanceCrossMemberWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._member = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("会員番号・事業所名・代表者名で検索し、発行する項目を選択してください。"))

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("会員番号・事業所名・フリガナ・代表者名")
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._search_member)
        self._search.textChanged.connect(lambda: self._timer.start(300))
        search_row.addWidget(QLabel("検索："))
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        self._member_table = QTableWidget(0, 3)
        self._member_table.setHorizontalHeaderLabels(["会員番号", "事業所名", "代表者名"])
        self._member_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._member_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._member_table.setMaximumHeight(120)
        self._member_table.currentCellChanged.connect(self._on_member_select)
        layout.addWidget(self._member_table)

        layout.addWidget(QLabel("未発行一覧（全事業横断）："))
        self._pending_table = QTableWidget(0, 4)
        self._pending_table.setHorizontalHeaderLabels(
            ["選択", "事業名", "書類種別", "金額"])
        self._pending_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._pending_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._pending_table)

        btn_row = QHBoxLayout()
        self._delivery_combo = QComboBox()
        self._delivery_combo.addItems(["窓口手渡し", "郵送", "メール送付", "その他"])
        btn_issue = QPushButton("選択した項目を発行する")
        btn_issue.clicked.connect(self._issue)
        btn_row.addWidget(QLabel("配付方法："))
        btn_row.addWidget(self._delivery_combo)
        btn_row.addWidget(btn_issue)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _search_member(self):
        query = self._search.text().strip()
        if not query:
            return
        session = get_session()
        try:
            members = search_members(session, query)[:10]
        finally:
            session.close()
        self._member_table.setRowCount(0)
        for m in members:
            row = self._member_table.rowCount()
            self._member_table.insertRow(row)
            for col, val in enumerate([
                m.member_number or "", m.organization_name, m.representative_name
            ]):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, m.id)
                self._member_table.setItem(row, col, item)

    def _on_member_select(self, row, *_):
        if row < 0:
            return
        member_id = self._member_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        session = get_session()
        try:
            from app.database.models import Member
            self._member = session.get(Member, member_id)
            pending = get_pending_issuances_for_member(session, member_id)
            self._pending_table.setRowCount(0)
            for iss in pending:
                proj = get_project_by_id(session, iss.project_id)
                r = self._pending_table.rowCount()
                self._pending_table.insertRow(r)
                cb = QCheckBox()
                cb.setChecked(True)
                self._pending_table.setCellWidget(r, 0, cb)
                doc_label = "請求書" if iss.doc_type == "invoice" else "領収書"
                for col, val in enumerate([proj.name if proj else "", doc_label,
                                            f"¥{int(iss.amount):,}"], 1):
                    item = QTableWidgetItem(val)
                    item.setData(Qt.ItemDataRole.UserRole,
                                 (iss.id, iss.project_id, iss.project_member_id,
                                  iss.doc_type))
                    self._pending_table.setItem(r, col, item)
        finally:
            session.close()

    def _issue(self):
        if self._member is None:
            QMessageBox.warning(self, "エラー", "会員を選択してください。")
            return
        selected = []
        doc_types = set()
        for row in range(self._pending_table.rowCount()):
            cb = self._pending_table.cellWidget(row, 0)
            if cb and cb.isChecked():
                data = self._pending_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
                iss_id, proj_id, pm_id, doc_type = data
                selected.append({
                    "issuance_id": iss_id,
                    "project_id": proj_id,
                    "project_member_id": pm_id,
                    "quantity": 1
                })
                doc_types.add(doc_type)
        if not selected:
            QMessageBox.warning(self, "エラー", "発行する項目を選択してください。")
            return
        session = get_session()
        try:
            today = date.today()
            delivery = self._delivery_combo.currentText()
            for doc_type in doc_types:
                items = [s for s in selected
                         if self._get_doc_type(session, s["issuance_id"]) == doc_type]
                if not items:
                    continue
                create_combined_issuance(
                    session,
                    issuances_data=items,
                    doc_type=doc_type,
                    recipient_organization=self._member.organization_name,
                    recipient_name=self._member.representative_name,
                    fiscal_year=today.year,
                    month=today.month,
                    staff_id=current_user.get_id(),
                    staff_name=current_user.get_name(),
                    delivery_method=delivery
                )
        finally:
            session.close()
        QMessageBox.information(self, "発行完了", "発行しました。")
        self._on_member_select(self._member_table.currentRow())

    def _get_doc_type(self, session, issuance_id: int) -> str:
        from app.database.models import Issuance
        iss = session.get(Issuance, issuance_id)
        return iss.doc_type if iss else "invoice"
```

- [ ] **Step 2: issuance_counter.py を作成**

```python
# app/ui/issuance_counter.py
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QLabel, QPushButton,
    QMessageBox, QGroupBox
)
from app.database.connection import get_session
from app.services.project_service import get_projects, get_project_by_id
from app.services.issuance_service import create_counter_issuance
from app.utils import current_user


class IssuanceCounterWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load_projects()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("窓口型事業：その場で宛先・数量を入力して即発行します。"))

        form = QFormLayout()
        self._proj_combo = QComboBox()
        self._proj_combo.setMinimumWidth(300)
        self._proj_combo.currentIndexChanged.connect(self._on_project_change)
        self._org_name = QLineEdit()
        self._org_name.setPlaceholderText("事業所名（任意）")
        self._rep_name = QLineEdit()
        self._rep_name.setPlaceholderText("代表者名・個人名（任意）")
        self._quantity = QSpinBox()
        self._quantity.setRange(1, 9999)
        self._quantity.setValue(1)
        self._quantity.valueChanged.connect(self._update_amount)
        self._delivery_combo = QComboBox()
        self._delivery_combo.addItems(["窓口手渡し", "郵送", "メール送付", "その他"])

        form.addRow("事業", self._proj_combo)
        form.addRow("事業所名", self._org_name)
        form.addRow("代表者名/個人名", self._rep_name)
        form.addRow("数量", self._quantity)
        form.addRow("配付方法", self._delivery_combo)
        layout.addLayout(form)

        self._amount_label = QLabel("金額：¥0")
        self._amount_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2563EB;")
        layout.addWidget(self._amount_label)

        grp = QGroupBox("明細プレビュー")
        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        from PyQt6.QtWidgets import QVBoxLayout as VL
        vl = VL(grp)
        vl.addWidget(self._preview_label)
        layout.addWidget(grp)

        btn = QPushButton("発行する")
        btn.setFixedHeight(40)
        btn.setStyleSheet("font-size: 14px; font-weight: bold;")
        btn.clicked.connect(self._issue)
        layout.addWidget(btn)
        layout.addStretch()

    def _load_projects(self):
        session = get_session()
        try:
            projects = [p for p in get_projects(session, status="active")
                        if p.project_type == "counter"]
        finally:
            session.close()
        self._proj_combo.clear()
        for p in projects:
            self._proj_combo.addItem(p.name, p.id)
        self._on_project_change()

    def _on_project_change(self):
        self._update_amount()
        self._update_preview()

    def _get_unit_price(self) -> int:
        project_id = self._proj_combo.currentData()
        if project_id is None:
            return 0
        session = get_session()
        try:
            from app.database.models import ProjectTemplate
            pts = session.query(ProjectTemplate).filter_by(project_id=project_id).all()
            total = sum(int(pt.unit_price_override or pt.item_template.unit_price)
                        for pt in pts)
        finally:
            session.close()
        return total

    def _update_amount(self):
        price = self._get_unit_price()
        qty = self._quantity.value()
        self._amount_label.setText(f"金額：¥{price * qty:,}")

    def _update_preview(self):
        project_id = self._proj_combo.currentData()
        if project_id is None:
            self._preview_label.setText("")
            return
        session = get_session()
        try:
            from app.database.models import ProjectTemplate
            pts = session.query(ProjectTemplate).filter_by(project_id=project_id).all()
            lines = []
            for pt in pts:
                t = pt.item_template
                price = int(pt.unit_price_override or t.unit_price)
                lines.append(f"・{t.name}  ¥{price:,}/{t.unit}")
        finally:
            session.close()
        self._preview_label.setText("\n".join(lines))

    def _issue(self):
        org = self._org_name.text().strip()
        rep = self._rep_name.text().strip()
        if not org and not rep:
            QMessageBox.warning(self, "入力エラー", "事業所名または代表者名を入力してください。")
            return
        project_id = self._proj_combo.currentData()
        if project_id is None:
            QMessageBox.warning(self, "エラー", "事業を選択してください。")
            return
        today = date.today()
        session = get_session()
        try:
            proj = get_project_by_id(session, project_id)
            from app.database.models import ProjectTemplate
            pts = session.query(ProjectTemplate).filter_by(project_id=project_id).first()
            doc_type = "receipt"
            if pts and pts.item_template.doc_type == "invoice":
                doc_type = "invoice"
            iss = create_counter_issuance(
                session,
                project_id=project_id,
                recipient_organization=org,
                recipient_name=rep,
                doc_type=doc_type,
                quantity=self._quantity.value(),
                fiscal_year=today.year,
                month=today.month
            )
            iss.staff_id = current_user.get_id()
            iss.staff_name = current_user.get_name()
            iss.delivery_method = self._delivery_combo.currentText()
            session.commit()
        finally:
            session.close()
        QMessageBox.information(self, "発行完了",
                                f"発行しました。\n印刷はPlan 3で実装されます。")
        self._org_name.clear()
        self._rep_name.clear()
        self._quantity.setValue(1)
```

- [ ] **Step 3: payment_dialog.py を作成**

```python
# app/ui/payment_dialog.py
from datetime import date
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QDateEdit, QSpinBox, QComboBox, QLineEdit,
    QPushButton, QLabel, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QWidget
)
from PyQt6.QtCore import Qt, QDate
from app.database.connection import get_session
from app.services.issuance_service import record_payment, get_project_issuances
from app.services.project_service import get_projects
from app.utils import current_user


class PaymentManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("発行済み書類の支払管理"))

        top = QHBoxLayout()
        self._proj_combo = QComboBox()
        self._proj_combo.setMinimumWidth(300)
        self._proj_combo.currentIndexChanged.connect(self._load)
        self._status_combo = QComboBox()
        self._status_combo.addItems(["発行済み", "支払済み", "すべて"])
        self._status_combo.currentIndexChanged.connect(self._load)
        top.addWidget(QLabel("事業："))
        top.addWidget(self._proj_combo)
        top.addWidget(QLabel("状態："))
        top.addWidget(self._status_combo)
        top.addStretch()
        layout.addLayout(top)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["発行番号", "宛先", "金額", "状態", "発行日"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_pay = QPushButton("支払済みに更新")
        btn_pay.clicked.connect(self._mark_paid)
        btn_row.addWidget(btn_pay)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        session = get_session()
        try:
            for p in get_projects(session, status="active"):
                self._proj_combo.addItem(p.name, p.id)
        finally:
            session.close()

    def _load(self):
        project_id = self._proj_combo.currentData()
        if project_id is None:
            return
        status_text = self._status_combo.currentText()
        status = None if status_text == "すべて" else status_text
        session = get_session()
        try:
            issuances = get_project_issuances(session, project_id, status)
        finally:
            session.close()
        self._table.setRowCount(0)
        for iss in issuances:
            row = self._table.rowCount()
            self._table.insertRow(row)
            recipient = iss.recipient_organization or iss.recipient_name
            issued = iss.issued_at.strftime("%Y/%m/%d") if iss.issued_at else ""
            for col, val in enumerate([
                iss.doc_number, recipient,
                f"¥{int(iss.amount):,}", iss.status, issued
            ]):
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, iss.id)
                self._table.setItem(row, col, item)

    def _mark_paid(self):
        row = self._table.currentRow()
        if row < 0:
            return
        issuance_id = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dlg = PaymentDialog(issuance_id, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()


class PaymentDialog(QDialog):
    def __init__(self, issuance_id: int, parent=None):
        super().__init__(parent)
        self._issuance_id = issuance_id
        self.setWindowTitle("入金記録")
        self.setFixedSize(360, 260)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
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

- [ ] **Step 4: コミット**

```bash
git add app/ui/issuance_cross_member.py app/ui/issuance_counter.py app/ui/payment_dialog.py
git commit -m "feat: 発行フロー②③（横断合算・窓口型）と支払管理UIを追加"
```

---

## Task 7: 発行タブ統合・メインウィンドウ更新

**Files:**
- Create: `app/ui/issuance_tab.py`
- Modify: `app/ui/main_window.py`

- [ ] **Step 1: issuance_tab.py を作成**

```python
# app/ui/issuance_tab.py
from PyQt6.QtWidgets import QWidget, QTabWidget, QVBoxLayout
from app.ui.issuance_from_project import IssuanceFromProjectWidget
from app.ui.issuance_cross_member import IssuanceCrossMemberWidget
from app.ui.issuance_counter import IssuanceCounterWidget
from app.ui.payment_dialog import PaymentManagementWidget


class IssuanceTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        inner = QTabWidget()
        inner.addTab(IssuanceFromProjectWidget(), "事業から発行")
        inner.addTab(IssuanceCrossMemberWidget(), "人を検索して発行")
        inner.addTab(IssuanceCounterWidget(), "窓口型（即時発行）")
        inner.addTab(PaymentManagementWidget(), "支払管理")
        layout.addWidget(inner)
```

- [ ] **Step 2: main_window.py を更新**

`app/ui/main_window.py` の `_build_tabs` を以下に書き換える：

```python
def _build_tabs(self):
    tabs = QTabWidget()

    from app.ui.dashboard import DashboardWidget
    tabs.addTab(DashboardWidget(), "ダッシュボード")

    from app.ui.project_tab import ProjectTab
    tabs.addTab(ProjectTab(), "事業管理")

    from app.ui.issuance_tab import IssuanceTab
    tabs.addTab(IssuanceTab(), "発行")

    tabs.addTab(QLabel("レポート（Plan 4で実装）"), "レポート")

    from app.ui.settings_tab import SettingsTab
    tabs.addTab(SettingsTab(), "設定")

    self.setCentralWidget(tabs)
```

- [ ] **Step 3: 全テストがパスすることを確認**

```bash
python -m pytest tests/ -v
```

期待: 全テスト PASSED（新サービス含め）

- [ ] **Step 4: コミット**

```bash
git add app/ui/issuance_tab.py app/ui/main_window.py
git commit -m "feat: 発行タブ統合・メインウィンドウ更新 — Plan 2 完了"
```

---

## Plan 2 完了チェックリスト

- [ ] `python -m pytest tests/ -v` で全テストがパス
- [ ] `python main.py` でアプリが起動する
- [ ] ダッシュボードに年度別の事業進捗が表示される
- [ ] 事業を作成（リスト型・窓口型）できる
- [ ] リスト型事業に会員を割り当てられる
- [ ] 発行フロー①（事業から発行）が動作する
- [ ] 発行フロー②（人起点横断合算）が動作する
- [ ] 発行フロー③（窓口型即時発行）が動作する
- [ ] 支払管理で発行済み→支払済みに更新できる

---

**次のステップ：** Plan 3「PDF・印刷」
