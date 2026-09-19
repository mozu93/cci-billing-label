from PyQt6.QtWidgets import QPushButton


def test_bank_default_button_sets_selected_account(qtbot, memory_db):
    from app.database.connection import get_session
    from app.database.models import BankAccount, CompanySettings
    from app.ui.company_settings import CompanySettingsWidget

    session = get_session()
    company = CompanySettings(name="発行元", is_default=True)
    session.add(company)
    session.commit()
    bank1 = BankAccount(
        company_id=company.id,
        label="口座1",
        bank_name="A銀行",
        is_default=False,
    )
    bank2 = BankAccount(
        company_id=company.id,
        label="口座2",
        bank_name="B銀行",
        is_default=False,
    )
    session.add_all([bank1, bank2])
    session.commit()
    bank1_id, bank2_id = bank1.id, bank2.id
    session.close()

    widget = CompanySettingsWidget()
    qtbot.addWidget(widget)
    buttons = widget.findChildren(QPushButton)
    assert any(button.text() == "★ デフォルトに設定" for button in buttons)

    widget._bank_table.selectRow(1)
    widget._set_default_bank()

    session = get_session()
    assert session.get(BankAccount, bank1_id).is_default is False
    assert session.get(BankAccount, bank2_id).is_default is True
    session.close()
    assert widget._bank_table.item(1, 6).text() == "★ デフォルト"


def test_first_new_bank_is_default(qtbot, memory_db):
    from app.database.connection import get_session
    from app.database.models import BankAccount, CompanySettings
    from app.ui.company_settings import BankAccountDialog

    session = get_session()
    company = CompanySettings(name="発行元", is_default=True)
    session.add(company)
    session.commit()
    company_id = company.id
    session.close()

    dialog = BankAccountDialog(company_id=company_id)
    qtbot.addWidget(dialog)
    dialog._label.setText("メイン口座")
    dialog._bank_name.setText("○○銀行")
    dialog._save()

    session = get_session()
    bank = session.query(BankAccount).one()
    assert bank.is_default is True
    session.close()


def test_issuer_table_lists_all_issuers(qtbot, memory_db):
    """発行元一覧がID順に並び、デフォルト印が付く。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings
    from app.ui.company_settings import CompanySettingsWidget

    session = get_session()
    session.add_all([
        CompanySettings(name="あ商工会議所", address="住所A", is_default=False),
        CompanySettings(name="い商工会議所", address="住所B", is_default=True),
    ])
    session.commit()
    session.close()

    widget = CompanySettingsWidget()
    qtbot.addWidget(widget)

    assert widget._issuer_table.rowCount() == 2
    assert widget._issuer_table.item(0, 0).text() == "あ商工会議所"
    assert widget._issuer_table.item(1, 0).text() == "い商工会議所"
    assert widget._issuer_table.item(0, 2).text() == ""
    assert widget._issuer_table.item(1, 2).text() == "★ デフォルト"


def test_seal_table_lists_seals_of_selected_issuer(qtbot, memory_db):
    """印影一覧が、選択中の発行元の分だけ表示される。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings, SealImage
    from app.ui.company_settings import CompanySettingsWidget

    session = get_session()
    company = CompanySettings(name="発行元", is_default=True)
    other = CompanySettings(name="別の発行元")
    session.add_all([company, other])
    session.commit()
    session.add_all([
        SealImage(company_id=company.id, label="角印",
                  path="", image_data=b"PNG", is_default=True),
        SealImage(company_id=other.id, label="他社印",
                  path="", image_data=b"PNG"),
    ])
    session.commit()
    session.close()

    widget = CompanySettingsWidget()
    qtbot.addWidget(widget)

    assert widget._seal_table.rowCount() == 1
    assert widget._seal_table.item(0, 0).text() == "角印"
    assert widget._seal_table.item(0, 1).text() == "DB保存済"
    assert widget._seal_table.item(0, 2).text() == "★ デフォルト"


def test_seal_path_is_migrated_to_blob_on_load(qtbot, memory_db, tmp_path):
    """旧形式（ファイルパス）の印影は、一覧表示時にBLOBへ移行される。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings, SealImage
    from app.ui.company_settings import CompanySettingsWidget

    img = tmp_path / "seal.png"
    img.write_bytes(b"IMAGEBYTES")

    session = get_session()
    company = CompanySettings(name="発行元", is_default=True)
    session.add(company)
    session.commit()
    seal = SealImage(company_id=company.id, label="旧印", path=str(img))
    session.add(seal)
    session.commit()
    seal_id = seal.id
    session.close()

    widget = CompanySettingsWidget()
    qtbot.addWidget(widget)

    assert widget._seal_table.item(0, 1).text() == "DB保存済"
    session = get_session()
    assert session.get(SealImage, seal_id).image_data == b"IMAGEBYTES"
    session.close()


def test_deleting_default_issuer_is_refused(qtbot, memory_db, monkeypatch):
    """デフォルト発行元は削除できない。確認ダイアログも出さない。"""
    from app.database.connection import get_session
    from app.database.models import CompanySettings
    from app.ui import company_settings as mod
    from app.ui.company_settings import CompanySettingsWidget

    session = get_session()
    session.add_all([
        CompanySettings(name="デフォルト", is_default=True),
        CompanySettings(name="その他"),
    ])
    session.commit()
    session.close()

    widget = CompanySettingsWidget()
    qtbot.addWidget(widget)
    widget._issuer_table.selectRow(0)

    warned: list[str] = []
    asked: list[int] = []
    # monkeypatch で戻すこと。直接代入すると後続テストに漏れる。
    monkeypatch.setattr(mod.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a[2])))
    monkeypatch.setattr(mod.QMessageBox, "question",
                        staticmethod(lambda *a, **k: asked.append(1)))

    widget._del_issuer()

    assert len(warned) == 1
    assert "デフォルト発行元" in warned[0]
    assert asked == []  # 確認ダイアログまで進まない
    session = get_session()
    assert session.query(CompanySettings).count() == 2
    session.close()
