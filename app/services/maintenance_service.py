# app/services/maintenance_service.py
"""業務データの一括削除。設定画面の3つの削除機能が使う。

テーブル名と削除順序は settings_tab から移したものをそのまま使っている。
順序は外部キー制約に依存するので、並べ替えないこと。
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

# 発行書類まわり。発行番号の採番表（document_sequences）も消して振り直す。
_DOCUMENT_TABLES = [
    "payments", "issuance_lines", "issuances",
    "document_sequences",
]

# 上記に加えて、名簿・会員・操作ログ。業務名とテンプレートは残す。
_BUSINESS_TABLES = _DOCUMENT_TABLES + [
    "project_members", "project_templates", "projects",
    "members", "operation_logs",
]

# 上記に加えて、テンプレート・業務名・スタッフ。発行元情報だけ残る。
_ALL_EXCEPT_ISSUERS = _BUSINESS_TABLES + [
    "item_templates", "categories", "staff",
]


def _delete_tables(session: Session, tables: list[str]) -> None:
    for table in tables:
        session.execute(text(f"DELETE FROM {table}"))
    session.commit()


def reset_document_numbers(session: Session) -> None:
    """発行書類と入金記録を消し、発行番号を振り直せる状態にする。"""
    _delete_tables(session, _DOCUMENT_TABLES)


def initialize_business_data(session: Session) -> None:
    """案件・発行書類・入金記録・会員マスタ・操作ログを消す。"""
    _delete_tables(session, _BUSINESS_TABLES)


def delete_all_except_issuers(session: Session) -> None:
    """発行元情報以外のデータをすべて消す。"""
    _delete_tables(session, _ALL_EXCEPT_ISSUERS)
