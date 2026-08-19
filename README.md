# CCI請求書・ラベル発行システム

商工会議所向けの請求書・領収書・宛名ラベル発行アプリです。

## 主な機能

- 請求書・領収書の単発発行
- 名簿を使ったまとめて発行
- Excel・貼り付けによる名簿取り込み
- 事業所ごとの個別PDF、一括PDFの出力
- PDFファイル名のカスタマイズ
- 税率別内訳と税込合計を備えた請求書PDF
- 宛名ラベル発行
- 入金管理、修正・再発行
- Microsoft 365によるメール送信・代理送信・テスト送信
- Microsoft 365の配信状況（配信済み・確認待ち・配信失敗）の確認
- 複数のメールテンプレートと差し込みタグ
- SQLite／PostgreSQL対応
- 社内利用向けのログイン不要起動
- Windows 11 デザインガイドラインに準拠した左メニュー（ウィンドウ幅に応じて自動で折りたたみ）

## 最新バージョン

v2.4.2

変更内容は [RELEASE_NOTES.md](RELEASE_NOTES.md) を参照してください。

## インストール

[GitHub Releases](https://github.com/mozu93/cci-billing-label-releases/releases) から
`CCIBillingLabel_Setup_2.4.2.exe` をダウンロードして実行してください。
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
