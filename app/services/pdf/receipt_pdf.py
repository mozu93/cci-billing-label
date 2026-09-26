# app/services/pdf/receipt_pdf.py
"""
領収書 PDF 生成
  通常: A5縦（1事業所）・上=原本 / 下=控え
  メール添付用: A6横・原本のみ
"""
import os
from datetime import date as date_type
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from app.services.pdf.fonts import register_fonts, FONT_NORMAL, FONT_BOLD
from app.services.pdf.seal_image import seal_image_reader
from app.utils.applog import get_logger

_log = get_logger(__name__)

C_GRAY_BOX   = HexColor("#D8D8D8")
C_BORDER     = HexColor("#555555")
C_LINE       = HexColor("#888888")
C_STAMP_LINE = HexColor("#AAAAAA")
C_CUT_LINE   = HexColor("#BBBBBB")
C_TEXT_SUB   = HexColor("#555555")


def _seal_source(seal_image):
    return seal_image_reader(seal_image)


def generate_receipt_pdf(issuance, company, output_path: str,
                          seal_image=None, copies: int = 4,
                          reissue: bool = False,
                          include_copy: bool = True) -> str:
    register_fonts()
    parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent, exist_ok=True)

    # 原本1面はA6横。通常はA5縦へ原本と控えを上下に配置する。
    page_w, page_h = A5 if include_copy else (A5[0], A5[1] / 2)
    margin = 3 * mm
    slot_h = page_h / 2 if include_copy else page_h
    draw_w = page_w - 2 * margin
    draw_h = slot_h - 2 * margin

    c = Canvas(output_path, pagesize=(page_w, page_h))
    c.setTitle(f"領収書_{issuance.doc_number}")
    c.setAuthor(getattr(company, "name", "") or "")

    # 原本
    _draw_one(c, issuance, company, seal_image,
              margin, slot_h + margin if include_copy else margin,
              draw_w, draw_h,
              is_copy=False, reissue=reissue)

    if include_copy:
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


def generate_receipt_originals_pdf(issuances: list, company, output_path: str,
                                   seal_image=None) -> str:
    """控え不要のとき、原本だけをA5用紙に2件（上下）ずつ詰めて印刷する。

    件数が奇数の場合、最後のページは下段を空けたまま出力する。"""
    register_fonts()
    parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent, exist_ok=True)

    page_w, page_h = A5
    margin = 3 * mm
    slot_h = page_h / 2
    draw_w = page_w - 2 * margin
    draw_h = slot_h - 2 * margin

    c = Canvas(output_path, pagesize=(page_w, page_h))
    c.setAuthor(getattr(company, "name", "") or "")

    n_pages = (len(issuances) + 1) // 2
    for page_idx in range(n_pages):
        top_iss = issuances[page_idx * 2]
        bottom_iss = (issuances[page_idx * 2 + 1]
                     if page_idx * 2 + 1 < len(issuances) else None)
        c.setTitle(f"領収書_{top_iss.doc_number}")
        _draw_one(c, top_iss, company, seal_image,
                  margin, slot_h + margin, draw_w, draw_h, is_copy=False)
        if bottom_iss is not None:
            _draw_one(c, bottom_iss, company, seal_image,
                      margin, margin, draw_w, draw_h, is_copy=False)
        if page_idx < n_pages - 1:
            c.showPage()

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

    TITLE_H = 13.0 * mm
    NAME_H  = 11.0 * mm
    AMT_H   = 14.0 * mm
    UEKI_H  = 7.0 * mm
    SEP_GAP = 5.0 * mm

    # ── 但し書きの折り返し行数を先に決める（内容量から縦位置を決めるため） ──
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
        for tada_fs in (10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5, 6):
            prefix_w = stringWidth(tada_label, FONT_NORMAL, tada_fs)
            d_lines  = _wrap_to_lines(desc, FONT_NORMAL, tada_fs, avail_w - prefix_w)
            if len(d_lines) <= 2:
                break
        else:
            tada_fs = 6.0
            prefix_w = stringWidth(tada_label, FONT_NORMAL, tada_fs)
            d_lines  = _wrap_to_lines(desc, FONT_NORMAL, tada_fs, avail_w - prefix_w)[:2]
    else:
        tada_fs, d_lines = 10, []
        prefix_w = stringWidth(tada_label, FONT_NORMAL, tada_fs)

    TADA_LINE_H = 6.5 * mm
    tada_n_lines = max(1, len(d_lines))
    TADA_H = TADA_LINE_H * tada_n_lines

    # ── 枠の上下中央に近づける：内容量に対して枠が広いぶんを
    #    上下に等分の余白として振り分ける（狭いときは詰めて崩れないようにする） ──
    top_block_h = TM + TITLE_H + NAME_H + AMT_H + TADA_H + UEKI_H + SEP_GAP
    lower_natural_h = max(
        _naiwa_row_count(inv_lines) * 5.0 * mm,
        _company_info_natural_height(company, seal_image))
    slack = h - top_block_h - lower_natural_h
    shift = max(0.0, slack / 2)

    cur = top - TM - shift

    # ── タイトル + No. + 発行日 ───────────────────────────
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
    cur -= NAME_H

    recipient = (issuance.recipient_organization or issuance.recipient_name or "").strip()
    name_rx   = x0 + w * 0.75
    name_line_lx = x0 + P
    name_line_rx = name_line_lx + (name_rx - 5 * mm - name_line_lx) * 0.8
    _line(c, name_line_lx, cur + NAME_H * 0.25,
          name_line_rx, cur + NAME_H * 0.25, black, 0.5)

    name_max_w = name_line_rx - (x0 + P + 2 * mm)
    name_fs    = 14
    while name_fs > 6 and stringWidth(recipient, FONT_NORMAL, name_fs) > name_max_w:
        name_fs -= 0.5
    c.setFillColor(black)
    c.setFont(FONT_NORMAL, name_fs)
    c.drawString(x0 + P + 2 * mm, cur + NAME_H * 0.38, recipient)
    if recipient:
        c.setFont(FONT_NORMAL, 14)
        c.drawString(name_rx - 4.5 * mm, cur + NAME_H * 0.33, "様")

    # ── 金額 + 収入印紙枠 ─────────────────────────────────
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

    # ── 但し書き（行数・フォントサイズは冒頭で計算済み） ──────────
    cur -= TADA_H

    c.setFillColor(black)
    c.setFont(FONT_NORMAL, tada_fs)
    content_x = text_x + prefix_w

    if not d_lines:
        c.drawString(text_x, cur + TADA_LINE_H * 0.28, tada_label)
    else:
        for i, line in enumerate(d_lines):
            y = cur + TADA_LINE_H * (tada_n_lines - 1 - i + 0.28)
            if i == 0:
                c.drawString(text_x, y, tada_label)
                c.drawString(content_x, y, line)
            else:
                c.drawString(content_x, y, line)

    # ── 上記正に領収いたしました ──────────────────────────
    cur   -= UEKI_H
    c.setFont(FONT_NORMAL, 9.5)
    c.drawString(x0 + P + INDENT, cur + UEKI_H * 0.32, "上記正に領収いたしました")

    # 区切り線
    cur -= SEP_GAP
    _line(c, x0, cur, x0 + w, cur, C_LINE, 0.5)

    # ── 内訳（左） + 会社情報・印鑑（右） ────────────────
    # 内容量ぶんの高さだけを使い、余った分は下側にも均等に残す（上下中央寄せ）
    section_top = cur
    content_y0  = y0 + shift
    left_w  = w * 0.39
    right_w = w - left_w
    # 区切り線は枠の底（y0）まで届かせ、内容が中央寄りでも枠が途切れて
    # 見えないようにする
    _line(c, x0 + left_w, y0, x0 + left_w, section_top, C_LINE, 0.4)

    _draw_naiwa(c, issuance, x0, content_y0, left_w, section_top)
    _draw_company_info(c, company, seal_image,
                       x0 + left_w, content_y0, right_w, section_top)

    if not recipient:
        # 枠内を圧迫しないよう、枠の外側（用紙の余白）に注記する。
        # 和文フォントは字面（アセント）が大きく、下線ぎりぎりだと枠と重なるため
        # ベースラインを字の高さ分下げる
        c.setFont(FONT_NORMAL, 6)
        c.setFillColor(C_TEXT_SUB)
        c.drawString(x0 + P, y0 - 2.2 * mm, "※簡易インボイス")
        c.setFillColor(black)

    c.restoreState()


# ── 内訳テーブル（左側） ─────────────────────────────────

def _naiwa_row_count(lines) -> int:
    """内訳テーブルの行数（見出し1行 + 税率ごとの内訳2行×該当税率数 + 課税対象外1行）。"""
    tax10 = sum(int(l.line_total) for l in lines if l.tax_rate == 10)
    tax8  = sum(int(l.line_total) for l in lines if l.tax_rate == 8)
    exempt = sum(int(l.line_total) for l in lines if l.tax_rate in (0, -1))
    n = 1
    if tax10 > 0: n += 2
    if tax8  > 0: n += 2
    if exempt > 0: n += 1
    return n


def _draw_naiwa(c, issuance, x0, y0, w, top):
    P = 1.5 * mm

    lines = getattr(issuance, "lines", []) or []
    # 税額は請求書（invoice_pdf）と同じく、税率ごとに1回・整数で切り捨てる。
    # 税抜額を先に切り捨てて差し引くと税額が実質切り上げになり、請求書と1円ずれる
    tax10_incl = sum(int(l.line_total) for l in lines if l.tax_rate == 10)
    tax10_amt  = tax10_incl * 10 // 110

    tax8_incl  = sum(int(l.line_total) for l in lines if l.tax_rate == 8)
    tax8_amt   = tax8_incl * 8 // 108

    exempt = sum(int(l.line_total) for l in lines if l.tax_rate in (0, -1))

    n_rows = _naiwa_row_count(lines)
    ROW = min(5.0 * mm, (top - y0) / max(n_rows, 1))
    # 行数が少なく空きができる場合は、枠の途中で切れて見えないよう
    # テーブルごと欄の上下中央に寄せる
    leftover = (top - y0) - ROW * n_rows
    cur = top - max(0.0, leftover / 2)

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
        c.drawString(COL_TAX, cur + ROW * 0.28, f"うち{rate_label}税額")
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

def _company_info_natural_height(company, seal_image) -> float:
    """会社情報ブロックの自然な高さ（_draw_company_info の縦位置決めと同じ計算）。"""
    LINE_H = 5.0 * mm
    co_name   = getattr(company, "name",             "") or ""
    co_postal = getattr(company, "postal_code",       "") or ""
    co_addr   = getattr(company, "address",           "") or ""
    co_phone  = getattr(company, "phone",             "") or ""
    co_reg    = getattr(company, "invoice_reg_number", "") or ""
    has_seal  = _seal_source(seal_image) is not None

    used = 1.5 * mm
    if co_reg:
        used += LINE_H
    if co_name:
        used += LINE_H * 1.3
    if co_postal:
        used += LINE_H
    if co_addr:
        max_c = 15
        n = 0
        remaining = co_addr
        while remaining:
            n += 1
            remaining = remaining[max_c:]
        used += LINE_H * 0.9 * n
    if co_phone:
        used += LINE_H
    seal_reserve = 24.5 * mm if has_seal else 0.0
    return max(used, seal_reserve)


def _draw_company_info(c, company, seal_image, x0, y0, w, top):
    P      = 2.0 * mm
    LINE_H = 5.0 * mm

    co_name   = getattr(company, "name",             "") or ""
    co_postal = getattr(company, "postal_code",       "") or ""
    co_addr   = getattr(company, "address",           "") or ""
    co_phone  = getattr(company, "phone",             "") or ""
    co_reg    = getattr(company, "invoice_reg_number", "") or ""
    _seal_src = _seal_source(seal_image)
    has_seal = _seal_src is not None

    cur = top - 1.5 * mm

    if co_reg:
        c.setFont(FONT_NORMAL, 9)
        c.setFillColor(C_TEXT_SUB)
        cur -= LINE_H
        c.drawString(x0 + P, cur, f"登録番号　{co_reg}")
        c.setFillColor(black)

    if co_name:
        if has_seal:
            seal_left  = x0 + w - 22.5 * mm - P - 2 * mm
            name_max_w = seal_left - (x0 + P) - 2 * mm
        else:
            name_max_w = w - 2 * P
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
    if has_seal:
        seal_y = max(phone_bottom_y, y0 + 1 * mm)
        sz = min(22.5 * mm, top - seal_y - 1 * mm, w - 2 * mm)
        if sz > 4 * mm:
            try:
                c.drawImage(_seal_src,
                            x0 + w - sz - P - 2 * mm, seal_y - 2 * mm,
                            sz, sz, mask="auto", preserveAspectRatio=True)
            except Exception:
                _log.warning("領収書の印影描画に失敗", exc_info=True)


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
