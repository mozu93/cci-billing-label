# app/database/connection.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.utils.app_config import get_db_url

_SessionFactory = None


def get_engine(url: str | None = None):
    target = url or get_db_url()
    if target.startswith("postgresql"):
        from urllib.parse import urlparse, unquote
        p = urlparse(target)
        host = p.hostname or "localhost"
        port = p.port or 5432
        dbname = p.path.lstrip("/")
        user = unquote(p.username or "")
        password = unquote(p.password or "")

        def _pg_connect():
            import pg8000.dbapi as pg
            _PG_ERRORS = {
                "28P01": "パスワード認証に失敗しました。ユーザー名・パスワードを確認してください。",
                "28000": f"ユーザー '{user}' のアクセスが拒否されました。",
                "3D000": f"データベース '{dbname}' が存在しません。",
                "08001": f"サーバー {host}:{port} に接続できません。",
                "08006": f"サーバー {host}:{port} との接続が切断されました。",
                "42501": "権限がありません。",
            }
            try:
                return pg.connect(
                    host=host, port=port, database=dbname,
                    user=user, password=password,
                )
            except pg.DatabaseError as e:
                code = e.args[0].get("C", "") if e.args and isinstance(e.args[0], dict) else ""
                msg = _PG_ERRORS.get(code, f"PostgreSQL 接続エラー (コード: {code})")
                raise Exception(msg) from None
            except Exception as e:
                raise Exception(f"接続エラー: {e}") from None

        return create_engine("postgresql+pg8000://", creator=_pg_connect)
    return create_engine(target, echo=False)


def _table_columns(conn, dialect: str, table: str) -> set[str]:
    if dialect == "sqlite":
        return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
    ), {"t": table})
    return {row[0] for row in rows}


def _migrate(engine):
    """既存DBに不足カラムを追加するマイグレーション（SQLite / PostgreSQL 両対応）"""
    dialect = engine.dialect.name
    if dialect not in ("sqlite", "postgresql"):
        return
    blob_type = "BLOB" if dialect == "sqlite" else "BYTEA"

    with engine.connect() as conn:
        staff_cols = _table_columns(conn, dialect, "staff")
        if "is_admin" not in staff_cols:
            conn.execute(text("ALTER TABLE staff ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
            conn.commit()
        if "password_hash" not in staff_cols:
            conn.execute(text("ALTER TABLE staff ADD COLUMN password_hash VARCHAR(200)"))
            conn.commit()
        if "supervisor_name" not in staff_cols:
            conn.execute(text("ALTER TABLE staff ADD COLUMN supervisor_name VARCHAR(100) DEFAULT ''"))
            conn.commit()
        if "supervisor_email" not in staff_cols:
            conn.execute(text("ALTER TABLE staff ADD COLUMN supervisor_email VARCHAR(200) DEFAULT ''"))
            conn.commit()
        if "supervisor_id" not in staff_cols:
            conn.execute(text(
                "ALTER TABLE staff ADD COLUMN supervisor_id INTEGER REFERENCES staff(id)"))
            conn.commit()
        if "is_department_head" not in staff_cols:
            conn.execute(text("ALTER TABLE staff ADD COLUMN is_department_head BOOLEAN DEFAULT FALSE"))
            conn.commit()
        if "email" not in staff_cols:
            conn.execute(text("ALTER TABLE staff ADD COLUMN email VARCHAR(200)"))
            conn.commit()
        cols = _table_columns(conn, dialect, "company_settings")
        if "print_seal" not in cols:
            conn.execute(text(
                "ALTER TABLE company_settings ADD COLUMN print_seal BOOLEAN DEFAULT TRUE"))
            conn.commit()

        mem_cols = _table_columns(conn, dialect, "members")
        if "department" not in mem_cols:
            conn.execute(text(
                "ALTER TABLE members ADD COLUMN department VARCHAR(100) DEFAULT ''"))
            conn.commit()

        pm_cols = _table_columns(conn, dialect, "project_members")
        if "department" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN department VARCHAR(100) DEFAULT ''"))
            conn.commit()
        if "created_at" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN created_at TIMESTAMP"))
            conn.commit()
        if "member_number" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN member_number VARCHAR(50) DEFAULT ''"))
            conn.commit()
        if "roster_no" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN roster_no VARCHAR(50) DEFAULT ''"))
            conn.commit()
        if "address2" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN address2 VARCHAR(300) DEFAULT ''"))
            conn.commit()

        pt_cols = _table_columns(conn, dialect, "project_templates")
        if "default_quantity" not in pt_cols:
            conn.execute(text(
                "ALTER TABLE project_templates ADD COLUMN default_quantity INTEGER DEFAULT 1"))
            conn.commit()
        if "tax_rate_override" not in pt_cols:
            conn.execute(text(
                "ALTER TABLE project_templates ADD COLUMN tax_rate_override INTEGER"))
            conn.commit()

        iss_cols = _table_columns(conn, dialect, "issuances")
        for col, ddl in [
            ("roster_no",            "VARCHAR(50) DEFAULT ''"),
            ("member_number",        "VARCHAR(50) DEFAULT ''"),
            ("recipient_kana",       "VARCHAR(200) DEFAULT ''"),
            ("recipient_department", "VARCHAR(100) DEFAULT ''"),
            ("recipient_name_kana",  "VARCHAR(100) DEFAULT ''"),
            ("recipient_phone",      "VARCHAR(50) DEFAULT ''"),
            ("company_settings_id",   "INTEGER REFERENCES company_settings(id)"),
            ("bank_account_id",       "INTEGER REFERENCES bank_accounts(id)"),
            ("seal_image_id",          "INTEGER REFERENCES seal_images(id)"),
            ("show_recipient_person", "BOOLEAN DEFAULT TRUE"),
        ]:
            if col not in iss_cols:
                conn.execute(text(f"ALTER TABLE issuances ADD COLUMN {col} {ddl}"))
                conn.commit()

        cs_cols = _table_columns(conn, dialect, "company_settings")
        if "is_default" not in cs_cols:
            conn.execute(text(
                "ALTER TABLE company_settings ADD COLUMN is_default BOOLEAN DEFAULT FALSE"))
            # 既存の最初のレコードをデフォルトに設定
            conn.execute(text(
                "UPDATE company_settings SET is_default = TRUE "
                "WHERE id = (SELECT MIN(id) FROM company_settings)"))
            conn.commit()

        bank_cols = _table_columns(conn, dialect, "bank_accounts")
        if "bank_account_name_kana" not in bank_cols:
            conn.execute(text(
                "ALTER TABLE bank_accounts "
                "ADD COLUMN bank_account_name_kana VARCHAR(200) DEFAULT ''"))
            conn.commit()

        proj_cols = _table_columns(conn, dialect, "projects")
        for col, ddl in [
            ("company_settings_id", "INTEGER REFERENCES company_settings(id)"),
            ("bank_account_id",     "INTEGER REFERENCES bank_accounts(id)"),
            ("seal_image_id",       "INTEGER REFERENCES seal_images(id)"),
        ]:
            if col not in proj_cols:
                conn.execute(text(f"ALTER TABLE projects ADD COLUMN {col} {ddl}"))
                conn.commit()

        sup_cols = _table_columns(conn, dialect, "supervisors")
        if "staff_id" not in sup_cols:
            conn.execute(text("ALTER TABLE supervisors ADD COLUMN staff_id INTEGER"))
            conn.commit()

        # supervisor_id が staff テーブルに存在しない値（旧 supervisors.id 参照）をリセット
        conn.execute(text(
            "UPDATE staff SET supervisor_id = NULL "
            "WHERE supervisor_id IS NOT NULL "
            "AND supervisor_id NOT IN (SELECT id FROM staff)"
        ))
        conn.commit()

        si_cols = _table_columns(conn, dialect, "seal_images")
        if "image_data" not in si_cols:
            conn.execute(text(f"ALTER TABLE seal_images ADD COLUMN image_data {blob_type}"))
            conn.commit()


def init_db(url: str | None = None):
    global _SessionFactory
    from app.database.models import Base
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    _migrate(engine)
    _SessionFactory = sessionmaker(bind=engine)


def get_session() -> Session:
    if _SessionFactory is None:
        init_db()
    return _SessionFactory()
