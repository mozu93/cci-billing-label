# tests/test_pdf_helpers.py
from app.database.models import CompanySettings, BankAccount, SealImage, Project


def test_get_issuer_for_project_uses_project_company(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project

    cs_default = CompanySettings(name="デフォルト会社", is_default=True)
    cs_other   = CompanySettings(name="別会社",         is_default=False)
    db_session.add_all([cs_default, cs_other])
    db_session.commit()

    bank = BankAccount(company_id=cs_other.id, label="口座A",
                       bank_name="○○銀行", is_default=True)
    db_session.add(bank)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="list",
                   company_settings_id=cs_other.id, bank_account_id=bank.id)
    db_session.add(proj)
    db_session.commit()

    company, ba, seal = get_issuer_for_project(db_session, proj)
    assert company.id == cs_other.id
    assert ba.id == bank.id
    assert seal is None


def test_get_issuer_for_project_falls_back_to_default(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project

    cs = CompanySettings(name="デフォルト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    bank = BankAccount(company_id=cs.id, label="口座A",
                       bank_name="○○銀行", is_default=True)
    db_session.add(bank)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="list")
    db_session.add(proj)
    db_session.commit()

    company, ba, seal = get_issuer_for_project(db_session, proj)
    assert company.id == cs.id
    assert ba.id == bank.id


def test_get_issuer_for_project_respects_print_seal_false(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project

    cs = CompanySettings(name="会社", is_default=True, print_seal=False)
    db_session.add(cs)
    db_session.commit()

    seal_img = SealImage(company_id=cs.id, label="印鑑", path="/tmp/seal.png",
                         is_default=True)
    db_session.add(seal_img)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="list",
                   seal_image_id=seal_img.id)
    db_session.add(proj)
    db_session.commit()

    _, _, seal = get_issuer_for_project(db_session, proj)
    assert seal is None  # print_seal=False なので常に None


def test_get_issuer_for_project_project_none_falls_back(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project

    cs = CompanySettings(name="会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    company, _, _ = get_issuer_for_project(db_session, None)
    assert company.id == cs.id


def test_get_issuer_for_project_uses_project_seal(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project

    cs = CompanySettings(name="会社", is_default=True, print_seal=True)
    db_session.add(cs)
    db_session.commit()

    seal_default = SealImage(company_id=cs.id, label="デフォルト印鑑",
                             path="/tmp/default.png", is_default=True)
    seal_project = SealImage(company_id=cs.id, label="プロジェクト印鑑",
                             path="/tmp/project.png", is_default=False)
    db_session.add_all([seal_default, seal_project])
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="list",
                   seal_image_id=seal_project.id)
    db_session.add(proj)
    db_session.commit()

    _, _, seal = get_issuer_for_project(db_session, proj)
    assert seal.id == seal_project.id  # プロジェクト固有の印鑑が使われること


def test_generate_and_open_uses_save_path(db_session, tmp_path, monkeypatch):
    """save_path を指定した場合、そのパスに PDF が生成されること"""
    from app.utils.pdf_helpers import generate_and_open
    from app.database.models import Issuance

    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="list")
    db_session.add(proj)
    db_session.commit()

    saved_to = []

    def fake_generate_receipt(issuance, company, path, **kwargs):
        with open(path, "wb") as f:
            f.write(b"%PDF")
        saved_to.append(path)

    monkeypatch.setattr(
        "app.services.pdf.receipt_pdf.generate_receipt_pdf",
        fake_generate_receipt,
    )

    iss = Issuance(
        doc_number="R2026-001", doc_type="receipt",
        recipient_organization="テスト", status="発行済み",
        project_id=proj.id, amount=1000,
    )
    db_session.add(iss)
    db_session.commit()

    custom_path = str(tmp_path / "my_receipt.pdf")
    result = generate_and_open(iss, db_session, open_file=False, save_path=custom_path)

    assert result == custom_path
    assert saved_to == [custom_path]


def test_generate_and_open_default_path_when_save_path_none(db_session, tmp_path, monkeypatch):
    """save_path=None の場合、従来の output_dir に保存されること"""
    from app.utils.pdf_helpers import generate_and_open
    from app.database.models import Issuance

    cs = CompanySettings(name="テスト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="list")
    db_session.add(proj)
    db_session.commit()

    saved_to = []

    def fake_generate_receipt(issuance, company, path, **kwargs):
        with open(path, "wb") as f:
            f.write(b"%PDF")
        saved_to.append(path)

    monkeypatch.setattr(
        "app.services.pdf.receipt_pdf.generate_receipt_pdf",
        fake_generate_receipt,
    )
    monkeypatch.setattr(
        "app.utils.pdf_helpers.get_pdf_output_dir",
        lambda: str(tmp_path),
    )

    iss = Issuance(
        doc_number="R2026-002", doc_type="receipt",
        recipient_organization="テスト", status="発行済み",
        project_id=proj.id, amount=500,
    )
    db_session.add(iss)
    db_session.commit()

    result = generate_and_open(iss, db_session, open_file=False, save_path=None)

    assert result is not None
    assert "R2026-002" in result
    assert result.startswith(str(tmp_path))


def test_merge_and_open_accepts_output_dir(tmp_path):
    """output_dir 引数を指定できること（空リスト→ None の早期リターンで検証）"""
    from app.utils.pdf_helpers import merge_and_open
    # 空リスト → 早期リターン（None を返す）
    assert merge_and_open([], "テスト", output_dir=str(tmp_path)) is None


def test_get_issuer_for_project_issuance_overrides_project(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project
    from app.database.models import Issuance

    cs_proj = CompanySettings(name="プロジェクト発行元", is_default=True)
    cs_iss  = CompanySettings(name="発行ごとの発行元",   is_default=False)
    db_session.add_all([cs_proj, cs_iss])
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="counter",
                   company_settings_id=cs_proj.id)
    db_session.add(proj)
    db_session.commit()

    iss = Issuance(doc_number="INV-001", doc_type="invoice",
                   recipient_organization="テスト", status="発行済み",
                   project_id=proj.id, amount=1000,
                   company_settings_id=cs_iss.id)
    db_session.add(iss)
    db_session.commit()

    company, _, _ = get_issuer_for_project(db_session, proj, issuance=iss)
    assert company.id == cs_iss.id


def test_get_issuer_for_project_issuance_dangling_reference_falls_back(db_session):
    from app.utils.pdf_helpers import get_issuer_for_project
    from app.database.models import Issuance

    cs = CompanySettings(name="デフォルト会社", is_default=True)
    db_session.add(cs)
    db_session.commit()

    proj = Project(name="PJ", fiscal_year=2026, project_type="counter")
    db_session.add(proj)
    db_session.commit()

    iss = Issuance(doc_number="INV-002", doc_type="invoice",
                   recipient_organization="テスト", status="発行済み",
                   project_id=proj.id, amount=1000,
                   company_settings_id=99999)  # 存在しないID
    db_session.add(iss)
    db_session.commit()

    company, _, _ = get_issuer_for_project(db_session, proj, issuance=iss)
    assert company.id == cs.id  # フォールバックでデフォルト発行元
