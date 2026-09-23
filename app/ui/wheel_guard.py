# app/ui/wheel_guard.py
"""マウスホイールで入力値が変わらないようにする（誤入力防止）。

画面をスクロールしようとしてプルダウンや数量欄の上でホイールを回すと、
気づかないうちに値が変わってしまう。アプリ全体のイベントフィルタとして
一度だけ登録し、後から作られる画面の入力欄にも効かせる。
"""
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox


class WheelGuard(QObject):
    """閉じたプルダウン・数値欄・日付欄へのホイール操作を無効にする。"""

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            # 開いている候補リストは通常どおりホイールでスクロールできる
            if isinstance(watched, QComboBox) and not watched.view().isVisible():
                event.accept()
                return True
            # QSpinBox・QDoubleSpinBox・QDateEdit など（▲▼やキー入力では変更できる）
            if isinstance(watched, QAbstractSpinBox):
                event.accept()
                return True
        return super().eventFilter(watched, event)


def install_wheel_guard(app: QApplication) -> WheelGuard:
    guard = WheelGuard(app)
    app.installEventFilter(guard)
    return guard
