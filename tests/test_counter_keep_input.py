# tests/test_counter_keep_input.py
"""単発発行：発行後も入力を残し、同じ内容の二重発行は確認する。"""
import pytest
from PyQt6.QtWidgets import QFileDialog, QMessageBox


@pytest.fixture
def widget(qtbot, memory_db, monkeypatch):
    import app.utils.app_config as app_config
    from app.database.connection import get_session
    from app.database.models import CompanySettings
    from app.ui.issuance_counter import IssuanceCounterWidget

    s = get_session()
    s.add(CompanySettings(name="発行元", is_default=True))
    s.commit()
    s.close()
    # 実際の設定ファイルに書き込まない
    monkeypatch.setattr(app_config, "get_config", lambda: {})
    monkeypatch.setattr(app_config, "save_config", lambda cfg: None)
    # 保存先は選んだことにし、PDF の作成だけ差し替える
    import app.utils.pdf_helpers as pdf_helpers
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: ("C:/print/INV.pdf", ""))
    monkeypatch.setattr(pdf_helpers, "generate_and_open",
                        lambda iss, session, **k: k.get("save_path"))
    msgs = {"question": [], "answer": QMessageBox.StandardButton.No}
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail(a[2]))

    def fake_question(*a, **k):
        msgs["question"].append(a[2])
        return msgs["answer"]
    monkeypatch.setattr(QMessageBox, "question", fake_question)

    w = IssuanceCounterWidget(doc_type="invoice")
    qtbot.addWidget(w)
    w._reload_master()
    w._delivery.setCurrentText("印刷")
    w._org_name.setText("○○商店")
    row = w._rows[0]
    row.tmpl_combo.setEditText("年会費")
    row.price_edit.setText("10000")
    w.msgs = msgs
    return w


def _issued_count():
    from app.database.connection import get_session
    from app.database.models import Issuance
    s = get_session()
    try:
        return s.query(Issuance).count()
    finally:
        s.close()


def test_input_is_kept_after_issue(widget):
    widget._issue()
    assert _issued_count() == 1
    assert widget._org_name.text() == "○○商店"
    assert widget._rows[0].tmpl_combo.currentText() == "年会費"
    assert widget._rows[0].price_edit.text() == "10000"


def test_issued_number_is_shown(widget):
    widget._issue()
    assert "INV-" in widget._issued_label.text()
    assert "発行しました" in widget._issued_label.text()


def test_same_content_asks_before_issuing_again(widget):
    widget._issue()
    widget.msgs["answer"] = QMessageBox.StandardButton.No
    widget._issue()
    assert any("同じ内容" in q for q in widget.msgs["question"])
    assert _issued_count() == 1

    widget.msgs["answer"] = QMessageBox.StandardButton.Yes
    widget._issue()
    assert _issued_count() == 2


def test_changed_content_is_issued_without_asking(widget):
    widget._issue()
    widget._org_name.setText("△△商店")
    widget._issue()
    assert widget.msgs["question"] == []
    assert _issued_count() == 2


def test_clear_button_clears_everything(widget):
    widget._issue()
    widget._btn_clear.click()
    assert widget._org_name.text() == ""
    assert len(widget._rows) == 1
    assert widget._rows[0].tmpl_combo.currentData() is None
    assert widget._rows[0].price_edit.text() == "0"
    assert widget._issued_label.text() == ""
    # クリア後は同じ内容を入れ直しても確認しない
    widget._org_name.setText("○○商店")
    widget._rows[0].tmpl_combo.setEditText("年会費")
    widget._rows[0].price_edit.setText("10000")
    widget._issue()
    assert widget.msgs["question"] == []
