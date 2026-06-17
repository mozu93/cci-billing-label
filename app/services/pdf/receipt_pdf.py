# app/services/pdf/receipt_pdf.py
"""
領収書 PDF 生成
  A5縦（1事業所）: 上=原本 / 下=控え
"""
import os
from datetime import date as date_type
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from app.services.pdf.fonts import register_fonts, FONT_NORMAL, FONT_BOLD

C_GRAY_BOX   = HexColor("#D8D8D8")
C_BORDER     = HexColor("#555555")
C_LINE       = HexColor("#888888")
C_STAMP_LINE = HexColor("#AAAAAA")
C_CUT_LINE   = HexColor("#BBBBBB")
C_TEXT_SUB   = HexColor("#555555")


def generate_receipt_pdf(issuance, company, output_path: str,
                          seal_image=None, copies: int = 4,
                          reissue: bool = False) -> str:
    register_fonts()
    parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent, exist_ok=True)

    # A5縦（148mm × 210mm）
    page_w, page_h = A5
    margin = 3 * mm
    slot_h = page_h / 2        # 上下2等分（各A6高さ）
    draw_w = page_w - 2 * margin
    draw_h = slot_h - 2 * margin

    c = Canvas(output_path, pagesize=A5)
    c.setTitle(f"領収書_{issuance.doc_number}")
    c.setAuthor(getattr(company, "name", "") or "")

    # 上：原本
    _draw_one(c, issuance, company, seal_image,
              margin, slot_h + margin, draw_w, draw_h,
              is_copy=False, reissue=reissue)

    # 下：控え
    _draw_one(c, issuance, company, seal_image,
              margin, margin, draw_w, draw_h,
              is_copy=True, reissue=reissue)

    # 切り取り線（中央水平）
    c.saveState()
    c.setStrokeColor(C_CUT_LINE)
    c.setLineWidth(0.4)
    c.setDash([3, 3], 0)
    c.line(margin, slot_h, page_w - margin, slot_h)
    c.restoreState()

    c.save()
    return output_path


# ── 1面を描画 ─────────────────────────────────────────────

def _draw_one(c, issuance, company, seal_image, x0, y0, w, h,
              is_copy=False, reissue=False):
    c.saveState()

    P      = 2.0 * mm
    TM     = 2.0 * mm
    INDENT = 11.0 * mm

    # 外枠
    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.6)
    c.rect(x0, y0, w, h)

    top = y0 + h
    cur = top - TM

    # ── タイトル + No. + 発行日 ───────────────────────────
    TITLE_H = 13.0 * mm
    cur -= TITLE_H

    c.setFillColor(black)
    c.setFont(FONT_BOLD, 16)
    c.drawString(x0 + P * 2, cur + TITLE_H * 0.50, "領 　収 　書")
    if reissue:
        c.setFont(FONT_NORMAL, 9)
        c.drawString(x0 + P * 2 + 39 * mm, cur + TITLE_H * 0.50, "（再発行）")

    # 控えラベル（右上）
    if is_copy:
        c.setFont(FONT_NORMAL, 9)
        c.setFillColor(C_TEXT_SUB)
        c.drawRightString(x0 + w - P, cur + TITLE_H * 0.85, "（控え）")
        c.setFillColor(black)

    doc_num  = issuance.doc_number or ""
    no_lx    = x0 + w * 0.60
    no_rx    = x0 + w - P
    c.setFont(FONT_NORMAL, 9)
    c.setFillColor(C_TEXT_SUB)
    c.drawString(no_lx, cur + TITLE_H * 0.85, f"No.　{doc_num}")
    _line(c, no_lx, cur + TITLE_H * 0.72, no_rx, cur + TITLE_H * 0.72, C_LINE, 0.4)

    issue_dt = getattr(issuance, "issued_at", None)
    issue_d  = issue_dt.date() if issue_dt else date_type.today()
    yr, mo, dy = str(issue_d.year), str(issue_d.month), str(issue_d.day)
    c.setFont(FONT_NORMAL, 9)
    c.setFillColor(black)
    _d = no_lx + 14 * mm
    c.drawString(no_lx,        cur + TITLE_H * 0.25, "発行日：")
    c.drawString(_d,           cur + TITLE_H * 0.25, yr)
    c.drawString(_d + 11 * mm, cur + TITLE_H * 0.25, "年")
    c.drawString(_d + 16 * mm, cur + TITLE_H * 0.25, mo)
    c.drawString(_d + 20 * mm, cur + TITLE_H * 0.25, "月")
    c.drawString(_d + 25 * mm, cur + TITLE_H * 0.25, dy)
    c.drawString(_d + 29 * mm, cur + TITLE_H * 0.25, "日")

    # ── 宛名 ─────────────────────────────────────────────
    NAME_H = 11.0 * mm
    cur -= NAME_H

    recipient = (issuance.recipient_organization or issuance.recipient_name or "").strip()
    name_rx   = x0 + w * 0.75
    _line(c, x0 + P, cur + NAME_H * 0.25,
          name_rx - 5 * mm, cur + NAME_H * 0.25, black, 0.5)

    name_max_w = (name_rx - 5 * mm) - (x0 + P + 2 * mm)
    name_fs    = 14
    while name_fs > 6 and stringWidth(recipient, FONT_NORMAL, name_fs) > name_max_w:
        name_fs -= 0.5
    c.setFillColor(black)
    c.setFont(FONT_NORMAL, name_fs)
    c.drawString(x0 + P + 2 * mm, cur + NAME_H * 0.38, recipient)
    c.setFont(FONT_NORMAL, 14)
    c.drawString(name_rx - 4.5 * mm, cur + NAME_H * 0.33, "様")

    # ── 金額 + 収入印紙枠 ─────────────────────────────────
    AMT_H = 14.0 * mm
    cur  -= AMT_H

    amount  = int(issuance.amount or 0)
    amt_str = f"{amount:,}円"
    amt_sw  = stringWidth(amt_str, FONT_BOLD, 14)

    box_h    = AMT_H - 2.5 * mm
    box_y    = cur + 1.2 * mm
    baseline = box_y + box_h * 0.35

    # 金額ブロック（ラベル・¥・数字・グレーボックス）全体を中央寄りへシフト
    AMT_SHIFT = 12 * mm

    # 「金額」ラベル ── 数字と下端をそろえる
    c.setFont(FONT_NORMAL, 13)
    c.setFillColor(black)
    c.drawString(x0 + P + 11 * mm + AMT_SHIFT, baseline, "金額")

    # ¥・数値の絶対 x 位置（元のボックス基準から計算）
    yen_abs_x = x0 + 22.5 * mm + 12 * mm + AMT_SHIFT   # = x0 + 34.5mm + shift
    num_abs_x = x0 + 22.5 * mm + 18 * mm + AMT_SHIFT   # = x0 + 40.5mm + shift

    # グレーボックス：左余白 20% 削除・右余白 50% 削除
    orig_right_edge = x0 + 22.5 * mm + w * 0.60 + AMT_SHIFT
    right_gray = max(0.0, orig_right_edge - (num_abs_x + amt_sw))
    box_x = yen_abs_x - 12 * mm * 0.80     # 左余白 12mm → 9.6mm
    box_w = (num_abs_x + amt_sw + right_gray * 0.50) - box_x

    c.setFillColor(C_GRAY_BOX)
    c.rect(box_x, box_y, box_w, box_h, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont(FONT_NORMAL, 14)
    c.drawString(yen_abs_x, box_y + box_h * 0.38, "¥")
    c.setFont(FONT_BOLD, 14)
    c.drawString(num_abs_x, baseline, amt_str)

    # 収入印紙枠
    stamp_w = 18 * mm
    stamp_h = box_h * 1.3
    stamp_x = x0 + w - stamp_w - P - 5 * mm   # 右端から 3mm 追加で左へ
    stamp_y = box_y - (stamp_h - box_h) + 2 * mm
    c.setStrokeColor(C_STAMP_LINE)
    c.setLineWidth(0.5)
    c.setDash([2, 2], 0)
    c.rect(stamp_x, stamp_y, stamp_w, stamp_h, fill=0, stroke=1)
    c.setDash([], 0)
    c.setFont(FONT_NORMAL, 7)
    c.setFillColor(C_TEXT_SUB)
    c.drawCentredString(stamp_x + stamp_w / 2, stamp_y + stamp_h * 0.72, "印紙税法")
    c.drawCentredString(stamp_x + stamp_w / 2, stamp_y + stamp_h * 0.46, "により")
    c.drawCentredString(stamp_x + stamp_w / 2, stamp_y + stamp_h * 0.20, "非課税")

    # ── 但し書き ──────────────────────────────────────────
    inv_lines = getattr(issuance, "lines", []) or []

    def _breakdown(l) -> str:
        price = int(l.unit_price or 0)
        qty   = float(l.quantity or 1)
        qty_s = str(int(qty)) if qty == int(qty) else str(qty)
        unit  = (l.unit or "").strip()
        return f"@{price:,}×{qty_s}{unit}"

    def _item(l) -> str:
        name = l.item_name or ""
        return f"{name}（{_breakdown(l)}）"

    if len(inv_lines) == 1:
        desc = _item(inv_lines[0]) + "として"
    elif len(inv_lines) > 1:
        parts = "、".join(_item(l) for l in inv_lines if l.item_name)
        desc = (parts or "別紙のとおり") + "として"
    else:
        desc = ""

    tada_label = "但し、"
    text_x     = x0 + P + INDENT
    avail_w    = (x0 + w - P) - text_x

    if desc:
        for fs in (10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5, 6):
            prefix_w = stringWidth(tada_label, FONT_NORMAL, fs)
            d_lines  = _wrap_to_lines(desc, FONT_NORMAL, fs, avail_w - prefix_w)
            if len(d_lines) <= 2:
                break
        else:
            fs = 6.0
            prefix_w = stringWidth(tada_label, FONT_NORMAL, fs)
            d_lines  = _wrap_to_lines(desc, FONT_NORMAL, fs, avail_w - prefix_w)[:2]
    else:
        fs, d_lines = 10, []
        prefix_w = stringWidth(tada_label, FONT_NORMAL, fs)

    LINE_H  = 6.5 * mm
    n_lines = max(1, len(d_lines))
    TADA_H  = LINE_H * n_lines
    cur    -= TADA_H

    c.setFillColor(black)
    c.setFont(FONT_NORMAL, fs)
    content_x = text_x + prefix_w

    if not d_lines:
        c.drawString(text_x, cur + LINE_H * 0.28, tada_label)
    else:
        for i, line in enumerate(d_lines):
            y = cur + LINE_H * (n_lines - 1 - i + 0.28)
            if i == 0:
                c.drawString(text_x, y, tada_label)
                c.drawString(content_x, y, line)
            else:
                c.drawString(content_x, y, line)

    # ── 上記正に領収いたしました ──────────────────────────
    UEKI_H = 7.0 * mm
    cur   -= UEKI_H
    c.setFont(FONT_NORMAL, 9.5)
    c.drawString(x0 + P + INDENT, cur + UEKI_H * 0.32, "上記正に領収いたしました")

    # 区切り線
    cur -= 5.0 * mm
    _line(c, x0, cur, x0 + w, cur, C_LINE, 0.5)

    # ── 内訳（左） + 会社情報・印鑑（右） ────────────────
    section_top = cur
    left_w  = w * 0.39
    right_w = w - left_w
    _line(c, x0 + left_w, y0, x0 + left_w, section_top, C_LINE, 0.4)

    _draw_naiwa(c, issuance, x0, y0, left_w, section_top)
    _draw_company_info(c, company, seal_image,
                       x0 + left_w, y0, right_w, section_top)

    c.restoreState()


# ── 内訳テーブル（左側） ─────────────────────────────────

def _draw_naiwa(c, issuance, x0, y0, w, top):
    P = 1.5 * mm

    lines = getattr(issuance, "lines", []) or []
    tax10_incl = sum(int(l.line_total) for l in lines if l.tax_rate == 10)
    tax10_base = int(tax10_incl / 1.1)
    tax10_amt  = tax10_incl - tax10_base

    tax8_incl  = sum(int(l.line_total) for l in lines if l.tax_rate == 8)
    tax8_base  = int(tax8_incl / 1.08)
    tax8_amt   = tax8_incl - tax8_base

    exempt = sum(int(l.line_total) for l in lines if l.tax_rate in (0, -1))

    n_rows = 1
    if tax10_incl > 0: n_rows += 2
    if tax8_incl  > 0: n_rows += 2
    if exempt     > 0: n_rows += 1
    ROW = min(5.0 * mm, (top - y0) / max(n_rows, 1))

    cur = top

    cur -= ROW
    c.setFillColor(black)
    c.setFont(FONT_NORMAL, 10)
    c.drawString(x0 + P, cur + ROW * 0.28, "内　訳")
    _line(c, x0, cur, x0 + w, cur, C_LINE, 0.4)

    COL_TAX = x0 + P + 3 * mm
    COL_AMT = x0 + w - P

    def _tax_rows(rate_label, incl, tax):
        nonlocal cur
        cur -= ROW
        c.setFont(FONT_NORMAL, 9)
        c.setFillColor(C_TEXT_SUB)
        c.drawString(COL_TAX, cur + ROW * 0.28, f"{rate_label}対象")
        c.setFillColor(black)
        c.drawRightString(COL_AMT, cur + ROW * 0.28, f"{incl:,}円")
        _line(c, x0, cur, x0 + w, cur, C_LINE, 0.3)
        cur -= ROW
        c.setFillColor(C_TEXT_SUB)
        c.drawString(COL_TAX, cur + ROW * 0.28, "うち消費税")
        c.setFillColor(black)
        c.drawRightString(COL_AMT, cur + ROW * 0.28, f"{tax:,}円")
        _line(c, x0, cur, x0 + w, cur, C_LINE, 0.3)

    if tax10_incl > 0:
        _tax_rows("10%", tax10_incl, tax10_amt)
    if tax8_incl > 0:
        _tax_rows("8%", tax8_incl, tax8_amt)

    if exempt > 0:
        cur -= ROW
        c.setFont(FONT_NORMAL, 9)
        c.setFillColor(C_TEXT_SUB)
        c.drawString(COL_TAX, cur + ROW * 0.28, "課税対象外")
        c.setFillColor(black)
        c.drawRightString(COL_AMT, cur + ROW * 0.28, f"{exempt:,}円")
        _line(c, x0, cur, x0 + w, cur, C_LINE, 0.3)


# ── 会社情報 + 印鑑（右側） ──────────────────────────────

def _draw_company_info(c, company, seal_image, x0, y0, w, top):
    P      = 2.0 * mm
    LINE_H = 5.0 * mm

    co_name   = getattr(company, "name",             "") or ""
    co_postal = getattr(company, "postal_code",       "") or ""
    co_addr   = getattr(company, "address",           "") or ""
    co_phone  = getattr(company, "phone",             "") or ""
    co_reg    = getattr(company, "invoice_reg_number", "") or ""

    cur = top - 1.5 * mm

    if co_reg:
        c.setFont(FONT_NORMAL, 9)
        c.setFillColor(C_TEXT_SUB)
        cur -= LINE_H
        c.drawString(x0 + P, cur, f"登録番号　{co_reg}")
        c.setFillColor(black)

    if co_name:
        seal_left   = x0 + w - 22.5 * mm - P - 2 * mm   # 印鑑位置に合わせ 3mm 左へ
        name_max_w  = seal_left - (x0 + P) - 2 * mm
        name_fs     = 11
        while name_fs > 6 and stringWidth(co_name, FONT_BOLD, name_fs) > name_max_w:
            name_fs -= 0.5
        c.setFont(FONT_BOLD, name_fs)
        c.setFillColor(black)
        cur -= LINE_H * 1.3
        c.drawString(x0 + P, cur, co_name)

    c.setFont(FONT_NORMAL, 9)
    if co_postal:
        cur -= LINE_H
        c.drawString(x0 + P, cur, f"〒{co_postal}")

    if co_addr:
        max_c = 15
        while co_addr:
            cur -= LINE_H * 0.9
            c.drawString(x0 + P, cur, co_addr[:max_c])
            co_addr = co_addr[max_c:]

    if co_phone:
        cur -= LINE_H
        c.drawString(x0 + P, cur, f"TEL　{co_phone}")

    phone_bottom_y = cur

    # 印鑑
    if seal_image and getattr(seal_image, "path", None) and os.path.exists(seal_image.path):
        seal_y = max(phone_bottom_y, y0 + 1 * mm)
        sz = min(22.5 * mm, top - seal_y - 1 * mm, w - 2 * mm)
        if sz > 4 * mm:
            try:
                c.drawImage(seal_image.path,
                            x0 + w - sz - P - 2 * mm, seal_y - 2 * mm,   # 3mm 左へ
                            sz, sz, mask="auto", preserveAspectRatio=True)
            except Exception:
                pass


# ── ユーティリティ ────────────────────────────────────────

def _line(c, x1, y1, x2, y2, color, width=0.4):
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)
    c.restoreState()


def _wrap_to_lines(text: str, font: str, fs: float, max_w: float) -> list[str]:
    """テキストを max_w 幅で折り返した行リストを返す（文字単位グリージー）"""
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        if stringWidth(test, font, fs) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def _fit_tada(text: str, font: str, avail_w: float) -> tuple[float, list[str]]:
    """但し書きテキストを最大2行に収まる最大フォントサイズと行リストを返す"""
    for fs in (10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5, 6):
        lines = _wrap_to_lines(text, font, fs, avail_w)
        if len(lines) <= 2:
            return fs, lines
    return 6.0, _wrap_to_lines(text, font, 6.0, avail_w)[:2]
