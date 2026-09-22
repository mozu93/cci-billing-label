# app/services/company_service.py
"""発行元・銀行口座・印影画像の操作。

UI(company_settings.py)に散らばっていたクエリと業務ルールをここへ集める。
既存サービスと同じく、呼び出し側が開いた session を第1引数で受け取る。
"""
import os

from sqlalchemy.orm import Session

from app.database.models import BankAccount, CompanySettings, SealImage
from app.utils.applog import get_logger

_log = get_logger(__name__)


# ── 発行元 ─────────────────────────────────────────────────────

def list_issuers(session: Session) -> list[CompanySettings]:
    return session.query(CompanySettings).order_by(CompanySettings.id).all()


def get_issuer(session: Session, company_id: int) -> CompanySettings | None:
    return session.get(CompanySettings, company_id)


def count_issuers(session: Session) -> int:
    return session.query(CompanySettings).count()


def save_issuer(session: Session, company_id: int | None, **fields) -> int:
    """発行元を新規作成または更新し、そのIDを返す。"""
    if company_id:
        cs = session.get(CompanySettings, company_id)
        if cs is None:
            raise ValueError("発行元が見つかりません。")
    else:
        cs = CompanySettings()
        session.add(cs)
    for key, value in fields.items():
        setattr(cs, key, value)
    session.commit()
    return cs.id


def set_default_issuer(session: Session, company_id: int) -> None:
    """指定の発行元だけをデフォルトにする。"""
    for cs in session.query(CompanySettings).all():
        cs.is_default = (cs.id == company_id)
    session.commit()


def promote_only_issuer_to_default(session: Session, company_id: int) -> bool:
    """発行元が1件しか無いなら、それをデフォルトにする。

    最初の1件を登録した直後に呼ぶ。デフォルト不在の状態を作らないため。
    """
    if session.query(CompanySettings).count() != 1:
        return False
    cs = session.get(CompanySettings, company_id)
    if cs is None:
        return False
    cs.is_default = True
    session.commit()
    return True


def check_issuer_deletable(session: Session, company_id: int) -> tuple[bool, str]:
    """削除可否と、不可の場合の理由を返す。"""
    if session.query(CompanySettings).count() <= 1:
        return False, "発行元が1件しかないため削除できません。"
    cs = session.get(CompanySettings, company_id)
    if cs is None:
        return False, "発行元が見つかりません。"
    if cs.is_default:
        return False, ("デフォルト発行元は削除できません。\n"
                       "先に別の発行元をデフォルトに設定してください。")
    return True, ""


def delete_issuer(session: Session, company_id: int) -> None:
    cs = session.get(CompanySettings, company_id)
    if cs:
        session.delete(cs)
        session.commit()


def set_print_seal(session: Session, company_id: int, enabled: bool) -> None:
    cs = session.get(CompanySettings, company_id)
    if cs:
        cs.print_seal = enabled
        session.commit()


# ── 銀行口座 ───────────────────────────────────────────────────

def list_bank_accounts(session: Session, company_id: int) -> list[BankAccount]:
    return session.query(BankAccount).filter_by(company_id=company_id).all()


def get_bank_account(session: Session, bank_id: int) -> BankAccount | None:
    return session.get(BankAccount, bank_id)


def save_bank_account(session: Session, company_id: int,
                      bank_id: int | None, **fields) -> int:
    """銀行口座を新規作成または更新し、そのIDを返す。

    その発行元で最初の口座なら、自動でデフォルトにする。
    """
    if bank_id:
        bank = session.get(BankAccount, bank_id)
        if bank is None:
            raise ValueError("銀行口座が見つかりません。")
    else:
        is_first = session.query(BankAccount).filter_by(
            company_id=company_id).count() == 0
        bank = BankAccount(company_id=company_id, is_default=is_first)
        session.add(bank)
    for key, value in fields.items():
        setattr(bank, key, value)
    session.commit()
    return bank.id


def set_default_bank_account(session: Session, company_id: int,
                             bank_id: int) -> None:
    """同じ発行元の中で、指定の口座だけをデフォルトにする。"""
    for bank in session.query(BankAccount).filter_by(
            company_id=company_id).all():
        bank.is_default = (bank.id == bank_id)
    session.commit()


def delete_bank_account(session: Session, bank_id: int) -> None:
    bank = session.get(BankAccount, bank_id)
    if bank:
        session.delete(bank)
        session.commit()


# ── 印影画像 ───────────────────────────────────────────────────

def list_seals(session: Session, company_id: int) -> list[SealImage]:
    return session.query(SealImage).filter_by(company_id=company_id).all()


def get_seal(session: Session, seal_id: int) -> SealImage | None:
    return session.get(SealImage, seal_id)


def add_seal(session: Session, company_id: int, label: str,
             image_bytes: bytes) -> int:
    """印影画像を登録する。その発行元で最初なら自動でデフォルトにする。"""
    is_first = session.query(SealImage).filter_by(
        company_id=company_id).count() == 0
    seal = SealImage(
        company_id=company_id,
        label=label,
        path="",
        image_data=image_bytes,
        is_default=is_first,
    )
    session.add(seal)
    session.commit()
    return seal.id


def set_default_seal(session: Session, company_id: int, seal_id: int) -> None:
    """同じ発行元の中で、指定の印影だけをデフォルトにする。"""
    for seal in session.query(SealImage).filter_by(
            company_id=company_id).all():
        seal.is_default = (seal.id == seal_id)
    session.commit()


def delete_seal(session: Session, seal_id: int) -> None:
    seal = session.get(SealImage, seal_id)
    if seal:
        session.delete(seal)
        session.commit()


def migrate_seal_to_blob(session: Session, seal: SealImage) -> bool:
    """ファイルパス保存の旧データをBLOBへ移す。移せたら True。

    失敗しても画面表示は続けたいので、例外は投げずログに残す。
    """
    if seal.image_data or not seal.path:
        return False
    if not os.path.exists(seal.path):
        return False
    try:
        with open(seal.path, "rb") as fp:
            seal.image_data = fp.read()
        session.commit()
        return True
    except Exception:
        _log.warning("印影画像のBLOB移行に失敗: %s", seal.path, exc_info=True)
        session.rollback()
        return False
