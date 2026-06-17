# 単発発行（請求書）の発行元選択・宛名表示設定 設計書

**作成日：** 2026-06-17
**ステータス：** 承認済み

---

## 概要

単発発行（`IssuanceCounterWidget`、請求書タブ）で請求書を発行する際、現在は発行元（会社情報）・銀行口座・印鑑が自動解決のみで、ユーザーが選べない。また、請求書PDFの宛名は「氏名欄に入力があれば役職・氏名を印字する」という暗黙のルールしかなく、明示的にオン/オフを選べない。

本機能では、単発発行の「発行設定」に発行元・銀行口座・印鑑の選択コンボと、宛名に役職・氏名を印字するかのチェックボックスを追加し、発行ごとに個別保存する。

---

## 要件

- 単発発行（請求書のみ。領収書タブは対象外）の「発行設定」グループボックスで、発行元・銀行口座・印鑑を選択できる
- 発行元を選ぶと、銀行口座・印鑑はその発行元のデフォルトに自動リセットされる（個別に上書き可能）
- 請求書の宛名に役職・氏名を印字するかどうかをチェックボックスで選べる
- チェックボックスの初期値は組ごとの最後使用値を記憶する（`window_envelope_last` と同じ方式）
- これらの設定は発行（`Issuance`）ごとに個別保存する（同じ業務名を共有する他の発行に影響しない）
- 「内容修正」で編集する際、保存済みの設定が復元される
- 「再発行」では、コード変更なしで元の発行時の設定がそのまま使われる

---

## 背景・設計判断

単発発行は `create_direct_issuance()` が業務名（カテゴリ名 or "直接発行"）ごとに共有の "system project"（`project_type="counter"`）を検索 or 作成し、そこに紐付けている。この共有プロジェクトは同じ業務名の発行間で再利用されるため、発行元等の選択を **共有プロジェクト側に保存すると、ある1件の発行設定変更が同じ業務名の他の全発行（過去・未来）の解決結果に影響してしまう**。

単発発行は「その場限りの独立した発行」という性質上、選択した発行元・銀行口座・印鑑・宛名表示設定は **`Issuance` 自体に個別保存する**。これにより：
- 発行ごとに異なる発行元を選んでも互いに干渉しない
- 再発行時に元の発行時と同じ見た目を再現できる

---

## データベース設計

### `issuances` テーブルの変更

```sql
ALTER TABLE issuances ADD COLUMN company_settings_id INTEGER REFERENCES company_settings(id);
ALTER TABLE issuances ADD COLUMN bank_account_id INTEGER REFERENCES bank_accounts(id);
ALTER TABLE issuances ADD COLUMN seal_image_id INTEGER REFERENCES seal_images(id);
ALTER TABLE issuances ADD COLUMN show_recipient_person BOOLEAN DEFAULT 1;
```

既存レコードは全カラムNULL（`show_recipient_person`は1=True）のまま移行し、フォールバックにより既存の挙動を維持する。

### モデル変更（`app/database/models.py`）

`Issuance` に以下を追加：
```python
company_settings_id   = Column(Integer, ForeignKey("company_settings.id"), nullable=True)
bank_account_id       = Column(Integer, ForeignKey("bank_accounts.id"), nullable=True)
seal_image_id          = Column(Integer, ForeignKey("seal_images.id"), nullable=True)
show_recipient_person  = Column(Boolean, default=True)
```
リレーションシップは不要（PDF生成時に都度 `session.get()` で解決する。project_form.pyの `Project.issuer` 等と同じ運用は今回は見送り、シンプルにIDのみ持つ）。

`app/database/connection.py` の `_migrate()` に、`issuances` テーブル向けの同パターンのALTER TABLE処理を追加する。

---

## PDF生成フロー変更

### 発行元・銀行口座・印鑑の解決順序（更新）

| 優先度 | 発行元 | 銀行口座 | 印鑑 |
|---|---|---|---|
| 1 | `issuance.company_settings_id` | `issuance.bank_account_id` | `issuance.seal_image_id` |
| 2 | `project.company_settings_id` | `project.bank_account_id` | `project.seal_image_id` |
| 3 | `is_default=True` のCompanySettings | 発行元の `is_default=True` 口座 | 発行元の `is_default=True` 印鑑 |
| 4 | 最初のCompanySettings | 発行元の最初の口座 | 発行元の最初の印鑑 |

### `app/utils/pdf_helpers.py` の変更

`get_issuer_for_project(session, project, issuance=None)` に `issuance` 引数を追加（デフォルト `None` で後方互換維持）。`issuance` が渡され、かつ `issuance.company_settings_id` 等が設定されていれば、project側の解決より先にそれを優先する。

`generate_and_open(issuance, session, ..., project=None)` 内の呼び出しを `get_issuer_for_project(session, project, issuance=issuance)` に変更する（1行）。

**エラー処理：** `issuance.company_settings_id`（または bank/seal）が指している先のレコードが後から削除されている場合、`session.get()` は `None` を返す。この場合は「未設定」と同じ扱いとして次の優先度（project → システムデフォルト → 先頭）にフォールバックする。例外は発生させない。

### `app/services/pdf/invoice_pdf.py` の変更

`_build_client_block(issuance, ..., show_recipient_person: bool = True)` を追加。`show_recipient_person=False` の場合、`recipient_name`（氏名）が入力されていても印字せず、常に「事業所名　御中」の表示にする（`recipient_department` も連動して非表示）。

`generate_invoice_pdf()` は `issuance.show_recipient_person`（属性が無い場合は `True` にフォールバック。`getattr` で安全に取得）を `_build_client_block` に渡す。

---

## UI設計（`app/ui/issuance_counter.py`、請求書タブのみ）

既存の「発行設定」グループボックス内、「配付方法」の下に追加する（`project_form.py` の `_reload_issuers`/`_reload_bank_seal` のロジックを移植・適用）：

```
配付方法 : [窓口手渡し ▼]
発行元   : [コンボボックス（発行元一覧）        ▼]
銀行口座 : [コンボボックス（選択発行元の口座一覧） ▼]
印鑑     : [コンボボックス（選択発行元の印鑑一覧） ▼]
☑ 宛名に役職・氏名を印字する
支払期日 : [日付]
☑ 窓あき封筒モード（住所を印字）
```

**動作：**
- ウィジェット構築時：システムデフォルト発行元のデフォルト口座・印鑑を初期選択
- 発行元コンボを変更すると、銀行口座・印鑑コンボがその発行元のデフォルト値にリセットされる（個別に変更可）
- 「宛名に役職・氏名を印字する」チェックボックスの初期値：`app_config` の `recipient_person_last`（未設定時は `True`）

---

## データフロー

### 新規発行（`_issue()`）

1. フォームから `company_settings_id` / `bank_account_id` / `seal_image_id` / `show_recipient_person` を取得
2. `create_direct_issuance()` の引数として渡し、`Issuance` の新カラムに保存
3. チェックボックスの状態を `app_config["recipient_person_last"]` に保存（`window_envelope_last` と同じパターン）
4. `generate_and_open(issuance=iss, ..., project=_proj)` は変更不要（内部の解決ロジックが新カラムを見るようになる）

### 内容修正（`_load_edit_data()`）

既存 `Issuance` の4設定を読み込み、発行元コンボ→銀行口座/印鑑コンボ→チェックボックスの順で復元する（発行元コンボ変更時の自動リセットが走る前に、明示的に銀行口座/印鑑を選択し直す）。

### 再発行（`reissue_tab.py._reissue()`）

コード変更不要。`generate_and_open(iss, session, ..., project=_proj)` は既存のまま呼ばれ、解決ロジック側の変更だけで元の発行時の設定が自動的に使われる。

---

## サービス層の変更（`app/services/issuance_service.py`）

`create_direct_issuance()` / `update_direct_issuance()` に以下のキーワード引数を追加：
```python
company_settings_id: int | None = None,
bank_account_id: int | None = None,
seal_image_id: int | None = None,
show_recipient_person: bool = True,
```
それぞれ `Issuance` の対応カラムに設定する。

---

## テスト方針

- `get_issuer_for_project`：issuance側の設定がproject側より優先されることのユニットテスト
- `_build_client_block`：`show_recipient_person=False` で役職・氏名が印字されず「御中」表示になることのテスト
- `IssuanceCounterWidget`（請求書タブ）：発行元コンボを変更すると銀行口座・印鑑コンボが自動リセットされることのテスト
- `_issue()` 経由で発行した `Issuance` に選択した発行元・銀行口座・印鑑・宛名表示設定が保存されることのテスト
- `_load_edit_data()` で既存設定が正しく復元されることのテスト

---

## 影響範囲

| ファイル | 変更内容 |
|---|---|
| `app/database/models.py` | `Issuance` に4カラム追加 |
| `app/database/connection.py` | `issuances` テーブル向けマイグレーション追加 |
| `app/utils/pdf_helpers.py` | `get_issuer_for_project()` に `issuance` 引数追加 |
| `app/services/pdf/invoice_pdf.py` | `_build_client_block`/`generate_invoice_pdf` に `show_recipient_person` 対応追加 |
| `app/services/issuance_service.py` | `create_direct_issuance`/`update_direct_issuance` に4引数追加 |
| `app/ui/issuance_counter.py` | 発行設定に発行元・銀行口座・印鑑コンボ、宛名表示チェックボックスを追加（請求書タブのみ） |

---

## スコープ外

- 領収書タブへの同機能追加（請求書のみが対象）
- まとめて発行（`issuance_from_project.py`）側への同機能追加
- 発行元ごとのデフォルト宛名表示設定（システム全体/組単位の `recipient_person_last` のみ）
