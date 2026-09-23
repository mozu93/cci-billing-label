# tests/test_counter_zero_quantity.py
"""単発発行：数量0を入力でき、数量0の行は明細に含めない。"""
import pytest
from PyQt6.QtWidgets import QMessageBox


class _Stop(Exception):
    """発行処理を DB 登録の手前で止めるための例外。"""


@pytest.fixture
def widget(qtbot, memory_db, monkeypatch):
    import app.ui.issuance_counter as ic
    import app.utils.app_config as app_config
    import app.utils.pdf_helpers as pdf_helpers
    # 実際の設定ファイルに書き込まない・自社情報は登録済みとみなす
    monkeypatch.setattr(app_config, "get_config", lambda: {})
    monkeypatch.setattr(app_config, "save_config", lambda cfg: None)
    monkeypatch.setattr(pdf_helpers, "get_company_and_bank", lambda s: (object(), None))

    captured = {}

    def fake_create(session, **kwargs):
        captured["lines"] = kwargs["lines_data"]
        raise _Stop()
    monkeypatch.setattr(ic, "create_direct_issuance", fake_create)

    msgs = {"warning": [], "question": [], "critical": []}
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: msgs["warning"].append(a[2]))
    monkeypatch.setattr(QMessageBox, "critical",
                        lambda *a, **k: msgs["critical"].append(a[2]))

    w = ic.IssuanceCounterWidget(doc_type="invoice")
    qtbot.addWidget(w)
    w._org_name.setText("○○商店")
    w._delivery.setCurrentText("印刷")
    w.captured, w.msgs = captured, msgs
    return w


def _set_row(w, index, name, price, qty):
    while len(w._rows) <= index:
        w._add_row()
    row = w._rows[index]
    row.tmpl_combo.setEditText(name)
    row.price_edit.setText(str(price))
    row.qty_spin.setValue(qty)
    return row


def _answer_question(monkeypatch, w, answer):
    def fake_question(*a, **k):
        w.msgs["question"].append(a[2])
        return answer
    monkeypatch.setattr(QMessageBox, "question", fake_question)


def test_quantity_can_be_zero(widget):
    row = widget._rows[0]
    assert row.qty_spin.minimum() == 0
    row.qty_spin.setValue(0)
    assert row.qty_spin.value() == 0


def test_zero_quantity_rows_are_excluded_from_lines(widget, monkeypatch):
    _answer_question(monkeypatch, widget, QMessageBox.StandardButton.Yes)
    _set_row(widget, 0, "年会費", 10000, 1)
    _set_row(widget, 1, "視察研修会参加費", 5000, 0)
    widget._issue()
    names = [l["item_name"] for l in widget.captured["lines"]]
    assert names == ["年会費"]
    assert widget.msgs["question"] == []   # 合計は0円ではないので確認しない


def test_all_zero_quantity_is_not_issued(widget, monkeypatch):
    _answer_question(monkeypatch, widget, QMessageBox.StandardButton.Yes)
    _set_row(widget, 0, "視察研修会参加費", 5000, 0)
    widget._issue()
    assert "lines" not in widget.captured
    assert any("数量が1以上の項目がありません" in m for m in widget.msgs["warning"])


def test_zero_total_asks_before_issuing(widget, monkeypatch):
    _answer_question(monkeypatch, widget, QMessageBox.StandardButton.No)
    _set_row(widget, 0, "無料相談", 0, 1)
    widget._issue()
    assert any("合計が0円" in m for m in widget.msgs["question"])
    assert "lines" not in widget.captured   # 「いいえ」なら発行しない

    _answer_question(monkeypatch, widget, QMessageBox.StandardButton.Yes)
    widget._issue()
    assert [l["item_name"] for l in widget.captured["lines"]] == ["無料相談"]
