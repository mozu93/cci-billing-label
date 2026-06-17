# まとめて発行フロー簡略化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。各タスクをTDDで実装し、タスクごとにテスト緑を保つ。

**Goal:** まとめて発行の手数を減らす（受付開始廃止・発行1ボタン化・一括を発行タブへ移動＋書類種別選択・ステータス2状態化）。

**Architecture:** 事業管理＝準備専用、事業から発行＝発行集約。Project.status は active/closed の2値。発行ロジック・DB宛名構造は不変。

**Tech Stack:** Python / PyQt6 / SQLAlchemy / pytest+pytest-qt。ブランチ `feature/batch-simplification`。テスト `python -m pytest`。コミット末尾に `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。

**順序性:** Task1 はサービス層（activate/archive は互換のため残す）。Task3 で project_tab/dashboard が activate/archive 参照を撤去した後、Task4 でサービスから削除する。各タスクでテスト緑。

---

## Task 1: サービス層（status既定 active・batch_pdf 書類種別）

**Files:** `app/services/project_service.py`, `app/services/fiscal_year_service.py`, `app/services/pdf/batch_pdf.py`, tests

- `create_project` を `status="active"` で作成。
- `reopen_project(session, project_id)`（→"active"）を追加。`close_project`（→"closed"）は既存維持。`activate_project`/`archive_project` は**この時点では残す**（UIがまだ参照）。
- `fiscal_year_service.rollover_fiscal_year`：複製事業を `status="active"` で作成。
- `batch_pdf.generate_batch_pdf(session, project_id, company, output_dir, bank_account=None, doc_type="invoice")`：引数 `doc_type` を追加し暗黙判定を廃止。各名簿行で未採番なら採番→PDF生成→`status="発行済み"`・`issued_at` 設定。宛名空はスキップ。
- テスト：create_project が active、reopen_project、batch が doc_type 指定で受領書/請求書を生成し発行済みになること。

## Task 2: 事業から発行（書類種別・発行1ボタン・全員まとめて発行）

**Files:** `app/ui/issuance_from_project.py`, tests（構造/挙動の軽いUIテスト）

- 書類種別コンボ（請求書／領収書）を追加。既定は事業テンプレートから推定。
- 「準備（採番）」「発行する」を廃し **「発行」1ボタン**：選択行が未採番なら `create_issuance_for_member(..., doc_type=選択)` で採番→`mark_as_issued`→PDF生成して開く。発行済みなら再発行（PDFを開く）。
- **「全員まとめて発行」** ボタン：選択中の書類種別で `generate_batch_pdf(..., doc_type=...)` を実行し件数と保存先を通知→一覧再読込。
- テスト：ウィジェットに「発行」「全員まとめて発行」ボタンと書類種別コンボが存在すること。

## Task 3: 事業管理＋ダッシュボード（不要操作の撤去）

**Files:** `app/ui/project_tab.py`, `app/ui/dashboard.py`, tests

- `project_tab`：`受付開始`・`アーカイブ`・`一括PDF生成` ボタンと該当ハンドラ（`_activate`/`_archive`/`_batch_pdf`）を削除。`完了`（close_project）と `完了を戻す`（reopen_project）を追加。状態フィルタを `["受付中","完了","すべて"]`（active/closed/None、既定=受付中）に。activate_project/archive_project の import を除去。
- `dashboard`：`draft` セクション（"準備中の事業（draft）" 一覧・受付開始ボタン・`get_projects(status="draft")`）を削除。active 進捗のみ表示。
- テスト：project_tab に「受付開始」「一括PDF生成」ボタンが無く「完了」がある。dashboard が draft を参照しない。

## Task 4: サービスのクリーンアップ

**Files:** `app/services/project_service.py`, tests

- 参照が無くなった `activate_project`・`archive_project` を削除（`grep -rn "activate_project\|archive_project" app/ tests/` で確認）。
- `python -m pytest` 全緑。

---

## 受け入れ基準（再掲）
新規事業が即発行可能／書類種別選択可／発行1ボタン／全員まとめて発行が発行タブにあり発行済みになる／事業管理に一括PDF・受付開始・アーカイブ無し／status は active・closed の2値・既定受付中表示／dashboard に draft 無し／テスト緑。
