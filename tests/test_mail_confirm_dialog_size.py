# tests/test_mail_confirm_dialog_size.py
"""送信確認ダイアログが小さい画面に収まる。

初期サイズが 1180x800 で、1366x768 のノートPC（有効高さ約728px）では
下部が画面外に出ていた。請求書のメール送信で必ず通る画面なので、
送信ボタンに手が届かなくなる。
"""
from PyQt6.QtWidgets import QApplication


def test_minimum_size_is_within_base_dialog_limit(qtbot, memory_db):
    """最小サイズが基準（780x600）以内に収まる。"""
    from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog

    dlg = InvoiceMailConfirmDialog()
    qtbot.addWidget(dlg)

    assert dlg.minimumWidth() <= 780
    assert dlg.minimumHeight() <= 600


def test_initial_size_fits_available_screen(qtbot, memory_db):
    """初期サイズが画面の有効領域を超えない。"""
    from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog

    dlg = InvoiceMailConfirmDialog()
    qtbot.addWidget(dlg)

    avail = QApplication.primaryScreen().availableGeometry()
    assert dlg.width() <= avail.width()
    assert dlg.height() <= avail.height()


def test_contents_do_not_force_oversized_dialog(qtbot, memory_db):
    """中身の最小高さの合計が、ダイアログの最小高さを押し上げない。"""
    from app.ui.invoice_mail_confirm_dialog import InvoiceMailConfirmDialog

    dlg = InvoiceMailConfirmDialog()
    qtbot.addWidget(dlg)

    # sizeHint ではなく、実際に縮められる下限で見る。
    assert dlg.minimumSizeHint().height() <= 600
