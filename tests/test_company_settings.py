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
