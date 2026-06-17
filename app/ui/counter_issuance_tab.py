# app/ui/counter_issuance_tab.py
from PyQt6.QtWidgets import QWidget, QTabWidget, QVBoxLayout
from app.ui.issuance_counter import IssuanceCounterWidget


class CounterIssuanceTab(QWidget):
    """単発発行：請求書・領収書タブ。"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        inner = QTabWidget()

        inner.addTab(IssuanceCounterWidget("invoice"), "請求書")
        inner.addTab(IssuanceCounterWidget("receipt"), "領収書")

        layout.addWidget(inner)
