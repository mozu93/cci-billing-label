# app/ui/label_settings.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QDoubleSpinBox, QPushButton, QMessageBox,
)
from PyQt6.QtCore import Qt

from app.utils.app_config import get_label_print_offset, save_label_print_offset


_DESC = (
    "印刷後にシールと印刷位置がずれる場合に補正します。\n"
    "内容が右にずれる → 横補正を負に　　内容が左にずれる → 横補正を正に\n"
    "内容が下にずれる → 縦補正を負に　　内容が上にずれる → 縦補正を正に"
)


class LabelSettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        from app.services.pdf.label_pdf import LABEL_LAYOUTS

        self._spins: dict[str, tuple[QDoubleSpinBox, QDoubleSpinBox]] = {}

        for key, layout in LABEL_LAYOUTS.items():
            h_mm, v_mm = get_label_print_offset(key)
            grp = QGroupBox(layout.name)
            lay = QVBoxLayout(grp)

            desc = QLabel(_DESC)
            desc.setStyleSheet("color: #555; font-size: 11px;")
            desc.setWordWrap(True)
            lay.addWidget(desc)

            row = QHBoxLayout()
            row.addWidget(QLabel("横補正:"))
            h_spin = _make_spin(h_mm)
            row.addWidget(h_spin)
            row.addSpacing(20)
            row.addWidget(QLabel("縦補正:"))
            v_spin = _make_spin(v_mm)
            row.addWidget(v_spin)
            row.addStretch()
            lay.addLayout(row)

            root.addWidget(grp)
            self._spins[key] = (h_spin, v_spin)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.setFixedHeight(32)
        save_btn.setStyleSheet(
            "QPushButton { background:#2563EB; color:white; border-radius:4px;"
            " font-weight:bold; padding:0 20px; }"
            "QPushButton:hover { background:#1D4ED8; }"
        )
        save_btn.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)
        root.addStretch()

    def _save(self):
        for key, (h_spin, v_spin) in self._spins.items():
            save_label_print_offset(key, h_spin.value(), v_spin.value())
        QMessageBox.information(self, "保存完了", "ラベル印刷補正値を保存しました。")


def _make_spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(-15.0, 15.0)
    spin.setSingleStep(0.5)
    spin.setDecimals(1)
    spin.setValue(value)
    spin.setSuffix(" mm")
    spin.setFixedWidth(90)
    return spin
