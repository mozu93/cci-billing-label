# 商工会議所請求書・領収書発行システム — Plan 3: PDF・印刷

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 請求書・領収書・催促状のPDFを生成し、印刷・保存できる状態にする。発行UI（Plan 2）の「発行する」ボタン押下後にPDF生成→印刷プレビューが開くまでを実装する。

**Architecture:** ReportLabでPDFを生成（既存invoiceアプリと同じパターン）。請求書はA4縦・適格請求書対応。領収書はA4横4面付け。催促状はA4縦シンプルレイアウト。PrintServiceがQPrinterでOS標準印刷ダイアログを呼び出す。PDFはDBの`pdf_path`カラムに保存パスを記録する。

**Tech Stack:** Python 3.11+, ReportLab 4+, PyQt6（QPrinter・QPrintDialog）, Meiryo フォント（Windows）

---

## ファイル構成（新規作成）

```
app/
  services/
    pdf/
      __init__.py
      fonts.py             # フォント登録ユーティリティ
      invoice_pdf.py       # 請求書PDF生成
      receipt_pdf.py       # 領収書PDF生成（A4横4面付け）
      reminder_pdf.py      # 催促状PDF生成
      batch_pdf.py         # 一括PDF生成
    print_service.py       # OS印刷ダイアログ呼び出し
tests/
  test_invoice_pdf.py
  test_receipt_pdf.py
```

---

## Task 1: フォント登録ユーティリティ

**Files:**
- Create: `app/services/pdf/__init__.py`
- Create: `app/services/pdf/fonts.py`

- [ ] **Step 1: fonts.py を作成**

```python
# app/services/pdf/fonts.py
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_NORMAL = "Meiryo"
FONT_BOLD   = "Meiryo-Bold"

_registered = False


def register_fonts() -> None:
    global _registered
    if _registered:
        return
    paths = [
        ("Meiryo",      "C:/Windows/Fonts/meiryo.ttc",  0),
        ("Meiryo-Bold", "C:/Windows/Fonts/meiryob.ttc", 0),
    ]
    for name, path, idx in paths:
        try:
            pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
        except Exception:
            pass
    _registered = True
```

- [ ] **Step 2: コミット**

```bash
git add app/services/pdf/
git commit -m "feat: PDFフォント登録ユーティリティを追加"
```

---

## Task 2: 請求書PDF生成

**Files:**
- Create: `app/services/pdf/invoice_pdf.py`
- Create: `tests/test_invoice_pdf.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_invoice_pdf.py
import os, tempfile
from datetime import date
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.member_service import create_member
from app.services.project_service import (
    create_project, add_template_to_project, add_members_to_project,
    get_project_members
)
from app.services.issuance_service import create_issuance_for_member
from app.database.models import CompanySettings
from app.services.pdf.invoice_pdf import generate_invoice_pdf


def _make_issuance(db_session):
    cat = create_category(db_session, "青年部")
    tmpl = create_item_template(db_session, cat.id, "青年部会費",
                                10000, "式", 0, "invoice", "")
    proj = create_project(db_session, "2026年度 青年部会費", cat.id, 2026, "list")
    add_template_to_project(db_session, proj.id, tmpl.id)
    m = create_member(db_session, member_number="A-001",
                      organization_name="○○商事株式会社",
                      organization_kana="マルマルショウジ",
                      representative_name="田中 太郎")
    add_members_to_project(db_session, proj.id, [m.id])
    pm = get_project_members(db_session, proj.id)[0]
    return create_issuance_for_member(
        db_session, proj.id, pm.id, m, "invoice", 2026, 5)


def test_generate_invoice_pdf(db_session):
    issuance = _make_issuance(db_session)
    company = CompanySettings(
        name="○○商工会議所",
        postal_code="123-4567",
        address="東京都千代田区1-1-1",
        phone="03-1234-5678",
        invoice_reg_number="T1234567890123"
    )
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        result = generate_invoice_pdf(issuance, company, path)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 1000
    finally:
        os.unlink(path)
```

- [ ] **Step 2: テスト実行→失敗確認**

```bash
python -m pytest tests/test_invoice_pdf.py -v
```

- [ ] **Step 3: invoice_pdf.py を作成**

```python
# app/services/pdf/invoice_pdf.py
import os
from datetime import date
from decimal import Decimal
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from app.services.pdf.fonts import register_fonts, FONT_NORMAL, FONT_BOLD

C_BLUE   = HexColor("#1E40AF")
C_LIGHT  = HexColor("#EFF6FF")
C_GRAY   = HexColor("#F8FAFC")
C_BORDER = HexColor("#CBD5E1")
C_TEXT   = HexColor("#1E293B")
C_SUB    = HexColor("#64748B")


def _style(name, font=None, size=10, leading=None, alignment=TA_LEFT,
           color=None, bold=False):
    register_fonts()
    f = font or (FONT_BOLD if bold else FONT_NORMAL)
    return ParagraphStyle(
        name=name, fontName=f, fontSize=size,
        leading=leading or size * 1.4,
        alignment=alignment,
        textColor=color or C_TEXT,
    )


def generate_invoice_pdf(issuance, company, output_path: str,
                          bank_account=None, seal_path: str | None = None) -> str:
    register_fonts()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
    )

    W = A4[0] - 30*mm
    story = []

    # ── タイトル ──
    story.append(Paragraph(
        "請　求　書" if not getattr(issuance, '_reissue', False) else "請　求　書（再発行）",
        _style("title", size=20, bold=True, alignment=TA_CENTER)
    ))
    story.append(Spacer(1, 4*mm))

    # ── 発行番号・日付 ──
    issue_date = getattr(issuance, 'issued_at', None)
    if issue_date:
        date_str = issue_date.strftime("%Y年%m月%d日")
    else:
        date_str = date.today().strftime("%Y年%m月%d日")

    info_data = [
        ["発行番号：", issuance.doc_number, "発行日：", date_str],
    ]
    info_table = Table(info_data, colWidths=[25*mm, 60*mm, 20*mm, 50*mm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), FONT_NORMAL),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("TEXTCOLOR", (0,0), (-1,-1), C_SUB),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 4*mm))

    # ── 宛先 + 発行元 ──
    recipient = (issuance.recipient_organization or "") + (
        f" {issuance.recipient_name}" if issuance.recipient_name else "")
    recipient = recipient.strip() or "　"

    issuer_lines = [
        company.name or "",
        f"〒{company.postal_code}" if company.postal_code else "",
        company.address or "",
        f"TEL {company.phone}" if company.phone else "",
    ]
    if company.invoice_reg_number:
        issuer_lines.append(f"登録番号：{company.invoice_reg_number}")

    addr_data = [
        [
            Paragraph(f"{recipient} 御中",
                      _style("addr", size=13, bold=True)),
            Paragraph("<br/>".join(l for l in issuer_lines if l),
                      _style("issuer", size=8, alignment=TA_RIGHT, color=C_SUB))
        ]
    ]
    addr_table = Table(addr_data, colWidths=[W*0.55, W*0.45])
    addr_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "BOTTOM"),
    ]))
    story.append(addr_table)
    story.append(Spacer(1, 2*mm))

    story.append(HRFlowable(width=W, color=C_BLUE, thickness=2))
    story.append(Spacer(1, 3*mm))

    # ── 合計金額 ──
    total = int(issuance.amount)
    story.append(Paragraph(
        f"ご請求金額：<b>¥{total:,}</b>（税込）",
        _style("total", size=14, bold=True, color=C_BLUE)
    ))
    story.append(Spacer(1, 4*mm))

    # ── 明細テーブル ──
    header = ["品目・摘要", "数量", "単位", "単価", "金額", "税率"]
    rows = [header]
    for line in issuance.lines:
        tax_label = {10: "10%", 8: "8%", 0: "非課税", -1: "不課税"}.get(
            line.tax_rate, f"{line.tax_rate}%")
        rows.append([
            line.item_name,
            str(int(line.quantity)),
            line.unit,
            f"¥{int(line.unit_price):,}",
            f"¥{int(line.line_total):,}",
            tax_label,
        ])

    col_w = [W*0.38, W*0.08, W*0.08, W*0.14, W*0.14, W*0.08]
    detail_table = Table(rows, colWidths=col_w, repeatRows=1)
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_BLUE),
        ("TEXTCOLOR", (0,0), (-1,0), white),
        ("FONTNAME", (0,0), (-1,0), FONT_BOLD),
        ("FONTNAME", (0,1), (-1,-1), FONT_NORMAL),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (1,0), (-1,-1), "CENTER"),
        ("ALIGN", (3,1), (4,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, C_GRAY]),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 3*mm))

    # ── 税率別小計 ──
    tax10_base = sum(int(l.unit_price) * int(l.quantity)
                     for l in issuance.lines if l.tax_rate == 10)
    tax8_base  = sum(int(l.unit_price) * int(l.quantity)
                     for l in issuance.lines if l.tax_rate == 8)
    exempt     = sum(int(l.line_total)
                     for l in issuance.lines if l.tax_rate == 0)
    non_tax    = sum(int(l.line_total)
                     for l in issuance.lines if l.tax_rate == -1)

    subtotal_rows = [["", "小計", "消費税", "合計"]]
    if tax10_base:
        subtotal_rows.append(["10%対象", f"¥{tax10_base:,}",
                               f"¥{int(tax10_base*0.1):,}",
                               f"¥{int(tax10_base*1.1):,}"])
    if tax8_base:
        subtotal_rows.append(["8%対象", f"¥{tax8_base:,}",
                               f"¥{int(tax8_base*0.08):,}",
                               f"¥{int(tax8_base*1.08):,}"])
    if exempt:
        subtotal_rows.append(["非課税", f"¥{exempt:,}", "—", f"¥{exempt:,}"])
    if non_tax:
        subtotal_rows.append(["不課税", f"¥{non_tax:,}", "—", f"¥{non_tax:,}"])
    subtotal_rows.append(["合計", "", "", f"¥{total:,}"])

    sub_col_w = [W*0.2, W*0.2, W*0.2, W*0.2]
    sub_x = W * 0.2
    sub_table = Table(subtotal_rows, colWidths=sub_col_w)
    sub_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), FONT_NORMAL),
        ("FONTNAME", (0,0), (-1,0), FONT_BOLD),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("BACKGROUND", (0,0), (-1,0), C_LIGHT),
        ("BACKGROUND", (0,-1), (-1,-1), C_LIGHT),
        ("FONTNAME", (0,-1), (-1,-1), FONT_BOLD),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))

    right_data = [["", sub_table]]
    right_table = Table(right_data, colWidths=[W*0.2, W*0.8])
    right_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(right_table)
    story.append(Spacer(1, 4*mm))

    # ── 振込先 ──
    if bank_account:
        story.append(HRFlowable(width=W, color=C_BORDER, thickness=0.5))
        story.append(Spacer(1, 2*mm))
        bank_lines = [
            f"【振込先】 {bank_account.bank_name} {bank_account.bank_branch}",
            f"　{bank_account.bank_account_type}　{bank_account.bank_account_number}",
            f"　口座名義：{bank_account.bank_account_name}",
        ]
        for line in bank_lines:
            story.append(Paragraph(line, _style("bank", size=9, color=C_SUB)))

    # ── 備考 ──
    if getattr(issuance, 'notes', None):
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(f"備考：{issuance.notes}",
                                _style("notes", size=8, color=C_SUB)))

    # T番号フッター
    if company.invoice_reg_number:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(
            f"※ 本書は適格請求書（インボイス）です。登録番号：{company.invoice_reg_number}",
            _style("footer", size=7, color=C_SUB)
        ))

    doc.build(story)
    return output_path
```

- [ ] **Step 4: テスト→パス確認**

```bash
python -m pytest tests/test_invoice_pdf.py -v
```

期待: `PASSED`

- [ ] **Step 5: コミット**

```bash
git add app/services/pdf/invoice_pdf.py tests/test_invoice_pdf.py
git commit -m "feat: 請求書PDF生成（適格請求書対応）を追加"
```

---

## Task 3: 領収書PDF生成

**Files:**
- Create: `app/services/pdf/receipt_pdf.py`
- Create: `tests/test_receipt_pdf.py`

- [ ] **Step 1: テストを書く**

```python
# tests/test_receipt_pdf.py
import os, tempfile
from datetime import date
from app.services.category_service import create_category
from app.services.item_template_service import create_item_template
from app.services.project_service import create_project, add_template_to_project
from app.services.issuance_service import create_counter_issuance
from app.database.models import CompanySettings
from app.services.pdf.receipt_pdf import generate_receipt_pdf


def test_generate_receipt_pdf(db_session):
    cat = create_category(db_session, "検定")
    tmpl = create_item_template(db_session, cat.id, "珠算検定受験料",
                                3000, "人", 0, "receipt", "珠算検定受験料として")
    proj = create_project(db_session, "珠算検定", cat.id, 2026, "counter")
    add_template_to_project(db_session, proj.id, tmpl.id)
    issuance = create_counter_issuance(
        db_session, project_id=proj.id,
        recipient_organization="△△そろばん教室",
        recipient_name="", doc_type="receipt",
        quantity=3, fiscal_year=2026, month=5
    )
    company = CompanySettings(
        name="○○商工会議所",
        postal_code="123-4567",
        address="東京都千代田区1-1-1",
        phone="03-1234-5678",
        invoice_reg_number="T1234567890123"
    )
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = f.name
    try:
        result = generate_receipt_pdf(issuance, company, path)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 1000
    finally:
        os.unlink(path)
```

- [ ] **Step 2: テスト実行→失敗確認**

```bash
python -m pytest tests/test_receipt_pdf.py -v
```

- [ ] **Step 3: receipt_pdf.py を作成（A4横4面付け）**

```python
# app/services/pdf/receipt_pdf.py
import os
from datetime import date
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen.canvas import Canvas
from app.services.pdf.fonts import register_fonts, FONT_NORMAL, FONT_BOLD

C_BOX    = HexColor("#E2E8F0")
C_BORDER = HexColor("#475569")
C_BLUE   = HexColor("#1E40AF")
C_GRAY   = HexColor("#64748B")


def _draw_receipt(c: Canvas, issuance, company, x: float, y: float,
                  w: float, h: float, seal_path: str | None = None) -> None:
    """1面分の領収書を描画する（左下を原点とするx,y座標）"""
    pad = 3 * mm

    # 外枠
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(1)
    c.rect(x, y, w, h)

    # タイトル
    c.setFillColor(C_BLUE)
    c.setFont(FONT_BOLD, 16)
    c.drawCentredString(x + w / 2, y + h - 10*mm, "領　収　書")

    # 発行番号・日付
    issue_date = getattr(issuance, 'issued_at', None)
    date_str = issue_date.strftime("%Y年%m月%d日") if issue_date else date.today().strftime("%Y年%m月%d日")
    c.setFillColor(C_GRAY)
    c.setFont(FONT_NORMAL, 7)
    c.drawString(x + pad, y + h - 14*mm, f"No. {issuance.doc_number}")
    c.drawRightString(x + w - pad, y + h - 14*mm, f"発行日：{date_str}")

    # 区切り線
    c.setStrokeColor(C_BLUE)
    c.setLineWidth(1.5)
    c.line(x + pad, y + h - 16*mm, x + w - pad, y + h - 16*mm)

    # 宛名
    recipient = (issuance.recipient_organization or issuance.recipient_name or "").strip()
    c.setFillColor(black)
    c.setFont(FONT_BOLD, 12)
    c.drawString(x + pad, y + h - 24*mm, f"{recipient} 様")

    # 金額
    total = int(issuance.amount)
    c.setFillColor(C_BOX)
    c.rect(x + pad, y + h - 36*mm, w - 2*pad, 10*mm, fill=1, stroke=0)
    c.setFillColor(C_BLUE)
    c.setFont(FONT_BOLD, 14)
    c.drawCentredString(x + w / 2, y + h - 30*mm, f"¥ {total:,} -")

    # 但し書き
    description = ""
    for line in issuance.lines:
        tmpl_desc = getattr(line, 'item_name', "")
        if tmpl_desc:
            description = tmpl_desc
            break
    c.setFillColor(black)
    c.setFont(FONT_NORMAL, 8)
    c.drawString(x + pad, y + h - 40*mm, f"但し　{description}")

    # 区切り線
    c.setStrokeColor(C_BOX)
    c.setLineWidth(0.5)
    c.line(x + pad, y + h - 43*mm, x + w - pad, y + h - 43*mm)

    # 税区分内訳
    cy = y + h - 47*mm
    tax10 = sum(int(l.line_total) for l in issuance.lines if l.tax_rate == 10)
    tax8  = sum(int(l.line_total) for l in issuance.lines if l.tax_rate == 8)
    exempt = sum(int(l.line_total) for l in issuance.lines if l.tax_rate in (0, -1))
    c.setFont(FONT_NORMAL, 7)
    c.setFillColor(C_GRAY)
    if tax10:
        c.drawString(x + pad, cy, f"（10%対象 ¥{int(tax10/1.1):,}  消費税 ¥{tax10-int(tax10/1.1):,}）")
        cy -= 4*mm
    if tax8:
        c.drawString(x + pad, cy, f"（8%対象 ¥{int(tax8/1.08):,}  消費税 ¥{tax8-int(tax8/1.08):,}）")
        cy -= 4*mm
    if exempt:
        c.drawString(x + pad, cy, f"（非課税・不課税 ¥{exempt:,}）")

    # 発行元
    bottom_y = y + 3*mm
    c.setFillColor(black)
    c.setFont(FONT_BOLD, 9)
    c.drawString(x + pad, bottom_y + 16*mm, company.name or "")
    c.setFont(FONT_NORMAL, 7)
    c.setFillColor(C_GRAY)
    for i, line in enumerate([
        f"〒{company.postal_code}  {company.address}",
        f"TEL {company.phone}",
        f"登録番号：{company.invoice_reg_number}" if company.invoice_reg_number else "",
    ]):
        if line:
            c.drawString(x + pad, bottom_y + (10 - i*4)*mm, line)


def generate_receipt_pdf(issuance, company, output_path: str,
                          seal_path: str | None = None,
                          copies: int = 4) -> str:
    register_fonts()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    copies = max(1, min(4, copies))
    page_w, page_h = landscape(A4)
    margin = 5*mm
    gap    = 2*mm
    r_w = (page_w - 2*margin - gap) / 2
    r_h = (page_h - 2*margin - gap) / 2

    scale  = 0.92
    draw_w = r_w * scale
    draw_h = r_h * scale
    ox     = (r_w - draw_w) / 2
    oy     = (r_h - draw_h) / 2

    positions = [
        (margin + ox,           margin + r_h + gap + oy),
        (margin + ox,           margin + oy),
        (margin + r_w + gap + ox, margin + r_h + gap + oy),
        (margin + r_w + gap + ox, margin + oy),
    ]

    c = Canvas(output_path, pagesize=landscape(A4))
    c.setTitle(f"領収書_{issuance.doc_number}")

    for i in range(copies):
        px, py = positions[i]
        _draw_receipt(c, issuance, company, px, py, draw_w, draw_h, seal_path)

    # 切り取り線
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.3)
    c.setDash(4, 3)
    mid_x = margin + r_w + gap / 2
    mid_y = margin + r_h + gap / 2
    c.line(mid_x, margin, mid_x, page_h - margin)
    c.line(margin, mid_y, page_w - margin, mid_y)

    c.save()
    return output_path
```

- [ ] **Step 4: テスト→パス確認**

```bash
python -m pytest tests/test_receipt_pdf.py -v
```

期待: `PASSED`

- [ ] **Step 5: コミット**

```bash
git add app/services/pdf/receipt_pdf.py tests/test_receipt_pdf.py
git commit -m "feat: 領収書PDF生成（A4横4面付け）を追加"
```

---

## Task 4: 催促状PDF生成

**Files:**
- Create: `app/services/pdf/reminder_pdf.py`

- [ ] **Step 1: reminder_pdf.py を作成**

```python
# app/services/pdf/reminder_pdf.py
import os
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from app.services.pdf.fonts import register_fonts, FONT_NORMAL, FONT_BOLD

C_BLUE = HexColor("#1E40AF")
C_SUB  = HexColor("#64748B")


def generate_reminder_pdf(issuance, company, output_path: str,
                           custom_message: str = "") -> str:
    register_fonts()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=25*mm, rightMargin=25*mm,
        topMargin=25*mm, bottomMargin=25*mm,
    )

    def s(name, size=11, bold=False, align=TA_LEFT, color=None):
        return ParagraphStyle(
            name=name,
            fontName=FONT_BOLD if bold else FONT_NORMAL,
            fontSize=size,
            leading=size * 1.6,
            alignment=align,
            textColor=color or black,
        )

    story = []

    issue_date = date.today().strftime("%Y年%m月%d日")
    story.append(Paragraph(issue_date, s("date", size=10, color=C_SUB, align=TA_LEFT)))
    story.append(Spacer(1, 6*mm))

    recipient = (issuance.recipient_organization or issuance.recipient_name or "").strip()
    story.append(Paragraph(f"{recipient} 様", s("recipient", size=13, bold=True)))
    story.append(Spacer(1, 8*mm))

    story.append(Paragraph(
        "お支払いのお願い", s("title", size=18, bold=True, align=TA_CENTER, color=C_BLUE)
    ))
    story.append(HRFlowable(width="100%", color=C_BLUE, thickness=2))
    story.append(Spacer(1, 8*mm))

    proj_name = ""
    if hasattr(issuance, 'project') and issuance.project:
        proj_name = issuance.project.name

    default_msg = (
        f"平素より大変お世話になっております。{company.name or '商工会議所'}でございます。<br/>"
        "<br/>"
        f"下記の件につきまして、いまだお支払いが確認できておりません。<br/>"
        "ご多忙のところ恐れ入りますが、お早めにお手続きいただきますよう、<br/>"
        "何卒よろしくお願い申し上げます。"
    )
    story.append(Paragraph(custom_message or default_msg, s("body", size=11)))
    story.append(Spacer(1, 8*mm))

    # 対象書類情報
    from reportlab.platypus import Table, TableStyle
    info_data = [
        ["書類番号", issuance.doc_number],
        ["事業名", proj_name],
        ["金額", f"¥{int(issuance.amount):,}（税込）"],
    ]
    info_table = Table(info_data, colWidths=[40*mm, 100*mm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), FONT_NORMAL),
        ("FONTNAME", (0,0), (0,-1), FONT_BOLD),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("BACKGROUND", (0,0), (0,-1), HexColor("#EFF6FF")),
        ("GRID", (0,0), (-1,-1), 0.5, HexColor("#CBD5E1")),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10*mm))

    story.append(HRFlowable(width="100%", color=HexColor("#E2E8F0"), thickness=0.5))
    story.append(Spacer(1, 4*mm))

    issuer_lines = [
        company.name or "",
        f"〒{company.postal_code}  {company.address}",
        f"TEL：{company.phone}",
    ]
    for line in issuer_lines:
        if line.strip():
            story.append(Paragraph(line, s("issuer", size=9, color=C_SUB)))

    doc.build(story)
    return output_path
```

- [ ] **Step 2: コミット**

```bash
git add app/services/pdf/reminder_pdf.py
git commit -m "feat: 催促状PDF生成を追加"
```

---

## Task 5: 一括PDF生成・印刷サービス

**Files:**
- Create: `app/services/pdf/batch_pdf.py`
- Create: `app/services/print_service.py`

- [ ] **Step 1: batch_pdf.py を作成**

```python
# app/services/pdf/batch_pdf.py
import os
from app.services.pdf.invoice_pdf import generate_invoice_pdf
from app.services.pdf.receipt_pdf import generate_receipt_pdf
from app.services.project_service import get_project_members, get_project_by_id
from app.services.issuance_service import create_issuance_for_member
from app.database.models import Issuance, CompanySettings, BankAccount
from datetime import date


def generate_batch_pdf(session, project_id: int, company: CompanySettings,
                        output_dir: str,
                        bank_account: BankAccount | None = None) -> list[str]:
    """事業の全会員分PDFを生成してパスのリストを返す"""
    from app.database.models import ProjectTemplate
    pts = session.query(ProjectTemplate).filter_by(project_id=project_id).first()
    doc_type = "receipt" if (pts and pts.item_template.doc_type == "receipt") else "invoice"

    os.makedirs(output_dir, exist_ok=True)
    pms = get_project_members(session, project_id)
    today = date.today()
    generated = []

    for pm in pms:
        iss = (session.query(Issuance)
               .filter_by(project_member_id=pm.id)
               .order_by(Issuance.created_at.desc())
               .first())
        if iss is None:
            m = pm.member
            if not m:
                continue
            iss = create_issuance_for_member(
                session, project_id=project_id,
                project_member_id=pm.id,
                member=m, doc_type=doc_type,
                fiscal_year=today.year, month=today.month
            )
        fname = f"{iss.doc_number}.pdf"
        path = os.path.join(output_dir, fname)
        if doc_type == "invoice":
            generate_invoice_pdf(iss, company, path, bank_account)
        else:
            generate_receipt_pdf(iss, company, path)
        iss.pdf_path = path
        session.commit()
        generated.append(path)

    return generated
```

- [ ] **Step 2: print_service.py を作成**

```python
# app/services/print_service.py
import subprocess
import sys


def print_pdf(pdf_path: str) -> bool:
    """OSの標準機能でPDFを印刷ダイアログに送る"""
    if not pdf_path or not __import__('os').path.exists(pdf_path):
        return False
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.Popen(
                ["rundll32.exe", "C:\\Windows\\System32\\shell32.dll,ShellExec_RunDLL",
                 "print", pdf_path],
                shell=False
            )
        else:
            subprocess.Popen(["lp", pdf_path])
        return True
    except Exception:
        return False


def open_pdf(pdf_path: str) -> bool:
    """PDFをデフォルトビューアで開く"""
    if not pdf_path or not __import__('os').path.exists(pdf_path):
        return False
    try:
        if sys.platform == "win32":
            import os
            os.startfile(pdf_path)
        else:
            subprocess.Popen(["xdg-open", pdf_path])
        return True
    except Exception:
        return False
```

- [ ] **Step 3: コミット**

```bash
git add app/services/pdf/batch_pdf.py app/services/print_service.py
git commit -m "feat: 一括PDF生成・印刷サービスを追加"
```

---

## Task 6: 発行UIへのPDF統合

**Files:**
- Modify: `app/ui/issuance_from_project.py`
- Modify: `app/ui/issuance_counter.py`
- Modify: `app/ui/project_tab.py`

- [ ] **Step 1: PDF生成ヘルパー関数を作成（app/utils/pdf_helpers.py）**

```python
# app/utils/pdf_helpers.py
import os
from app.database.connection import get_session
from app.database.models import CompanySettings, BankAccount


def get_company_and_bank(session=None) -> tuple:
    """発行元情報とデフォルト銀行口座を取得"""
    close = session is None
    if session is None:
        from app.database.connection import get_session as _gs
        session = _gs()
    try:
        company = session.query(CompanySettings).first()
        bank = None
        if company:
            bank = (session.query(BankAccount)
                    .filter_by(company_id=company.id, is_default=True)
                    .first()
                    or session.query(BankAccount)
                    .filter_by(company_id=company.id)
                    .first())
        return company, bank
    finally:
        if close:
            session.close()


def get_pdf_output_dir() -> str:
    """PDF保存先ディレクトリを返す（設定から取得、なければデフォルト）"""
    from app.utils.app_config import get_config
    config = get_config()
    base = config.get("pdf_output_dir", "")
    if not base:
        base = os.path.join(os.path.expanduser("~"), "cci-billing", "pdf")
    os.makedirs(base, exist_ok=True)
    return base


def generate_and_open(issuance, session=None) -> str | None:
    """発行レコードのPDFを生成してビューアで開く。パスを返す。"""
    close = session is None
    if session is None:
        from app.database.connection import get_session as _gs
        session = _gs()
    try:
        company, bank = get_company_and_bank(session)
        if not company:
            return None
        output_dir = get_pdf_output_dir()
        path = os.path.join(output_dir, f"{issuance.doc_number}.pdf")
        if issuance.doc_type == "invoice":
            from app.services.pdf.invoice_pdf import generate_invoice_pdf
            generate_invoice_pdf(issuance, company, path, bank)
        else:
            from app.services.pdf.receipt_pdf import generate_receipt_pdf
            generate_receipt_pdf(issuance, company, path)
        issuance.pdf_path = path
        session.commit()
        from app.services.print_service import open_pdf
        open_pdf(path)
        return path
    finally:
        if close:
            session.close()
```

- [ ] **Step 2: issuance_from_project.py の `_issue` メソッドを更新**

`app/ui/issuance_from_project.py` の `_issue` メソッド内の `QMessageBox.information` の部分を以下に変更する：

```python
def _issue(self):
    sel = self._selected_pm()
    if sel is None:
        return
    pm_id, issuance_id = sel
    if issuance_id is None:
        QMessageBox.warning(self, "エラー", "先に「準備（採番）」を行ってください。")
        return
    delivery = self._delivery_combo.currentText()
    session = get_session()
    try:
        from app.database.models import Issuance
        iss = session.get(Issuance, issuance_id)
        if iss and iss.status == "発行済み":
            # 再発行：PDFを開くのみ
            if iss.pdf_path and __import__('os').path.exists(iss.pdf_path):
                from app.services.print_service import open_pdf
                open_pdf(iss.pdf_path)
            else:
                from app.utils.pdf_helpers import generate_and_open
                generate_and_open(iss, session)
            return
        mark_as_issued(session, issuance_id,
                       staff_id=current_user.get_id(),
                       staff_name=current_user.get_name(),
                       delivery_method=delivery)
        iss = session.get(Issuance, issuance_id)
        from app.utils.pdf_helpers import generate_and_open
        generate_and_open(iss, session)
    finally:
        session.close()
    self._load_members()
```

- [ ] **Step 3: issuance_counter.py の `_issue` メソッドを更新**

`app/ui/issuance_counter.py` の `_issue` メソッドの `session.commit()` の後に追加：

```python
            from app.utils.pdf_helpers import generate_and_open
            generate_and_open(iss, session)
```

`QMessageBox.information` の行を削除する。

- [ ] **Step 4: project_tab.py に「一括PDF生成」ボタンを追加**

`app/ui/project_tab.py` の `btn_row2` に追加：

```python
btn_batch_pdf = QPushButton("一括PDF生成")
btn_batch_pdf.clicked.connect(self._batch_pdf)
btn_row2.addWidget(btn_batch_pdf)
```

`_batch_pdf` メソッドを追加：

```python
def _batch_pdf(self):
    pid = self._selected_project_id()
    if pid is None:
        return
    session = get_session()
    try:
        from app.utils.pdf_helpers import get_company_and_bank, get_pdf_output_dir
        from app.services.pdf.batch_pdf import generate_batch_pdf
        company, bank = get_company_and_bank(session)
        if not company:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "エラー", "発行元情報が設定されていません。")
            return
        output_dir = get_pdf_output_dir()
        from PyQt6.QtWidgets import QMessageBox
        paths = generate_batch_pdf(session, pid, company, output_dir, bank)
        QMessageBox.information(self, "完了",
                                f"{len(paths)} 件のPDFを生成しました。\n保存先：{output_dir}")
    except Exception as e:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "エラー", str(e))
    finally:
        session.close()
```

- [ ] **Step 5: 全テスト確認**

```bash
python -m pytest tests/ -v
```

期待: 全テスト PASSED

- [ ] **Step 6: コミット**

```bash
git add app/utils/pdf_helpers.py app/ui/issuance_from_project.py
git add app/ui/issuance_counter.py app/ui/project_tab.py
git commit -m "feat: 発行UIにPDF生成・表示を統合 — Plan 3 完了"
```

---

## Plan 3 完了チェックリスト

- [ ] `python -m pytest tests/ -v` で全テストがパス
- [ ] 発行フロー①で「発行する」を押すとPDFが生成されてビューアで開く
- [ ] 発行フロー③（窓口型）でPDFが生成される
- [ ] 事業管理の「一括PDF生成」で全会員分PDFが生成される
- [ ] 請求書PDFにT番号（登録番号）が印字される
- [ ] 領収書PDFがA4横4面付けで生成される

---

**次のステップ：** Plan 4「メール・レポート・年度更新・バックアップ」
