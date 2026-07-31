from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout,
)

from app.database.connection import get_session
from app.services.staff_service import get_active_staff


class StaffSelectionDialog(QDialog):
    """パスワードなしで、この端末の担当者を選択するダイアログ。"""

    def __init__(self, parent=None, selected_staff_id: int | None = None):
        super().__init__(parent)
        self.setWindowTitle("担当者の選択")
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        description = QLabel(
            "この端末を使用する担当者を選択してください。\n"
            "選択内容は次回の起動時にも使用されます。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self._staff_combo = QComboBox()
        session = get_session()
        try:
            staff_list = get_active_staff(session)
            for staff in staff_list:
                self._staff_combo.addItem(staff.name, staff.id)
        finally:
            session.close()

        if selected_staff_id is not None:
            index = self._staff_combo.findData(selected_staff_id)
            if index >= 0:
                self._staff_combo.setCurrentIndex(index)
        layout.addWidget(self._staff_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("選択")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_staff_id(self) -> int | None:
        return self._staff_combo.currentData()
