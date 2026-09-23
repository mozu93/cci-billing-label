# tests/test_counter_preview_button.py
"""単発発行の「プレビュー」ボタン。"""
import pytest
from PyQt6.QtWidgets import QMessageBox


@pytest.fixture
def widget(qtbot, memory_db, monkeypatch):
    import app.services.print_service as print_service
    import app.utils.pdf_helpers as pdf_helpers
    from app.ui.issuance_counter import IssuanceCounterWidget

    calls = {"preview": [], "open": [], "warning": []}

    def fake_preview(session, issuance, **kwargs):
        calls["preview"].append((issuance, kwargs))
        return "C:/preview/preview_x.pdf"
    monkeypatch.setattr(pdf_helpers, "generate_preview_pdf", fake_preview)
    monkeypatch.setattr(print_service, "open_pdf", lambda p: calls["open"].append(p) or True)
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: calls["warning"].append(a[2]))

    w = IssuanceCounterWidget(doc_type="invoice")
    qtbot.addWidget(w)
    w.resize(1120, 728)
    w.show()
    w.calls = calls
    return w


def _fill(w):
    w._org_name.setText("○○商店")
    w._rep_name_edit.setText("山田太郎")
    row = w._rows[0]
    row.tmpl_combo.setEditText("年会費")
    row.price_edit.setText("10000")
    row.qty_spin.setValue(1)
    w._add_row()
    row2 = w._rows[1]
    row2.tmpl_combo.setEditText("視察研修会参加費")
    row2.price_edit.setText("5000")
    row2.qty_spin.setValue(0)


def test_preview_button_is_left_of_issue_button(widget):
    btn = widget._btn_preview
    assert btn.text() == "プレビュー"
    assert btn.mapTo(widget, btn.rect().topLeft()).x() < \
        widget._btn_issue.mapTo(widget, widget._btn_issue.rect().topLeft()).x()


def test_preview_opens_pdf_without_saving(widget):
    from app.database.connection import get_session
    from app.database.models import Issuance
    _fill(widget)
    widget._btn_preview.click()

    assert widget.calls["open"] == ["C:/preview/preview_x.pdf"]
    iss, kwargs = widget.calls["preview"][0]
    assert iss.recipient_organization == "○○商店"
    assert iss.recipient_name == "山田太郎"
    assert [l.item_name for l in iss.lines] == ["年会費"]   # 数量0は除く
    assert iss.amount == 10000
    assert kwargs["subject"] == "直接発行"
    s = get_session()
    try:
        assert s.query(Issuance).count() == 0
    finally:
        s.close()


def test_preview_requires_organization(widget):
    _fill(widget)
    widget._org_name.clear()
    widget._btn_preview.click()
    assert widget.calls["preview"] == []
    assert any("事業所名" in m for m in widget.calls["warning"])
