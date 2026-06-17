import types


def _make_pm(**kwargs):
    pm = types.SimpleNamespace(
        organization_name="テスト商事",
        postal_code="123-4567",
        address="東京都千代田区1-2-3",
        address2="ビル4F",
        department="営業部長",
        representative_name="田中太郎",
        organization_kana="テストショウジ",
        member_number="001",
    )
    for k, v in kwargs.items():
        setattr(pm, k, v)
    return pm


def test_adapter_basic_mapping():
    from app.ui.label_issuance_tab import _LabelEntryAdapter
    pm = _make_pm()
    entry = _LabelEntryAdapter(pm)
    assert entry.company_name == "テスト商事"
    assert entry.postal_code  == "123-4567"
    assert entry.address1     == "東京都千代田区1-2-3"
    assert entry.address2     == "ビル4F"
    assert entry.title        == "営業部長"
    assert entry.person_name  == "田中太郎"
    assert entry.barcode_address == ""
    assert entry.entry_mode   == "inherit"


def test_adapter_none_fields_become_empty():
    from app.ui.label_issuance_tab import _LabelEntryAdapter
    pm = _make_pm(organization_name=None, department=None, representative_name=None,
                  postal_code=None, address=None, address2=None)
    entry = _LabelEntryAdapter(pm)
    assert entry.company_name == ""
    assert entry.title        == ""
    assert entry.person_name  == ""
    assert entry.postal_code  == ""
    assert entry.address1     == ""
    assert entry.address2     == ""
