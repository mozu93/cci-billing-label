# tests/test_counter_cancel_unoutput.py
"""単発発行：印刷の保存先を選ばなかったなど、何も出力されなかった発行は取り消す。"""
import pytest
from PyQt6.QtWidgets import QFileDialog, QMessageBox


@pytest.fixture
def env(qtbot, memory_db, monkeypatch):
    import app.utils.app_config as app_config
    import app.utils.pdf_helpers as pdf_helpers
    from app.database.connection import get_session
    from app.database.models import CompanySettings

    s = get_session()
    s.add(CompanySettings(name="発行元", is_default=True))
    s.commit()
    s.close()
    monkeypatch.setattr(app_config, "get_config", lambda: {})
    monkeypatch.setattr(app_config, "save_config", lambda cfg: None)
    monkeypatch.setattr(pdf_helpers, "generate_and_open",
                        lambda iss, session, **k: k.get("save_path"))
    msgs = {"information": []}
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: msgs["information"].append(a[2]))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    for name in ("warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: pytest.fail(a[2]))
    return msgs


def _make(qtbot, **kwargs):
    from app.ui.issuance_counter import IssuanceCounterWidget
    w = IssuanceCounterWidget(doc_type="invoice", **kwargs)
    qtbot.addWidget(w)
    w._reload_master()
    w._delivery.setCurrentText("印刷")
    w._org_name.setText("○○商店")
    if not w._rows:          # 修正・再発行の画面は空の行を作らない
        w._add_row()
    row = w._rows[0]
    row.tmpl_combo.setEditText("年会費")
    row.price_edit.setText("10000")
    return w


def _issuances():
    from app.database.connection import get_session
    from app.database.models import Issuance, OperationLog
    s = get_session()
    try:
        return ([i.doc_number for i in s.query(Issuance).all()],
                [l.detail for l in s.query(OperationLog).filter_by(action="発行取消")])
    finally:
        s.close()


def test_print_save_cancelled_cancels_issuance(qtbot, env, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    w = _make(qtbot)
    w._issue()
    numbers, cancel_logs = _issuances()
    assert numbers == []
    assert len(cancel_logs) == 1
    assert any("取り消しました" in m for m in env["information"])
    assert w._issued_label.text() == ""
    assert w._org_name.text() == "○○商店"     # 入力は残るので、そのまま発行し直せる


def test_saved_print_is_kept(qtbot, env, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: ("C:/print/INV.pdf", ""))
    w = _make(qtbot)
    w._issue()
    numbers, cancel_logs = _issuances()
    assert len(numbers) == 1 and cancel_logs == []


def test_edit_mode_is_never_cancelled(qtbot, env, monkeypatch):
    """修正・再発行で保存しなくても、元の発行は消さない。"""
    from app.database.connection import get_session
    from app.services.issuance_service import create_direct_issuance
    s = get_session()
    iss = create_direct_issuance(
        s, lines_data=[{"item_template_id": None, "item_name": "年会費", "quantity": 1,
                        "unit": "式", "unit_price": 10000, "tax_rate": 10}],
        recipient_organization="○○商店", recipient_name="", doc_type="invoice",
        fiscal_year=2026, month=9, staff_id=None, staff_name="",
        delivery_method="印刷", project_name="直接発行")
    iss_id = iss.id
    s.close()

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    w = _make(qtbot, edit_issuance_id=iss_id)
    w._issue()
    numbers, cancel_logs = _issuances()
    assert len(numbers) == 1 and cancel_logs == []
    assert any("再発行タブから出力できます" in m for m in env["information"])
