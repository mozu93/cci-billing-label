# 商工会議所請求書・領収書発行システム — Plan 4: メール・レポート・年度更新・バックアップ

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** メール送付（個別・一括・テスト送信）、レポート・CSV/Excelエクスポート、年度更新機能、データバックアップ・復元を実装してシステムを完成させる。

**Architecture:** メールはsmtplibでSMTP送信。レポートはサービス層で集計しUIで表示・エクスポート。年度更新はprojectのコピーとメンバーリストの引き継ぎ/リセット。バックアップはDBファイルのコピー。

**Tech Stack:** Python 3.11+, smtplib, openpyxl, PyQt6, SQLAlchemy

---

## ファイル構成（新規作成）

```
app/
  services/
    email_service.py       # SMTP送信・テスト送信
    report_service.py      # 集計クエリ
    fiscal_year_service.py # 年度更新
    backup_service.py      # バックアップ・復元
  ui/
    report_tab.py          # レポートタブ
    email_settings.py      # メール設定UI（設定タブに追加）
    fiscal_year_dialog.py  # 年度更新ダイアログ
    backup_settings.py     # バックアップ設定UI（設定タブに追加）
tests/
  test_report_service.py
  test_fiscal_year_service.py
  test_backup_service.py
```

---

## Task 1: メールサービス

**Files:**
- Create: `app/services/email_service.py`

- [ ] **Step 1: email_service.py を作成**

```python
# app/services/email_service.py
import smtplib
import ssl
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header
from app.utils.app_config import get_config


def get_smtp_config() -> dict:
    return get_config().get("smtp", {})


def _build_message(smtp_config: dict, to_addr: str, subject: str,
                   body: str, pdf_path: str | None = None,
                   is_test: bool = False) -> MIMEMultipart:
    msg = MIMEMultipart()
    from_addr = smtp_config.get("from_addr", "")
    from_name = smtp_config.get("from_name", "")
    msg["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    msg["To"] = to_addr
    msg["Subject"] = Header(
        f"【テスト】{subject}" if is_test else subject, "utf-8"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(pdf_path))
        part["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(pdf_path)}"'
        )
        msg.attach(part)
    return msg


def send_email(to_addr: str, subject: str, body: str,
               pdf_path: str | None = None) -> None:
    """メールを送信する。失敗時は例外を送出。"""
    config = get_smtp_config()
    msg = _build_message(config, to_addr, subject, body, pdf_path)
    _send(config, to_addr, msg)


def send_test_email(subject: str, body: str,
                    pdf_path: str | None = None) -> None:
    """テストメールを設定されたテスト宛先に送信する。"""
    config = get_smtp_config()
    test_addr = config.get("test_addr", "")
    if not test_addr:
        raise ValueError("テスト送信先メールアドレスが設定されていません。")
    msg = _build_message(config, test_addr, subject, body, pdf_path, is_test=True)
    _send(config, test_addr, msg)


def _send(config: dict, to_addr: str, msg: MIMEMultipart) -> None:
    host = config.get("host", "")
    port = int(config.get("port", 587))
    user = config.get("user", "")
    password = config.get("password", "")
    use_tls = config.get("use_tls", True)

    if not host:
        raise ValueError("SMTPサーバーが設定されていません。")

    if use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo()
            s.starttls(context=context)
            if user:
                s.login(user, password)
            s.sendmail(msg["From"], [to_addr], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=15) as s:
            if user:
                s.login(user, password)
            s.sendmail(msg["From"], [to_addr], msg.as_string())


def build_issuance_email(issuance, company_name: str,
                          template_subject: str = "",
                          template_body: str = "") -> tuple[str, str]:
    """発行レコードからメール件名・本文を生成する"""
    doc_label = "請求書" if issuance.doc_type == "invoice" else "領収書"
    subject = template_subject or f"【{company_name}】{doc_label}をお送りします"
    recipient = (issuance.recipient_organization or issuance.recipient_name or "")
    body = template_body or (
        f"{recipient} 様\n\n"
        f"お世話になっております。{company_name}でございます。\n\n"
        f"{doc_label}（{issuance.doc_number}）をお送りします。\n"
        f"金額：¥{int(issuance.amount):,}（税込）\n\n"
        "ご確認のほどよろしくお願いいたします。\n\n"
        f"{company_name}"
    )
    return subject, body
```

- [ ] **Step 2: コミット**

```bash
git add app/services/email_service.py
git commit -m "feat: メールサービス（SMTP送信・テスト送信）を追加"
```

---

## Task 2: レポートサービス

**Files:**
- Create: `app/services/report_service.py`
- Create: `tests/test_report_service.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_report_service.py
from datetime import date
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.member_service import create_member
from app.services.project_service import (
    create_project, add_template_to_project, add_members_to_project,
    get_project_members, activate_project
)
from app.services.issuance_service import (
    create_issuance_for_member, mark_as_issued, record_payment
)
from app.services.report_service import (
    get_unpaid_report, get_payment_report, get_project_summary
)


def _setup(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    activate_project(db_session, proj.id)
    add_template_to_project(db_session, proj.id, tmpl.id)
    m1 = create_member(db_session, member_number="A-001", organization_name="○○商事",
                       organization_kana="マルマルショウジ")
    m2 = create_member(db_session, member_number="A-002", organization_name="△△産業",
                       organization_kana="サンカクサンギョウ")
    add_members_to_project(db_session, proj.id, [m1.id, m2.id])
    pms = get_project_members(db_session, proj.id)
    iss1 = create_issuance_for_member(db_session, proj.id, pms[0].id, m1, "invoice", 2026, 5)
    iss2 = create_issuance_for_member(db_session, proj.id, pms[1].id, m2, "invoice", 2026, 5)
    mark_as_issued(db_session, iss1.id, None, "田中", "窓口手渡し")
    record_payment(db_session, iss1.id, date(2026, 5, 30), 10000, "現金", staff_name="田中")
    return proj, [iss1, iss2]


def test_get_unpaid_report(db_session):
    proj, issuances = _setup(db_session)
    rows = get_unpaid_report(db_session, fiscal_year=2026)
    assert len(rows) == 1
    assert rows[0]["organization_name"] == "△△産業"


def test_get_payment_report(db_session):
    proj, issuances = _setup(db_session)
    rows = get_payment_report(db_session, fiscal_year=2026)
    assert len(rows) == 1
    assert rows[0]["amount"] == 10000


def test_get_project_summary(db_session):
    proj, issuances = _setup(db_session)
    summary = get_project_summary(db_session, fiscal_year=2026)
    assert len(summary) == 1
    row = summary[0]
    assert row["total"] == 2
    assert row["paid"] == 1
    assert row["pending"] == 1
```

- [ ] **Step 2: テスト実行→失敗確認**

```bash
python -m pytest tests/test_report_service.py -v
```

- [ ] **Step 3: report_service.py を作成**

```python
# app/services/report_service.py
from sqlalchemy.orm import Session
from app.database.models import (
    Issuance, ProjectMember, Member, Project, Payment
)
from app.services.project_service import get_project_progress


def get_unpaid_report(session: Session,
                      fiscal_year: int | None = None,
                      project_id: int | None = None) -> list[dict]:
    """未発行・未支払いの発行レコード一覧"""
    q = (session.query(Issuance, Project)
         .join(Project, Issuance.project_id == Project.id)
         .filter(Issuance.status.in_(["準備中", "発行済み"])))
    if fiscal_year:
        q = q.filter(Project.fiscal_year == fiscal_year)
    if project_id:
        q = q.filter(Issuance.project_id == project_id)

    rows = []
    for iss, proj in q.all():
        member = None
        if iss.project_member_id:
            pm = session.get(ProjectMember, iss.project_member_id)
            if pm:
                member = pm.member
        rows.append({
            "doc_number":        iss.doc_number,
            "project_name":      proj.name,
            "fiscal_year":       proj.fiscal_year,
            "organization_name": iss.recipient_organization or (member.organization_name if member else ""),
            "representative_name": iss.recipient_name or (member.representative_name if member else ""),
            "member_number":     member.member_number if member else "",
            "amount":            int(iss.amount),
            "status":            iss.status,
            "doc_type":          iss.doc_type,
        })
    return rows


def get_payment_report(session: Session,
                       fiscal_year: int | None = None,
                       project_id: int | None = None) -> list[dict]:
    """支払済みの入金一覧"""
    q = (session.query(Payment, Issuance, Project)
         .join(Issuance, Payment.issuance_id == Issuance.id)
         .join(Project, Issuance.project_id == Project.id))
    if fiscal_year:
        q = q.filter(Project.fiscal_year == fiscal_year)
    if project_id:
        q = q.filter(Issuance.project_id == project_id)
    q = q.order_by(Payment.payment_date.desc())

    rows = []
    for payment, iss, proj in q.all():
        rows.append({
            "payment_date":    payment.payment_date.strftime("%Y/%m/%d"),
            "doc_number":      iss.doc_number,
            "project_name":    proj.name,
            "fiscal_year":     proj.fiscal_year,
            "organization":    iss.recipient_organization or iss.recipient_name,
            "amount":          int(payment.amount),
            "payment_method":  payment.payment_method,
            "staff_name":      payment.staff_name,
        })
    return rows


def get_project_summary(session: Session,
                         fiscal_year: int | None = None) -> list[dict]:
    """事業別集計"""
    q = session.query(Project).filter(Project.status.in_(["active", "closed"]))
    if fiscal_year:
        q = q.filter(Project.fiscal_year == fiscal_year)

    rows = []
    for proj in q.order_by(Project.fiscal_year.desc(), Project.name).all():
        p = get_project_progress(session, proj.id)
        total_amount = sum(
            int(iss.amount) for iss in
            session.query(Issuance).filter_by(project_id=proj.id).all()
        )
        paid_amount = sum(
            int(iss.amount) for iss in
            session.query(Issuance).filter_by(
                project_id=proj.id, status="支払済み").all()
        )
        rows.append({
            "fiscal_year":   proj.fiscal_year,
            "project_name":  proj.name,
            "project_type":  proj.project_type,
            "total":         p["total"],
            "issued":        p["issued"],
            "paid":          p["paid"],
            "pending":       p["pending"],
            "total_amount":  total_amount,
            "paid_amount":   paid_amount,
        })
    return rows


def export_to_excel(rows: list[dict], headers: list[str],
                    output_path: str) -> str:
    """辞書のリストをExcelファイルに書き出す"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook()
    ws = wb.active
    # ヘッダー行
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1E40AF")
        cell.alignment = Alignment(horizontal="center")
    # データ行
    keys = list(rows[0].keys()) if rows else []
    for row_idx, row in enumerate(rows, 2):
        for col_idx, key in enumerate(keys, 1):
            ws.cell(row=row_idx, column=col_idx, value=row.get(key, ""))
    # 列幅自動調整
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)
    import os
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    wb.save(output_path)
    return output_path
```

- [ ] **Step 4: テスト→パス確認**

```bash
python -m pytest tests/test_report_service.py -v
```

期待: `3 passed`

- [ ] **Step 5: コミット**

```bash
git add app/services/report_service.py tests/test_report_service.py
git commit -m "feat: レポートサービス（未払い・入金・事業別集計・Excelエクスポート）を追加"
```

---

## Task 3: 年度更新サービス

**Files:**
- Create: `app/services/fiscal_year_service.py`
- Create: `tests/test_fiscal_year_service.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_fiscal_year_service.py
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.member_service import create_member
from app.services.project_service import (
    create_project, add_template_to_project, add_members_to_project,
    get_project_members, get_projects
)
from app.services.fiscal_year_service import rollover_fiscal_year


def _setup(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    m1 = create_member(db_session, member_number="A-001", organization_name="○○商事",
                       organization_kana="マルマルショウジ")
    m2 = create_member(db_session, member_number="A-002", organization_name="△△産業",
                       organization_kana="サンカクサンギョウ")
    add_members_to_project(db_session, proj.id, [m1.id, m2.id])
    return proj, [m1, m2]


def test_rollover_creates_new_projects(db_session):
    proj, members = _setup(db_session)
    new_projects = rollover_fiscal_year(
        db_session, from_year=2026, to_year=2027,
        project_ids=[proj.id],
        keep_members={proj.id: True}
    )
    assert len(new_projects) == 1
    assert new_projects[0].fiscal_year == 2027
    assert new_projects[0].status == "draft"
    assert "2027年度" in new_projects[0].name


def test_rollover_keeps_members(db_session):
    proj, members = _setup(db_session)
    new_projects = rollover_fiscal_year(
        db_session, from_year=2026, to_year=2027,
        project_ids=[proj.id],
        keep_members={proj.id: True}
    )
    new_pms = get_project_members(db_session, new_projects[0].id)
    assert len(new_pms) == 2


def test_rollover_resets_members(db_session):
    proj, members = _setup(db_session)
    new_projects = rollover_fiscal_year(
        db_session, from_year=2026, to_year=2027,
        project_ids=[proj.id],
        keep_members={proj.id: False}
    )
    new_pms = get_project_members(db_session, new_projects[0].id)
    assert len(new_pms) == 0


def test_old_year_data_preserved(db_session):
    proj, members = _setup(db_session)
    rollover_fiscal_year(
        db_session, from_year=2026, to_year=2027,
        project_ids=[proj.id],
        keep_members={proj.id: True}
    )
    old_projects = get_projects(db_session, fiscal_year=2026)
    assert len(old_projects) == 1
    assert old_projects[0].fiscal_year == 2026
```

- [ ] **Step 2: テスト実行→失敗確認**

```bash
python -m pytest tests/test_fiscal_year_service.py -v
```

- [ ] **Step 3: fiscal_year_service.py を作成**

```python
# app/services/fiscal_year_service.py
from sqlalchemy.orm import Session
from app.database.models import Project, ProjectTemplate, ProjectMember
from app.services.project_service import (
    get_project_by_id, get_project_templates, get_project_members,
    add_template_to_project, add_members_to_project
)


def rollover_fiscal_year(session: Session,
                          from_year: int, to_year: int,
                          project_ids: list[int],
                          keep_members: dict[int, bool]) -> list[Project]:
    """
    指定した事業を新年度にコピーする。
    keep_members: {project_id: True=引き継ぐ, False=リセット}
    旧年度データは保持される。
    新年度の事業はdraftステータスで作成される。
    """
    new_projects = []
    year_str = str(from_year)
    new_year_str = str(to_year)

    for pid in project_ids:
        old_proj = get_project_by_id(session, pid)
        if not old_proj or old_proj.fiscal_year != from_year:
            continue

        new_name = old_proj.name.replace(f"{from_year}年度", f"{to_year}年度")
        if new_name == old_proj.name:
            new_name = f"{to_year}年度 {old_proj.name}"

        new_proj = Project(
            name=new_name,
            category_id=old_proj.category_id,
            fiscal_year=to_year,
            project_type=old_proj.project_type,
            status="draft",
            notes=old_proj.notes or "",
        )
        session.add(new_proj)
        session.flush()

        for pt in get_project_templates(session, pid):
            add_template_to_project(
                session, new_proj.id,
                pt.item_template_id,
                unit_price_override=int(pt.unit_price_override) if pt.unit_price_override else None,
                sort_order=pt.sort_order
            )

        if keep_members.get(pid, True):
            old_pms = get_project_members(session, pid)
            member_ids = [pm.member_id for pm in old_pms if pm.member_id]
            if member_ids:
                add_members_to_project(session, new_proj.id, member_ids)

        new_projects.append(new_proj)

    session.commit()
    return new_projects


def get_rollover_candidates(session: Session, fiscal_year: int) -> list[Project]:
    """年度更新の候補となる事業（active/closed）を返す"""
    return (session.query(Project)
            .filter(Project.fiscal_year == fiscal_year,
                    Project.status.in_(["active", "closed"]))
            .order_by(Project.name)
            .all())
```

- [ ] **Step 4: テスト→パス確認**

```bash
python -m pytest tests/test_fiscal_year_service.py -v
```

期待: `4 passed`

- [ ] **Step 5: コミット**

```bash
git add app/services/fiscal_year_service.py tests/test_fiscal_year_service.py
git commit -m "feat: 年度更新サービスを追加"
```

---

## Task 4: バックアップサービス

**Files:**
- Create: `app/services/backup_service.py`
- Create: `tests/test_backup_service.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_backup_service.py
import os, tempfile
from app.services.backup_service import create_backup, list_backups


def test_create_backup(tmp_path):
    # ダミーのDBファイルを作成
    db_path = str(tmp_path / "test.db")
    with open(db_path, "wb") as f:
        f.write(b"SQLite format 3\x00" + b"\x00" * 100)
    backup_dir = str(tmp_path / "backups")
    result = create_backup(db_path=db_path, backup_dir=backup_dir)
    assert os.path.exists(result)
    assert result.endswith(".db")


def test_list_backups(tmp_path):
    db_path = str(tmp_path / "test.db")
    with open(db_path, "wb") as f:
        f.write(b"SQLite format 3\x00" + b"\x00" * 100)
    backup_dir = str(tmp_path / "backups")
    create_backup(db_path=db_path, backup_dir=backup_dir)
    create_backup(db_path=db_path, backup_dir=backup_dir)
    backups = list_backups(backup_dir)
    assert len(backups) == 2
```

- [ ] **Step 2: テスト実行→失敗確認**

```bash
python -m pytest tests/test_backup_service.py -v
```

- [ ] **Step 3: backup_service.py を作成**

```python
# app/services/backup_service.py
import os
import shutil
from datetime import datetime
from app.utils.app_config import get_db_url


def get_db_path() -> str | None:
    """SQLiteのDBファイルパスを返す（PostgreSQLの場合はNone）"""
    url = get_db_url()
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "")
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        return path
    return None


def create_backup(db_path: str | None = None,
                  backup_dir: str | None = None) -> str:
    """DBファイルをバックアップする。バックアップファイルのパスを返す。"""
    if db_path is None:
        db_path = get_db_path()
    if not db_path or not os.path.exists(db_path):
        raise FileNotFoundError(f"DBファイルが見つかりません: {db_path}")

    if backup_dir is None:
        from app.utils.app_config import get_config
        config = get_config()
        backup_dir = config.get("backup_dir", "")
        if not backup_dir:
            backup_dir = os.path.join(os.path.expanduser("~"), "cci-billing", "backup")

    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"cci_billing_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    shutil.copy2(db_path, backup_path)
    return backup_path


def list_backups(backup_dir: str | None = None) -> list[dict]:
    """バックアップ一覧を返す（新しい順）"""
    if backup_dir is None:
        from app.utils.app_config import get_config
        config = get_config()
        backup_dir = config.get("backup_dir", "")
        if not backup_dir:
            backup_dir = os.path.join(os.path.expanduser("~"), "cci-billing", "backup")

    if not os.path.exists(backup_dir):
        return []

    backups = []
    for fname in os.listdir(backup_dir):
        if fname.endswith(".db"):
            fpath = os.path.join(backup_dir, fname)
            stat = os.stat(fpath)
            backups.append({
                "name": fname,
                "path": fpath,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y/%m/%d %H:%M"),
            })
    return sorted(backups, key=lambda x: x["created_at"], reverse=True)


def restore_backup(backup_path: str, db_path: str | None = None) -> None:
    """バックアップからDBを復元する"""
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"バックアップファイルが見つかりません: {backup_path}")
    if db_path is None:
        db_path = get_db_path()
    if not db_path:
        raise ValueError("復元先DBパスを特定できません（PostgreSQL構成では手動対応が必要です）。")
    shutil.copy2(backup_path, db_path)
```

- [ ] **Step 4: テスト→パス確認**

```bash
python -m pytest tests/test_backup_service.py -v
```

期待: `2 passed`

- [ ] **Step 5: コミット**

```bash
git add app/services/backup_service.py tests/test_backup_service.py
git commit -m "feat: バックアップサービスを追加"
```

---

## Task 5: レポートタブUI

**Files:**
- Create: `app/ui/report_tab.py`

- [ ] **Step 1: report_tab.py を作成**

```python
# app/ui/report_tab.py
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QComboBox, QLabel,
    QPushButton, QHeaderView, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.report_service import (
    get_unpaid_report, get_payment_report,
    get_project_summary, export_to_excel
)


class ReportTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        inner = QTabWidget()
        inner.addTab(UnpaidReportWidget(), "未払い一覧")
        inner.addTab(PaymentReportWidget(), "入金一覧")
        inner.addTab(ProjectSummaryWidget(), "事業別集計")
        layout.addWidget(inner)


class _BaseReportWidget(QWidget):
    HEADERS: list[str] = []
    KEYS: list[str] = []

    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("年度："))
        self._year_combo = QComboBox()
        current_year = date.today().year
        self._year_combo.addItem("すべて", None)
        for y in range(current_year + 1, current_year - 5, -1):
            self._year_combo.addItem(f"{y}年度", y)
        self._year_combo.setCurrentIndex(2)
        self._year_combo.currentIndexChanged.connect(self._load)
        top.addWidget(self._year_combo)
        btn_refresh = QPushButton("更新")
        btn_refresh.clicked.connect(self._load)
        btn_export_csv = QPushButton("CSV出力")
        btn_export_csv.clicked.connect(self._export_csv)
        btn_export_excel = QPushButton("Excel出力")
        btn_export_excel.clicked.connect(self._export_excel)
        top.addWidget(btn_refresh)
        top.addWidget(btn_export_csv)
        top.addWidget(btn_export_excel)
        top.addStretch()
        layout.addLayout(top)

        self._table = QTableWidget(0, len(self.HEADERS))
        self._table.setHorizontalHeaderLabels(self.HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)
        self._count_label = QLabel("")
        layout.addWidget(self._count_label)

    def _get_rows(self, session, fiscal_year) -> list[dict]:
        raise NotImplementedError

    def _load(self):
        year = self._year_combo.currentData()
        session = get_session()
        try:
            self._rows = self._get_rows(session, year)
        finally:
            session.close()
        self._table.setRowCount(0)
        for row in self._rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            for col, key in enumerate(self.KEYS):
                val = str(row.get(key, ""))
                item = QTableWidgetItem(val)
                self._table.setItem(r, col, item)
        self._count_label.setText(f"{len(self._rows)} 件")

    def _export_csv(self):
        if not hasattr(self, '_rows') or not self._rows:
            QMessageBox.information(self, "情報", "データがありません。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "CSV保存", "", "CSV (*.csv)")
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=self.KEYS)
            writer.writeheader()
            writer.writerows(self._rows)
        QMessageBox.information(self, "完了", f"CSVを保存しました。\n{path}")

    def _export_excel(self):
        if not hasattr(self, '_rows') or not self._rows:
            QMessageBox.information(self, "情報", "データがありません。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Excel保存", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            export_to_excel(self._rows, self.HEADERS, path)
            QMessageBox.information(self, "完了", f"Excelを保存しました。\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))


class UnpaidReportWidget(_BaseReportWidget):
    HEADERS = ["発行番号", "事業名", "年度", "事業所名", "代表者名", "会員番号", "金額", "状態"]
    KEYS = ["doc_number", "project_name", "fiscal_year", "organization_name",
            "representative_name", "member_number", "amount", "status"]

    def _get_rows(self, session, fiscal_year):
        return get_unpaid_report(session, fiscal_year)


class PaymentReportWidget(_BaseReportWidget):
    HEADERS = ["入金日", "発行番号", "事業名", "年度", "宛先", "入金額", "入金方法", "担当者"]
    KEYS = ["payment_date", "doc_number", "project_name", "fiscal_year",
            "organization", "amount", "payment_method", "staff_name"]

    def _get_rows(self, session, fiscal_year):
        return get_payment_report(session, fiscal_year)


class ProjectSummaryWidget(_BaseReportWidget):
    HEADERS = ["年度", "事業名", "種別", "全件", "発行済", "支払済", "未発行", "総額", "入金額"]
    KEYS = ["fiscal_year", "project_name", "project_type", "total", "issued",
            "paid", "pending", "total_amount", "paid_amount"]

    def _get_rows(self, session, fiscal_year):
        return get_project_summary(session, fiscal_year)
```

- [ ] **Step 2: コミット**

```bash
git add app/ui/report_tab.py
git commit -m "feat: レポートタブUI（未払い・入金・事業別集計・CSV/Excel出力）を追加"
```

---

## Task 6: メール設定・年度更新・バックアップUI

**Files:**
- Create: `app/ui/email_settings.py`
- Create: `app/ui/fiscal_year_dialog.py`
- Create: `app/ui/backup_settings.py`

- [ ] **Step 1: email_settings.py を作成**

```python
# app/ui/email_settings.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLineEdit, QSpinBox, QCheckBox, QPushButton, QGroupBox, QMessageBox
)
from app.utils.app_config import get_config, save_config


class EmailSettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        grp = QGroupBox("SMTP設定")
        form = QFormLayout(grp)

        self._host = QLineEdit()
        self._host.setPlaceholderText("例：smtp.gmail.com")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(587)
        self._user = QLineEdit()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._from_addr = QLineEdit()
        self._from_name = QLineEdit()
        self._use_tls = QCheckBox("STARTTLS を使用")
        self._use_tls.setChecked(True)
        self._test_addr = QLineEdit()
        self._test_addr.setPlaceholderText("テスト送信先メールアドレス")

        form.addRow("SMTPサーバー", self._host)
        form.addRow("ポート", self._port)
        form.addRow("ユーザー名", self._user)
        form.addRow("パスワード", self._password)
        form.addRow("送信元アドレス", self._from_addr)
        form.addRow("送信者名", self._from_name)
        form.addRow("", self._use_tls)
        form.addRow("テスト送信先", self._test_addr)
        layout.addWidget(grp)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("設定を保存")
        btn_save.clicked.connect(self._save)
        btn_test = QPushButton("テストメール送信")
        btn_test.clicked.connect(self._test)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_test)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _load(self):
        smtp = get_config().get("smtp", {})
        self._host.setText(smtp.get("host", ""))
        self._port.setValue(int(smtp.get("port", 587)))
        self._user.setText(smtp.get("user", ""))
        self._password.setText(smtp.get("password", ""))
        self._from_addr.setText(smtp.get("from_addr", ""))
        self._from_name.setText(smtp.get("from_name", ""))
        self._use_tls.setChecked(smtp.get("use_tls", True))
        self._test_addr.setText(smtp.get("test_addr", ""))

    def _save(self):
        config = get_config()
        config["smtp"] = {
            "host":      self._host.text().strip(),
            "port":      self._port.value(),
            "user":      self._user.text().strip(),
            "password":  self._password.text(),
            "from_addr": self._from_addr.text().strip(),
            "from_name": self._from_name.text().strip(),
            "use_tls":   self._use_tls.isChecked(),
            "test_addr": self._test_addr.text().strip(),
        }
        save_config(config)
        QMessageBox.information(self, "保存", "メール設定を保存しました。")

    def _test(self):
        self._save()
        try:
            from app.services.email_service import send_test_email
            send_test_email("テスト送信", "cci-billingからのテストメールです。")
            QMessageBox.information(self, "成功", "テストメールを送信しました。")
        except Exception as e:
            QMessageBox.critical(self, "送信エラー", str(e))
```

- [ ] **Step 2: fiscal_year_dialog.py を作成**

```python
# app/ui/fiscal_year_dialog.py
from datetime import date
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QTableWidget, QTableWidgetItem, QCheckBox, QPushButton,
    QMessageBox, QHeaderView, QWidget
)
from PyQt6.QtCore import Qt
from app.database.connection import get_session
from app.services.fiscal_year_service import (
    get_rollover_candidates, rollover_fiscal_year
)
from app.services.project_service import get_project_members


class FiscalYearDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("年度更新")
        self.resize(700, 500)
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("更新元年度："))
        self._from_year = QSpinBox()
        self._from_year.setRange(2020, 2099)
        self._from_year.setValue(date.today().year)
        self._from_year.valueChanged.connect(self._load)
        top.addWidget(self._from_year)
        top.addWidget(QLabel("→　更新先年度："))
        self._to_year = QSpinBox()
        self._to_year.setRange(2020, 2099)
        self._to_year.setValue(date.today().year + 1)
        top.addWidget(self._to_year)
        top.addStretch()
        layout.addLayout(top)

        layout.addWidget(QLabel(
            "引き継ぐ事業にチェックを入れてください。\n"
            "「会員引き継ぎ」にチェックがあると、会員リストをそのまま新年度にコピーします。\n"
            "単発事業（視察研修会など）はチェックを外してください。"
        ))

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["選択", "事業名", "種別", "会員引き継ぎ"])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("キャンセル")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("年度更新を実行する")
        btn_ok.setStyleSheet("font-weight: bold;")
        btn_ok.clicked.connect(self._execute)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _load(self):
        from_year = self._from_year.value()
        session = get_session()
        try:
            candidates = get_rollover_candidates(session, from_year)
        finally:
            session.close()
        self._table.setRowCount(0)
        for proj in candidates:
            row = self._table.rowCount()
            self._table.insertRow(row)
            cb_select = QCheckBox()
            cb_select.setChecked(True)
            self._table.setCellWidget(row, 0, cb_select)
            self._table.setItem(row, 1, QTableWidgetItem(proj.name))
            type_label = "リスト型" if proj.project_type == "list" else "窓口型"
            self._table.setItem(row, 2, QTableWidgetItem(type_label))
            cb_keep = QCheckBox()
            cb_keep.setChecked(proj.project_type == "list")
            self._table.setCellWidget(row, 3, cb_keep)
            self._table.item(row, 1).setData(Qt.ItemDataRole.UserRole, proj.id)

    def _execute(self):
        to_year = self._to_year.value()
        from_year = self._from_year.value()
        if to_year <= from_year:
            QMessageBox.warning(self, "エラー", "更新先年度は更新元年度より大きい値を指定してください。")
            return

        project_ids = []
        keep_members = {}
        for row in range(self._table.rowCount()):
            cb_select = self._table.cellWidget(row, 0)
            if not (cb_select and cb_select.isChecked()):
                continue
            proj_id = self._table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            cb_keep = self._table.cellWidget(row, 3)
            project_ids.append(proj_id)
            keep_members[proj_id] = cb_keep.isChecked() if cb_keep else False

        if not project_ids:
            QMessageBox.warning(self, "エラー", "引き継ぐ事業を選択してください。")
            return

        session = get_session()
        try:
            new_projects = rollover_fiscal_year(
                session, from_year=from_year, to_year=to_year,
                project_ids=project_ids, keep_members=keep_members
            )
            QMessageBox.information(
                self, "完了",
                f"{len(new_projects)} 件の事業を{to_year}年度にコピーしました。\n"
                "ダッシュボードで新年度の事業を「受付開始」してください。"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
        finally:
            session.close()
        self.accept()
```

- [ ] **Step 3: backup_settings.py を作成**

```python
# app/ui/backup_settings.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QGroupBox, QHeaderView, QFileDialog, QLabel
)
from PyQt6.QtCore import Qt
from app.utils.app_config import get_config, save_config
from app.services.backup_service import create_backup, list_backups, restore_backup, get_db_path


class BackupSettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        self._load()

    def _build(self):
        layout = QVBoxLayout(self)

        grp = QGroupBox("バックアップ設定")
        form = QFormLayout(grp)
        self._backup_dir = QLineEdit()
        self._backup_dir.setPlaceholderText("バックアップ保存先フォルダ")
        btn_browse = QPushButton("参照")
        btn_browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._backup_dir)
        dir_row.addWidget(btn_browse)
        form.addRow("保存先", dir_row)
        layout.addWidget(grp)

        btn_row = QHBoxLayout()
        btn_save_cfg = QPushButton("設定を保存")
        btn_save_cfg.clicked.connect(self._save_config)
        btn_backup = QPushButton("今すぐバックアップ")
        btn_backup.setStyleSheet("font-weight: bold;")
        btn_backup.clicked.connect(self._backup_now)
        btn_refresh = QPushButton("一覧を更新")
        btn_refresh.clicked.connect(self._load_list)
        btn_row.addWidget(btn_save_cfg)
        btn_row.addWidget(btn_backup)
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        db_type = get_config().get("db_type", "sqlite")
        if db_type != "sqlite":
            layout.addWidget(QLabel(
                "※ PostgreSQL構成のバックアップはpg_dumpコマンドを使用してください。\n"
                "SQLiteファイルのバックアップのみ自動対応しています。"
            ))

        layout.addWidget(QLabel("バックアップ一覧："))
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["ファイル名", "作成日時", "サイズ"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        btn_row2 = QHBoxLayout()
        btn_restore = QPushButton("選択したバックアップを復元")
        btn_restore.clicked.connect(self._restore)
        btn_row2.addWidget(btn_restore)
        btn_row2.addStretch()
        layout.addLayout(btn_row2)

    def _load(self):
        config = get_config()
        self._backup_dir.setText(config.get("backup_dir", ""))
        self._load_list()

    def _load_list(self):
        backups = list_backups()
        self._table.setRowCount(0)
        for b in backups:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(b["name"]))
            self._table.setItem(row, 1, QTableWidgetItem(b["created_at"]))
            size_kb = b["size"] // 1024
            self._table.setItem(row, 2, QTableWidgetItem(f"{size_kb} KB"))
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, b["path"])

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "バックアップ先を選択")
        if d:
            self._backup_dir.setText(d)

    def _save_config(self):
        config = get_config()
        config["backup_dir"] = self._backup_dir.text().strip()
        save_config(config)
        QMessageBox.information(self, "保存", "設定を保存しました。")

    def _backup_now(self):
        db_path = get_db_path()
        if not db_path:
            QMessageBox.warning(self, "非対応",
                                "PostgreSQL構成では自動バックアップに対応していません。")
            return
        try:
            self._save_config()
            path = create_backup()
            QMessageBox.information(self, "完了", f"バックアップしました。\n{path}")
            self._load_list()
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))

    def _restore(self):
        row = self._table.currentRow()
        if row < 0:
            return
        backup_path = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        ret = QMessageBox.warning(
            self, "復元の確認",
            f"このバックアップから復元しますか？\n\n{backup_path}\n\n"
            "現在のデータはすべて上書きされます。\nアプリを再起動してください。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            restore_backup(backup_path)
            QMessageBox.information(self, "完了",
                                    "復元しました。アプリを再起動してください。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", str(e))
```

- [ ] **Step 4: コミット**

```bash
git add app/ui/email_settings.py app/ui/fiscal_year_dialog.py app/ui/backup_settings.py
git commit -m "feat: メール設定・年度更新・バックアップUIを追加"
```

---

## Task 7: 設定タブ・メインウィンドウ統合

**Files:**
- Modify: `app/ui/settings_tab.py`
- Modify: `app/ui/main_window.py`
- Modify: `app/ui/dashboard.py`（年度更新ボタン追加）

- [ ] **Step 1: settings_tab.py を更新**

```python
# app/ui/settings_tab.py
from PyQt6.QtWidgets import QWidget, QTabWidget, QVBoxLayout


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
        from app.ui.email_settings import EmailSettingsWidget
        from app.ui.backup_settings import BackupSettingsWidget

        inner.addTab(CompanySettingsWidget(), "発行元情報")
        inner.addTab(StaffManagementWidget(), "スタッフ管理")
        inner.addTab(CategoryManagementWidget(), "カテゴリ")
        inner.addTab(ItemTemplateManagementWidget(), "請求項目テンプレート")
        inner.addTab(MemberListWidget(), "会員マスタ")
        inner.addTab(EmailSettingsWidget(), "メール設定")
        inner.addTab(BackupSettingsWidget(), "バックアップ")
        layout.addWidget(inner)
```

- [ ] **Step 2: main_window.py のレポートタブを更新**

`app/ui/main_window.py` の `_build_tabs` を更新：

```python
        from app.ui.report_tab import ReportTab
        tabs.addTab(ReportTab(), "レポート")
```

- [ ] **Step 3: dashboard.py に年度更新ボタンを追加**

`DashboardWidget._build` の top_row に追加：

```python
        btn_rollover = QPushButton("年度更新")
        btn_rollover.clicked.connect(self._rollover)
        top_row.addWidget(btn_rollover)
```

`_rollover` メソッドを追加：

```python
    def _rollover(self):
        from app.ui.fiscal_year_dialog import FiscalYearDialog
        from PyQt6.QtWidgets import QDialog
        dlg = FiscalYearDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()
```

- [ ] **Step 4: 全テスト確認**

```bash
python -m pytest tests/ -v
```

期待: 全テスト PASSED

- [ ] **Step 5: 最終コミット**

```bash
git add .
git commit -m "feat: Plan 4完了 — メール・レポート・年度更新・バックアップ — システム完成"
```

---

## Plan 4 完了チェックリスト

- [ ] `python -m pytest tests/ -v` で全テストがパス
- [ ] 設定タブ→「メール設定」でSMTP設定・テスト送信できる
- [ ] レポートタブ→「未払い一覧」「入金一覧」「事業別集計」が表示される
- [ ] CSV・Excel出力ができる
- [ ] ダッシュボード→「年度更新」で新年度の事業がdraftで作成される
- [ ] 設定タブ→「バックアップ」でバックアップ・復元できる
