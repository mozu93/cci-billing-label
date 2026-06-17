# 事業名簿モデル再設計 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 中央の会員マスタを廃止し、事業（イベント）ごとに宛名を自前保持する名簿モデルへ移行する。

**Architecture:** `ProjectMember` が宛名フィールド（事業所名・代表者名・フリガナ・郵便番号・住所・電話・メール・備考）を直接保持する。発行・一括PDF・レポートは `pm.member.*` 参照をやめ `pm.*` を直接読む。名簿は手入力・Excel/貼り付け取り込み（既存の列マッピング機構を転用）・他事業からのコピーで登録する。会員マスタ関連（テーブル・サービス・UI）は削除する。

**Tech Stack:** Python / PyQt6 / SQLAlchemy / SQLite（開発）/ pytest + pytest-qt。

**前提:** 本番DB未稼働・実データなし。開発DBは作り直し前提（破壊的スキーマ変更可）。作業は `cci-billing` リポジトリ。テスト実行は `python -m pytest`。

**重要な順序性:** Task 1 でデータ層を入れ替えると、UI（事業から発行・名簿パネル・随時受取）は Task 2〜4 で直すまで一時的に動作しない。テストはタスクごとに緑を保つが、アプリ全体の手動動作確認は Task 5 完了後に行う。

---

## File Structure

| ファイル | 責務 | 変更 |
|---------|------|------|
| `app/database/models.py` | ORMモデル | `ProjectMember` に宛名フィールド追加・`member_id`/`member` 削除。`Member`/`MemberNameHistory` は Task 5 で削除 |
| `app/services/project_service.py` | 事業・名簿サービス | 名簿行作成 `add_roster_entries`、コピー `copy_roster_from_project`、`get_project_members`（joinedload撤去） |
| `app/services/issuance_service.py` | 発行サービス | `create_issuance_for_member` の宛名引数化、`get_pending_issuances_for_project_member` 追加 |
| `app/services/report_service.py` | レポート | `pm.member.*` → `pm.*` |
| `app/services/pdf/batch_pdf.py` | 一括PDF | `pm.member` → `pm` 直接 |
| `app/services/fiscal_year_service.py` | 年度更新 | 引き継ぎを名簿スナップショット複製に |
| `app/services/roster_recipient.py`（新規） | 宛名整形 | `recipient_label(pm)` を提供（旧 `get_recipient_label` 相当） |
| `app/ui/project_member_panel.py` | 名簿パネル | 手入力追加/編集ダイアログ・取り込み転用・他事業コピー |
| `app/ui/roster_import.py`（新規・旧 member_import 転用） | 名簿取り込み | 列マッピングで事業名簿に取り込み |
| `app/ui/issuance_from_project.py` | 事業から発行 | `pm.member` → `pm` 直接 |
| `app/ui/issuance_cross_member.py` | 随時受取 | 名簿検索→事業内未発行発行 |
| `app/ui/settings_tab.py` | 設定タブ | 会員マスタ タブ削除 |
| 削除：`app/ui/member_list.py` `app/ui/member_form.py` `app/services/member_service.py` `app/ui/member_import.py` | 会員マスタ機能 | Task 5 |

---

## Task 1: データ層の入れ替え（モデル＋サービス＋発行/レポート/PDF/年度更新）

**Files:**
- Modify: `app/database/models.py`（`ProjectMember`）
- Modify: `app/services/project_service.py`
- Modify: `app/services/issuance_service.py`
- Modify: `app/services/report_service.py`
- Modify: `app/services/pdf/batch_pdf.py`
- Modify: `app/services/fiscal_year_service.py`
- Create: `app/services/roster_recipient.py`
- Test: `tests/test_project_service.py`（書き換え）, `tests/test_roster_recipient.py`（新規）, `tests/test_fiscal_year_service.py`（更新）

- [ ] **Step 1: `ProjectMember` モデルを自己完結に変更**

`app/database/models.py` の `ProjectMember` を次に置換：

```python
class ProjectMember(Base):
    __tablename__ = "project_members"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    organization_name = Column(String(200), default="")
    organization_kana = Column(String(200), default="")
    representative_name = Column(String(100), default="")
    representative_kana = Column(String(100), default="")
    postal_code = Column(String(10), default="")
    address = Column(String(300), default="")
    phone = Column(String(50), default="")
    email = Column(String(200), default="")
    notes = Column(Text, default="")
    sort_order = Column(Integer, default=0)
```

（`member_id` と `member` リレーションを削除。`Member`/`MemberNameHistory` クラスはこの時点では残す＝import互換のため。）

- [ ] **Step 2: 宛名整形サービスを作成（失敗するテストを先に）**

`tests/test_roster_recipient.py`:

```python
from app.database.models import ProjectMember
from app.services.roster_recipient import recipient_label


def test_recipient_label_org_and_rep():
    pm = ProjectMember(organization_name="○○商事", representative_name="田中太郎")
    assert recipient_label(pm) == "○○商事 田中太郎 様"


def test_recipient_label_org_only():
    pm = ProjectMember(organization_name="○○商事", representative_name="")
    assert recipient_label(pm) == "○○商事 御中"


def test_recipient_label_rep_only():
    pm = ProjectMember(organization_name="", representative_name="田中太郎")
    assert recipient_label(pm) == "田中太郎 様"
```

- [ ] **Step 3: テストが失敗することを確認**

Run: `python -m pytest tests/test_roster_recipient.py -v`
Expected: FAIL（`ModuleNotFoundError: app.services.roster_recipient`）

- [ ] **Step 4: 宛名整形サービスを実装**

`app/services/roster_recipient.py`:

```python
# app/services/roster_recipient.py
from app.database.models import ProjectMember


def recipient_label(pm: ProjectMember) -> str:
    if pm.organization_name and pm.representative_name:
        return f"{pm.organization_name} {pm.representative_name} 様"
    if pm.organization_name:
        return f"{pm.organization_name} 御中"
    return f"{pm.representative_name} 様"
```

- [ ] **Step 5: テストが通ることを確認**

Run: `python -m pytest tests/test_roster_recipient.py -v`
Expected: PASS

- [ ] **Step 6: `project_service` の名簿関数を置換（失敗するテストを先に）**

`tests/test_project_service.py` の名簿関連テストを次に置換（既存の `add_members_to_project`/`Member` を使うテストは削除し、以下を追加）：

```python
from app.services.project_service import (
    create_project, add_roster_entries, get_project_members,
    remove_member_from_project, copy_roster_from_project,
)


def _mk_project(session, name="2026 青年部"):
    return create_project(session, name=name, category_id=None,
                          fiscal_year=2026, project_type="list")


def test_add_roster_entries_and_get(db_session):
    proj = _mk_project(db_session)
    add_roster_entries(db_session, proj.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
        {"organization_name": "△△産業", "representative_name": "鈴木",
         "email": "suzuki@example.com"},
    ])
    pms = get_project_members(db_session, proj.id)
    assert [p.organization_name for p in pms] == ["○○商事", "△△産業"]
    assert pms[1].email == "suzuki@example.com"
    assert pms[0].sort_order == 0 and pms[1].sort_order == 1


def test_copy_roster_from_project_snapshot(db_session):
    src = _mk_project(db_session, "2025 青年部")
    add_roster_entries(db_session, src.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    dst = _mk_project(db_session, "2026 青年部")
    copy_roster_from_project(db_session, src.id, dst.id)
    dst_pms = get_project_members(db_session, dst.id)
    assert len(dst_pms) == 1
    assert dst_pms[0].organization_name == "○○商事"
    # スナップショット：コピー先を編集しても元に影響しない
    dst_pms[0].organization_name = "改名"
    db_session.commit()
    src_pms = get_project_members(db_session, src.id)
    assert src_pms[0].organization_name == "○○商事"
```

- [ ] **Step 7: テストが失敗することを確認**

Run: `python -m pytest tests/test_project_service.py -v`
Expected: FAIL（`add_roster_entries` 等が未定義）

- [ ] **Step 8: `project_service` を更新**

`app/services/project_service.py`：
`add_members_to_project` を削除し、以下を追加。`get_project_members` の `joinedload(ProjectMember.member)` を撤去。

```python
def add_roster_entries(session: Session, project_id: int,
                       entries: list[dict]) -> list[ProjectMember]:
    base = session.query(ProjectMember).filter_by(project_id=project_id).count()
    pms = []
    for i, e in enumerate(entries):
        pm = ProjectMember(
            project_id=project_id,
            organization_name=e.get("organization_name", ""),
            organization_kana=e.get("organization_kana", ""),
            representative_name=e.get("representative_name", ""),
            representative_kana=e.get("representative_kana", ""),
            postal_code=e.get("postal_code", ""),
            address=e.get("address", ""),
            phone=e.get("phone", ""),
            email=e.get("email", ""),
            notes=e.get("notes", ""),
            sort_order=base + i,
        )
        session.add(pm)
        pms.append(pm)
    session.commit()
    return pms


def copy_roster_from_project(session: Session, src_project_id: int,
                             dst_project_id: int) -> list[ProjectMember]:
    src = get_project_members(session, src_project_id)
    entries = [{
        "organization_name": p.organization_name,
        "organization_kana": p.organization_kana,
        "representative_name": p.representative_name,
        "representative_kana": p.representative_kana,
        "postal_code": p.postal_code,
        "address": p.address,
        "phone": p.phone,
        "email": p.email,
        "notes": p.notes,
    } for p in src]
    return add_roster_entries(session, dst_project_id, entries)
```

`get_project_members` を次に変更：

```python
def get_project_members(session: Session, project_id: int) -> list[ProjectMember]:
    return (session.query(ProjectMember)
            .filter_by(project_id=project_id)
            .order_by(ProjectMember.sort_order)
            .all())
```

- [ ] **Step 9: テストが通ることを確認**

Run: `python -m pytest tests/test_project_service.py -v`
Expected: PASS

- [ ] **Step 10: 発行サービスの宛名引数化**

`app/services/issuance_service.py`：
`create_issuance_for_member` の `member: Member` 引数を廃し、宛名を引数で受ける。`get_pending_issuances_for_member` を `get_pending_issuances_for_project_member` に置換。

```python
def create_issuance_for_member(session: Session, project_id: int,
                               project_member_id: int,
                               recipient_organization: str,
                               recipient_name: str,
                               doc_type: str, fiscal_year: int,
                               month: int) -> Issuance:
    doc_number = get_next_doc_number(session, doc_type, fiscal_year, month)
    lines, total = _build_lines_from_project(session, project_id)
    issuance = Issuance(
        project_id=project_id,
        project_member_id=project_member_id,
        recipient_organization=recipient_organization,
        recipient_name=recipient_name,
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
```

ファイル末尾の `get_pending_issuances_for_member` を置換：

```python
def get_pending_issuances_for_project_member(session: Session,
                                             project_member_id: int) -> list[Issuance]:
    return (session.query(Issuance)
            .filter(Issuance.project_member_id == project_member_id,
                    Issuance.status == "準備中")
            .all())
```

`issuance_service.py` 冒頭の `from app.database.models import ... Member ...` があれば `Member` を除く（`Member` 型注釈の使用箇所がなくなるため）。

- [ ] **Step 11: 一括PDFの宛名解決を直接参照に**

`app/services/pdf/batch_pdf.py` の `for pm in pms:` ループ内、`m = pm.member` 分岐を次に変更：

```python
    for pm in pms:
        iss = (session.query(Issuance)
               .filter_by(project_member_id=pm.id)
               .order_by(Issuance.created_at.desc())
               .first())
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
        # 以降は既存どおり
```

- [ ] **Step 12: レポートの宛名解決を直接参照に**

`app/services/report_service.py` の `get_unpaid_report`（10-37行付近）内、`member` を引く箇所を `pm` 直接に変更：

```python
    for iss, proj in q.all():
        pm = session.get(ProjectMember, iss.project_member_id) if iss.project_member_id else None
        rows.append({
            "doc_number":          iss.doc_number,
            "project_name":        proj.name,
            "fiscal_year":         proj.fiscal_year,
            "organization_name":   iss.recipient_organization or (pm.organization_name if pm else ""),
            "representative_name": iss.recipient_name or (pm.representative_name if pm else ""),
            "member_number":       "",
            "amount":              int(iss.amount),
            "status":              iss.status,
            "doc_type":            iss.doc_type,
        })
```

（`member_number` 列は廃止だが互換のため空文字で残す。Excel/CSV出力側の列定義は変更しない。）

- [ ] **Step 13: 年度更新の引き継ぎをスナップショット複製に（失敗テスト→実装）**

`tests/test_fiscal_year_service.py` の引き継ぎテストを、`copy_roster` ベースに更新（既存が `Member`/`add_members_to_project` 前提なら置換）：

```python
def test_rollover_copies_roster(db_session):
    from app.services.project_service import create_project, add_roster_entries, get_project_members
    from app.services.fiscal_year_service import rollover_fiscal_year
    src = create_project(db_session, name="2025年度 青年部", category_id=None,
                         fiscal_year=2025, project_type="list")
    src.status = "active"
    db_session.commit()
    add_roster_entries(db_session, src.id, [
        {"organization_name": "○○商事", "representative_name": "田中"},
    ])
    new = rollover_fiscal_year(db_session, 2025, 2026, [src.id], {src.id: True})
    pms = get_project_members(db_session, new[0].id)
    assert len(pms) == 1
    assert pms[0].organization_name == "○○商事"
```

`app/services/fiscal_year_service.py`：import を更新し、引き継ぎ部を置換。

```python
from app.services.project_service import (
    get_project_by_id, get_project_templates, get_project_members,
    add_template_to_project, copy_roster_from_project,
)
```

```python
        if keep_members.get(pid, True):
            copy_roster_from_project(session, pid, new_proj.id)
```

- [ ] **Step 14: データ層全体のテストを実行**

Run: `python -m pytest tests/test_project_service.py tests/test_roster_recipient.py tests/test_fiscal_year_service.py tests/test_issuance_service.py tests/test_report_service.py -v`
Expected: PASS（`test_issuance_service.py`/`test_report_service.py` が `Member`/旧API を使っていれば、本タスク内で新APIに合わせて修正する）

- [ ] **Step 15: コミット**

```bash
git add app/database/models.py app/services/project_service.py app/services/issuance_service.py app/services/report_service.py app/services/pdf/batch_pdf.py app/services/fiscal_year_service.py app/services/roster_recipient.py tests/
git commit -m "refactor: 事業名簿を自己完結化しデータ層の宛名解決を直接参照に"
```

---

## Task 2: 名簿パネルの手入力追加/編集・他事業コピー

**Files:**
- Modify: `app/ui/project_member_panel.py`
- Modify: `app/ui/issuance_from_project.py`
- Test: `tests/test_project_member_panel.py`（新規）

- [ ] **Step 1: 名簿エントリ編集ダイアログと操作のテスト（失敗）**

`tests/test_project_member_panel.py`:

```python
from PyQt6.QtWidgets import QPushButton


def _button_texts(w):
    return [b.text() for b in w.findChildren(QPushButton)]


def test_entry_dialog_returns_values(qtbot, memory_db):
    from app.ui.project_member_panel import RosterEntryDialog
    dlg = RosterEntryDialog()
    qtbot.addWidget(dlg)
    dlg._fields["organization_name"].setText("○○商事")
    dlg._fields["representative_name"].setText("田中")
    dlg._fields["email"].setText("t@example.com")
    v = dlg.values()
    assert v["organization_name"] == "○○商事"
    assert v["representative_name"] == "田中"
    assert v["email"] == "t@example.com"


def test_panel_has_add_and_copy_buttons(qtbot, memory_db):
    from app.ui.project_member_panel import ProjectMemberPanel
    from app.services.project_service import create_project
    from app.database.connection import get_session
    s = get_session()
    try:
        proj = create_project(s, name="2026 青年部", category_id=None,
                              fiscal_year=2026, project_type="list")
        pid = proj.id
    finally:
        s.close()
    panel = ProjectMemberPanel(pid)
    qtbot.addWidget(panel)
    texts = _button_texts(panel)
    assert "行を追加" in texts
    assert "他の事業からコピー" in texts
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python -m pytest tests/test_project_member_panel.py -v`
Expected: FAIL（`RosterEntryDialog` 未定義 等）

- [ ] **Step 3: 名簿パネルを更新**

`app/ui/project_member_panel.py`：
- import を更新（`add_roster_entries`, `copy_roster_from_project`, `get_projects` を使用。`add_members_to_project`/`search_members` 依存を削除）。
- テーブル列を `["事業所名", "代表者名", "メール", "電話"]` に変更し、`_load` で `pm.organization_name` 等を直接表示（`pm.member` 参照を撤去）。`UserRole` に `pm.id` を保持。
- ボタン行に「行を追加」「他の事業からコピー」を追加（既存の「削除」確認ダイアログは維持）。
- `RosterEntryDialog`（QFormLayout に8項目：事業所名・フリガナ・代表者名・代表者フリガナ・郵便番号・住所・電話・メール、`self._fields: dict[str, QLineEdit]`、`values()` で dict を返す）を追加。「事業所名」「代表者名」のいずれも空なら保存時に警告。
- 「行を追加」→ `RosterEntryDialog` → `add_roster_entries(session, self._project_id, [values])` → `_load()`。
- ダブルクリック/「編集」→ 既存行を `RosterEntryDialog` に初期表示し、保存で当該 `ProjectMember` の各属性を更新・commit。
- 「他の事業からコピー」→ `ProjectCopyDialog`（年度・事業を選ぶ QComboBox、`get_projects(session)` で一覧）→ 選択した事業IDで `copy_roster_from_project(session, src_id, self._project_id)` → `_load()`。
- 取り込み（既存の「Excelインポート」「貼り付けインポート」）は Task 3 で `RosterImportDialog` に差し替えるため、本タスクではボタンの `clicked` 接続先を一旦 `_open_import_dialog`（Task 3で実装）に向けるプレースホルダにせず、**Task 3 まで既存ボタンは残し未接続にしない**：本タスクでは取り込みボタンの中身は触らず、`_register_rows` のみ `add_roster_entries(session, self._project_id, rows)` に変更（マスタ照合を除去）。

`_register_rows` を次に変更：

```python
    def _register_rows(self, rows: list[dict]):
        from app.services.project_service import add_roster_entries
        valid = [r for r in rows
                 if r.get("organization_name") or r.get("representative_name")]
        if valid:
            add_roster_entries(get_session(), self._project_id, valid)
        QMessageBox.information(self, "完了", f"{len(valid)} 件を追加しました。")
        self._load()
```

- [ ] **Step 4: 事業から発行UIの直接参照化**

`app/ui/issuance_from_project.py`：
- 列を `["事業所名", "代表者名", "ステータス", "発行番号"]` に変更。
- `_load_members` の `m = pm.member; if not m: continue` を撤去し、`pm.organization_name` 等を直接使用。検索対象も `pm.organization_name/representative_name/organization_kana`。
- `_prepare` の `create_issuance_for_member(...)` 呼び出しを新シグネチャに：

```python
            create_issuance_for_member(
                session, project_id=project_id,
                project_member_id=pm_id,
                recipient_organization=pm.organization_name,
                recipient_name=pm.representative_name,
                doc_type=doc_type,
                fiscal_year=today.year, month=today.month,
            )
```

（`pm = session.get(ProjectMember, pm_id)` を使用。`m = pm.member` を削除。）

- [ ] **Step 5: テストが通ることを確認**

Run: `python -m pytest tests/test_project_member_panel.py -v`
Expected: PASS

- [ ] **Step 6: 全体テスト**

Run: `python -m pytest`
Expected: PASS

- [ ] **Step 7: コミット**

```bash
git add app/ui/project_member_panel.py app/ui/issuance_from_project.py tests/test_project_member_panel.py
git commit -m "feat: 事業名簿の手入力追加/編集と他事業コピーを追加"
```

---

## Task 3: 名簿取り込み（列マッピング）を会員マスタから事業名簿へ転用

**Files:**
- Create: `app/ui/roster_import.py`（`app/ui/member_import.py` を基に）
- Modify: `app/ui/project_member_panel.py`（取り込みボタンを `RosterImportDialog` に接続）
- Modify: `tests/test_member_import_mapping.py` → `tests/test_roster_import_mapping.py`（リネーム＆更新）

- [ ] **Step 1: 取り込みダイアログのテスト（失敗）**

`tests/test_roster_import_mapping.py`（既存 `test_member_import_mapping.py` の純粋関数テストは `excel_utils` 側で維持。ダイアログ部のみ更新）：

```python
def test_roster_import_dialog_maps_rows(qtbot, memory_db):
    from app.ui.roster_import import RosterImportDialog
    dlg = RosterImportDialog(project_id=1)
    qtbot.addWidget(dlg)
    dlg._set_raw_rows([["○○商事", "田中", "t@example.com"]])
    # 既定は位置割り当て：列0=事業所名…だが mapping は調整可能
    rows = dlg._mapped_rows()
    assert len(rows) == 1
    assert rows[0]["organization_name"] == "○○商事"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python -m pytest tests/test_roster_import_mapping.py -v`
Expected: FAIL（`app.ui.roster_import` 未定義）

- [ ] **Step 3: `RosterImportDialog` を作成**

`app/ui/member_import.py` を `app/ui/roster_import.py` にコピーして次を変更：
- クラス名 `MemberImportDialog` → `RosterImportDialog`。`__init__(self, project_id: int, parent=None)` で `self._project_id` を保持。
- `FIELD_LABELS` から `member_number` を除いた8項目を対象にする（`excel_utils` に `ROSTER_COLUMNS = [c for c in MEMBER_COLUMNS if c != "member_number"]` を追加して使用、または既存 `MEMBER_COLUMNS` を使いつつ会員番号列は無視）。最小変更として `MEMBER_COLUMNS` のうち `member_number` 以外をマッピング対象にする。
- `_import` を、`create_member` ではなく `add_roster_entries(session, self._project_id, rows)` に変更：

```python
    def _import(self):
        rows = self._mapped_rows()
        from app.services.project_service import add_roster_entries
        add_roster_entries(get_session(), self._project_id, rows)
        QMessageBox.information(self, "インポート完了", f"{len(rows)} 件を追加しました。")
        self.accept()
```

- ウィンドウタイトルを「名簿の取り込み」に。

- [ ] **Step 4: 名簿パネルから接続**

`app/ui/project_member_panel.py`：「Excelインポート」「貼り付けインポート」ボタンを次の単一ボタン「取り込み（Excel/貼り付け）」に統合し、`RosterImportDialog` を開く：

```python
    def _open_import(self):
        from app.ui.roster_import import RosterImportDialog
        dlg = RosterImportDialog(self._project_id, self)
        if dlg.exec():
            self._load()
```

（旧 `_import`/`_paste_import`/`_register_rows` は削除。）

- [ ] **Step 5: テストが通ることを確認**

Run: `python -m pytest tests/test_roster_import_mapping.py -v`
Expected: PASS

- [ ] **Step 6: 全体テスト**

Run: `python -m pytest`
Expected: PASS

- [ ] **Step 7: コミット**

```bash
git add app/ui/roster_import.py app/ui/project_member_panel.py app/ui/member_import.py tests/
git rm app/ui/member_import.py 2>/dev/null || true
git commit -m "feat: 名簿取り込み（列マッピング）を事業名簿向けに転用"
```

---

## Task 4: 随時受取を事業名簿ベースに

**Files:**
- Modify: `app/ui/issuance_cross_member.py`
- Test: `tests/test_issuance_service.py`（`get_pending_issuances_for_project_member` のテスト追加）

- [ ] **Step 1: 未発行取得のテスト（失敗）**

`tests/test_issuance_service.py` に追加：

```python
def test_pending_for_project_member(db_session):
    from app.services.project_service import create_project, add_roster_entries, get_project_members
    from app.services.item_template_service import create_item_template
    from app.services.category_service import create_category
    from app.services.project_service import add_template_to_project
    from app.services.issuance_service import (
        create_issuance_for_member, get_pending_issuances_for_project_member,
    )
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "会費", 1000, "式", 0, "invoice", "")
    proj = create_project(db_session, name="2026 青年部", category_id=cat.id,
                          fiscal_year=2026, project_type="list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    add_roster_entries(db_session, proj.id, [{"organization_name": "○○商事"}])
    pm = get_project_members(db_session, proj.id)[0]
    create_issuance_for_member(db_session, proj.id, pm.id,
                               "○○商事", "", "invoice", 2026, 4)
    pending = get_pending_issuances_for_project_member(db_session, pm.id)
    assert len(pending) == 1
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python -m pytest tests/test_issuance_service.py::test_pending_for_project_member -v`
Expected: FAIL（Task 1 で関数は追加済みなら PASS。未追加なら関数を Task1 Step10 のとおり実装）

- [ ] **Step 3: 随時受取UIを名簿検索ベースに変更**

`app/ui/issuance_cross_member.py`：
- `from app.services.member_service import search_members` を削除。
- 検索を `get_project_members` 横断に変更：全 active 事業の名簿から、入力文字列が `organization_name/representative_name/organization_kana` に含まれる行を集める新ヘルパ（UI内ローカル関数で可）。検索結果テーブル列は `["事業名", "事業所名", "代表者名"]`、`UserRole` に `pm.id` を保持。
- 行選択時：`get_pending_issuances_for_project_member(session, pm_id)` でその名簿行の未発行を表示（「全事業横断」表記を「この名簿の未発行」に変更）。
- 発行時の `recipient_organization`/`recipient_name` は選択した `ProjectMember` の `organization_name`/`representative_name` を使用（`self._member` を `self._pm` に置換）。
- 説明ラベルを「名簿を検索して選択すると、その事業の未発行が表示されます」に更新。

- [ ] **Step 4: 全体テスト**

Run: `python -m pytest`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add app/ui/issuance_cross_member.py tests/test_issuance_service.py
git commit -m "feat: 随時受取を事業名簿の検索→事業内未発行発行に変更"
```

---

## Task 5: 会員マスタの撤去

**Files:**
- Delete: `app/ui/member_list.py`, `app/ui/member_form.py`, `app/services/member_service.py`
- Modify: `app/ui/settings_tab.py`, `app/database/models.py`
- Delete: `tests/test_member_service.py`
- Test: `tests/test_no_member_master.py`（新規・ガード）

- [ ] **Step 1: 会員マスタ撤去のガードテスト（失敗）**

`tests/test_no_member_master.py`:

```python
def test_member_master_removed():
    import importlib
    for mod in ("app.services.member_service", "app.ui.member_list",
                "app.ui.member_form"):
        try:
            importlib.import_module(mod)
            assert False, f"{mod} はまだ存在します"
        except ModuleNotFoundError:
            pass


def test_models_have_no_member_classes():
    import app.database.models as m
    assert not hasattr(m, "Member")
    assert not hasattr(m, "MemberNameHistory")


def test_settings_tab_has_no_member_master(qtbot, memory_db):
    from PyQt6.QtWidgets import QTabWidget
    from app.ui.settings_tab import SettingsTab
    w = SettingsTab()
    qtbot.addWidget(w)
    inner = w.findChild(QTabWidget)
    titles = [inner.tabText(i) for i in range(inner.count())]
    assert "会員マスタ" not in titles
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python -m pytest tests/test_no_member_master.py -v`
Expected: FAIL（モジュール・クラスがまだ存在）

- [ ] **Step 3: 設定タブから会員マスタを削除**

`app/ui/settings_tab.py`：`from app.ui.member_list import MemberListWidget` と `inner.addTab(MemberListWidget(), "会員マスタ")` の2行を削除。

- [ ] **Step 4: モデルから `Member`/`MemberNameHistory` を削除**

`app/database/models.py`：`class Member(Base)`（100-119行付近）と `class MemberNameHistory(Base)`（122-131行付近）を削除。`Member.name_history` リレーションも一緒に消える。他に `Member` を参照する箇所が無いことを確認（Task 1〜4 で除去済み）。

- [ ] **Step 5: 会員マスタ関連ファイルを削除**

```bash
git rm app/ui/member_list.py app/ui/member_form.py app/services/member_service.py tests/test_member_service.py
```

- [ ] **Step 6: 残存参照の検査**

Run: `python -c "import app.ui.main_window"`（インポートエラーが無いこと）
Run: `grep -rn "member_service\|MemberList\|MemberForm\|members_master\|MemberNameHistory\|\.member\b" app/`
Expected: 宛名解決・名簿の `pm.*` 直接参照のみが残り、`Member` 系の参照が無い。残っていれば修正。

- [ ] **Step 7: テストが通ることを確認**

Run: `python -m pytest tests/test_no_member_master.py -v`
Expected: PASS

- [ ] **Step 8: 全体テスト**

Run: `python -m pytest`
Expected: PASS（`test_excel_utils.py` の `parse_tsv_text`/`MEMBER_COLUMNS` は維持。`create_member` を使っていたテストは削除済み）

- [ ] **Step 9: 開発DBの作り直し確認**

既存の開発用 SQLite ファイルがある場合は削除し、アプリ起動（または `python -c "from app.database.connection import init_db; init_db()"`）で再作成されることを確認。Expected: エラーなく `project_members` が新スキーマで作成される。

- [ ] **Step 10: コミット**

```bash
git add -A
git commit -m "refactor: 会員マスタ（テーブル・サービス・UI）を撤去"
```

---

## Self-Review

**Spec coverage:**
- §3 モデル変更 → Task 1 Step1
- §3-2 廃止（Member/MemberNameHistory） → Task 5 Step4
- §3-3 宛名解決 → Task 1 Step10-12, Task 2 Step4
- §4-1 直接入力 → Task 2
- §4-2 取り込み転用 → Task 3
- §4-3 他事業コピー → Task 1 Step8（service）＋ Task 2（UI）
- §4-4 年度更新引き継ぎ → Task 1 Step13
- §5 随時受取 → Task 4
- §6 廃止画面・サービス → Task 5
- §7 マイグレーション（作り直し） → Task 5 Step9
- §9 受け入れ基準 → 各タスクのテストで担保

**Type consistency:** `add_roster_entries(session, project_id, entries: list[dict])`、`copy_roster_from_project(session, src, dst)`、`create_issuance_for_member(session, project_id, project_member_id, recipient_organization, recipient_name, doc_type, fiscal_year, month)`、`get_pending_issuances_for_project_member(session, project_member_id)`、`recipient_label(pm)`、`RosterEntryDialog.values() -> dict`、`RosterImportDialog(project_id, parent)` — 各タスク間で一貫。

**Placeholder scan:** なし（各コードステップに実体を記載）。
