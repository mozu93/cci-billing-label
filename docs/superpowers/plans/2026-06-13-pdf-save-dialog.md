# PDF保存先選択ダイアログ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 請求書・領収書の発行・再発行時に毎回ファイル保存先ダイアログを表示し、指定パスへ保存してPDFビューアで開く。一括発行はフォルダ選択1回で全PDF保存・結合PDFを開く。

**Architecture:** `generate_and_open()` に `save_path: str | None` 引数、`merge_and_open()` に `output_dir: str | None` 引数を追加。ダイアログ表示はUI層（`issuance_counter.py` / `reissue_tab.py` / `issuance_from_project.py`）で行い、PDF生成ロジックはUI依存なし。

**Tech Stack:** PyQt6 (`QFileDialog`), Python 3.11+, SQLAlchemy

---

### Task 1: `generate_and_open` / `merge_and_open` に引数を追加してテストを書く

**Files:**
- Modify: `app/utils/pdf_helpers.py:85-190`
- Test: `tests/test_pdf_helpers.py`

- [ ] **Step 1: `save_path` 引数のテストを書く**

`tests/test_pdf_helpers.py` に追記：

```python
def test_generate_and_open_uses_save_path(db_session, tmp_path, monkeypatch):
    """save_path を指定した場合、そのパスに PDF が生成されること"""
    from app.utils.pdf_helpers import generate_and_open
    from app.database.models import CompanySettings, Issuance

    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    saved_to = []

    def fake_generate_receipt(issuance, company, path, **kwargs):
        with open(path, "wb") as f:
            f.write(b"%PDF")
        saved_to.append(path)

    monkeypatch.setattr(
        "app.services.pdf.receipt_pdf.generate_receipt_pdf",
        fake_generate_receipt,
    )

    iss = Issuance(
        doc_number="R2026-001", doc_type="receipt",
        recipient_organization="テスト", status="発行済み",
        fiscal_year=2026, month=6, amount=1000,
    )
    db_session.add(iss)
    db_session.commit()

    custom_path = str(tmp_path / "my_receipt.pdf")
    result = generate_and_open(iss, db_session, open_file=False, save_path=custom_path)

    assert result == custom_path
    assert saved_to == [custom_path]


def test_generate_and_open_default_path_when_save_path_none(db_session, tmp_path, monkeypatch):
    """save_path=None の場合、従来の output_dir に保存されること"""
    from app.utils.pdf_helpers import generate_and_open
    from app.database.models import CompanySettings, Issuance

    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    saved_to = []

    def fake_generate_receipt(issuance, company, path, **kwargs):
        with open(path, "wb") as f:
            f.write(b"%PDF")
        saved_to.append(path)

    monkeypatch.setattr(
        "app.services.pdf.receipt_pdf.generate_receipt_pdf",
        fake_generate_receipt,
    )
    monkeypatch.setattr(
        "app.utils.pdf_helpers.get_pdf_output_dir",
        lambda: str(tmp_path),
    )

    iss = Issuance(
        doc_number="R2026-002", doc_type="receipt",
        recipient_organization="テスト", status="発行済み",
        fiscal_year=2026, month=6, amount=500,
    )
    db_session.add(iss)
    db_session.commit()

    result = generate_and_open(iss, db_session, open_file=False, save_path=None)

    assert result is not None
    assert "R2026-002" in result
    assert result.startswith(str(tmp_path))


def test_merge_and_open_accepts_output_dir(tmp_path):
    """output_dir 引数を指定できること（空リスト→ None の早期リターンで検証）"""
    from app.utils.pdf_helpers import merge_and_open
    # 空リスト → 早期リターン（None を返す）
    assert merge_and_open([], "テスト", output_dir=str(tmp_path)) is None
```

- [ ] **Step 2: テストが失敗することを確認**

```
pytest tests/test_pdf_helpers.py::test_generate_and_open_uses_save_path tests/test_pdf_helpers.py::test_generate_and_open_default_path_when_save_path_none tests/test_pdf_helpers.py::test_merge_and_open_uses_custom_output_dir -v
```

期待結果: 2件 FAILED（`save_path` / `output_dir` 引数が未定義のため）、`test_merge_and_open_accepts_output_dir` は TypeError で FAILED

- [ ] **Step 3: `generate_and_open` に `save_path` 引数を追加**

`app/utils/pdf_helpers.py` の `generate_and_open` シグネチャを変更：

```python
def generate_and_open(issuance, session, reissue: bool = False,
                      due_date=None, open_file: bool = True,
                      window_envelope: bool = False,
                      recipient_postal_code: str = "",
                      recipient_address: str = "",
                      recipient_address2: str = "",
                      project=None,
                      save_path: str | None = None) -> str | None:
```

関数内、`output_dir = get_pdf_output_dir()` の直後、`suffix = ...` の前に何も変えず、invoice用のpath行とreceipt用のpath行だけ変更：

invoice用（`path = os.path.join(output_dir, f"{issuance.doc_number}{suffix}.pdf")` — invoiceブロック）:
```python
path = save_path or os.path.join(output_dir, f"{issuance.doc_number}{suffix}.pdf")
```

receipt用（`path = os.path.join(output_dir, f"{issuance.doc_number}{suffix}.pdf")` — receiptブロック）:
```python
path = save_path or os.path.join(output_dir, f"{issuance.doc_number}{suffix}.pdf")
```

- [ ] **Step 4: `merge_and_open` に `output_dir` 引数を追加**

```python
def merge_and_open(paths: list[str], base_name: str,
                   output_dir: str | None = None) -> str | None:
    paths = [p for p in paths if p and os.path.exists(p)]
    if not paths:
        return None
    if output_dir is None:
        output_dir = get_pdf_output_dir()
    from app.services.print_service import open_pdf
    try:
        from pypdf import PdfWriter
    except ImportError:
        os.startfile(output_dir)
        return None
    from datetime import datetime
    safe = "".join(c for c in base_name if c not in '\\/:*?"<>|')
    merged = os.path.join(
        output_dir,
        f"{safe}_一括_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    writer = PdfWriter()
    for p in paths:
        writer.append(p)
    with open(merged, "wb") as f:
        writer.write(f)
    writer.close()
    open_pdf(merged)
    return merged
```

- [ ] **Step 5: テストを実行して確認**

```
pytest tests/test_pdf_helpers.py -v
```

期待結果: 全テスト PASSED

- [ ] **Step 6: コミット**

```bash
git add app/utils/pdf_helpers.py tests/test_pdf_helpers.py
git commit -m "feat: generate_and_open に save_path 引数、merge_and_open に output_dir 引数を追加"
```

---

### Task 2: 窓口発行（`issuance_counter.py`）にファイル保存先ダイアログを追加

**Files:**
- Modify: `app/ui/issuance_counter.py:829-994`（`_issue` メソッド）

- [ ] **Step 1: `_issue` メソッドのDB保存後にダイアログ処理を追加**

まず `issuance_counter.py` の先頭 import ブロックに `import os` を追加する（既存の `import calendar` の直下など）。

次に `_issue()` メソッド内、`_add_log(...)` の呼び出し直後（`from app.utils.pdf_helpers import generate_and_open` の直前）に以下を挿入：

```python
# ── 保存先を選択（メール送付以外）──────────────────────────
from PyQt6.QtWidgets import QFileDialog
from app.utils.pdf_helpers import get_pdf_output_dir
_delivery_text = self._delivery.currentText()
_save_path: str | None = None
if _delivery_text != "メール送付":
    _out_dir = get_pdf_output_dir()
    _default_name = os.path.join(_out_dir, f"{iss.doc_number}.pdf")
    _save_path, _ = QFileDialog.getSaveFileName(
        self, "PDFの保存先を選択", _default_name, "PDF ファイル (*.pdf)"
    )
    if not _save_path:
        QMessageBox.information(
            self, "保存キャンセル",
            "発行は記録されましたが、PDFは保存されませんでした。\n"
            "再発行タブから出力できます。",
        )
```

- [ ] **Step 2: `generate_and_open` 呼び出しを条件分岐に変更**

現在の `generate_and_open(iss, session, ...)` 呼び出しブロック全体を以下に置き換える：

```python
from app.utils.pdf_helpers import generate_and_open
due_date = None
window_envelope = False
postal_code = address1 = address2 = ""
if doc_type == "invoice":
    qd = self._due_date.date()
    due_date = date(qd.year(), qd.month(), qd.day())
    window_envelope = self._window_envelope_chk.isChecked()
    if window_envelope:
        postal_code = self._postal_code_edit.text().strip()
        address1    = self._address1_edit.text().strip()
        address2    = self._address2_edit.text().strip()
from app.database.models import Project as _Project
_proj = session.get(_Project, iss.project_id)
if _delivery_text == "メール送付":
    # メール添付用に生成（ビューアで開かない）
    generate_and_open(iss, session, due_date=due_date, open_file=False,
                      window_envelope=window_envelope,
                      recipient_postal_code=postal_code,
                      recipient_address=address1,
                      recipient_address2=address2,
                      project=_proj)
elif _save_path:
    # 指定パスに保存してビューアで開く
    generate_and_open(iss, session, due_date=due_date,
                      save_path=_save_path,
                      window_envelope=window_envelope,
                      recipient_postal_code=postal_code,
                      recipient_address=address1,
                      recipient_address2=address2,
                      project=_proj)
```

注: 既存の `due_date`/`window_envelope`/`postal_code` 設定コードは置き換え後のブロック内に含める（重複させない）。

- [ ] **Step 3: アプリを起動して動作確認**

```
python main.py
```

1. 窓口発行タブ → 宛先・項目を入力 → 「発行する」ボタン
2. ファイル保存先ダイアログが表示されること
3. 任意の場所を選んで保存 → PDFビューアが開くこと
4. キャンセル → 「保存キャンセル」メッセージが表示されること
5. 再発行タブに発行記録が残っていること

- [ ] **Step 4: コミット**

```bash
git add app/ui/issuance_counter.py
git commit -m "feat: 窓口発行にPDF保存先選択ダイアログを追加"
```

---

### Task 3: 再発行（`reissue_tab.py`）にファイル保存先ダイアログを追加

**Files:**
- Modify: `app/ui/reissue_tab.py:312-332`（再発行処理ブロック）

- [ ] **Step 1: `generate_and_open` 呼び出し前にダイアログを追加**

`reissue_tab.py` の `generate_and_open(iss, session, reissue=True, ...)` 呼び出しの直前に挿入：

```python
from PyQt6.QtWidgets import QFileDialog
from app.utils.pdf_helpers import get_pdf_output_dir
import os
_out_dir = get_pdf_output_dir()
_default_name = os.path.join(_out_dir, f"{iss.doc_number}_再発行.pdf")
_save_path, _ = QFileDialog.getSaveFileName(
    self, "PDFの保存先を選択", _default_name, "PDF ファイル (*.pdf)"
)
if not _save_path:
    return  # キャンセル時は何も変更せず終了
```

- [ ] **Step 2: `generate_and_open` 呼び出しに `save_path` を追加**

```python
generate_and_open(iss, session, reissue=True, due_date=due_date,
                  save_path=_save_path,
                  project=_proj)
```

- [ ] **Step 3: アプリを起動して動作確認**

```
python main.py
```

1. 再発行タブ → 任意の行を選択 → 「再発行」ボタン
2. 請求書の場合: 支払期日ダイアログ → OK → ファイル保存ダイアログが開くこと
3. 保存先を選んで保存 → PDFビューアが開くこと
4. キャンセル → 何も変わらないこと（ログも残らない）

- [ ] **Step 4: コミット**

```bash
git add app/ui/reissue_tab.py
git commit -m "feat: 再発行にPDF保存先選択ダイアログを追加"
```

---

### Task 4: プロジェクト一括発行（`issuance_from_project.py`）にフォルダ選択ダイアログを追加

**Files:**
- Modify: `app/ui/issuance_from_project.py:780-858`（`_do_issue_rows` の発行ループ前後）

- [ ] **Step 1: `_do_issue_rows` 内のループ前にフォルダ選択を挿入**

`window_envelope = self._window_envelope_chk.isChecked()` の直後（`session = get_session()` の直前）に挿入：

```python
# ── 保存先フォルダを選択（メール送付以外）──────────────────
save_dir: str | None = None
if delivery != "メール送付":
    from PyQt6.QtWidgets import QFileDialog
    from app.utils.pdf_helpers import get_pdf_output_dir
    save_dir = QFileDialog.getExistingDirectory(
        self, "PDFの保存先フォルダを選択", get_pdf_output_dir()
    )
    if not save_dir:
        return errors  # キャンセル → DB変更なしで終了
```

- [ ] **Step 2: ループ内の `generate_and_open` 呼び出しに `save_path` を追加**

現在（約828行目）：

```python
path = generate_and_open(iss, session, due_date=due_date,
                         open_file=open_each,
                         window_envelope=window_envelope,
                         project=_proj)
```

変更後：

```python
_pdf_save_path = (
    os.path.join(save_dir, f"{iss.doc_number}.pdf")
    if save_dir else None
)
path = generate_and_open(iss, session, due_date=due_date,
                         open_file=open_each,
                         save_path=_pdf_save_path,
                         window_envelope=window_envelope,
                         project=_proj)
```

`issuance_from_project.py` の先頭に `import os` がなければ追加する（`import calendar` の直下など）。

- [ ] **Step 3: `merge_and_open` 呼び出しに `output_dir=save_dir` を追加**

現在（約854行目）：

```python
merge_and_open(pdf_paths, self._proj_combo.currentText())
```

変更後：

```python
merge_and_open(pdf_paths, self._proj_combo.currentText(), output_dir=save_dir)
```

- [ ] **Step 4: アプリを起動して動作確認**

```
python main.py
```

1. プロジェクトから発行タブ → プロジェクトを選択 → 複数行にチェック → 「選択行に発行」
2. フォルダ選択ダイアログが表示されること
3. フォルダを選んで OK → 各PDFが選んだフォルダに保存 → 結合PDFがビューアで開くこと
4. キャンセル → 何も変わらないこと（発行記録なし）
5. 1件だけチェックして発行 → フォルダ選択 → PDFがそのフォルダに保存されビューアで開くこと

- [ ] **Step 5: コミット**

```bash
git add app/ui/issuance_from_project.py
git commit -m "feat: プロジェクト一括発行にフォルダ選択ダイアログを追加"
```

---

## チェックリスト（スペック対照）

| 要件 | 対応タスク |
|---|---|
| 窓口発行: 毎回ファイル保存ダイアログ | Task 2 |
| 窓口発行: 保存後にPDFビューアで開く | Task 1 + Task 2 |
| 窓口発行: キャンセル時にDB記録は残り案内メッセージ表示 | Task 2 |
| 再発行: 毎回ファイル保存ダイアログ | Task 3 |
| 再発行: キャンセル時は何も変更しない | Task 3 |
| 一括発行: フォルダ選択ダイアログ（1回） | Task 4 |
| 一括発行: 結合PDFをビューアで開く | Task 1 + Task 4 |
| 一括発行: キャンセル時はDB変更なし | Task 4 |
| メール送付時はダイアログを表示しない | Task 2 |
| `generate_and_open` の後方互換性 | Task 1 |
