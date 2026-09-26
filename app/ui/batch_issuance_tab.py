# app/ui/batch_issuance_tab.py
from PyQt6.QtWidgets import QWidget, QTabWidget, QVBoxLayout
from app.ui.project_tab import ProjectTab
from app.ui.issuance_from_project import IssuanceFromProjectWidget


class BatchIssuanceTab(QWidget):
    """まとめて発行：名簿単位の準備と書類発行をまとめるタブ。

    プルダウンのホイール操作の無効化は、アプリ全体（app/ui/wheel_guard.py）で行う。
    """

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        # ここは単なる入れ物。PageShell 側の余白（app/ui/nav_shell.py の
        # PAGE_MARGIN）に、中の ProjectTab 自身の既定余白が乗るだけで十分な
        # ため、ここでも既定余白を持つと二重になり不要な空白が増える。
        layout.setContentsMargins(0, 0, 0, 0)
        self._tabs = QTabWidget()
        self._project_tab = ProjectTab()
        self._tabs.addTab(self._project_tab, "名簿・請求内容登録")
        self._tabs.addTab(IssuanceFromProjectWidget("invoice"), "請求書を発行")
        self._tabs.addTab(IssuanceFromProjectWidget("receipt"), "領収書を発行")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)

    def _on_tab_changed(self, index: int):
        """発行画面から戻った時点の集計値を表示する。"""
        if self._tabs.widget(index) is self._project_tab:
            self._project_tab._load()
