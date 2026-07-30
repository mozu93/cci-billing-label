# CCI請求書・ラベル発行システム

商工会議所向けの請求書・領収書・宛名ラベル発行アプリです。

## 主な機能

- 請求書・領収書の単発発行
- 名簿を使ったまとめて発行
- Excel・貼り付けによる名簿取り込み
- 事業所ごとの個別PDF、一括PDFの出力
- PDFファイル名のカスタマイズ
- 宛名ラベル発行
- 入金管理、修正・再発行
- Microsoft 365によるメール送信
- SQLite／PostgreSQL対応

## 最新バージョン

v2.2.0

変更内容は [RELEASE_NOTES.md](RELEASE_NOTES.md) を参照してください。

## インストール

[GitHub Releases](https://github.com/mozu93/cci-billing-label/releases) から
`CCIBillingLabel_Setup_2.2.0.exe` をダウンロードして実行してください。
管理者権限は不要です。

## 開発環境での起動

```powershell
pip install -r requirements.txt
python main.py
```

## テスト

```powershell
pip install -r requirements-dev.txt
pytest -q
```

## マニュアル

[docs/manual/manual.html](docs/manual/manual.html) をブラウザで開いてください。
