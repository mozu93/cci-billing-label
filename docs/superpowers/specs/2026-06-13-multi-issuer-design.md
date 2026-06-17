# 複数発行元管理機能 設計書

**作成日：** 2026-06-13  
**ステータス：** 承認済み

---

## 概要

現在、発行元情報（CompanySettings）はシステムに1件しか登録できない。本機能では複数の発行元を登録・管理できるようにし、銀行口座・印鑑画像をそれぞれの発行元に紐づける。プロジェクト単位で使用する発行元・口座・印鑑を選択できるようにする。

---

## 要件

- 発行元（CompanySettings）を複数登録できる
- 各発行元は複数の銀行口座・印鑑画像を持てる（既存の構造を維持）
- システム全体のデフォルト発行元を1つ指定できる
- プロジェクトごとに発行元・銀行口座・印鑑画像を選択できる
- 発行元を選ぶと口座・印鑑はその発行元のデフォルトが自動セットされ、個別オーバーライドも可能
- 未設定（NULL）の場合はシステムデフォルト発行元のデフォルト口座・印鑑にフォールバック
- 既存データは無変更で移行できる（既存1レコードがデフォルト発行元になる）

---

## データベース設計

### `company_settings` テーブルの変更

```sql
ALTER TABLE company_settings ADD COLUMN is_default BOOLEAN DEFAULT FALSE;
```

既存の1レコードには `is_default = TRUE` を設定するマイグレーションを実行する。

### `projects` テーブルの変更

```sql
ALTER TABLE projects ADD COLUMN company_settings_id INTEGER REFERENCES company_settings(id);
ALTER TABLE projects ADD COLUMN bank_account_id INTEGER REFERENCES bank_accounts(id);
ALTER TABLE projects ADD COLUMN seal_image_id INTEGER REFERENCES seal_images(id);
```

既存プロジェクトはすべて NULL のまま移行する（フォールバックによりデフォルト発行元が使われる）。

### モデル変更（`app/database/models.py`）

**CompanySettings：**
```python
is_default = Column(Boolean, default=False)
```

**Project：**
```python
company_settings_id = Column(Integer, ForeignKey("company_settings.id"), nullable=True)
bank_account_id     = Column(Integer, ForeignKey("bank_accounts.id"),    nullable=True)
seal_image_id       = Column(Integer, ForeignKey("seal_images.id"),      nullable=True)

issuer       = relationship("CompanySettings")
bank_account = relationship("BankAccount")
seal_image   = relationship("SealImage")
```

---

## PDF生成フロー変更

### フォールバック順序

| 優先度 | 発行元 | 銀行口座 | 印鑑 |
|---|---|---|---|
| 1 | `project.company_settings_id` | `project.bank_account_id` | `project.seal_image_id` |
| 2 | `is_default=True` のCompanySettings | 発行元の `is_default=True` 口座 | 発行元の `is_default=True` 印鑑 |
| 3 | 最初のCompanySettings（既存の挙動） | 発行元の最初の口座 | 発行元の最初の印鑑 |

### `app/utils/pdf_helpers.py` の変更

`get_company_and_bank(session)` はシグネチャを維持しつつ、新関数を追加する：

```python
def get_issuer_for_project(session, project) -> tuple[CompanySettings, BankAccount | None, SealImage | None]:
    """プロジェクト設定 → 発行元デフォルト → システムデフォルトの順に解決する。"""
```

`generate_and_open()` にオプション引数 `project=None` を追加し、渡された場合は `get_issuer_for_project()` を使う。渡されない場合は既存の `get_company_and_bank()` にフォールバックして後方互換を維持する。

---

## UI設計

### 設定タブ（`app/ui/company_settings.py`）

現在の「1社分フォーム」を「発行元リスト + 選択した発行元の詳細」という構成に変更する。

**レイアウト変更：**
- 上部：発行元一覧テーブル（名称・住所・デフォルトマーク）
  - ボタン：「＋ 発行元追加」「編集」「削除」「★ デフォルトに設定」
- 発行元を選択すると、既存の「銀行口座」「印鑑画像」セクションがその発行元のデータを表示
- 発行元の詳細編集はダイアログ（`IssuerEditDialog`）で行う

**制約：**
- デフォルト発行元は削除不可（削除前に別の発行元をデフォルトに設定する必要がある）
- 発行元が1件の場合は削除不可

### プロジェクト作成・編集フォーム（`app/ui/project_form.py`）

発行元選択エリアを追加する（既存フォームの下部または別タブ）。

**追加コントロール：**
```
発行元  : [コンボボックス（発行元一覧）       ▼]
銀行口座: [コンボボックス（選択発行元の口座）  ▼]
印鑑    : [コンボボックス（選択発行元の印鑑）  ▼]
```

**動作：**
- プロジェクト作成時の初期値：システムデフォルト発行元のデフォルト口座・印鑑
- 発行元コンボを変更すると、口座・印鑑コンボが自動リセットされデフォルト値にセット
- 口座・印鑑は個別に変更可能（発行元のリスト内から選択）

---

## 移行方針

1. `company_settings` に `is_default` 追加、既存1レコードを `is_default=True` に更新
2. `projects` に3カラム追加（すべてNULL）
3. 既存プロジェクトはNULLのままで動作確認（フォールバックにより既存の挙動を維持）

---

## 影響範囲

| ファイル | 変更内容 |
|---|---|
| `app/database/models.py` | CompanySettings に `is_default`、Project に3FK追加 |
| `app/database/connection.py` | マイグレーション処理追加 |
| `app/utils/pdf_helpers.py` | `get_issuer_for_project()` 追加、`generate_and_open()` に `project` 引数追加 |
| `app/ui/company_settings.py` | 発行元リスト・編集UI追加 |
| `app/ui/project_form.py` | 発行元・口座・印鑑の選択コントロール追加 |
| `app/services/project_service.py` | プロジェクト保存時の新カラム対応 |
| `app/ui/issuance_from_project.py` | `generate_and_open()` 呼び出しにproject渡し |
| `app/ui/issuance_counter.py` | 同上 |
| `app/ui/reissue_tab.py` | 同上（存在する場合） |

---

## スコープ外

- 発行元ごとのロゴ画像（将来対応）
- 発行元ごとのメール送信設定（将来対応）
- 発行元の使用履歴・統計（将来対応）
