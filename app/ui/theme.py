# -*- coding: utf-8 -*-
"""
アプリ全体の共通スタイル。Windows 11 / Fluent Design のガイドラインに準拠する。

- タイプランプ: Caption 12 / Body 14 / Body Strong 14 semibold / Subtitle 20 semibold
- 角丸: 最上位コンテナ 8px、ページ内コントロール 4px
- 強調は Bold ではなく Semibold(600) を使う
- 日本語 UI フォントは Yu Gothic UI（Windows 11 標準）、無い環境は Meiryo UI
"""
import os as _os

_ICONS = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "icons")
_UP   = _os.path.join(_ICONS, "spin_up.svg").replace("\\", "/")
_DOWN = _os.path.join(_ICONS, "spin_down.svg").replace("\\", "/")

# ── カラートークン ──────────────────────────────────────────────
PRIMARY        = "#2563EB"
DANGER         = "#DC2626"
SUCCESS        = "#16A34A"
PRIMARY_HOVER  = "#1D4ED8"
SURFACE        = "#FFFFFF"
NAV_BG         = "#F1F5F9"
HOVER          = "#E8EEF7"
BORDER         = "#E2E8F0"
BORDER_STRONG  = "#CBD5E1"
TEXT           = "#1E293B"
TEXT_SECONDARY = "#64748B"
TEXT_MUTED     = "#94A3B8"

# ── タイプランプ（Windows 11） ────────────────────────────────────
FONT_STACK     = '"Yu Gothic UI", "Meiryo UI", sans-serif'
# アイコンフォント。Windows 11 は Segoe Fluent Icons、Windows 10 は Segoe MDL2 Assets。
ICON_FONT      = '"Segoe Fluent Icons", "Segoe MDL2 Assets"'
SIZE_CAPTION   = 12   # 12/16  データ密度が必要な表・補足テキスト
SIZE_BODY      = 14   # 14/20  既定の本文・フォーム部品
SIZE_SUBTITLE  = 20   # 20/28  ページ見出し

STYLESHEET = f"""
/* ── 全体 ─────────────────────────────────────────────────── */
QWidget {{
    font-family: {FONT_STACK};
    color: {TEXT};
}}
QMainWindow, #pageShell, #pageBody {{ background: {SURFACE}; }}

/* ── 左ナビゲーション（NavigationView 相当） ──────────────────── */
#navRail {{
    background: {NAV_BG};
    border-right: 1px solid {BORDER};
}}
#navTitle {{
    font-size: {SIZE_BODY}px; font-weight: 600;
    color: {TEXT}; padding-left: 4px; background: transparent;
}}
/* アイコンフォントの指定はここで行う。QWidget の font-family 指定が
   setFont() より優先されるため、コード側で設定しても上書きされてしまう。 */
#navIcon, #navToggle {{ font-family: {ICON_FONT}; font-size: 16px; }}
#navIcon[textGlyph="true"] {{ font-family: {FONT_STACK}; font-weight: 600; }}
#navToggle {{
    background: transparent; border: none; border-radius: 4px;
    color: {TEXT_SECONDARY};
}}
#navToggle:hover {{ background: {HOVER}; color: {TEXT}; }}
#navSeparator {{ background: {BORDER}; border: none; margin: 4px 12px; }}
#navItem {{
    background: transparent; border: none; border-radius: 4px;
    text-align: left; margin: 0 6px;
}}
#navItem:hover  {{ background: {HOVER}; }}
#navItem:checked {{ background: {SURFACE}; }}
#navAccent {{ background: {PRIMARY}; border: none; border-radius: 2px; }}
#navIcon {{ color: {TEXT_SECONDARY}; background: transparent; }}
#navIcon[selected="true"] {{ color: {PRIMARY}; }}
#navLabel {{
    font-size: {SIZE_BODY}px; color: {TEXT};
    background: transparent; padding-left: 2px;
}}
#navLabel[selected="true"] {{ color: {PRIMARY}; font-weight: 600; }}

/* ── ページ見出し（高さ52px） ───────────────────────────────── */
#pageTitle {{
    font-size: {SIZE_SUBTITLE}px; font-weight: 600;
    color: {TEXT}; background: {SURFACE};
}}

/* ── グループ・入力系 ─────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 8px;
    margin-top: 10px; padding: 6px;
    background: {SURFACE};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
    color: {PRIMARY}; font-weight: 600; font-size: {SIZE_BODY}px;
}}
QLineEdit, QComboBox, QDateEdit, QTextEdit, QPlainTextEdit, QSpinBox {{
    border: 1px solid {BORDER_STRONG}; border-radius: 4px;
    padding: 4px 6px; background: {SURFACE}; color: {TEXT};
    font-size: {SIZE_BODY}px;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{
    border: 1px solid {PRIMARY};
    border-bottom: 2px solid {PRIMARY};
    background: {SURFACE};
}}
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled,
QTextEdit:disabled, QSpinBox:disabled {{
    background: {NAV_BG}; color: {TEXT_MUTED};
}}
QSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 16px; background-color: {NAV_BG};
    border-left: 1px solid {BORDER_STRONG}; border-bottom: 1px solid {BORDER_STRONG};
    border-top-right-radius: 3px;
}}
QSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 16px; background-color: {NAV_BG};
    border-left: 1px solid {BORDER_STRONG}; border-top: 1px solid {BORDER_STRONG};
    border-bottom-right-radius: 3px;
}}
QSpinBox::up-arrow   {{ image: url({_UP});   width: 8px; height: 5px; }}
QSpinBox::down-arrow {{ image: url({_DOWN}); width: 8px; height: 5px; }}

/* ── 表 ───────────────────────────────────────────────────── */
QTableWidget, QTableView {{
    border: 1px solid {BORDER}; border-radius: 8px;
    gridline-color: {NAV_BG}; background: {SURFACE};
    font-size: {SIZE_CAPTION}px;
    selection-background-color: #DBEAFE; selection-color: {TEXT};
}}
QTableWidget::item, QTableView::item {{ padding: 4px 6px; }}
QTableWidget::item:selected, QTableView::item:selected {{
    background: #DBEAFE; color: {TEXT};
}}
QHeaderView::section {{
    background: #F8FAFC; border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 2px solid {PRIMARY};
    padding: 7px 8px; font-weight: 600;
    font-size: {SIZE_CAPTION}px; color: {TEXT_SECONDARY};
}}

/* ── ボタン・ラベル ───────────────────────────────────────── */
QPushButton {{ font-size: {SIZE_BODY}px; }}
QLabel      {{ font-size: {SIZE_BODY}px; color: {TEXT}; }}
QCheckBox, QRadioButton {{ font-size: {SIZE_BODY}px; spacing: 6px; }}

/* ── サブタブ（セグメント型） ──────────────────────────────── */
QTabWidget::pane {{
    border: none; border-top: 1px solid {BORDER};
    background: {SURFACE};
}}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    padding: 7px 16px; margin-right: 4px;
    border: none; border-bottom: 2px solid transparent;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
    background: transparent; color: {TEXT_SECONDARY};
    font-size: {SIZE_BODY}px;
}}
QTabBar::tab:hover {{ background: {HOVER}; color: {TEXT}; }}
QTabBar::tab:selected {{
    background: transparent; color: {PRIMARY};
    font-weight: 600; border-bottom: 2px solid {PRIMARY};
}}

/* ── スクロールバー ───────────────────────────────────────── */
QScrollBar:vertical {{ width: 6px; background: transparent; }}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG}; border-radius: 3px; min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 6px; background: transparent; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG}; border-radius: 3px; min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── ステータスバー ───────────────────────────────────────── */
QStatusBar {{
    background: #F8FAFC; border-top: 1px solid {BORDER};
    font-size: {SIZE_CAPTION}px; color: {TEXT_SECONDARY};
}}
QStatusBar::item {{ border: none; }}
"""
