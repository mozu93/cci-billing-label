# cci-billing-label 設計ドキュメント

**日付**: 2026-06-17  
**対象**: `C:\Users\taka\Documents\Gemini\0030Business\cci-billing-label`

---

## 概要

`cci-billing` をベースに「宛名ラベル発行」タブを追加した統合アプリ `cci-billing-label` を新規作成する。  
`label_ippatsusaku` のラベル PDF 生成機能を移植し、cci-billing の ProjectMember（プロジェクト名簿）と連携してラベルを印刷できるようにする。

---

## アプローチ: コピー方式（独立リポジトリ）

- `cci-billing` フォルダを `cci-billing-label` にコピーし、新 git リポジトリとして初期化
- `label_ippatsusaku` から PDF サービスとユーティリティのみ移植
- cci-billing の既存機能には一切手を触れない
- 将来 cci-billing 側に修正が入った場合は手動マージで対応

---

## データフロー

```
[件名選択]
  └→ get_project_members(session, project_id)
       └→ ProjectMember リスト表示（チェックボックス付き）
            └→ チェック済みを _LabelEntryAdapter でラップ
                 └→ generate_label_pdf(entries, path, batch_mode, layout_key, font_key)
                      └→ 一時フォルダに PDF 保存 → os.startfile() で自動表示
```

### フィールドマッピング（ProjectMember → LabelEntry）

| ProjectMember      | LabelEntry アダプター |
|--------------------|----------------------|
| organization_name  | company_name         |
| postal_code        | postal_code          |
| address            | address1             |
| address2           | address2             |
| department         | title（役職名）       |
| representative_name| person_name          |
| （なし）           | barcode_address = "" |
| （なし）           | entry_mode = "inherit"|

バーコードは常に無効（`barcode_enabled=False`）。DB への変更不要。

---

## UI 設計

### 画面レイアウト（宛名ラベル発行タブ）

```
┌─────────────────────────────────────────────────────────────────────┐
│ 年度: [2025年度▼]  業務区分: [すべて▼]  件名: [〇〇業務▼]         │
├─────────────────────────────────────────────────────────────────────┤
│ モード: [宛名(氏名あり)▼]  用紙: [A-ONE 28185▼]  フォント:[MSPゴシック▼]│
│ [ラベルPDF生成]                                         検索: [____] │
├──┬──────┬────────────────┬──────────────┬────────────┬─────────────┤
│☐ │会員番号│ 事業所名       │ フリガナ     │ 代表者名   │ 郵便番号    │
├──┼──────┼────────────────┼──────────────┼────────────┼─────────────┤
│☑ │001   │ 〇〇商事       │ …           │ 田中 太郎  │ 123-4567   │
│☐ │002   │ △△工業        │ …           │ 鈴木 花子  │ 234-5678   │
└──┴──────┴────────────────┴──────────────┴────────────┴─────────────┘
  3件表示 / チェック済み 2件
```

### 操作フロー

1. 年度 → 業務区分 → 件名 で絞り込み（issuance_from_project.py と同じ動き）
2. テーブルにプロジェクト会員が表示（Shift+クリックで範囲選択）
3. モード・用紙レイアウト・フォントを選択
4. 「ラベルPDF生成」ボタン → PDF 生成 → ビューアで自動表示

### ラベルモード一覧

| UI 表示        | batch_mode  | 動作内容                              |
|----------------|-------------|---------------------------------------|
| 宛名（氏名あり）| `normal`    | 郵便番号・住所・事業所名・役職・氏名 様 |
| 宛名（氏名なし）| `no_person` | 郵便番号・住所・事業所名 御中          |
| 事業所名のみ    | `simple`    | 事業所名 御中（住所なし）              |
| 名札            | `nametag`   | 事業所名・役職・氏名（大きめ）         |
| 卓上プレート    | `split4`    | 事業所名を均等割付                     |

### 制約・仕様

- 件名が「すべて」（未選択）の場合は PDF生成ボタンを無効化
- 郵便番号・住所が空の会員はラベルに住所なしで出力（エラーにしない）
- PDF 保存先は既存の `pdf_output_dir` 設定を共用（一時ファイル名: `label_<timestamp>.pdf`）
- ラベルバッチの DB 保存なし（使い捨て生成）

---

## 追加・変更ファイル

### 新規追加

| ファイル                            | 内容                                          |
|-------------------------------------|-----------------------------------------------|
| `app/services/pdf/label_pdf.py`     | label_ippatsusaku の label_pdf_service.py 移植 |
| `app/utils/customer_barcode.py`     | バーコード描画ユーティリティ移植               |
| `app/ui/label_issuance_tab.py`      | 宛名ラベル発行タブ（新規 UI）                  |

### 変更

| ファイル                  | 変更内容                        |
|---------------------------|---------------------------------|
| `app/ui/main_window.py`   | 「宛名ラベル発行」タブを追加    |

---

## 実装手順

1. `cci-billing` → `cci-billing-label` へファイルコピー
2. `cci-billing-label` で `git init` + 初回コミット
3. `app/utils/customer_barcode.py` を label_ippatsusaku からコピー
4. `app/services/pdf/label_pdf.py` を label_ippatsusaku の label_pdf_service.py からコピー（import パスを調整）
5. `app/ui/label_issuance_tab.py` を新規作成
6. `app/ui/main_window.py` に「宛名ラベル発行」タブを追加
7. 動作確認

---

## スコープ外（将来検討）

- ラベルバッチの保存・履歴管理
- 会員マスター（Member テーブル）からの取込
- バーコード印刷
- Excel/CSV からの直接取込
