# app/ui/batch_issuance_tab.py
from PyQt6.QtWidgets import QApplication, QWidget, QComboBox, QTabWidget, QVBoxLayout
from PyQt6.QtCore import QObject, QEvent
from app.ui.project_tab import ProjectTab
from app.ui.issuance_from_project import IssuanceFromProjectWidget


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
    """まとめて発行：名簿単位の準備と書類発行をまとめるタブ。"""

    def __init__(self):
        super().__init__()
        # 動的に追加される名簿パネル内のQComboBoxも含めて保護する。
        self._combo_wheel_guard = _BatchComboWheelGuard(self)
        QApplication.instance().installEventFilter(self._combo_wheel_guard)
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._project_tab = ProjectTab()
        self._tabs.addTab(self._project_tab, "名簿・請求内容")
        self._tabs.addTab(IssuanceFromProjectWidget("invoice"), "請求書を発行")
        self._tabs.addTab(IssuanceFromProjectWidget("receipt"), "領収書を発行")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)

    def _on_tab_changed(self, index: int):
        """発行画面から戻った時点の集計値を表示する。"""
        if self._tabs.widget(index) is self._project_tab:
            self._project_tab._load()
