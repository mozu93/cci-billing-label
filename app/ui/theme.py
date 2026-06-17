# app/ui/theme.py
import os as _os

_ICONS = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "icons")
_UP   = _os.path.join(_ICONS, "spin_up.svg").replace("\\", "/")
_DOWN = _os.path.join(_ICONS, "spin_down.svg").replace("\\", "/")

STYLESHEET = f"""
QGroupBox {{
    border: 1px solid #E2E8F0; border-radius: 8px;
    margin-top: 10px; padding: 6px 6px 6px 6px;
    background: white; font-family: "Meiryo UI";
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: #2563EB; font-weight: bold; font-size: 12px;
}}
QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox {{
    border: 1px solid #CBD5E1; border-radius: 5px;
    padding: 3px 4px; background: white; color: #1E293B;
    font-family: "Meiryo UI"; font-size: 12px;
}}
QSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 16px; background-color: #F1F5F9;
    border-left: 1px solid #CBD5E1; border-bottom: 1px solid #CBD5E1;
    border-top-right-radius: 4px;
}}
QSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 16px; background-color: #F1F5F9;
    border-left: 1px solid #CBD5E1; border-top: 1px solid #CBD5E1;
    border-bottom-right-radius: 4px;
}}
QSpinBox::up-arrow   {{ image: url({_UP});   width: 8px; height: 5px; }}
QSpinBox::down-arrow {{ image: url({_DOWN}); width: 8px; height: 5px; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {{
    border: 1.5px solid #3B82F6; background: #F8FAFF;
}}
QTableWidget {{
    border: 1px solid #E2E8F0; border-radius: 6px;
    gridline-color: #F1F5F9; background: white;
    font-family: "Meiryo UI"; font-size: 12px;
    selection-background-color: #DBEAFE; selection-color: #1E293B;
}}
QTableWidget::item {{ padding: 4px 6px; }}
QTableWidget::item:selected {{ background: #DBEAFE; color: #1E293B; }}
QHeaderView::section {{
    background: #F8FAFC; border: none;
    border-right: 1px solid #E2E8F0;
    border-bottom: 2px solid #3B82F6;
    padding: 7px 8px; font-weight: bold;
    font-size: 11px; color: #475569; font-family: "Meiryo UI";
}}
QPushButton {{ font-family: "Meiryo UI"; font-size: 12px; }}
QLabel {{ font-family: "Meiryo UI"; color: #1E293B; }}
QTabBar::tab {{
    padding: 8px 18px; border: 1px solid #E2E8F0;
    border-bottom: none; border-radius: 6px 6px 0 0;
    background: #F1F5F9; color: #64748B;
    font-family: "Meiryo UI"; font-size: 12px; margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: white; color: #2563EB;
    font-weight: bold; border-bottom: 2px solid white;
}}
QScrollBar:vertical {{ width: 6px; background: transparent; }}
QScrollBar::handle:vertical {{
    background: #CBD5E1; border-radius: 3px; min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""

PRIMARY = "#2563EB"
DANGER  = "#DC2626"
SUCCESS = "#16A34A"
