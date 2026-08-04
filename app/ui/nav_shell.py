# -*- coding: utf-8 -*-
"""
Windows 11 / Fluent Design 準拠の左ナビゲーションとページシェル。

Microsoft の NavigationView ガイドラインに沿った構成:
- 左ペインは展開時 260px / 折りたたみ時 48px（アイコンのみ）
- ウィンドウ幅 1008px を境に展開・折りたたみを自動切替（NavigationView の Auto 相当）
- 「設定」はペイン末尾に分離（FooterMenuItems 相当）
- 選択中の項目には左端に縦アクセントバーを表示
- ページ見出しは高さ 52px 固定
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal

# ── レイアウト定数（Windows 11 デザインガイドライン準拠） ──────────────
PANE_WIDTH_EXPANDED = 260
PANE_WIDTH_COMPACT  = 48
COMPACT_THRESHOLD   = 1008   # これ未満の幅では折りたたむ
HEADER_HEIGHT       = 52     # ページ見出しの固定高さ
# 子ウィジェットが既定で約9pxの余白を持つため、シェル側は16pxとして
# 合計の視覚的インセットをガイドラインの24pxに合わせる。
PAGE_MARGIN         = 16

# ── Segoe Fluent Icons のグリフ ────────────────────────────────────
GLYPH_MENU     = "\uE700"   # GlobalNavButton
GLYPH_DOCUMENT = "\uE8A5"   # Document
GLYPH_LIST     = "\uE8FD"   # BulletedList
GLYPH_PRINT    = "\uE749"   # Print
GLYPH_EDIT     = "\uE70F"   # Edit
GLYPH_LIBRARY  = "\uE8F1"   # Library
GLYPH_MAIL     = "\uE715"   # Mail
GLYPH_SETTINGS = "\uE713"   # Settings


class NavItem(QPushButton):
    """左ナビの1項目。アクセントバー・アイコン・ラベルを横に並べる。"""

    def __init__(self, label: str, glyph: str, parent=None):
        super().__init__(parent)
        self.setObjectName("navItem")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self._label_text = label

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # 選択インジケータ（Windows 11 の縦アクセントバー）
        self._accent = QFrame()
        self._accent.setObjectName("navAccent")
        self._accent.setFixedSize(3, 16)
        self._accent.setVisible(False)
        row.addSpacing(4)
        row.addWidget(self._accent)

        # アイコンフォントは theme.py の #navIcon で指定する。
        # スタイルシートは setFont() より優先されるため、ここで setFont してはいけない。
        self._icon = QLabel(glyph)
        self._icon.setObjectName("navIcon")
        self._icon.setFixedWidth(PANE_WIDTH_COMPACT - 7)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._icon)

        self._label = QLabel(label)
        self._label.setObjectName("navLabel")
        row.addWidget(self._label, 1)

        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool):
        """選択状態をアクセントバーと文字色に反映する。

        Qt のスタイルシートは祖先の擬似状態を子に伝播しないため、
        動的プロパティを立てて再ポリッシュする。
        """
        self._accent.setVisible(checked)
        for widget in (self._icon, self._label):
            widget.setProperty("selected", "true" if checked else "false")
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def label_text(self) -> str:
        return self._label_text

    def set_compact(self, compact: bool):
        self._label.setVisible(not compact)
        # 折りたたみ時はラベルが見えないのでツールチップで補う
        self.setToolTip(self._label_text if compact else "")


class NavRail(QWidget):
    """左ナビゲーションペイン。

    items の末尾 footer_count 件はペイン下部（設定などのアプリ全体設定）に配置する。
    インデックスは items の並び順のまま 0 始まりで通し、QStackedWidget と 1:1 で対応する。
    """

    currentChanged = pyqtSignal(int)
    toggleRequested = pyqtSignal()

    def __init__(self, items: list[tuple[str, str]], footer_count: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("navRail")
        # 素の QWidget はスタイルシートの背景・境界線を描画しないため明示的に有効化する
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._compact = False
        self._items: list[NavItem] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 8)
        root.setSpacing(2)

        # ── ペインヘッダ：ハンバーガー + アプリ名 ──────────────────
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 0, 0)
        header.setSpacing(0)
        self._toggle = QPushButton(GLYPH_MENU)
        self._toggle.setObjectName("navToggle")
        self._toggle.setFixedSize(PANE_WIDTH_COMPACT - 7, 40)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setToolTip("メニューの表示を切り替え")
        self._toggle.clicked.connect(self.toggleRequested)
        header.addWidget(self._toggle)
        self._title = QLabel("CCI請求書")
        self._title.setObjectName("navTitle")
        header.addWidget(self._title, 1)
        root.addLayout(header)
        root.addSpacing(4)

        main_count = len(items) - footer_count
        for index, (label, glyph) in enumerate(items):
            item = NavItem(label, glyph)
            item.clicked.connect(lambda _checked, i=index: self._on_clicked(i))
            self._items.append(item)
            if index == main_count:
                root.addStretch(1)
                root.addWidget(self._separator())
            root.addWidget(item)
        if footer_count == 0:
            root.addStretch(1)

        self.setFixedWidth(PANE_WIDTH_EXPANDED)
        if self._items:
            self._items[0].setChecked(True)

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setObjectName("navSeparator")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        return line

    def _on_clicked(self, index: int):
        self._items[index].setChecked(True)
        self.currentChanged.emit(index)

    # ── 公開 API ────────────────────────────────────────────────
    def labels(self) -> list[str]:
        return [item.label_text() for item in self._items]

    def current_index(self) -> int:
        for i, item in enumerate(self._items):
            if item.isChecked():
                return i
        return -1

    def set_current_index(self, index: int):
        if 0 <= index < len(self._items):
            self._on_clicked(index)

    def is_compact(self) -> bool:
        return self._compact

    def set_compact(self, compact: bool):
        if compact == self._compact:
            return
        self._compact = compact
        self.setFixedWidth(PANE_WIDTH_COMPACT if compact else PANE_WIDTH_EXPANDED)
        self._title.setVisible(not compact)
        for item in self._items:
            item.set_compact(compact)


class PageShell(QWidget):
    """ページ見出し（52px）と余白付きコンテンツ領域を持つラッパー。

    content には既存のタブウィジェットをそのまま渡せる（改変不要）。
    """

    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("pageShell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._title_text = title
        self._content = content

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._title = QLabel(title)
        self._title.setObjectName("pageTitle")
        self._title.setFixedHeight(HEADER_HEIGHT)
        self._title.setContentsMargins(PAGE_MARGIN + 8, 0, PAGE_MARGIN, 0)
        root.addWidget(self._title)

        body = QWidget()
        body.setObjectName("pageBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(PAGE_MARGIN, 0, PAGE_MARGIN, PAGE_MARGIN)
        body_layout.setSpacing(0)
        body_layout.addWidget(content)
        root.addWidget(body, 1)

    def title(self) -> str:
        return self._title_text

    def content(self) -> QWidget:
        return self._content
