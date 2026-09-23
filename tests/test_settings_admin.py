from PyQt6.QtWidgets import QMessageBox

from app.services import maintenance_service
from app.ui.settings_tab import _AdminWidget


def _capture_delete_func(qtbot, monkeypatch, handler_name):
    """削除ボタンが呼ぶサービス関数を横取りして返す。実際には削除しない。"""
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
        lambda func, *_args: captured.setdefault("func", func),
    )

    getattr(widget, handler_name)()
    return captured["func"]


def test_reset_numbers_calls_reset_document_numbers(qtbot, monkeypatch):
    assert _capture_delete_func(qtbot, monkeypatch, "_on_reset_numbers") \
        is maintenance_service.reset_document_numbers


def test_business_reset_calls_initialize_business_data(qtbot, monkeypatch):
    assert _capture_delete_func(qtbot, monkeypatch, "_on_init_clicked") \
        is maintenance_service.initialize_business_data


def test_delete_all_calls_delete_all_except_issuers(qtbot, monkeypatch):
    assert _capture_delete_func(qtbot, monkeypatch, "_on_delete_all") \
        is maintenance_service.delete_all_except_issuers


# 採番表（document_sequences）を消すかどうかは、どの削除でも守るべき挙動なので
# tests/test_maintenance_service.py::test_all_deletions_reset_document_sequence
# で実データに対して検証している。
