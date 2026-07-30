from PyQt6.QtWidgets import QMessageBox

from app.ui.settings_tab import _AdminWidget


def _capture_delete_tables(qtbot, monkeypatch, handler_name):
    widget = _AdminWidget()
    qtbot.addWidget(widget)
    captured = {}

    monkeypatch.setattr(
        "app.ui.settings_tab.QMessageBox.warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        widget,
        "_exec_delete",
        lambda tables, *_args: captured.setdefault("tables", tables),
    )

    getattr(widget, handler_name)()
    return captured["tables"]


def test_reset_numbers_also_resets_atomic_sequence(qtbot, monkeypatch):
    tables = _capture_delete_tables(
        qtbot, monkeypatch, "_on_reset_numbers")
    assert "document_sequences" in tables


def test_business_reset_also_resets_atomic_sequence(qtbot, monkeypatch):
    tables = _capture_delete_tables(
        qtbot, monkeypatch, "_on_init_clicked")
    assert "document_sequences" in tables


def test_delete_all_also_resets_atomic_sequence(qtbot, monkeypatch):
    tables = _capture_delete_tables(
        qtbot, monkeypatch, "_on_delete_all")
    assert "document_sequences" in tables
