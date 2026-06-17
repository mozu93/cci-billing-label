# tests/test_models.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.database.models import Base


def test_create_all_tables():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    tables = {row[0] for row in result}
    assert "staff" in tables
    assert "categories" in tables
    assert "item_templates" in tables
    assert "company_settings" in tables
    assert "projects" in tables
    assert "issuances" in tables
    session.close()


def test_company_settings_has_is_default(db_session):
    from app.database.models import CompanySettings
    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()
    db_session.refresh(cs)
    assert cs.is_default is True


def test_project_has_issuer_fks(db_session):
    from app.database.models import CompanySettings, BankAccount, Project
    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    bank = BankAccount(company_id=cs.id, label="メイン", bank_name="テスト銀行",
                       is_default=True)
    db_session.add(bank)
    db_session.commit()

    proj = Project(name="テストPJ", fiscal_year=2026, project_type="list",
                   company_settings_id=cs.id, bank_account_id=bank.id)
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    assert proj.company_settings_id == cs.id
    assert proj.bank_account_id == bank.id
    assert proj.seal_image_id is None
    assert proj.issuer.name == "テスト会社"
    assert proj.bank_account.bank_name == "テスト銀行"
