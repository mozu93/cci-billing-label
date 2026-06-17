# GitHub Release 配布 ＆ アプリ内自動アップデート設計

**日付:** 2026-06-14  
**リポジトリ:** mozu93/cci-billing  
**アプリ名:** CCI請求書システム

---

## 概要

cci-billing を GitHub Releases で配布し、アプリ起動時に新バージョンを自動検出してインストーラー経由で更新できる仕組みを追加する。参照実装として label_ippatsusaku の同機能を踏襲する。

---

## 追加・変更ファイル一覧

| ファイル | 種別 | 内容 |
|---|---|---|
| `app/version.py` | 新規 | バージョン番号の単一管理源（初期値 `1.0.0`） |
| `app/utils/updater.py` | 新規 | GitHub API チェック・ダウンロード・インストーラー起動 |
| `app/ui/update_banner.py` | 新規 | アップデートバナーウィジェット |
| `app/ui/main_window.py` | 変更 | バナー・ステータスバー・ヘルプメニューを追加 |
| `assets/app_icon.ico` | 新規 | プレースホルダーアイコン（Pythonで生成） |
| `cci_billing.spec` | 新規 | PyInstaller ビルド定義 |
| `installer/setup.iss` | 新規 | Inno Setup インストーラー定義 |
| `.github/workflows/release.yml` | 新規 | タグ push で自動ビルド＆リリース |
| `requirements.txt` | 変更 | `packaging` を追加 |

---

## アーキテクチャ

### バージョン管理

- `app/version.py` に `__version__ = "1.0.0"` のみを持つ
- PyInstaller spec・Inno Setup・GitHub Actions の全員がここから取得

### アップデートチェック

- GitHub API エンドポイント: `https://api.github.com/repos/mozu93/cci-billing/releases/latest`
- 起動時にバックグラウンドスレッド（`QThread`）で非同期チェック（タイムアウト 8 秒）
- `packaging.version.Version` で semver 比較

### バナー UI（`UpdateBanner`）

状態遷移：  
`非表示` → （新バージョン検出）→ `バナー表示 + ダウンロードボタン` → `プログレスバー` → `今すぐ更新ボタン`

- 背景色: `#FEF9C3`（黄色）、ボーダー: `#FDE047`
- 高さ固定 40px、メインウィンドウ上部に配置

### メインウィンドウ変更

現在の構造:
```
QMainWindow
  └─ QTabWidget（centralWidget）
```

変更後:
```
QMainWindow
  └─ QWidget（centralWidget）
       └─ QVBoxLayout
            ├─ UpdateBanner（新規、非表示スタート）
            └─ QTabWidget（既存）
```

- ステータスバーに右端バージョン表示を追加
- ヘルプメニュー追加（「バージョン情報」ダイアログ）

---

## ビルド・リリースフロー

### PyInstaller（`cci_billing.spec`）

- `one-dir` 形式（`--onefile` ではなく `COLLECT`）
- `assets/` フォルダを同梱
- `console=False`（ウィンドウアプリ）
- 出力 exe 名: `CCIBilling`

### Inno Setup（`installer/setup.iss`）

- インストール先: `{localappdata}\CCIBilling`（管理者権限不要）
- スタートメニュー・デスクトップショートカット作成
- 出力ファイル: `installer_output/CCIBilling_Setup_{VERSION}.exe`
- アンインストーラー付き

### GitHub Actions（`.github/workflows/release.yml`）

トリガー: `v*.*.*` タグの push

1. `actions/checkout@v4`
2. Python 3.11 セットアップ
3. `pip install -r requirements.txt`
4. `app/version.py` からバージョン取得
5. PyInstaller でビルド
6. Inno Setup インストーラー作成
7. `softprops/action-gh-release@v2` でリリース公開

---

## リリース手順（開発者）

```bash
# 1. バージョン番号を更新
# app/version.py の __version__ = "1.0.1" に編集してコミット

# 2. タグを付けてプッシュ
git tag v1.0.1
git push origin v1.0.1
# → GitHub Actions が自動でビルド・リリース
```

---

## ユーザー側のアップデート操作

1. アプリ起動 → バックグラウンドで GitHub API チェック
2. 新バージョンあり → 黄色バナー表示「新しいバージョン vX.X.X が利用可能です」
3. 「ダウンロード」ボタンクリック → プログレスバー表示・%TEMP% に保存
4. 完了 → 「今すぐ更新して再起動」ボタン
5. クリック → `updater.bat` 経由でインストーラー起動、アプリ終了
6. インストーラーが旧バージョンを上書きインストール

---

## エラーハンドリング

- バージョンチェック失敗（ネットワーク不通等）: バナー非表示のまま（サイレント失敗）
- ダウンロード失敗: バナーに「ダウンロードに失敗しました。後で再試行してください。」を表示、「ダウンロード」ボタン再表示
- 開発環境（frozen でない場合）: 「今すぐ更新」クリック時にダウンロード先パスをダイアログ表示（インストール実行しない）

---

## 依存追加

```
packaging>=23.0
```

（`is_newer_version` の semver 比較に使用）
