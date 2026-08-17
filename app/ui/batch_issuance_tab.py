# app/ui/batch_issuance_tab.py
from PyQt6.QtWidgets import QApplication, QWidget, QComboBox, QTabWidget, QVBoxLayout
from PyQt6.QtCore import QObject, QEvent
from app.ui.project_tab import ProjectTab
from app.ui.issuance_from_project import IssuanceFromProjectWidget
from app.ui.payment_dialog import PaymentManagementWidget


class _BatchComboWheelGuard(QObject):
    """まとめて発行内の閉じたプルダウンへのホイール操作を無効にする。"""

    @staticmethod
    def _is_in_batch_tab(combo: QComboBox) -> bool:
        parent = combo.parentWidget()
        while parent is not None:
            if isinstance(parent, BatchIssuanceTab):
                return True
            parent = parent.parentWidget()
        return False

    def eventFilter(self, watched, event):
        if (isinstance(watched, QComboBox)
                and event.type() == QEvent.Type.Wheel
                and self._is_in_batch_tab(watched)
                # 展開中の候補リストは通常どおりホイールでスクロールできる。
                and not watched.view().isVisible()):
            event.accept()
            return True
        return super().eventFilter(watched, event)


class BatchIssuanceTab(QWidget):
    """まとめて発行：名簿単位の準備・一括発行・入金管理・登録済発行をまとめるタブ。"""

    def __init__(self):
        super().__init__()
        # 動的に追加される名簿パネル内のQComboBoxも含めて保護する。
        self._combo_wheel_guard = _BatchComboWheelGuard(self)
        QApplication.instance().installEventFilter(self._combo_wheel_guard)
        layout = QVBoxLayout(self)
        inner = QTabWidget()
        inner.addTab(ProjectTab(), "名簿・請求内容")
        inner.addTab(IssuanceFromProjectWidget("invoice"), "請求書を発行")
        inner.addTab(IssuanceFromProjectWidget("receipt"), "領収書を発行")
        inner.addTab(PaymentManagementWidget(), "入金管理")
        layout.addWidget(inner)
