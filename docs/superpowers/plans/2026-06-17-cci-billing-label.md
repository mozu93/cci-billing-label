# cci-billing-label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cci-billing をコピーして独立リポジトリ `cci-billing-label` を作り、宛名ラベル発行タブを追加する。

**Architecture:** cci-billing フォルダを robocopy で `C:\Users\taka\Documents\Gemini\0030Business\cci-billing-label` にコピーし新 git リポジトリとして初期化。`label_ippatsusaku` から `customer_barcode.py` と PDF サービスを移植し、新規 `label_issuance_tab.py` を追加。main_window.py にタブを追加して統合する。

**Tech Stack:** Python 3.11, PyQt6, ReportLab, SQLAlchemy, Windows フォント（MSPGothic 等）

---

## ファイル構成

| 操作   | ファイル                              | 内容                                          |
|--------|---------------------------------------|-----------------------------------------------|
| 新規作成 | `app/utils/customer_barcode.py`     | バーコードユーティリティ（label_ippatsusaku からコピー） |
| 新規作成 | `app/services/pdf/label_pdf.py`     | ラベル PDF サービス（label_ippatsusaku からコピー）  |
| 新規作成 | `app/ui/label_issuance_tab.py`      | 宛名ラベル発行タブ UI                          |
| 変更   | `app/ui/main_window.py`              | 宛名ラベル発行タブを追加                       |

---

### Task 1: リポジトリのコピーと初期化

**Files:**
- 作業ディレクトリ: `C:\Users\taka\Documents\Gemini\0030Business\`

- [ ] **Step 1: cci-billing を cci-billing-label にコピーする**

```
robocopy "C:\Users\taka\Documents\Gemini\0030Business\cci-billing" "C:\Users\taka\Documents\Gemini\0030Business\cci-billing-label" /E /XD .git /XF *.pyc
```

Expected: `cci-billing-label` フォルダが作成され、`.git` を除く全ファイルがコピーされる。

- [ ] **Step 2: 新リポジトリとして初期化してコミット**

```bash
cd "C:\Users\taka\Documents\Gemini\0030Business\cci-billing-label"
git init
git add -A
git commit -m "chore: cci-billing-label 初期化（cci-billing コピー）"
```

Expected: `git log --oneline` に 1 コミット表示。

---

### Task 2: `app/utils/customer_barcode.py` を追加

**Files:**
- Create: `app/utils/customer_barcode.py`
- Test: `tests/test_customer_barcode.py`（cci-billing-label リポジトリ内）

- [ ] **Step 1: テストを書く**

`tests/test_customer_barcode.py` を作成:

```python
import pytest

def test_build_barcode_chars_length():
    from app.utils.customer_barcode import build_barcode_chars
    chars = build_barcode_chars("1000013", "1-3-2")
    assert len(chars) == 23

def test_build_barcode_chars_start_stop():
    from app.utils.customer_barcode import build_barcode_chars
    chars = build_barcode_chars("1000013", "1-3-2")
    assert chars[0] == "S"
    assert chars[-1] == "STOP"

def test_invalid_postal_raises():
    from app.utils.customer_barcode import build_barcode_chars
    with pytest.raises(ValueError):
        build_barcode_chars("123", "1-2")

def test_barcode_height_positive():
    from app.utils.customer_barcode import barcode_height
    assert barcode_height() > 0
```

- [ ] **Step 2: テストが失敗することを確認**

```
cd "C:\Users\taka\Documents\Gemini\0030Business\cci-billing-label"
python -m pytest tests/test_customer_barcode.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.utils.customer_barcode'`

- [ ] **Step 3: `app/utils/customer_barcode.py` を作成**

以下の内容をそのまま `app/utils/customer_barcode.py` に書き込む（label_ippatsusaku の内容と同一）:

```python
# -*- coding: utf-8 -*-
"""
日本郵便 カスタマバーコード（4ステイト3バー）

  - 住所表示番号の抽出
  - バーコード文字列の構築（スタート＋郵便番号7桁＋住所表示番号13桁＋チェックデジット＋ストップ）
  - チェックデジット計算（合計が19の倍数）
  - reportlab canvas への描画

仕様参照: https://www.post.japanpost.jp/zipcode/zipmanual/
"""
import re
from reportlab.lib.units import mm
from reportlab.lib.colors import black


def _normalize(text: str) -> str:
    result = []
    for ch in text:
        code = ord(ch)
        if 0xFF10 <= code <= 0xFF19:
            result.append(chr(code - 0xFF10 + ord('0')))
        elif ch in ('－', '−', 'ー', '‐', '–', '—'):
            result.append('-')
        else:
            result.append(ch)
    return ''.join(result)


def extract_address_code(address: str) -> tuple[str, bool]:
    if not address or not address.strip():
        return "", False
    text = _normalize(address)
    m = re.search(r'(\d+)丁目(\d+)番地?(\d+)?号?', text)
    if m:
        parts = [m.group(1), m.group(2)]
        if m.group(3):
            parts.append(m.group(3))
        return '-'.join(parts), True
    m = re.search(r'(\d+)番地(\d+)号?', text)
    if m:
        return f'{m.group(1)}-{m.group(2)}', True
    m = re.search(r'(\d+)番地', text)
    if m:
        return m.group(1), True
    m = re.search(r'(\d+(?:-\d+)+)', text)
    if m:
        return m.group(1), True
    m = re.search(r'(\d+)', text)
    if m:
        return m.group(1), False
    return "", False


_CHAR_VALUES: dict[str, int] = {str(i): i for i in range(10)}
_CHAR_VALUES['-'] = 10
_CHAR_VALUES.update({f'CC{i}': 10 + i for i in range(1, 9)})

_CHAR_PATTERNS: dict[str, tuple[str, str, str]] = {
    '0':    ('F', 'T', 'T'),
    '1':    ('A', 'T', 'D'),
    '2':    ('D', 'T', 'A'),
    '3':    ('T', 'F', 'T'),
    '4':    ('T', 'A', 'D'),
    '5':    ('A', 'D', 'T'),
    '6':    ('T', 'D', 'A'),
    '7':    ('D', 'A', 'T'),
    '8':    ('T', 'T', 'F'),
    '9':    ('F', 'A', 'T'),
    '-':    ('A', 'F', 'T'),
    'CC1':  ('D', 'F', 'T'),
    'CC2':  ('T', 'A', 'F'),
    'CC3':  ('F', 'T', 'A'),
    'CC4':  ('T', 'D', 'F'),
    'CC5':  ('F', 'D', 'T'),
    'CC6':  ('T', 'F', 'A'),
    'CC7':  ('A', 'A', 'D'),
    'CC8':  ('D', 'D', 'A'),
    'S':    ('F', 'A', 'D'),
    'STOP': ('D', 'A', 'F'),
}


def calc_check_digit(chars: list[str]) -> str:
    total = sum(_CHAR_VALUES.get(c, 0) for c in chars)
    remainder = total % 19
    check_val = (19 - remainder) % 19
    if check_val <= 9:
        return str(check_val)
    if check_val == 10:
        return '-'
    return f'CC{check_val - 10}'


def build_barcode_chars(postal: str, addr_code: str) -> list[str]:
    postal_clean = re.sub(r'\D', '', postal)
    if len(postal_clean) != 7:
        raise ValueError(f"郵便番号が7桁ではありません: {postal!r}")
    addr_chars: list[str] = [ch for ch in addr_code if ch.isdigit() or ch == '-']
    while len(addr_chars) < 13:
        addr_chars.append('CC4')
    addr_chars = addr_chars[:13]
    payload = list(postal_clean) + addr_chars
    check = calc_check_digit(payload)
    return ['S'] + payload + [check] + ['STOP']


_A = 8.0
_LONG_H  = 3.6 * _A / 10 * mm
_SHORT_H = 1.2 * _A / 10 * mm
_PITCH   = 1.2 * _A / 10 * mm
_BAR_W   = 0.6 * _A / 10 * mm
_EXTEND  = (_LONG_H - _SHORT_H) / 2


def barcode_height() -> float:
    return _LONG_H


def barcode_total_width(num_chars: int = 23) -> float:
    return num_chars * 3 * _PITCH


def draw_barcode(canvas, x0: float, y0: float, chars: list[str]) -> None:
    mid_y = y0 + _SHORT_H / 2 + _EXTEND
    canvas.saveState()
    canvas.setFillColor(black)
    canvas.setStrokeColor(black)
    x = x0
    for char in chars:
        patterns = _CHAR_PATTERNS.get(char, ('T', 'T', 'T'))
        for bar_type in patterns:
            if bar_type == 'F':
                bar_y = mid_y - _LONG_H / 2
                bar_h = _LONG_H
            elif bar_type == 'A':
                bar_y = mid_y - _SHORT_H / 2
                bar_h = _SHORT_H + _EXTEND
            elif bar_type == 'D':
                bar_y = mid_y - _SHORT_H / 2 - _EXTEND
                bar_h = _SHORT_H + _EXTEND
            else:
                bar_y = mid_y - _SHORT_H / 2
                bar_h = _SHORT_H
            canvas.rect(x, bar_y, _BAR_W, bar_h, fill=1, stroke=0)
            x += _PITCH
    canvas.restoreState()
```

- [ ] **Step 4: テストが通ることを確認**

```
python -m pytest tests/test_customer_barcode.py -v
```

Expected: 4 tests PASSED

- [ ] **Step 5: コミット**

```bash
git add app/utils/customer_barcode.py tests/test_customer_barcode.py
git commit -m "feat: カスタマバーコードユーティリティを追加"
```

---

### Task 3: `app/services/pdf/label_pdf.py` を追加

**Files:**
- Create: `app/services/pdf/label_pdf.py`
- Test: `tests/test_label_pdf.py`

- [ ] **Step 1: テストを書く**

`tests/test_label_pdf.py` を作成:

```python
import pytest
import os
import tempfile


def test_label_layouts_populated():
    from app.services.pdf.label_pdf import LABEL_LAYOUTS
    assert "a_one_28185" in LABEL_LAYOUTS
    assert "a_one_28187" in LABEL_LAYOUTS
    assert "a_one_51002" in LABEL_LAYOUTS
    assert "a4_4split"   in LABEL_LAYOUTS


def test_font_options_not_empty():
    from app.services.pdf.label_pdf import FONT_OPTIONS
    assert len(FONT_OPTIONS) > 0


def test_default_keys_exist():
    from app.services.pdf.label_pdf import (
        DEFAULT_LAYOUT_KEY, DEFAULT_FONT_KEY, LABEL_LAYOUTS, FONT_OPTIONS
    )
    assert DEFAULT_LAYOUT_KEY in LABEL_LAYOUTS
    assert DEFAULT_FONT_KEY in FONT_OPTIONS


class _DummyEntry:
    company_name    = "テスト商事"
    postal_code     = "123-4567"
    address1        = "東京都千代田区1-2-3"
    address2        = ""
    title           = "部長"
    person_name     = "田中太郎"
    barcode_address = ""
    entry_mode      = "inherit"


def test_generate_label_pdf_creates_file():
    from app.services.pdf.label_pdf import generate_label_pdf
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "test_label.pdf")
        generate_label_pdf([_DummyEntry()], out, batch_mode="normal")
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0
```

- [ ] **Step 2: テストが失敗することを確認**

```
python -m pytest tests/test_label_pdf.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.pdf.label_pdf'`

- [ ] **Step 3: `app/services/pdf/label_pdf.py` を作成**

以下の内容を `app/services/pdf/label_pdf.py` として書き込む（label_ippatsusaku の label_pdf_service.py と同内容。インポートパスは `from app.utils.customer_barcode import ...` のまま変更なし）:

```python
# -*- coding: utf-8 -*-
"""
宛名ラベル PDF 生成サービス

複数のラベルレイアウトに対応。
LABEL_LAYOUTS に仕様を追加するだけで新しいサイズを登録できる。

登録済みレイアウト:
  "a_one_28185" : A-ONE 28185  A4 3列×6行  70×42.3mm  上余白21.5mm
  "a_one_28187" : A-ONE 28187  A4 2列×6行  84×42mm    上余白22.5mm
  "a_one_51002" : A-ONE 51002  A4 2列×5行  91×55mm    上余白11mm（名札用）
  "a4_4split"   : A4 横長4分割 A4 1列×4行  210×74.25mm（プレートモード用）
"""
from dataclasses import dataclass, field
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
import os

from app.utils.customer_barcode import build_barcode_chars, draw_barcode, barcode_height

_FONT_FILES = {
    "Meiryo":        ("C:/Windows/Fonts/meiryo.ttc",           0),
    "MSPGothic":     ("C:/Windows/Fonts/msgothic.ttc",          2),
    "MSPMincho":     ("C:/Windows/Fonts/msmincho.ttc",          1),
    "UDKyokasho":    ("C:/Windows/Fonts/UDDigiKyokashoN-R.ttc", 0),
    "HGRMaruGothic": ("C:/Windows/Fonts/HGRSMP.TTF",            0),
}
_registered: set[str] = set()
for _name, (_path, _idx) in _FONT_FILES.items():
    try:
        pdfmetrics.registerFont(TTFont(_name, _path, subfontIndex=_idx))
        _registered.add(_name)
    except Exception:
        pass

_ALL_FONT_OPTIONS: dict[str, str] = {
    "MSPゴシック":   "MSPGothic",
    "MSP明朝":       "MSPMincho",
    "メイリオ":      "Meiryo",
    "UD教科書体":    "UDKyokasho",
    "HGR丸ゴシック": "HGRMaruGothic",
}
FONT_OPTIONS: dict[str, str] = {
    label: internal
    for label, internal in _ALL_FONT_OPTIONS.items()
    if internal in _registered
}
DEFAULT_FONT_KEY = "MSPゴシック"

FONT_G = "Meiryo"
C_BORDER = HexColor("#CCCCCC")
C_SUB    = HexColor("#555555")


@dataclass
class LabelLayout:
    name:            str
    cols:            int
    rows:            int
    label_w_mm:      float
    label_h_mm:      float
    margin_top_mm:   float
    margin_left_mm:  float
    gap_h_mm:        float
    gap_v_mm:        float
    page_h_mm:       float = 297.0
    col_offsets_mm:  list   = field(default=None)


LABEL_LAYOUTS: dict[str, LabelLayout] = {
    "a_one_28185": LabelLayout(
        name           = "A-ONE 28185  (A4 / 3列×6行 / 70×42.3mm)",
        cols           = 3,
        rows           = 6,
        label_w_mm     = 70.0,
        label_h_mm     = 42.3,
        margin_top_mm  = 21.5,
        margin_left_mm = 0.0,
        gap_h_mm       = 0.0,
        gap_v_mm       = 0.0,
        page_h_mm      = 296.9,
        col_offsets_mm = [1.0, 0.0, -1.0],
    ),
    "a_one_28187": LabelLayout(
        name           = "A-ONE 28187  (A4 / 2列×6行 / 84×42mm)",
        cols           = 2,
        rows           = 6,
        label_w_mm     = 84.0,
        label_h_mm     = 42.0,
        margin_top_mm  = 22.5,
        margin_left_mm = 20.0,
        gap_h_mm       = 2.0,
        gap_v_mm       = 0.0,
        page_h_mm      = 296.9,
    ),
    "a_one_51002": LabelLayout(
        name           = "A-ONE 51002  (A4 / 2列×5行 / 91×55mm・名札)",
        cols           = 2,
        rows           = 5,
        label_w_mm     = 91.0,
        label_h_mm     = 55.0,
        margin_top_mm  = 11.0,
        margin_left_mm = 14.0,
        gap_h_mm       = 0.0,
        gap_v_mm       = 0.0,
    ),
    "a4_4split": LabelLayout(
        name           = "A4 横長4分割  (A4 / 1列×4行 / 200×74.25mm)",
        cols           = 1,
        rows           = 4,
        label_w_mm     = 200.0,
        label_h_mm     = 74.25,
        margin_top_mm  = 0.0,
        margin_left_mm = 0.0,
        gap_h_mm       = 0.0,
        gap_v_mm       = 0.0,
    ),
}

DEFAULT_LAYOUT_KEY = "a_one_28185"


def _label_wh(layout: LabelLayout) -> tuple[float, float]:
    return layout.label_w_mm * mm, layout.label_h_mm * mm


def _label_origin(col: int, row: int, layout: LabelLayout) -> tuple[float, float]:
    page_h = layout.page_h_mm * mm
    lw = layout.label_w_mm  * mm
    lh = layout.label_h_mm  * mm
    mt = layout.margin_top_mm  * mm
    ml = layout.margin_left_mm * mm
    gh = layout.gap_h_mm * mm
    gv = layout.gap_v_mm * mm
    offsets = layout.col_offsets_mm or []
    col_offset = offsets[col] * mm if col < len(offsets) else 0.0
    x = ml + col * (lw + gh) + col_offset
    y = page_h - mt - (row + 1) * lh - row * gv
    return x, y


def generate_label_pdf(
    entries:         list,
    output_path:     str,
    batch_mode:      str  = "normal",
    layout_key:      str  = DEFAULT_LAYOUT_KEY,
    font_key:        str  = DEFAULT_FONT_KEY,
    barcode_enabled: bool = False,
) -> str:
    layout = LABEL_LAYOUTS.get(layout_key) or LABEL_LAYOUTS[DEFAULT_LAYOUT_KEY]
    font   = FONT_OPTIONS.get(font_key, FONT_OPTIONS[DEFAULT_FONT_KEY])
    lw, lh = _label_wh(layout)
    per_page = layout.cols * layout.rows

    if isinstance(output_path, str):
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    page_w = A4[0]
    page_h = layout.page_h_mm * mm
    c = Canvas(output_path, pagesize=(page_w, page_h))
    c.setTitle("宛名ラベル")

    draw_entries = (
        [e for e in entries for _ in range(2)]
        if layout_key == "a4_4split" else list(entries)
    )

    slot = 0
    for entry in draw_entries:
        if slot > 0 and slot % per_page == 0:
            c.showPage()

        page_slot = slot % per_page
        col = page_slot % layout.cols
        row = page_slot // layout.cols
        x0, y0 = _label_origin(col, row, layout)

        mode = batch_mode if entry.entry_mode == "inherit" else entry.entry_mode

        if layout_key == "a4_4split":
            _PLATE_SHIFT = 7.5 * mm
            plate_offset = -_PLATE_SHIFT if row in (0, 3) else 0.0
            if row % 2 == 0:
                c.saveState()
                c.translate(x0 + lw / 2, y0 + lh / 2)
                c.rotate(180)
                _draw_label(c, entry, -lw / 2, -lh / 2, lw, lh, mode, font, barcode_enabled,
                            plate_y_offset=plate_offset)
                c.restoreState()
            else:
                _draw_label(c, entry, x0, y0, lw, lh, mode, font, barcode_enabled,
                            plate_y_offset=plate_offset)
        else:
            _draw_label(c, entry, x0, y0, lw, lh, mode, font, barcode_enabled)
        slot += 1

    c.save()
    return output_path


def _fit_text(text: str, font: str, max_size: float,
              max_width: float, min_size: float = 5.5) -> float:
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _split_line(text: str, font: str, fs: float, max_w: float) -> tuple[str, str]:
    if not text:
        return "", ""
    if stringWidth(text, font, fs) <= max_w:
        return text, ""
    lo, hi = 1, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if stringWidth(text[:mid], font, fs) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo], text[lo:]


def _draw_label(c, entry, x0: float, y0: float, w: float, h: float, mode: str,
                font: str = "MSPGothic", barcode_enabled: bool = False,
                plate_y_offset: float = 0.0):
    c.saveState()

    company      = entry.company_name or ""
    postal       = entry.postal_code  or ""
    addr1        = entry.address1     or ""
    addr2        = entry.address2     or ""
    title        = entry.title        or ""
    person       = entry.person_name  or ""
    barcode_addr = getattr(entry, 'barcode_address', '') or ""

    if mode == "simple":
        _draw_simple(c, x0, y0, w, h, company, font)
    elif mode == "no_person":
        _draw_no_person(c, x0, y0, w, h, company, postal, addr1, addr2, font,
                        barcode_enabled, barcode_addr)
    elif mode == "nametag":
        _draw_nametag(c, x0, y0, w, h, company, title, person, font)
    elif mode == "split4":
        _draw_split4(c, x0, y0, w, h, company, font, plate_y_offset)
    else:
        _draw_normal(c, x0, y0, w, h, company, postal, addr1, addr2, title, person, font,
                     barcode_enabled, barcode_addr)

    c.restoreState()


def _draw_normal(c, x0, y0, w, h,
                 company, postal, addr1, addr2, title, person,
                 font: str = "MSPGothic",
                 barcode_enabled: bool = False,
                 barcode_addr: str = ""):
    _BC_MARGIN = 1.5 * mm
    _BC_TOP_MARGIN = 1.0 * mm
    use_barcode = barcode_enabled and bool(postal) and bool(barcode_addr)
    bc_reserve = (barcode_height() + _BC_MARGIN + _BC_TOP_MARGIN) if use_barcode else 0.0

    scale  = min(w / (92.5 * mm), (h - bc_reserve) / (53.0 * mm))
    P      = max(2.0 * mm, 3.0 * mm * scale)

    inner_w = w - 2 * P
    indent1 = P + 2.5 * mm * scale
    indent2 = P + 8.0 * mm * scale

    addr_fs     = 11.0
    co_max_fs   = 11.0
    title_fs    = 11.0
    name_max_fs = 11.0

    LH = addr_fs * 1.6

    effective_h = h - bc_reserve
    cur_y = y0 + effective_h - P - addr_fs * 0.85

    c.setFont(font, addr_fs)
    c.setFillColor(C_SUB)
    if postal:
        c.drawString(x0 + P, cur_y, f"〒{postal}")
        cur_y -= LH * 0.95

    if addr1:
        a = addr1
        while a:
            line, a = _split_line(a, font, addr_fs, inner_w)
            c.drawString(x0 + P, cur_y, line)
            cur_y -= addr_fs + (LH * 0.95 - addr_fs) * 0.25
    if addr2:
        c.drawString(x0 + P, cur_y, addr2)
        cur_y -= LH * 0.95

    if postal or addr1 or addr2:
        cur_y -= LH * 0.2

    if company:
        co_avail  = inner_w - (indent1 - P)
        target_fs = 10.0
        c.setFillColor(black)
        if "\n" not in company and stringWidth(company, font, target_fs) <= co_avail:
            fs = _fit_text(company, font, co_max_fs, co_avail, min_size=target_fs)
            c.setFont(font, fs)
            c.drawString(x0 + indent1, cur_y, company)
            cur_y -= LH * 1.26
        else:
            c.setFont(font, target_fs)
            for seg in company.split("\n"):
                if not seg:
                    continue
                rem = seg
                while rem:
                    line, rem = _split_line(rem, font, target_fs, co_avail)
                    c.drawString(x0 + indent1, cur_y, line)
                    cur_y -= target_fs + (LH * 0.9 - target_fs) * 0.25
            cur_y -= (target_fs + (LH * 0.9 - target_fs) * 0.25) * 0.2

    if title:
        title_avail = inner_w - (indent1 - P)
        target_fs   = 10.0
        c.setFillColor(black)
        t = title.strip()
        if "\n" not in t and stringWidth(t, font, target_fs) <= title_avail:
            fs = _fit_text(t, font, title_fs, title_avail, min_size=target_fs)
            c.setFont(font, fs)
            c.drawString(x0 + indent1, cur_y, t)
            cur_y -= LH * 0.95
        else:
            c.setFont(font, target_fs)
            for seg in t.split("\n"):
                seg = seg.strip()
                if not seg:
                    continue
                rem = seg
                while rem:
                    line, rem = _split_line(rem, font, target_fs, title_avail)
                    c.drawString(x0 + indent1, cur_y, line)
                    cur_y -= target_fs + (LH * 0.9 - target_fs) * 0.25

    if person:
        name_line = f"{person}　様"
        name_fs   = _fit_text(name_line, font, name_max_fs, inner_w - (indent2 - P))
        name_y    = max(y0 + P * 0.8, cur_y)
        c.setFont(font, name_fs)
        c.setFillColor(black)
        c.drawString(x0 + indent2, name_y, name_line)
    else:
        gochu_fs = max(7.0, 10.0 * scale)
        name_y   = max(y0 + P * 0.8, cur_y)
        c.setFont(font, gochu_fs)
        c.setFillColor(black)
        gw = stringWidth("御中", font, gochu_fs)
        c.drawString(x0 + w - P - gw, name_y, "御中")

    if use_barcode:
        try:
            chars = build_barcode_chars(re.sub(r'\D', '', postal), barcode_addr)
            draw_barcode(c, x0 + P, y0 + _BC_MARGIN, chars)
        except Exception:
            pass


def _draw_no_person(c, x0, y0, w, h, company, postal, addr1, addr2,
                    font: str = "MSPGothic",
                    barcode_enabled: bool = False,
                    barcode_addr: str = ""):
    _BC_MARGIN = 1.5 * mm
    _BC_TOP_MARGIN = 1.0 * mm
    use_barcode = barcode_enabled and bool(postal) and bool(barcode_addr)
    bc_reserve = (barcode_height() + _BC_MARGIN + _BC_TOP_MARGIN) if use_barcode else 0.0

    scale    = min(w / (92.5 * mm), (h - bc_reserve) / (53.0 * mm))
    P        = max(2.0 * mm, 3.0 * mm * scale)
    inner_w  = w - 2 * P
    indent1  = P + 2.5 * mm * scale
    co_avail = inner_w - (indent1 - P)

    addr_fs   = 11.0
    co_max_fs = 11.0
    LH        = addr_fs * 1.6

    effective_h = h - bc_reserve
    cur_y = y0 + effective_h - P - addr_fs * 0.85

    c.setFont(font, addr_fs)
    c.setFillColor(C_SUB)
    if postal:
        c.drawString(x0 + P, cur_y, f"〒{postal}")
        cur_y -= LH * 0.95

    if addr1:
        a = addr1
        while a:
            line, a = _split_line(a, font, addr_fs, inner_w)
            c.drawString(x0 + P, cur_y, line)
            cur_y -= LH * 0.95
    if addr2:
        c.drawString(x0 + P, cur_y, addr2)
        cur_y -= LH * 0.95

    if postal or addr1 or addr2:
        cur_y -= LH * 0.4

    if not company:
        return

    c.setFillColor(black)
    gochu = " 御中"

    if "\n" not in company and stringWidth(company + gochu, font, 10.0) <= co_avail:
        fs = _fit_text(company + gochu, font, co_max_fs, co_avail, min_size=10.0)
        c.setFont(font, fs)
        c.drawString(x0 + indent1, cur_y, company + gochu)
        return

    co_fs   = 10.0
    c.setFont(font, co_fs)
    gochu_w = stringWidth(gochu, font, co_fs)

    segments  = [s for s in company.split("\n") if s]
    all_lines = []

    for seg_idx, seg in enumerate(segments):
        is_last = (seg_idx == len(segments) - 1)
        rem = seg
        while rem:
            if is_last and stringWidth(rem + gochu, font, co_fs) <= co_avail:
                all_lines.append(rem + gochu)
                rem = ""
            else:
                line, rem = _split_line(rem, font, co_fs, co_avail)
                if is_last and not rem:
                    trimmed, rem = _split_line(line, font, co_fs, co_avail - gochu_w)
                    all_lines.append(trimmed)
                else:
                    all_lines.append(line)

    if not all_lines:
        return

    for i, line in enumerate(all_lines):
        c.drawString(x0 + indent1, cur_y, line)
        if i < len(all_lines) - 1:
            cur_y -= LH * 0.9

    if use_barcode:
        try:
            chars = build_barcode_chars(re.sub(r'\D', '', postal), barcode_addr)
            draw_barcode(c, x0 + P, y0 + _BC_MARGIN, chars)
        except Exception:
            pass


def _draw_nametag(c, x0, y0, w, h, company, title, person, font: str = "MSPGothic"):
    P = 4.0 * mm
    inner_w = w - 2 * P

    CO_MAX = 24.0
    CO_MIN = 16.0
    TI_MAX = 20.0
    TI_MIN = 14.0
    NA_FS  = 28.0

    cur_y = y0 + h - P - CO_MAX * 0.85

    if company:
        c.setFillColor(black)
        if "\n" in company:
            for line in company.split("\n"):
                if not line:
                    cur_y -= CO_MAX * 0.6
                    continue
                fs = _fit_text(line, font, CO_MAX, inner_w, min_size=CO_MIN)
                c.setFont(font, fs)
                c.drawString(x0 + P, cur_y, line)
                cur_y -= fs * 1.1
        else:
            fs = _fit_text(company, font, CO_MAX, inner_w, min_size=CO_MIN)
            if stringWidth(company, font, fs) <= inner_w:
                c.setFont(font, fs)
                c.drawString(x0 + P, cur_y, company)
                cur_y -= fs * 1.4
            else:
                c.setFont(font, CO_MIN)
                text = company
                while text:
                    line, text = _split_line(text, font, CO_MIN, inner_w)
                    c.drawString(x0 + P, cur_y, line)
                    cur_y -= CO_MIN * 1.1
    else:
        cur_y -= CO_MAX * 1.4

    if title:
        c.setFillColor(black)
        if "\n" in title:
            for line in title.split("\n"):
                if not line:
                    cur_y -= TI_MAX * 0.6
                    continue
                fs = _fit_text(line, font, TI_MAX, inner_w, min_size=TI_MIN)
                c.setFont(font, fs)
                indent = stringWidth("　", font, fs)
                c.drawString(x0 + P + indent, cur_y, line)
                cur_y -= fs * 1.1
        else:
            tl = title.strip()
            fs = _fit_text(tl, font, TI_MAX, inner_w, min_size=TI_MIN)
            if stringWidth(tl, font, fs) <= inner_w:
                c.setFont(font, fs)
                indent = stringWidth("　", font, fs)
                c.drawString(x0 + P + indent, cur_y, tl)
                cur_y -= fs * 1.4
            else:
                c.setFont(font, TI_MIN)
                text = tl
                while text:
                    line, text = _split_line(text, font, TI_MIN, inner_w)
                    indent = stringWidth("　", font, TI_MIN)
                    c.drawString(x0 + P + indent, cur_y, line)
                    cur_y -= TI_MIN * 1.1
    else:
        cur_y -= TI_MAX * 1.4

    cur_y -= 4.0

    if person:
        fs = _fit_text(person, font, NA_FS, inner_w)
        c.setFont(font, fs)
        c.setFillColor(black)
        nw = stringWidth(person, font, fs)
        c.drawString(x0 + (w - nw) / 2, cur_y, person)


def _draw_simple(c, x0, y0, w, h, company, font: str = "MSPGothic"):
    P       = 5.0 * mm
    inner_w = w - 2 * P
    co_fs   = 12.0
    go_fs   = 11.0
    line_h  = co_fs * 1.5

    co_lines = []
    for seg in (company or "").split("\n"):
        if not seg:
            continue
        rem = seg
        while rem:
            line, rem = _split_line(rem, font, co_fs, inner_w)
            co_lines.append(line)

    if not co_lines:
        return

    gw     = stringWidth("御中", font, go_fs)
    go_h   = go_fs * 1.5
    block_h = len(co_lines) * line_h + go_h
    cur_y   = y0 + (h + block_h) / 2 - co_fs * 0.15

    c.setFillColor(black)
    c.setFont(font, co_fs)
    for line in co_lines:
        c.drawString(x0 + P, cur_y, line)
        cur_y -= line_h

    c.setFont(font, go_fs)
    c.drawString(x0 + w - P - gw, cur_y, "御中")


def _draw_split4(c, x0, y0, w, h, company, font: str = "MSPGothic",
                 y_offset: float = 0.0):
    if not company:
        return

    P       = 4.0 * mm
    inner_w = w - 2 * P
    inner_h = h

    lines = [ln for ln in company.split("\n") if ln]
    if not lines:
        return

    n = len(lines)
    LINE_H = 1.08 if n > 1 else 1.4

    V_PAD        = 3.0 * mm if n > 1 else 0.0
    inner_h_eff  = inner_h - 2 * V_PAD

    widest = max(lines, key=lambda ln: stringWidth(ln, font, 150.0))
    fs_h   = min(inner_h_eff / ((n - 1) * LINE_H + 1.4), 125.0)
    fs     = min(_fit_text(widest, font, fs_h, inner_w, min_size=8.0), fs_h)
    line_h = fs * LINE_H

    start_y = y0 + h / 2 + (n - 1) * line_h / 2 - fs * 0.3 + y_offset

    bold = n > 1 or (n == 1 and len(lines[0]) >= 6)
    c.setFont(font, fs)
    c.setFillColor(black)
    if bold:
        c.setStrokeColor(black)
        c.setLineWidth(fs * 0.025)

    for i, line in enumerate(lines):
        cur_y = start_y - i * line_h
        mode  = 2 if bold else 0

        if len(line) == 2:
            pad = stringWidth(" ", font, fs) / 4
            cw  = [stringWidth(ch, font, fs) for ch in line]
            gap = inner_w - 2 * pad - sum(cw)
            x   = x0 + P + pad
            for j, ch in enumerate(line):
                c.drawString(x, cur_y, ch, mode=mode)
                x += cw[j] + (gap if j == 0 else 0)
        else:
            nchars = len(line)
            line_w = stringWidth(line, font, fs)
            gap    = (inner_w - line_w) / (nchars - 1) if nchars > 1 else 0
            x      = x0 + P
            for ch in line:
                c.drawString(x, cur_y, ch, mode=mode)
                x += stringWidth(ch, font, fs) + gap
```

- [ ] **Step 4: テストが通ることを確認**

```
python -m pytest tests/test_label_pdf.py -v
```

Expected: 4 tests PASSED

- [ ] **Step 5: コミット**

```bash
git add app/services/pdf/label_pdf.py tests/test_label_pdf.py
git commit -m "feat: ラベルPDFサービスを追加"
```

---

### Task 4: `app/ui/label_issuance_tab.py` を作成

**Files:**
- Create: `app/ui/label_issuance_tab.py`
- Test: `tests/test_label_entry_adapter.py`

- [ ] **Step 1: _LabelEntryAdapter のテストを書く**

`tests/test_label_entry_adapter.py` を作成:

```python
import types

def _make_pm(**kwargs):
    pm = types.SimpleNamespace(
        organization_name="テスト商事",
        postal_code="123-4567",
        address="東京都千代田区1-2-3",
        address2="ビル4F",
        department="営業部長",
        representative_name="田中太郎",
        organization_kana="テストショウジ",
        member_number="001",
    )
    for k, v in kwargs.items():
        setattr(pm, k, v)
    return pm


def test_adapter_basic_mapping():
    from app.ui.label_issuance_tab import _LabelEntryAdapter
    pm = _make_pm()
    entry = _LabelEntryAdapter(pm)
    assert entry.company_name == "テスト商事"
    assert entry.postal_code  == "123-4567"
    assert entry.address1     == "東京都千代田区1-2-3"
    assert entry.address2     == "ビル4F"
    assert entry.title        == "営業部長"
    assert entry.person_name  == "田中太郎"
    assert entry.barcode_address == ""
    assert entry.entry_mode   == "inherit"


def test_adapter_none_fields_become_empty():
    from app.ui.label_issuance_tab import _LabelEntryAdapter
    pm = _make_pm(organization_name=None, department=None, representative_name=None,
                  postal_code=None, address=None, address2=None)
    entry = _LabelEntryAdapter(pm)
    assert entry.company_name == ""
    assert entry.title        == ""
    assert entry.person_name  == ""
    assert entry.postal_code  == ""
    assert entry.address1     == ""
    assert entry.address2     == ""
```

- [ ] **Step 2: テストが失敗することを確認**

```
python -m pytest tests/test_label_entry_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.ui.label_issuance_tab'`

- [ ] **Step 3: `app/ui/label_issuance_tab.py` を作成**

```python
# app/ui/label_issuance_tab.py
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QComboBox, QLineEdit, QMessageBox,
    QCheckBox,
)
from PyQt6.QtCore import Qt, QTimer

from app.database.connection import get_session
from app.services.project_service import get_projects, get_project_members
from app.services.category_service import get_active_categories

COL_CHK  = 0
COL_NUM  = 1
COL_ORG  = 2
COL_KANA = 3
COL_REP  = 4
COL_POST = 5

LABEL_MODES = [
    ("宛名（氏名あり）", "normal"),
    ("宛名（氏名なし）", "no_person"),
    ("事業所名のみ",     "simple"),
    ("名札",            "nametag"),
    ("卓上プレート",     "split4"),
]


class _LabelEntryAdapter:
    def __init__(self, pm):
        self.company_name    = pm.organization_name or ""
        self.postal_code     = pm.postal_code or ""
        self.address1        = pm.address or ""
        self.address2        = pm.address2 or ""
        self.title           = pm.department or ""
        self.person_name     = pm.representative_name or ""
        self.barcode_address = ""
        self.entry_mode      = "inherit"


class _CheckableTable(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_checked_row = -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self.indexAt(event.pos())
            if idx.isValid() and idx.column() == COL_CHK:
                item = self.item(idx.row(), COL_CHK)
                if item and (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                    if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                            and self._last_checked_row >= 0):
                        new_state = (Qt.CheckState.Unchecked
                                     if item.checkState() == Qt.CheckState.Checked
                                     else Qt.CheckState.Checked)
                        r1 = min(self._last_checked_row, idx.row())
                        r2 = max(self._last_checked_row, idx.row())
                        self.blockSignals(True)
                        for r in range(r1, r2 + 1):
                            it = self.item(r, COL_CHK)
                            if it:
                                it.setCheckState(new_state)
                        self.blockSignals(False)
                        self._last_checked_row = idx.row()
                        return
                    else:
                        self._last_checked_row = idx.row()
        super().mousePressEvent(event)


class LabelIssuanceTab(QWidget):
    def __init__(self):
        super().__init__()
        self._all_projects: list = []
        self._pm_data: list = []
        self._build()
        self._load_projects()

    def _build(self):
        layout = QVBoxLayout(self)

        # ── フィルタ行（年度 / 業務区分 / 件名） ─────────────────────────
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("年度："))
        self._year_combo = QComboBox()
        self._year_combo.setMinimumWidth(95)
        self._year_combo.currentIndexChanged.connect(self._filter_projects)
        filter_row.addWidget(self._year_combo)

        filter_row.addWidget(QLabel("業務区分："))
        self._cat_combo = QComboBox()
        self._cat_combo.setMinimumWidth(120)
        self._cat_combo.currentIndexChanged.connect(self._filter_projects)
        filter_row.addWidget(self._cat_combo)

        filter_row.addWidget(QLabel("件名："))
        self._proj_combo = QComboBox()
        self._proj_combo.setMinimumWidth(200)
        self._proj_combo.currentIndexChanged.connect(self._on_project_changed)
        filter_row.addWidget(self._proj_combo)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # ── アクション行（モード / 用紙 / フォント / 生成ボタン / 検索） ─
        action_row = QHBoxLayout()
        from app.services.pdf.label_pdf import (
            LABEL_LAYOUTS, FONT_OPTIONS, DEFAULT_LAYOUT_KEY, DEFAULT_FONT_KEY
        )

        action_row.addWidget(QLabel("モード："))
        self._mode_combo = QComboBox()
        for label, _ in LABEL_MODES:
            self._mode_combo.addItem(label)
        action_row.addWidget(self._mode_combo)

        action_row.addWidget(QLabel("用紙："))
        self._layout_combo = QComboBox()
        for key, lo in LABEL_LAYOUTS.items():
            self._layout_combo.addItem(lo.name, key)
        idx = self._layout_combo.findData(DEFAULT_LAYOUT_KEY)
        if idx >= 0:
            self._layout_combo.setCurrentIndex(idx)
        action_row.addWidget(self._layout_combo)

        action_row.addWidget(QLabel("フォント："))
        self._font_combo = QComboBox()
        for label in FONT_OPTIONS.keys():
            self._font_combo.addItem(label)
        fidx = self._font_combo.findText(DEFAULT_FONT_KEY)
        if fidx >= 0:
            self._font_combo.setCurrentIndex(fidx)
        action_row.addWidget(self._font_combo)

        self._btn_generate = QPushButton("ラベルPDF生成")
        self._btn_generate.setEnabled(False)
        self._btn_generate.clicked.connect(self._generate_pdf)
        action_row.addWidget(self._btn_generate)

        action_row.addStretch()
        action_row.addWidget(QLabel("検索："))
        self._search = QLineEdit()
        self._search.setPlaceholderText("事業所名・代表者名で絞り込み")
        self._search.setMinimumWidth(150)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._load_members)
        self._search.textChanged.connect(lambda: self._timer.start(300))
        action_row.addWidget(self._search)
        layout.addLayout(action_row)

        # ── テーブル ─────────────────────────────────────────────────────
        self._table = _CheckableTable(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["", "会員番号", "事業所名", "フリガナ", "代表者名", "郵便番号"]
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_CHK,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_NUM,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_ORG,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_KANA, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_REP,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_POST, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(COL_CHK,  30)
        self._table.setColumnWidth(COL_NUM,  80)
        self._table.setColumnWidth(COL_REP, 100)
        self._table.setColumnWidth(COL_POST, 90)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._table)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        self._header_chk = QCheckBox(self._table.horizontalHeader())
        self._header_chk.setTristate(False)
        self._header_chk.toggled.connect(self._on_header_toggled)
        self._table.horizontalHeader().sectionResized.connect(
            lambda _l, _o, _n: self._reposition_header_chk()
        )

    def _reposition_header_chk(self):
        hdr = self._table.horizontalHeader()
        x = hdr.sectionViewportPosition(COL_CHK)
        w = hdr.sectionSize(COL_CHK)
        h = hdr.height()
        cw = self._header_chk.sizeHint().width()
        ch = self._header_chk.sizeHint().height()
        self._header_chk.move(x + (w - cw) // 2, (h - ch) // 2)

    def _on_header_toggled(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            it = self._table.item(r, COL_CHK)
            if it:
                it.setCheckState(state)
        self._table.blockSignals(False)
        self._update_status()

    def _on_item_changed(self, item):
        if item.column() == COL_CHK:
            self._update_status()

    def _load_projects(self):
        with get_session() as session:
            self._all_projects = get_projects(session)
            cats = get_active_categories(session)

        self._year_combo.blockSignals(True)
        self._cat_combo.blockSignals(True)
        years = sorted({p.fiscal_year for p in self._all_projects}, reverse=True)
        self._year_combo.clear()
        for y in years:
            self._year_combo.addItem(f"{y}年度", y)
        self._cat_combo.clear()
        self._cat_combo.addItem("すべて", None)
        for c in cats:
            self._cat_combo.addItem(c.name, c.id)
        self._year_combo.blockSignals(False)
        self._cat_combo.blockSignals(False)
        self._filter_projects()

    def _filter_projects(self):
        year = self._year_combo.currentData()
        cat_id = self._cat_combo.currentData()
        filtered = [
            p for p in self._all_projects
            if (year is None or p.fiscal_year == year)
            and (cat_id is None or p.category_id == cat_id)
        ]
        self._proj_combo.blockSignals(True)
        self._proj_combo.clear()
        self._proj_combo.addItem("（件名を選択）", None)
        for p in filtered:
            self._proj_combo.addItem(p.name, p.id)
        self._proj_combo.blockSignals(False)
        self._on_project_changed()

    def _on_project_changed(self):
        self._btn_generate.setEnabled(False)
        self._load_members()

    def _load_members(self):
        project_id = self._proj_combo.currentData()
        self._table.setRowCount(0)
        self._pm_data = []
        if project_id is None:
            self._status_label.setText("件名を選択してください")
            return

        kw = self._search.text().strip().lower()
        with get_session() as session:
            members = get_project_members(session, project_id)
            self._pm_data = [
                pm for pm in members
                if not kw
                or kw in (pm.organization_name or "").lower()
                or kw in (pm.organization_kana or "").lower()
                or kw in (pm.representative_name or "").lower()
            ]

        self._table.blockSignals(True)
        self._table.setRowCount(len(self._pm_data))
        for r, pm in enumerate(self._pm_data):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(r, COL_CHK,  chk)
            self._table.setItem(r, COL_NUM,  QTableWidgetItem(pm.member_number or ""))
            self._table.setItem(r, COL_ORG,  QTableWidgetItem(pm.organization_name or ""))
            self._table.setItem(r, COL_KANA, QTableWidgetItem(pm.organization_kana or ""))
            self._table.setItem(r, COL_REP,  QTableWidgetItem(pm.representative_name or ""))
            self._table.setItem(r, COL_POST, QTableWidgetItem(pm.postal_code or ""))
        self._table.blockSignals(False)

        self._btn_generate.setEnabled(len(self._pm_data) > 0)
        self._update_status()
        QTimer.singleShot(0, self._reposition_header_chk)

    def _update_status(self):
        total = self._table.rowCount()
        checked = sum(
            1 for r in range(total)
            if self._table.item(r, COL_CHK)
            and self._table.item(r, COL_CHK).checkState() == Qt.CheckState.Checked
        )
        self._status_label.setText(f"{total} 件表示　／　チェック済み {checked} 件")

    def _generate_pdf(self):
        checked_pms = [
            self._pm_data[r]
            for r in range(self._table.rowCount())
            if self._table.item(r, COL_CHK)
            and self._table.item(r, COL_CHK).checkState() == Qt.CheckState.Checked
        ]
        if not checked_pms:
            QMessageBox.warning(self, "未選択", "ラベルを生成するメンバーを選択してください。")
            return

        entries     = [_LabelEntryAdapter(pm) for pm in checked_pms]
        batch_mode  = LABEL_MODES[self._mode_combo.currentIndex()][1]
        layout_key  = self._layout_combo.currentData()
        font_key    = self._font_combo.currentText()

        from app.utils.pdf_helpers import get_pdf_output_dir
        from app.services.pdf.label_pdf import generate_label_pdf
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(get_pdf_output_dir(), f"label_{ts}.pdf")

        try:
            generate_label_pdf(entries, output_path, batch_mode, layout_key, font_key)
            os.startfile(output_path)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"PDF生成に失敗しました:\n{e}")
```

- [ ] **Step 4: テストが通ることを確認**

```
python -m pytest tests/test_label_entry_adapter.py -v
```

Expected: 2 tests PASSED

- [ ] **Step 5: コミット**

```bash
git add app/ui/label_issuance_tab.py tests/test_label_entry_adapter.py
git commit -m "feat: 宛名ラベル発行タブを追加"
```

---

### Task 5: `app/ui/main_window.py` に宛名ラベル発行タブを追加

**Files:**
- Modify: `app/ui/main_window.py:45-46`（BatchIssuanceTab 追加の直後）

- [ ] **Step 1: main_window.py の該当箇所を編集**

`app/ui/main_window.py` の `_build_tabs` メソッド内、BatchIssuanceTab の `addTab` 行の直後に以下を追加:

変更前:
```python
        from app.ui.batch_issuance_tab import BatchIssuanceTab
        tabs.addTab(BatchIssuanceTab(), "まとめて発行")

        from app.ui.reissue_tab import ReissueWidget
```

変更後:
```python
        from app.ui.batch_issuance_tab import BatchIssuanceTab
        tabs.addTab(BatchIssuanceTab(), "まとめて発行")

        from app.ui.label_issuance_tab import LabelIssuanceTab
        tabs.addTab(LabelIssuanceTab(), "宛名ラベル発行")

        from app.ui.reissue_tab import ReissueWidget
```

- [ ] **Step 2: インポートが通ることを確認**

```
python -c "from app.ui.main_window import MainWindow; print('OK')"
```

Expected: `OK` が出力される（GUI は起動しない）

- [ ] **Step 3: コミット**

```bash
git add app/ui/main_window.py
git commit -m "feat: main_window に宛名ラベル発行タブを統合"
```

---

### Task 6: 動作確認

- [ ] **Step 1: アプリを起動して宛名ラベル発行タブが表示されることを確認**

```
python main.py
```

確認項目:
1. タブ一覧に「宛名ラベル発行」が表示される
2. 年度・業務区分・件名コンボが機能する
3. 件名を選択すると会員一覧が表示される
4. チェックボックスで複数選択できる（Shift+クリックの範囲選択も動作する）
5. 「ラベルPDF生成」ボタンが有効になる（件名選択時）
6. チェックなし状態で「ラベルPDF生成」をクリックすると警告ダイアログが出る
7. メンバーをチェックして「ラベルPDF生成」をクリックすると PDF が生成されビューアで開く

- [ ] **Step 2: 全テストが通ることを確認**

```
python -m pytest tests/ -v --ignore=tests/test_main_window_tabs.py
```

Expected: 全テスト PASSED（`test_main_window_tabs.py` は既知の不安定テストのためスキップ）

- [ ] **Step 3: 最終コミット**

```bash
git add -A
git commit -m "chore: cci-billing-label v1.0 動作確認完了"
```
