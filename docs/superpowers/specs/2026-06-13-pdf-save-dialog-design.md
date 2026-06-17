# PDF保存先選択ダイアログ設計

**日付:** 2026-06-13  
**対象:** cci-billing — 請求書・領収書の発行フロー

---

## 概要

現在、PDFは設定済みの固定ディレクトリに自動保存された後、デフォルトのPDFビューアで開かれる。  
本変更により、発行時に毎回保存先ファイルダイアログを表示し、ユーザーが任意の場所へ保存できるようにする。

---

## 要件

| ケース | 動作 |
|---|---|
| 窓口発行（請求書・領収書） | 毎回ファイル保存ダイアログ → 保存 → PDFビューアで開く |
| 再発行 | 毎回ファイル保存ダイアログ → 保存 → PDFビューアで開く |
| プロジェクト一括発行 | フォルダ選択ダイアログ（1回）→ 各PDFを保存 → 結合PDFをビューアで開く |

- 「印刷できるように開く」= PDFビューアで開く（Adobeなど既定ビューア）
- キャンセル時はPDF未生成だがDB発行記録は残り、再発行タブから後で出力可能

---

## アーキテクチャ

### アプローチ：`generate_and_open` に `save_path` 引数を追加（A案）

UIとPDF生成ロジックの責務を分離したまま最小変更で対応する。

- **ダイアログ表示** → UI層（各呼び出し元）
- **PDF生成・保存・オープン** → `pdf_helpers.generate_and_open()`

---

## 変更詳細

### 1. `app/utils/pdf_helpers.py`

`generate_and_open()` に `save_path: str | None = None` を追加する。

```python
def generate_and_open(issuance, session, reissue=False,
                      due_date=None, open_file=True,
                      save_path: str | None = None,   # ← 追加
                      window_envelope=False, ...):
    ...
    suffix = "_再発行" if reissue else ""
    if save_path:
        path = save_path
    else:
        path = os.path.join(output_dir, f"{issuance.doc_number}{suffix}.pdf")
```

- `save_path` が指定されれば そのパスを使用
- `None` の場合は従来通り固定ディレクトリ（後方互換）

---

### 2. `app/ui/issuance_counter.py`（窓口発行）

処理順序：  
**DB保存（`create_direct_issuance`）→ ファイルダイアログ → PDF生成 → ビューアで開く**

```python
from PyQt6.QtWidgets import QFileDialog
import os

output_dir = get_pdf_output_dir()
default_name = os.path.join(output_dir, f"{iss.doc_number}.pdf")
save_path, _ = QFileDialog.getSaveFileName(
    self, "PDFの保存先を選択", default_name, "PDF ファイル (*.pdf)"
)
if not save_path:
    QMessageBox.information(
        self, "保存キャンセル",
        "発行は記録されましたが、PDFは保存されませんでした。\n"
        "再発行タブから出力できます。"
    )
else:
    generate_and_open(iss, session, save_path=save_path, ...)
```

---

### 3. `app/ui/reissue_tab.py`（再発行）

窓口発行と同様の手順。ただし `reissue=True` で呼び出す。  
デフォルトファイル名: `{doc_number}_再発行.pdf`

---

### 4. `app/ui/issuance_from_project.py`（プロジェクト一括発行）

発行ループ開始前にフォルダ選択ダイアログを表示する。

```python
from PyQt6.QtWidgets import QFileDialog

save_dir = QFileDialog.getExistingDirectory(
    self, "PDFの保存先フォルダを選択", get_pdf_output_dir()
)
if not save_dir:
    return  # キャンセル → DB書き込みなしで中断

# ループ内
for member in checked_members:
    save_path = os.path.join(save_dir, f"{iss.doc_number}.pdf")
    path = generate_and_open(iss, session, open_file=False,
                             save_path=save_path, ...)
    paths.append(path)

merge_and_open(paths, base_name)
```

- ループ開始前にキャンセル → DB書き込みなし・処理中断
- 結合PDFは `merge_and_open()` が既存ロジックで処理

---

## エラーハンドリング

| ケース | 対応 |
|---|---|
| 単発発行でダイアログキャンセル | `QMessageBox.information` で案内、DB記録は残る |
| 一括発行でフォルダ選択キャンセル | 即 `return`、DB書き込みなし |
| 既存ファイルの上書き | `QFileDialog.getSaveFileName` がOSの確認ダイアログを自動表示 |

---

## 変更ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `app/utils/pdf_helpers.py` | `generate_and_open` に `save_path` 引数追加 |
| `app/ui/issuance_counter.py` | DB保存後にファイルダイアログ追加 |
| `app/ui/reissue_tab.py` | DB保存後にファイルダイアログ追加 |
| `app/ui/issuance_from_project.py` | ループ前にフォルダ選択ダイアログ追加 |

---

## 非変更項目

- `app/services/print_service.py` — 変更なし
- `merge_and_open()` — 変更なし
- プレビュー生成（`generate_preview()`）— 変更なし
- バッチPDF（`batch_pdf.py`）— 変更なし
