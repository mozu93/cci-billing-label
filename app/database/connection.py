# app/database/connection.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.utils.app_config import get_db_url

_SessionFactory = None


def get_engine(url: str | None = None):
    return create_engine(url or get_db_url(), echo=False)


def _migrate(engine):
    """既存DBに不足カラムを追加するマイグレーション"""
    with engine.connect() as conn:
        staff_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(staff)"))}
        if "is_admin" not in staff_cols:
            conn.execute(text("ALTER TABLE staff ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
            conn.commit()
        if "password_hash" not in staff_cols:
            conn.execute(text("ALTER TABLE staff ADD COLUMN password_hash VARCHAR(200)"))
            conn.commit()
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(company_settings)"))}
        if "print_seal" not in cols:
            conn.execute(text(
                "ALTER TABLE company_settings ADD COLUMN print_seal BOOLEAN DEFAULT 1"))
            conn.commit()

        mem_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(members)"))}
        if "department" not in mem_cols:
            conn.execute(text(
                "ALTER TABLE members ADD COLUMN department VARCHAR(100) DEFAULT ''"))
            conn.commit()

        pm_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(project_members)"))}
        if "department" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN department VARCHAR(100) DEFAULT ''"))
            conn.commit()
        if "created_at" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN created_at DATETIME"))
            conn.commit()
        if "member_number" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN member_number VARCHAR(50) DEFAULT ''"))
            conn.commit()
        if "address2" not in pm_cols:
            conn.execute(text(
                "ALTER TABLE project_members ADD COLUMN address2 VARCHAR(300) DEFAULT ''"))
            conn.commit()

        pt_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(project_templates)"))}
        if "default_quantity" not in pt_cols:
            conn.execute(text(
                "ALTER TABLE project_templates ADD COLUMN default_quantity INTEGER DEFAULT 1"))
            conn.commit()

        iss_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(issuances)"))}
        for col, ddl in [
            ("member_number",        "VARCHAR(50) DEFAULT ''"),
            ("recipient_kana",       "VARCHAR(200) DEFAULT ''"),
            ("recipient_department", "VARCHAR(100) DEFAULT ''"),
            ("recipient_name_kana",  "VARCHAR(100) DEFAULT ''"),
            ("recipient_phone",      "VARCHAR(50) DEFAULT ''"),
            ("company_settings_id",   "INTEGER REFERENCES company_settings(id)"),
            ("bank_account_id",       "INTEGER REFERENCES bank_accounts(id)"),
            ("seal_image_id",          "INTEGER REFERENCES seal_images(id)"),
            ("show_recipient_person", "BOOLEAN DEFAULT 1"),
        ]:
            if col not in iss_cols:
                conn.execute(text(f"ALTER TABLE issuances ADD COLUMN {col} {ddl}"))
                conn.commit()

        cs_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(company_settings)"))}
        if "is_default" not in cs_cols:
            conn.execute(text(
                "ALTER TABLE company_settings ADD COLUMN is_default BOOLEAN DEFAULT 0"))
            # 既存の最初のレコードをデフォルトに設定
            conn.execute(text(
                "UPDATE company_settings SET is_default = 1 "
                "WHERE id = (SELECT MIN(id) FROM company_settings)"))
            conn.commit()

        proj_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(projects)"))}
        for col, ddl in [
            ("company_settings_id", "INTEGER REFERENCES company_settings(id)"),
            ("bank_account_id",     "INTEGER REFERENCES bank_accounts(id)"),
            ("seal_image_id",       "INTEGER REFERENCES seal_images(id)"),
        ]:
            if col not in proj_cols:
                conn.execute(text(f"ALTER TABLE projects ADD COLUMN {col} {ddl}"))
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
