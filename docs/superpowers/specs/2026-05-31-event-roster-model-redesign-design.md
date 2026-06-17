# 事業名簿モデル再設計 設計仕様書

**作成日：** 2026-05-31
**ステータス：** ドラフト（レビュー待ち）
**対象：** `cci-billing`（商工会議所請求書・領収書発行システム）
**位置づけ：** 中央の会員マスタ（`members_master`）を廃止し、事業（イベント）ごとに自己完結した名簿を持つデータモデルへの再設計。発行・PDF・レポートの宛名解決もこれに合わせて変更する。

---

## 1. 背景・課題

### 現状の構造
- `members_master`：会社（会員）ごとに **代表者1名・メール1つ** を保持。約4000件。
- `project_members`：`project_id` と `member_id` を結ぶだけ。宛名は持たず、表示時にマスタを参照。

### 業務実態と限界
同じ会社でも事業によって出てくる人・連絡先が異なる。

| 事業 | 実際の宛名 |
|------|-----------|
| 議員懇談会 | 会員とは別の人が代表（非会員のことも） |
| 青年部 | その会社の若手社員 |
| 女性部 | 会社内の女性担当者 |
| いずれも | メールアドレスも会社代表と異なることがある |

「1会社＝1代表者＝1メール」を前提にしたマスタ参照では表現できない。**会員マスタという中央台帳は業務に合わず、事業ごとに名簿を作るのが実態に即す。**

---

## 2. 方針

**中央の会員マスタを廃止する。** 事業（`Project`）が、その事業だけの名簿（`ProjectMember`）を **宛名情報ごと自前で保持** する。名簿は事業ごとに独立し、他事業からのコピーで使い回せる。

### 決定事項（ヒアリング）
- 会員マスタ機能（テーブル・設定タブ・会員検索）は不要 → 廃止。
- 名簿は事業ごとに登録（直接入力／Excel・貼り付け取り込み）。
- 他事業から名簿を **コピー** して使い回す場面がある（前年に限らず任意の事業から）。コピーは **スナップショット**（複製後はコピー先で独立して編集、元事業とは連動しない）。
- 「会員／非会員」区分は不要。

---

## 3. 新しいデータモデル

### 3-1. `project_members`（事業名簿）を自己完結に
`member_id` 参照を廃止し、宛名フィールドを直接持たせる。

```
project_members:
  id            (PK)
  project_id    (FK → projects.id)
  organization_name      事業所名
  organization_kana      フリガナ
  representative_name     代表者名（宛名）
  representative_kana     代表者フリガナ
  postal_code            郵便番号
  address                住所
  phone                  電話
  email                  メール
  notes                  備考
  sort_order             並び順
```

- 必須は「事業所名・代表者名のいずれか」（取り込み・入力時に検証）。
- `is_member`（会員区分）・`member_number`（会員番号）は持たない。

### 3-2. 廃止するもの
- `members_master` テーブル（`Member` モデル）
- `member_name_history` テーブル（`MemberNameHistory`、名称変更履歴）
- `ProjectMember.member_id` 外部キーと `Member` リレーション

### 3-3. 影響を受ける参照（宛名解決）
`pm.member.<field>` で参照していた箇所を、`pm.<field>` の直接参照に変更する。

| ファイル | 変更 |
|---------|------|
| `services/issuance_service.py` | `member.organization_name` → `pm.organization_name` 等。`create_issuance` の `member: Member` 引数を廃し、`ProjectMember` から宛名を取る |
| `services/report_service.py` | `pm.member.*` → `pm.*` |
| `services/pdf/batch_pdf.py` | `m = pm.member` → `pm` を直接使用 |
| `services/project_service.py` | `add_members_to_project(member_ids)` を廃し、宛名 dict から名簿行を作る関数に置換。`get_project_members` の joinedload(member) 撤去 |

---

## 4. 名簿の登録・取り込み・コピー

### 4-1. 直接入力
事業名簿パネル（`ProjectMemberPanel`）に「行追加／編集」ダイアログを設け、宛名フィールドを手入力できる。編集・削除（確認ダイアログ付き）も可能。

### 4-2. Excel・貼り付け取り込み（列マッピング）
既に実装済みの列マッピング機構（`excel_utils` の `parse_*_raw` / `guess_mapping_from_header` / `build_member_rows`）を **事業名簿の取り込み** に付け替える。

- 取り込み先は選択中の事業の名簿（マスタ照合はしない）。
- マッピング対象フィールドは 3-1 の宛名項目（会員番号を除く）。
- `build_member_rows` 相当の出力を、そのまま `ProjectMember` 行として作成。
- `MemberImportDialog` を `RosterImportDialog`（事業名簿向け）に転用。

### 4-3. 他事業からコピー
- 名簿パネルに「他の事業から名簿をコピー」ボタン。
- 事業選択ダイアログ（年度・事業名で絞り込み）→ 選んだ事業の全名簿行を **複製** して現事業に追加（スナップショット）。
- `copy_roster_from_project(session, src_project_id, dst_project_id)` を新設。

### 4-4. 年度更新の引き継ぎ
`fiscal_year_service` の引き継ぎを、`member_id` コピーから **名簿行のスナップショット複製** に変更（4-3 の関数を再利用）。

---

## 5. 随時受取（窓口発行 → 随時受取）の扱い

現状：マスタの会員を検索 → その会員の **全事業横断** の未発行を合算発行（`get_pending_issuances_for_member` が `ProjectMember.member_id` を使用）。

マスタ廃止で「同一人物の事業横断」という概念が無くなるため、次に変更する。

- 検索元を **事業名簿（`project_members`）** に変更（事業所名・代表者名・フリガナで検索）。
- 選択した名簿行（`project_member`）の **その事業内の未発行** を表示し、まとめて発行。
- 「全事業横断の合算」は廃止（業務上、随時受取は事業内の窓口受け渡しが実態）。
- `get_pending_issuances_for_member(member_id)` → `get_pending_issuances_for_project_member(project_member_id)` に置換。

> この変更が随時受取の使い勝手に影響するため、レビュー時に重点確認。

---

## 6. 廃止する画面・サービス

| 対象 | 措置 |
|------|------|
| 設定 → 会員マスタ タブ（`MemberListWidget`） | 削除 |
| `MemberFormDialog` | 削除 |
| `member_service.py`（master CRUD・検索・名称履歴） | 削除（`get_recipient_label` は宛名整形として `ProjectMember` 向けに移設して残す） |
| `MemberImportDialog` | `RosterImportDialog` に転用 |
| `settings_tab.py` | 会員マスタ タブの登録行を削除 |

---

## 7. マイグレーション

- 開発は SQLite、本番 PostgreSQL は未稼働で実データなし。
- モデル変更後、開発DBは作り直し（`init_db` で再作成）。本番投入前のため破壊的変更で問題なし。
- 既存のバックアップ/復元機能はスキーマ追従のみ確認。

---

## 8. スコープ外

- 窓口発行 フリー発行（事業に紐づかない単発）は変更なし。
- 請求項目テンプレート・カテゴリ（業務名）・PDFレイアウトは変更なし。
- 名簿行どうしの名寄せ・重複検出（事業をまたいだ同一人物の自動判定）は行わない。

---

## 9. 受け入れ基準

1. 会員マスタ（テーブル・設定タブ・会員検索）が存在しない。
2. 事業名簿が宛名（事業所名・代表者名・フリガナ・郵便番号・住所・電話・メール・備考）を自前で保持する。
3. 事業名簿に手入力・Excel/貼り付け取り込み（列マッピング）で行を追加できる。
4. 他事業から名簿をコピー（スナップショット）できる。
5. 事業からの発行・一括PDF・レポートの宛名が、名簿行の値で正しく出る。
6. 随時受取が、事業名簿の検索→その事業内の未発行発行として動作する。
7. 年度更新の引き継ぎが名簿スナップショット複製で動作する。
8. 既存の発行ロジック（採番・入金・PDF生成）の挙動は宛名取得元以外変わらない。
