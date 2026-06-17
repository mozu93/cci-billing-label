# GitHub Release 配布 ＆ アプリ内自動アップデート 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cci-billing を GitHub Releases で Inno Setup インストーラーとして配布し、アプリ起動時に新バージョンを自動検出してアップデートできる仕組みを追加する。

**Architecture:** バージョン番号は `app/version.py` で一元管理し、`app/utils/updater.py` が GitHub API で最新リリースを確認、`app/ui/update_banner.py` がバナーとして通知する。`v*.*.*` タグの push で GitHub Actions が PyInstaller ビルド → Inno Setup インストーラー作成 → GitHub Release 公開を自動実行する。

**Tech Stack:** PyQt6, PyInstaller, Inno Setup 6, GitHub Actions (windows-latest), packaging (semver 比較)

---

## ファイルマップ

| ファイル | 種別 | 責務 |
|---|---|---|
| `app/version.py` | 新規 | バージョン番号の単一管理源 |
| `app/utils/updater.py` | 新規 | GitHub API チェック・ダウンロード・インストーラー起動 |
| `app/ui/update_banner.py` | 新規 | アップデートバナーウィジェット |
| `app/ui/main_window.py` | 変更 | バナー・ステータスバー・ヘルプメニュー追加 |
| `assets/app_icon.ico` | 新規 | プレースホルダーアイコン（32x32 blue） |
| `cci_billing.spec` | 新規 | PyInstaller ビルド定義 |
| `installer/setup.iss` | 新規 | Inno Setup インストーラー定義 |
| `.github/workflows/release.yml` | 新規 | タグ push 自動ビルド＆リリース |
| `requirements.txt` | 変更 | `packaging>=23.0` を追加 |

---

## Task 1: requirements.txt に packaging を追加し app/version.py を作成

**Files:**
- Modify: `requirements.txt`
- Create: `app/version.py`

- [ ] **Step 1: requirements.txt に packaging を追記**

`requirements.txt` の末尾に以下を追加：

```
packaging>=23.0
```

最終的な `requirements.txt`：
```
PyQt6>=6.6.0
SQLAlchemy>=2.0.0
psycopg2-binary>=2.9.0
reportlab>=4.0.0
openpyxl>=3.1.0
pypdf>=4.0.0
packaging>=23.0
```

- [ ] **Step 2: packaging をインストール**

```bash
pip install packaging>=23.0
```

Expected: Successfully installed

- [ ] **Step 3: app/version.py を作成**

```python
# -*- coding: utf-8 -*-
__version__ = "1.0.0"
```

- [ ] **Step 4: コミット**

```bash
git add requirements.txt app/version.py
git commit -m "feat: バージョン管理ファイルとpackaging依存を追加"
```

---

## Task 2: app/utils/updater.py を TDD で実装

**Files:**
- Create: `tests/test_updater.py`
- Create: `app/utils/updater.py`

- [ ] **Step 1: テストを書く**

`tests/test_updater.py` を作成：

```python
# -*- coding: utf-8 -*-
from app.utils.updater import is_newer_version


def test_newer_patch():
    assert is_newer_version("1.0.0", "1.0.1") is True

def test_same_version():
    assert is_newer_version("1.0.0", "1.0.0") is False

def test_older_version():
    assert is_newer_version("1.0.1", "1.0.0") is False

def test_minor_bump():
    assert is_newer_version("1.0.0", "1.1.0") is True

def test_major_bump():
    assert is_newer_version("1.0.0", "2.0.0") is True

def test_v_prefix_stripped():
    assert is_newer_version("1.0.0", "v1.0.1") is True
```

- [ ] **Step 2: テストが FAIL することを確認**

```bash
pytest tests/test_updater.py -v
```

Expected: `ImportError: cannot import name 'is_newer_version'` または `ModuleNotFoundError`

- [ ] **Step 3: app/utils/updater.py を実装**

```python
# -*- coding: utf-8 -*-
import os
import sys
import json
import tempfile
import subprocess
import urllib.request
import urllib.error
from typing import Optional

from packaging.version import Version

GITHUB_API_URL = "https://api.github.com/repos/mozu93/cci-billing/releases/latest"
_TIMEOUT = 8


def is_newer_version(current: str, latest: str) -> bool:
    """latest が current より新しければ True。v プレフィックスは除去する。"""
    current = current.lstrip("v")
    latest  = latest.lstrip("v")
    return Version(latest) > Version(current)


def check_latest_version() -> Optional[dict]:
    """
    GitHub API で最新リリースを取得する。
    戻り値: {"tag_name": "v1.0.1", "download_url": "https://..."} または None（失敗時）
    """
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "cci-billing-updater"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        assets = data.get("assets", [])
        if not tag or not assets:
            return None
        download_url = assets[0].get("browser_download_url", "")
        if not download_url:
            return None
        return {"tag_name": tag, "download_url": download_url}
    except Exception:
        return None


def download_new_exe(url: str, progress_callback=None) -> Optional[str]:
    """
    新しいインストーラー exe を %TEMP% にダウンロードする。
    progress_callback(received_bytes, total_bytes) を呼び出す（total が不明な場合は -1）。
    成功時はダウンロード先パスを返す。失敗時は None。
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cci-billing-updater"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", -1))
            fd, tmp_path = tempfile.mkstemp(suffix=".exe", prefix="cci_billing_new_")
            received = 0
            with os.fdopen(fd, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    if progress_callback:
                        progress_callback(received, total)
        return tmp_path
    except Exception:
        return None


def launch_updater(new_exe_path: str, current_exe_path: str):
    """
    updater.bat を %TEMP% に生成して起動し、アプリを終了する。
    bat は: 3秒待機（アプリ終了を待つ）→ インストーラーを起動 → 自己削除
    """
    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="cci_billing_updater_")
    with os.fdopen(bat_fd, "w", encoding="cp932") as f:
        f.write("@echo off\r\n")
        f.write("timeout /t 3 /nobreak > nul\r\n")
        f.write(f'start "" "{new_exe_path}"\r\n')
        f.write('del "%~f0"\r\n')
    subprocess.Popen(["cmd", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)
```

- [ ] **Step 4: テストが PASS することを確認**

```bash
pytest tests/test_updater.py -v
```

Expected: 6 passed

- [ ] **Step 5: コミット**

```bash
git add tests/test_updater.py app/utils/updater.py
git commit -m "feat: GitHub APIアップデートチェッカーを追加"
```

---

## Task 3: assets/app_icon.ico をプレースホルダー生成

**Files:**
- Create: `assets/app_icon.ico`

- [ ] **Step 1: アイコン生成スクリプトを実行**

プロジェクトルートで以下の Python コードを直接実行する（ファイルは作らない）：

```python
import struct, os

def make_simple_ico(path):
    w, h = 32, 32
    # Color: #2563EB (blue) -> BGRA: B=0xEB, G=0x63, R=0x25, A=0xFF
    pixels = bytes([0xEB, 0x63, 0x25, 0xFF] * (w * h))
    # AND mask: 32px wide = 4 bytes/row (DWORD-aligned), all 0 (opaque)
    and_mask = bytes([0x00, 0x00, 0x00, 0x00] * h)
    bih = struct.pack('<IiiHHIIiiII',
        40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    image_data = bih + pixels + and_mask
    icon_dir = struct.pack('<HHH', 0, 1, 1)
    icon_entry = struct.pack('<BBBBHHII',
        w, h, 0, 0, 1, 32, len(image_data), 6 + 16)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(icon_dir + icon_entry + image_data)
    print(f"Generated {path}")

make_simple_ico('assets/app_icon.ico')
```

実行方法：
```bash
python -c "
import struct, os
def make_simple_ico(path):
    w, h = 32, 32
    pixels = bytes([0xEB, 0x63, 0x25, 0xFF] * (w * h))
    and_mask = bytes([0x00, 0x00, 0x00, 0x00] * h)
    bih = struct.pack('<IiiHHIIiiII', 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    image_data = bih + pixels + and_mask
    icon_dir = struct.pack('<HHH', 0, 1, 1)
    icon_entry = struct.pack('<BBBBHHII', w, h, 0, 0, 1, 32, len(image_data), 6 + 16)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(icon_dir + icon_entry + image_data)
    print(f'Generated {path}')
make_simple_ico('assets/app_icon.ico')
"
```

Expected: `Generated assets/app_icon.ico`

- [ ] **Step 2: コミット**

```bash
git add assets/app_icon.ico
git commit -m "feat: アプリアイコン（プレースホルダー）を追加"
```

---

## Task 4: app/ui/update_banner.py を実装

**Files:**
- Create: `app/ui/update_banner.py`

- [ ] **Step 1: update_banner.py を作成**

```python
# -*- coding: utf-8 -*-
"""
アップデート通知バー。MainWindow の上部に差し込む。
状態: hidden → 「ダウンロード」ボタン → プログレスバー → 「今すぐ更新」ボタン
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QProgressBar,
)
from PyQt6.QtCore import QThread, pyqtSignal


class _VersionCheckThread(QThread):
    found = pyqtSignal(str, str)   # (tag_name, download_url)

    def run(self):
        from app.utils.updater import check_latest_version, is_newer_version
        from app.version import __version__
        result = check_latest_version()
        if result and is_newer_version(__version__, result["tag_name"]):
            self.found.emit(result["tag_name"], result["download_url"])


class _DownloadThread(QThread):
    progress = pyqtSignal(int, int)   # (received, total)
    finished = pyqtSignal(str)        # tmp_path
    failed   = pyqtSignal()

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        from app.utils.updater import download_new_exe
        path = download_new_exe(self._url, progress_callback=self.progress.emit)
        if path:
            self.finished.emit(path)
        else:
            self.failed.emit()


class UpdateBanner(QWidget):
    """アップデート通知バー。新バージョンがなければ非表示のまま。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._download_url = ""
        self._tmp_exe_path = ""
        self._init_ui()
        self.setVisible(False)
        self._start_check()

    def _init_ui(self):
        self.setStyleSheet(
            "background: #FEF9C3; border-bottom: 1px solid #FDE047;"
        )
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)

        self._lbl = QLabel()
        self._lbl.setStyleSheet("color: #713F12; font-size: 12px;")

        self._btn_dl = QPushButton("ダウンロード")
        self._btn_dl.setFixedHeight(28)
        self._btn_dl.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; border-radius: 5px; "
            "padding: 0 12px; font-size: 12px; }"
            "QPushButton:hover { background: #1D4ED8; }"
        )
        self._btn_dl.clicked.connect(self._start_download)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(20)
        self._progress.setVisible(False)

        self._btn_install = QPushButton("今すぐ更新して再起動")
        self._btn_install.setFixedHeight(28)
        self._btn_install.setStyleSheet(
            "QPushButton { background: #16A34A; color: white; border-radius: 5px; "
            "padding: 0 12px; font-size: 12px; }"
            "QPushButton:hover { background: #15803D; }"
        )
        self._btn_install.setVisible(False)
        self._btn_install.clicked.connect(self._install)

        layout.addWidget(self._lbl)
        layout.addStretch()
        layout.addWidget(self._btn_dl)
        layout.addWidget(self._progress)
        layout.addWidget(self._btn_install)

    def _start_check(self):
        self._check_thread = _VersionCheckThread(self)
        self._check_thread.found.connect(self._on_update_found)
        self._check_thread.start()

    def _on_update_found(self, tag: str, url: str):
        self._download_url = url
        self._lbl.setText(f"新しいバージョン {tag} が利用可能です")
        self.setVisible(True)

    def _start_download(self):
        self._btn_dl.setVisible(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._dl_thread = _DownloadThread(self._download_url, self)
        self._dl_thread.progress.connect(self._on_progress)
        self._dl_thread.finished.connect(self._on_download_done)
        self._dl_thread.failed.connect(self._on_download_failed)
        self._dl_thread.start()

    def _on_progress(self, received: int, total: int):
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(received)

    def _on_download_done(self, tmp_path: str):
        self._tmp_exe_path = tmp_path
        self._progress.setVisible(False)
        self._lbl.setText("ダウンロード完了。アプリを再起動して更新します。")
        self._btn_install.setVisible(True)

    def _on_download_failed(self):
        self._progress.setVisible(False)
        self._btn_dl.setVisible(True)
        self._lbl.setText("ダウンロードに失敗しました。後で再試行してください。")

    def _install(self):
        import sys
        from app.utils.updater import launch_updater
        current_exe = sys.executable if getattr(sys, "frozen", False) else ""
        if not current_exe:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "開発環境",
                "開発環境では更新インストールを実行できません。\n"
                f"ダウンロード先: {self._tmp_exe_path}"
            )
            return
        launch_updater(self._tmp_exe_path, current_exe)
```

- [ ] **Step 2: import が通ることを確認**

```bash
python -c "from app.ui.update_banner import UpdateBanner; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: コミット**

```bash
git add app/ui/update_banner.py
git commit -m "feat: アップデートバナーウィジェットを追加"
```

---

## Task 5: app/ui/main_window.py にバナー・ステータスバー・ヘルプメニューを追加

**Files:**
- Modify: `app/ui/main_window.py`

現在の `app/ui/main_window.py`：
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
        tabs.addTab(CounterIssuanceTab(), "単発発行")

        from app.ui.batch_issuance_tab import BatchIssuanceTab
        tabs.addTab(BatchIssuanceTab(), "まとめて発行")

        from app.ui.reissue_tab import ReissueWidget
        tabs.addTab(ReissueWidget(), "修正・再発行")

        from app.ui.settings_tab import SettingsTab
        tabs.addTab(SettingsTab(), "設定")

        tabs.setCurrentIndex(0)
        self.setCentralWidget(tabs)
```

- [ ] **Step 1: main_window.py を以下に置き換え**

```python
# app/ui/main_window.py
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel, QMessageBox,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import pyqtSignal


class MainWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("商工会議所請求書・領収書発行システム")
        self.resize(780, 800)
        self._setup_menu()
        self._build_tabs()
        self._setup_statusbar()

    def _setup_menu(self):
        from app.version import __version__
        menubar = self.menuBar()
        help_menu = menubar.addMenu("ヘルプ")
        act_about = QAction("バージョン情報", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _build_tabs(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from app.ui.update_banner import UpdateBanner
        self._banner = UpdateBanner(self)
        layout.addWidget(self._banner)

        tabs = QTabWidget()

        from app.ui.counter_issuance_tab import CounterIssuanceTab
        tabs.addTab(CounterIssuanceTab(), "単発発行")

        from app.ui.batch_issuance_tab import BatchIssuanceTab
        tabs.addTab(BatchIssuanceTab(), "まとめて発行")

        from app.ui.reissue_tab import ReissueWidget
        tabs.addTab(ReissueWidget(), "修正・再発行")

        from app.ui.settings_tab import SettingsTab
        tabs.addTab(SettingsTab(), "設定")

        tabs.setCurrentIndex(0)
        layout.addWidget(tabs)

    def _setup_statusbar(self):
        from app.version import __version__
        sb = self.statusBar()
        sb.setStyleSheet(
            "QStatusBar { background: #F8FAFC; border-top: 1px solid #E2E8F0; "
            "font-size: 12px; color: #64748B; }"
            "QStatusBar::item { border: none; }"
        )
        ver_lbl = QLabel(f"v{__version__}")
        ver_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; padding: 0 8px;")
        sb.addPermanentWidget(ver_lbl)
        sb.showMessage("準備完了")

    def _show_about(self):
        from app.version import __version__
        QMessageBox.about(
            self,
            "バージョン情報",
            f"<b>CCI請求書システム</b><br>"
            f"バージョン {__version__}<br><br>"
            f"商工会議所向け請求書・領収書発行システムです。",
        )
```

- [ ] **Step 2: import が通ることを確認**

```bash
python -c "from app.ui.main_window import MainWindow; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: コミット**

```bash
git add app/ui/main_window.py
git commit -m "feat: メインウィンドウにアップデートバナー・ステータスバー・ヘルプメニューを追加"
```

---

## Task 6: cci_billing.spec を作成

**Files:**
- Create: `cci_billing.spec`

- [ ] **Step 1: cci_billing.spec を作成**

```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('reportlab')
datas += [('assets', 'assets')]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.postgresql',
        'sqlalchemy.sql.default_comparator',
        'psycopg2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CCIBilling',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CCIBilling',
)
```

- [ ] **Step 2: ローカルで PyInstaller が通るか確認（任意・CI で確認でも可）**

```bash
pip install pyinstaller
pyinstaller cci_billing.spec --noconfirm
```

Expected: `dist/CCIBilling/CCIBilling.exe` が生成される

- [ ] **Step 3: .gitignore に build/dist を追加（未追加の場合）**

`.gitignore` に以下がなければ追記：

```
build/
dist/
installer_output/
*.spec.bak
```

- [ ] **Step 4: コミット**

```bash
git add cci_billing.spec .gitignore
git commit -m "feat: PyInstaller spec を追加"
```

---

## Task 7: installer/setup.iss を作成

**Files:**
- Create: `installer/setup.iss`

- [ ] **Step 1: installer ディレクトリを作成し setup.iss を配置**

```bash
mkdir installer
```

`installer/setup.iss` を作成：

```iss
; CCI請求書システム Inno Setup スクリプト
#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

[Setup]
AppName=CCI請求書システム
AppVersion={#AppVersion}
AppPublisher=mozu93
AppPublisherURL=https://github.com/mozu93/cci-billing
AppSupportURL=https://github.com/mozu93/cci-billing/issues
DefaultDirName={localappdata}\CCIBilling
DefaultGroupName=CCI請求書システム
DisableDirPage=yes
OutputDir={#SourcePath}\..\installer_output
OutputBaseFilename=CCIBilling_Setup_{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
SetupIconFile={#SourcePath}\..\assets\app_icon.ico

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"; GroupDescription: "追加タスク:"

[Files]
Source: "{#SourcePath}\..\dist\CCIBilling\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CCI請求書システム"; Filename: "{app}\CCIBilling.exe"
Name: "{group}\アンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CCI請求書システム"; Filename: "{app}\CCIBilling.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CCIBilling.exe"; Description: "CCI請求書システムを起動する"; Flags: nowait postinstall skipifsilent
```

- [ ] **Step 2: コミット**

```bash
git add installer/setup.iss
git commit -m "feat: Inno Setupインストーラー定義を追加"
```

---

## Task 8: .github/workflows/release.yml を作成

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: .github/workflows ディレクトリを作成**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: release.yml を作成**

`.github/workflows/release.yml`：

```yaml
name: Build and Release

on:
  push:
    tags:
      - 'v*.*.*'

permissions:
  contents: write

jobs:
  build:
    runs-on: windows-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt pyinstaller

      - name: Get version
        id: ver
        shell: pwsh
        run: |
          $v = python -c "from app.version import __version__; print(__version__)"
          "VERSION=$v" | Out-File -FilePath $env:GITHUB_OUTPUT -Append

      - name: Build with PyInstaller
        run: pyinstaller cci_billing.spec --noconfirm

      - name: Install Inno Setup
        shell: pwsh
        run: |
          choco install innosetup --yes --no-progress
          $isccDir = "C:\Program Files (x86)\Inno Setup 6"
          if (-not (Test-Path $isccDir)) {
            $isccDir = "C:\Program Files\Inno Setup 6"
          }
          echo $isccDir | Out-File -FilePath $env:GITHUB_PATH -Append

      - name: Build installer
        shell: pwsh
        run: iscc "/DAppVersion=${{ steps.ver.outputs.VERSION }}" installer\setup.iss

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          name: "CCI請求書システム v${{ steps.ver.outputs.VERSION }}"
          body: |
            ## CCI請求書システム v${{ steps.ver.outputs.VERSION }}

            ### インストール方法
            1. 下記の `CCIBilling_Setup_${{ steps.ver.outputs.VERSION }}.exe` をダウンロード
            2. ダウンロードしたファイルをダブルクリックして実行
            3. 画面の指示に従ってインストール

            ※ 管理者権限は不要です。
          files: installer_output/CCIBilling_Setup_${{ steps.ver.outputs.VERSION }}.exe
          draft: false
          prerelease: false
```

- [ ] **Step 3: コミット**

```bash
git add .github/workflows/release.yml
git commit -m "feat: GitHub Actions自動ビルド・リリースワークフローを追加"
```

---

## Task 9: 動作確認と初回リリース

- [ ] **Step 1: 全テストを実行してパスを確認**

```bash
pytest -v
```

Expected: 全テスト PASS（test_updater.py の 6 件を含む）

- [ ] **Step 2: GitHub に push**

```bash
git push origin master
```

- [ ] **Step 3: 初回リリースタグを付けて push**

```bash
git tag v1.0.0
git push origin v1.0.0
```

Expected: GitHub Actions が起動し、数分後に https://github.com/mozu93/cci-billing/releases に `CCIBilling_Setup_1.0.0.exe` が公開される

- [ ] **Step 4: GitHub Actions の結果を確認**

https://github.com/mozu93/cci-billing/actions を開き、ワークフローが緑（成功）になっていることを確認する。

---

## リリース手順（次回以降）

```bash
# 1. app/version.py の __version__ を更新してコミット
# 例: "1.0.0" → "1.0.1"

# 2. タグを付けて push
git tag v1.0.1
git push origin v1.0.1
# → GitHub Actions が自動でビルド・インストーラー作成・リリース公開
```
