# -*- coding: utf-8 -*-
"""発行元・銀行口座・印影の業務ルールを確認する。

UI から切り出したルールが、切り出し後も同じ挙動であることを保証する。
"""
import pytest

from app.database.models import CompanySettings, SealImage
from app.services import company_service as cs_svc


def _make_issuer(session, name: str, **kw) -> CompanySettings:
    cs = CompanySettings(name=name, **kw)
    session.add(cs)
    session.commit()
    return cs


# ── 発行元 ─────────────────────────────────────────────────────

def test_list_issuers_is_ordered_by_id(db_session):
    _make_issuer(db_session, "あ商工会議所")
    _make_issuer(db_session, "い商工会議所")
    assert [c.name for c in cs_svc.list_issuers(db_session)] == [
        "あ商工会議所", "い商工会議所"]


def test_save_issuer_creates_and_returns_id(db_session):
    new_id = cs_svc.save_issuer(db_session, None, name="新規", address="住所")
    assert new_id is not None
    assert cs_svc.get_issuer(db_session, new_id).name == "新規"


def test_save_issuer_updates_existing(db_session):
    cs = _make_issuer(db_session, "旧名")
    returned = cs_svc.save_issuer(db_session, cs.id, name="新名")
    assert returned == cs.id
    assert cs_svc.get_issuer(db_session, cs.id).name == "新名"


def test_save_issuer_rejects_missing_id(db_session):
    with pytest.raises(ValueError):
        cs_svc.save_issuer(db_session, 999, name="ない")


def test_set_default_issuer_is_exclusive(db_session):
    a = _make_issuer(db_session, "A", is_default=True)
    b = _make_issuer(db_session, "B")
    cs_svc.set_default_issuer(db_session, b.id)
    assert cs_svc.get_issuer(db_session, a.id).is_default is False
    assert cs_svc.get_issuer(db_session, b.id).is_default is True


def test_only_issuer_is_promoted_to_default(db_session):
    a = _make_issuer(db_session, "A")
    assert cs_svc.promote_only_issuer_to_default(db_session, a.id) is True
    assert cs_svc.get_issuer(db_session, a.id).is_default is True


def test_second_issuer_is_not_promoted(db_session):
    _make_issuer(db_session, "A", is_default=True)
    b = _make_issuer(db_session, "B")
    assert cs_svc.promote_only_issuer_to_default(db_session, b.id) is False
    assert cs_svc.get_issuer(db_session, b.id).is_default in (False, None)


def test_last_issuer_cannot_be_deleted(db_session):
    a = _make_issuer(db_session, "唯一")
    ok, reason = cs_svc.check_issuer_deletable(db_session, a.id)
    assert ok is False
    assert "1件しかない" in reason


def test_default_issuer_cannot_be_deleted(db_session):
    a = _make_issuer(db_session, "A", is_default=True)
    _make_issuer(db_session, "B")
    ok, reason = cs_svc.check_issuer_deletable(db_session, a.id)
    assert ok is False
    assert "デフォルト発行元" in reason


def test_non_default_issuer_can_be_deleted(db_session):
    _make_issuer(db_session, "A", is_default=True)
    b = _make_issuer(db_session, "B")
    ok, reason = cs_svc.check_issuer_deletable(db_session, b.id)
    assert ok is True and reason == ""
    cs_svc.delete_issuer(db_session, b.id)
    assert cs_svc.get_issuer(db_session, b.id) is None


def test_set_print_seal(db_session):
    a = _make_issuer(db_session, "A")
    cs_svc.set_print_seal(db_session, a.id, False)
    assert cs_svc.get_issuer(db_session, a.id).print_seal is False


# ── 銀行口座 ───────────────────────────────────────────────────

def test_first_bank_account_becomes_default(db_session):
    a = _make_issuer(db_session, "A")
    bank_id = cs_svc.save_bank_account(db_session, a.id, None, label="メイン")
    assert cs_svc.get_bank_account(db_session, bank_id).is_default is True


def test_second_bank_account_is_not_default(db_session):
    a = _make_issuer(db_session, "A")
    cs_svc.save_bank_account(db_session, a.id, None, label="1つ目")
    second = cs_svc.save_bank_account(db_session, a.id, None, label="2つ目")
    assert cs_svc.get_bank_account(db_session, second).is_default is False


def test_first_bank_is_per_company(db_session):
    a = _make_issuer(db_session, "A")
    b = _make_issuer(db_session, "B")
    cs_svc.save_bank_account(db_session, a.id, None, label="A口座")
    b_bank = cs_svc.save_bank_account(db_session, b.id, None, label="B口座")
    # 別の発行元なので、こちらも「最初の1件」としてデフォルトになる。
    assert cs_svc.get_bank_account(db_session, b_bank).is_default is True


def test_save_bank_account_updates_existing(db_session):
    a = _make_issuer(db_session, "A")
    bank_id = cs_svc.save_bank_account(db_session, a.id, None, label="旧")
    cs_svc.save_bank_account(db_session, a.id, bank_id, label="新")
    assert cs_svc.get_bank_account(db_session, bank_id).label == "新"
    assert cs_svc.list_bank_accounts(db_session, a.id) != []


def test_set_default_bank_is_exclusive_within_company(db_session):
    a = _make_issuer(db_session, "A")
    first = cs_svc.save_bank_account(db_session, a.id, None, label="1")
    second = cs_svc.save_bank_account(db_session, a.id, None, label="2")
    cs_svc.set_default_bank_account(db_session, a.id, second)
    assert cs_svc.get_bank_account(db_session, first).is_default is False
    assert cs_svc.get_bank_account(db_session, second).is_default is True


def test_set_default_bank_does_not_touch_other_company(db_session):
    a = _make_issuer(db_session, "A")
    b = _make_issuer(db_session, "B")
    a_bank = cs_svc.save_bank_account(db_session, a.id, None, label="A")
    b_bank = cs_svc.save_bank_account(db_session, b.id, None, label="B")
    cs_svc.set_default_bank_account(db_session, a.id, a_bank)
    assert cs_svc.get_bank_account(db_session, b_bank).is_default is True


def test_delete_bank_account(db_session):
    a = _make_issuer(db_session, "A")
    bank_id = cs_svc.save_bank_account(db_session, a.id, None, label="消す")
    cs_svc.delete_bank_account(db_session, bank_id)
    assert cs_svc.get_bank_account(db_session, bank_id) is None


# ── 印影画像 ───────────────────────────────────────────────────

def test_first_seal_becomes_default(db_session):
    a = _make_issuer(db_session, "A")
    seal_id = cs_svc.add_seal(db_session, a.id, "印鑑", b"PNGDATA")
    seal = db_session.get(SealImage, seal_id)
    assert seal.is_default is True
    assert seal.image_data == b"PNGDATA"
    assert seal.path == ""


def test_second_seal_is_not_default(db_session):
    a = _make_issuer(db_session, "A")
    cs_svc.add_seal(db_session, a.id, "1つ目", b"A")
    second = cs_svc.add_seal(db_session, a.id, "2つ目", b"B")
    assert db_session.get(SealImage, second).is_default is False


def test_set_default_seal_is_exclusive(db_session):
    a = _make_issuer(db_session, "A")
    first = cs_svc.add_seal(db_session, a.id, "1", b"A")
    second = cs_svc.add_seal(db_session, a.id, "2", b"B")
    cs_svc.set_default_seal(db_session, a.id, second)
    assert db_session.get(SealImage, first).is_default is False
    assert db_session.get(SealImage, second).is_default is True


def test_delete_seal(db_session):
    a = _make_issuer(db_session, "A")
    seal_id = cs_svc.add_seal(db_session, a.id, "消す", b"A")
    cs_svc.delete_seal(db_session, seal_id)
    assert db_session.get(SealImage, seal_id) is None


def test_seal_migrates_from_path_to_blob(db_session, tmp_path):
    a = _make_issuer(db_session, "A")
    img = tmp_path / "seal.png"
    img.write_bytes(b"IMAGEBYTES")
    seal = SealImage(company_id=a.id, label="旧", path=str(img))
    db_session.add(seal)
    db_session.commit()

    assert cs_svc.migrate_seal_to_blob(db_session, seal) is True
    assert db_session.get(SealImage, seal.id).image_data == b"IMAGEBYTES"


def test_seal_migration_skips_when_blob_exists(db_session, tmp_path):
    a = _make_issuer(db_session, "A")
    img = tmp_path / "seal.png"
    img.write_bytes(b"NEW")
    seal = SealImage(company_id=a.id, label="済", path=str(img),
                     image_data=b"OLD")
    db_session.add(seal)
    db_session.commit()

    assert cs_svc.migrate_seal_to_blob(db_session, seal) is False
    assert db_session.get(SealImage, seal.id).image_data == b"OLD"


def test_seal_migration_skips_when_file_missing(db_session, tmp_path):
    a = _make_issuer(db_session, "A")
    seal = SealImage(company_id=a.id, label="欠落",
                     path=str(tmp_path / "ない.png"))
    db_session.add(seal)
    db_session.commit()

    assert cs_svc.migrate_seal_to_blob(db_session, seal) is False
    assert db_session.get(SealImage, seal.id).image_data is None


def test_list_seals_is_per_company(db_session):
    a = _make_issuer(db_session, "A")
    b = _make_issuer(db_session, "B")
    cs_svc.add_seal(db_session, a.id, "A印", b"A")
    assert len(cs_svc.list_seals(db_session, a.id)) == 1
    assert cs_svc.list_seals(db_session, b.id) == []
