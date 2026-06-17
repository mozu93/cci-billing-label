# タブ再編成 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** トップタブを `窓口発行 / まとめて発行 / 再発行 / ダッシュボード / レポート / 設定` に再編し、既存の発行系ウィジェットを新しいコンテナに並べ替える。

**Architecture:** 純粋な画面再配置。既存ウィジェット（`IssuanceCounterWidget`、`IssuanceCrossMemberWidget`、`ProjectTab`、`IssuanceFromProjectWidget`、`PaymentManagementWidget`、`ReissueWidget`、`DashboardWidget`、`ReportTab`、`SettingsTab`）のロジック・シグナル・サービス呼び出しには一切手を入れない。新たに2つのコンテナタブ（`CounterIssuanceTab`／`BatchIssuanceTab`）を作り、`MainWindow` の組み立てを差し替える。旧 `issuance_tab.py`（「発行」タブ）は廃止する。

**Tech Stack:** Python / PyQt6 / pytest + pytest-qt（オフスクリーン）/ SQLAlchemy（テストはin-memory SQLite）

**設計仕様書:** `docs/superpowers/specs/2026-05-31-tab-restructure-design.md`

---

## ファイル構成

| ファイル | 役割 | 操作 |
|---------|------|------|
| `app/ui/counter_issuance_tab.py` | 窓口発行コンテナ。フリー発行＋随時受取の2サブタブを束ねる | 新規 |
| `app/ui/batch_issuance_tab.py` | まとめて発行コンテナ。事業管理＋事業から発行＋入金管理の3サブタブを束ねる | 新規 |
| `app/ui/main_window.py` | トップタブの構成・並び順・初期表示を新構造に変更 | 変更 |
| `app/ui/issuance_tab.py` | 旧「発行」タブ。サブタブを再配分するため廃止 | 削除 |
| `tests/conftest.py` | UIテスト用に in-memory DB を初期化する `memory_db` フィクスチャと、Qtオフスクリーン設定を追加 | 変更 |
| `tests/test_counter_issuance_tab.py` | 窓口発行コンテナのサブタブ構成テスト | 新規 |
| `tests/test_batch_issuance_tab.py` | まとめて発行コンテナのサブタブ構成テスト | 新規 |
| `tests/test_main_window_tabs.py` | トップタブの順序・初期表示テスト | 新規 |

> コンテナは `app/ui/settings_tab.py`・`app/ui/issuance_tab.py` と同じ「`QTabWidget` に既存ウィジェットを `addTab` するだけ」のパターンに倣う。

---

## Task 1: テスト基盤の準備（conftest）

UIウィジェットは構築時に `get_session()` 経由でDBへアクセスする。テストでは事前に in-memory SQLite を `init_db()` で初期化しておく必要がある。また pytest-qt をヘッドレスで動かすため Qt をオフスクリーンにする。

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: conftest にオフスクリーン設定と memory_db フィクスチャを追加**

`tests/conftest.py` を以下の内容に変更する（既存の `db_session` フィクスチャは残す）：

```python
# tests/conftest.py
import os
# pytest-qt をヘッドレスで動かす（QApplication 生成前に設定する必要がある）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


@pytest.fixture
def memory_db():
    """UIウィジェットが get_session() で参照するグローバルDBを
    in-memory SQLite に初期化する。"""
    from app.database.connection import init_db
    init_db("sqlite:///:memory:")
    yield
```

- [ ] **Step 2: 既存テストが壊れていないことを確認**

Run: `pytest -q`
Expected: 既存テストが全て PASS（収集エラーなし）。`QT_QPA_PLATFORM` 設定とフィクスチャ追加は既存のサービス層テストに影響しない。

- [ ] **Step 3: コミット**

```bash
cd "C:/Users/taka/Documents/Gemini/0030Business/cci-billing"
git add tests/conftest.py
git commit -m "test: UIテスト用のmemory_dbフィクスチャとQtオフスクリーン設定を追加"
```

---

## Task 2: 窓口発行コンテナ（CounterIssuanceTab）

**Files:**
- Test: `tests/test_counter_issuance_tab.py`
- Create: `app/ui/counter_issuance_tab.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_counter_issuance_tab.py` を新規作成：

```python
# tests/test_counter_issuance_tab.py
from PyQt6.QtWidgets import QTabWidget


def _tab_titles(tabwidget: QTabWidget) -> list[str]:
    return [tabwidget.tabText(i) for i in range(tabwidget.count())]


def test_counter_issuance_subtabs(qtbot, memory_db):
    from app.ui.counter_issuance_tab import CounterIssuanceTab
    w = CounterIssuanceTab()
    qtbot.addWidget(w)
    inner = w.findChild(QTabWidget)
    assert inner is not None
    assert _tab_titles(inner) == ["フリー発行", "随時受取"]
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `pytest tests/test_counter_issuance_tab.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ui.counter_issuance_tab'`）

- [ ] **Step 3: コンテナを実装**

`app/ui/counter_issuance_tab.py` を新規作成：

```python
# app/ui/counter_issuance_tab.py
from PyQt6.QtWidgets import QWidget, QTabWidget, QVBoxLayout
from app.ui.issuance_counter import IssuanceCounterWidget
from app.ui.issuance_cross_member import IssuanceCrossMemberWidget


class CounterIssuanceTab(QWidget):
    """窓口発行：その場で1件ずつ発行する作業をまとめるタブ。"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        inner = QTabWidget()
        inner.addTab(IssuanceCounterWidget(), "フリー発行")
        inner.addTab(IssuanceCrossMemberWidget(), "随時受取")
        layout.addWidget(inner)
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `pytest tests/test_counter_issuance_tab.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
cd "C:/Users/taka/Documents/Gemini/0030Business/cci-billing"
git add app/ui/counter_issuance_tab.py tests/test_counter_issuance_tab.py
git commit -m "feat: 窓口発行コンテナ（フリー発行＋随時受取）を追加"
```

---

## Task 3: まとめて発行コンテナ（BatchIssuanceTab）

**Files:**
- Test: `tests/test_batch_issuance_tab.py`
- Create: `app/ui/batch_issuance_tab.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_batch_issuance_tab.py` を新規作成：

```python
# tests/test_batch_issuance_tab.py
from PyQt6.QtWidgets import QTabWidget


def _tab_titles(tabwidget: QTabWidget) -> list[str]:
    return [tabwidget.tabText(i) for i in range(tabwidget.count())]


def test_batch_issuance_subtabs(qtbot, memory_db):
    from app.ui.batch_issuance_tab import BatchIssuanceTab
    w = BatchIssuanceTab()
    qtbot.addWidget(w)
    inner = w.findChild(QTabWidget)
    assert inner is not None
    assert _tab_titles(inner) == ["事業管理", "事業から発行", "入金管理"]
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `pytest tests/test_batch_issuance_tab.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.ui.batch_issuance_tab'`）

- [ ] **Step 3: コンテナを実装**

`app/ui/batch_issuance_tab.py` を新規作成：

```python
# app/ui/batch_issuance_tab.py
from PyQt6.QtWidgets import QWidget, QTabWidget, QVBoxLayout
from app.ui.project_tab import ProjectTab
from app.ui.issuance_from_project import IssuanceFromProjectWidget
from app.ui.payment_dialog import PaymentManagementWidget


class BatchIssuanceTab(QWidget):
    """まとめて発行：事業単位の準備・一括発行・入金管理をまとめるタブ。"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        inner = QTabWidget()
        inner.addTab(ProjectTab(), "事業管理")
        inner.addTab(IssuanceFromProjectWidget(), "事業から発行")
        inner.addTab(PaymentManagementWidget(), "入金管理")
        layout.addWidget(inner)
```

- [ ] **Step 4: テストを実行して成功を確認**

Run: `pytest tests/test_batch_issuance_tab.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
cd "C:/Users/taka/Documents/Gemini/0030Business/cci-billing"
git add app/ui/batch_issuance_tab.py tests/test_batch_issuance_tab.py
git commit -m "feat: まとめて発行コンテナ（事業管理＋事業から発行＋入金管理）を追加"
```

---

## Task 4: MainWindow のタブ再編と旧「発行」タブの廃止

**Files:**
- Test: `tests/test_main_window_tabs.py`
- Modify: `app/ui/main_window.py`
- Delete: `app/ui/issuance_tab.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_main_window_tabs.py` を新規作成：

```python
# tests/test_main_window_tabs.py
from PyQt6.QtWidgets import QTabWidget


def _tab_titles(tabwidget: QTabWidget) -> list[str]:
    return [tabwidget.tabText(i) for i in range(tabwidget.count())]


def test_top_level_tabs_order(qtbot, memory_db):
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    tabs = window.centralWidget()
    assert isinstance(tabs, QTabWidget)
    assert _tab_titles(tabs) == [
        "窓口発行", "まとめて発行", "再発行",
        "ダッシュボード", "レポート", "設定",
    ]


def test_default_tab_is_counter(qtbot, memory_db):
    from app.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    tabs = window.centralWidget()
    assert tabs.currentIndex() == 0
    assert tabs.tabText(tabs.currentIndex()) == "窓口発行"
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `pytest tests/test_main_window_tabs.py -v`
Expected: FAIL（現状のタブは `["ダッシュボード", "事業管理", "発行", "レポート", "設定"]` のため、順序アサーションで失敗）

- [ ] **Step 3: MainWindow を新構造に書き換える**

`app/ui/main_window.py` を以下の内容に置き換える：

```python
# app/ui/main_window.py
from PyQt6.QtWidgets import QMainWindow, QTabWidget
from PyQt6.QtCore import pyqtSignal


class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("商工会議所請求書・領収書発行システム")
        self.resize(780, 800)
        self._build_tabs()

    def _build_tabs(self):
        tabs = QTabWidget()

        from app.ui.counter_issuance_tab import CounterIssuanceTab
        tabs.addTab(CounterIssuanceTab(), "窓口発行")

        from app.ui.batch_issuance_tab import BatchIssuanceTab
        tabs.addTab(BatchIssuanceTab(), "まとめて発行")

        from app.ui.reissue_tab import ReissueWidget
        tabs.addTab(ReissueWidget(), "再発行")

        from app.ui.dashboard import DashboardWidget
        tabs.addTab(DashboardWidget(), "ダッシュボード")

        from app.ui.report_tab import ReportTab
        tabs.addTab(ReportTab(), "レポート")

        from app.ui.settings_tab import SettingsTab
        tabs.addTab(SettingsTab(), "設定")

        tabs.setCurrentIndex(0)
        self.setCentralWidget(tabs)
```

- [ ] **Step 4: 旧「発行」タブを削除**

`app/ui/issuance_tab.py` を削除する。`IssuanceTab` は `main_window.py` 以外から参照されていない（確認済み）ため、削除しても他に影響はない。

```bash
cd "C:/Users/taka/Documents/Gemini/0030Business/cci-billing"
git rm app/ui/issuance_tab.py
```

- [ ] **Step 5: テストを実行して成功を確認**

Run: `pytest tests/test_main_window_tabs.py -v`
Expected: PASS（2件とも）

- [ ] **Step 6: 全テストを実行して回帰がないことを確認**

Run: `pytest -q`
Expected: 全テスト PASS

- [ ] **Step 7: コミット**

```bash
cd "C:/Users/taka/Documents/Gemini/0030Business/cci-billing"
git add app/ui/main_window.py tests/test_main_window_tabs.py
git commit -m "feat: トップタブを窓口発行/まとめて発行/再発行に再編し旧発行タブを廃止"
```

---

## Task 5: 手動スモークテスト

自動テストは構造（タブの有無・順序・初期表示）を担保するが、実際の見た目・操作は人手で確認する。

**Files:** なし（手動確認のみ）

- [ ] **Step 1: アプリを起動**

Run: `python main.py`

- [ ] **Step 2: 受け入れ基準を目視確認**

- 起動時に **窓口発行** タブが開いている
- トップタブが `窓口発行 / まとめて発行 / 再発行 / ダッシュボード / レポート / 設定` の順
- 窓口発行 → 「フリー発行」「随時受取」のサブタブがあり、従来どおり入力・発行できる
- まとめて発行 → 「事業管理」「事業から発行」「入金管理」のサブタブがあり、従来どおり動作する
- 再発行・ダッシュボード・レポート・設定が従来どおり開く

- [ ] **Step 3: 問題があれば報告**

見た目崩れや動作不良があれば内容を記録し、修正タスクを追加する。

---

## 受け入れ基準（設計仕様書 §5 と対応）

1. 起動時に窓口発行タブが表示される → Task 4 / Task 5
2. トップタブの並びが正しい → Task 4
3. 窓口発行に「フリー発行」「随時受取」がある → Task 2 / Task 5
4. まとめて発行に「事業管理」「事業から発行」「入金管理」がある → Task 3 / Task 5
5. 再発行・ダッシュボード・レポート・設定が従来どおり → Task 4 / Task 5
6. 発行・採番・入金・PDF生成の挙動に変化がない → 既存ウィジェット未改変（Task 2〜4）＋ Task 5
