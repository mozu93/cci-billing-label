# app/services/pdf/invoice_pdf.py
import os
import calendar as _cal
import unicodedata
from datetime import date as _date
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
    Flowable,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from app.services.pdf.fonts import register_fonts, FONT_NORMAL, FONT_BOLD
from app.services.pdf.seal_image import seal_image_reader

# ── 白黒カラー ──────────────────────────────────────────────
C_BLACK  = HexColor("#1A1A1A")
C_DARK   = HexColor("#333333")
C_BORDER = HexColor("#888888")
C_LIGHT  = HexColor("#EEEEEE")
C_PALE   = HexColor("#F8F8F8")
ISSUER_NAME_INDENT_CHARS = 8
ISSUER_SEAL_INDENT_CHARS = 2
ISSUER_SEAL_SIZE = 25 * mm
ISSUER_SEAL_GAP = 2 * mm


def _seal_source(seal_image):
    return seal_image_reader(seal_image)
C_SUB    = HexColor("#555555")


def _date_jp(d) -> str:
    if d is None:
        return ""
    if hasattr(d, "date"):
        d = d.date()
    return f"{d.year}年{d.month}月{d.day}日"


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "0"


def _s(name, size=10, bold=False, align=TA_LEFT, color=None, leading=None, **kwargs):
    register_fonts()
    return ParagraphStyle(
        name=name,
        fontName=FONT_BOLD if bold else FONT_NORMAL,
        fontSize=size,
        leading=leading or max(size * 1.5, size + 3),
        alignment=align,
        textColor=color or C_BLACK,
        **kwargs,
    )


def _total_suffix(lines) -> str:
    """消費税の状況に応じてラベルを返す。"""
    if not lines:
        return "税込"
    rates = {int(l.tax_rate) for l in lines}
    if rates & {10, 8}:
        return "税込"
    if rates <= {-1}:
        return "不課税"
    if rates <= {0}:
        return "非課税"
    if rates <= {0, -1}:
        return "非課税・不課税"
    return "税込"


class _FitOnePage(SimpleDocTemplate):
    """明細行が多い場合でも1ページに収まるよう自動縮小する DocTemplate"""

    def __init__(self, *args, **kwargs):
        self._fit_scale = 1.0
        super().__init__(*args, **kwargs)

    def build(self, flowables, **kw):
        import io, copy
        try:
            tall_h = A4[1] * 5
            buf = io.BytesIO()
            tmp = SimpleDocTemplate(
                buf, pagesize=(A4[0], tall_h),
                leftMargin=self.leftMargin, rightMargin=self.rightMargin,
                topMargin=self.topMargin, bottomMargin=self.bottomMargin,
            )
            tmp.build(copy.deepcopy(flowables))
            if hasattr(tmp, "frame") and tmp.frame:
                content_h = tmp.frame._y2 - tmp.frame._y
                avail_h = self.height
                if content_h > avail_h:
                    self._fit_scale = (avail_h / content_h) * 0.99
        except Exception:
            pass
        super().build(flowables, **kw)

    def _calc(self):
        super()._calc()
        s = self._fit_scale
        if s < 1.0:
            for tmpl in self.pageTemplates:
                for frame in tmpl.frames:
                    frame._x1 = self.leftMargin / s
                    frame._y1 = self.bottomMargin / s
                    frame._width = self.width / s
                    frame._height = self.height / s
                    frame._x2 = frame._x1 + frame._width
                    frame._y2 = frame._y1 + frame._height

    def handle_pageBegin(self):
        if self._fit_scale < 1.0:
            self.canv.scale(self._fit_scale, self._fit_scale)
        super().handle_pageBegin()


def generate_invoice_pdf(issuance, company, output_path: str,
                          bank_account=None, seal_image=None,
                          reissue: bool = False,
                          window_envelope: bool = False,
                          recipient_postal_code: str = "",
                          recipient_address: str = "",
                          recipient_address2: str = "",
                          subject: str = "",
                          due_date=None,
                          notes: str = "") -> str:
    register_fonts()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    doc = _FitOnePage(
        output_path, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm,
        title=f"請求書_{issuance.doc_number}",
        author=company.name if company else "",
    )
    W = A4[0] - 30*mm
    suffix = _total_suffix(issuance.lines)
    story = []

    # 支払期限: 未指定なら請求日翌月末を自動設定
    if due_date is None and issuance.issued_at:
        d = issuance.issued_at
        if hasattr(d, "date"):
            d = d.date()
        nxt_y, nxt_m = (d.year, d.month + 1) if d.month < 12 else (d.year + 1, 1)
        due_date = _date(nxt_y, nxt_m, _cal.monthrange(nxt_y, nxt_m)[1])

    # ── ① タイトル ───────────────────────────────────────────
    title_text = "請　求　書（再発行）" if reissue else "請　求　書"
    story.append(Paragraph(
        title_text,
        _s("title", size=18, bold=True, align=TA_CENTER, color=C_BLACK)
    ))
    story.append(Spacer(1, 4*mm))

    # ── ② 2カラムヘッダー：宛先 ／ 発行者 ────────────────────
    issue_str = _date_jp(issuance.issued_at)
    client_block = _build_client_block(
        issuance, subject=subject,
        window_envelope=window_envelope,
        recipient_postal_code=recipient_postal_code,
        recipient_address=recipient_address,
        recipient_address2=recipient_address2,
        show_recipient_person=bool(getattr(issuance, "show_recipient_person", True)),
    )
    company_block = _build_company_block(
        issuance, company, issue_str, seal_image, col_w=W * 0.45)

    header_tbl = Table([[client_block, company_block]],
                        colWidths=[W * 0.55, W * 0.45])
    header_tbl.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 3*mm))

    # ── ③ ご請求金額ボックス（1行・中央・ラベルと金額は1文字スペース） ──
    total = int(issuance.amount)
    amt_para = Paragraph(
        f'ご請求金額（{suffix}）：　'
        f'<font name="{FONT_BOLD}" size="18">¥ {_fmt(total)} -</font>',
        _s("amt_line", size=11, align=TA_CENTER, leading=24, color=C_BLACK),
    )
    amt_box = Table([[amt_para]], colWidths=[W])
    amt_box.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 1,     C_DARK),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4*mm),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4*mm),
        ("TOPPADDING",    (0, 0), (-1, -1), 3*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3*mm),
        ("BACKGROUND",    (0, 0), (-1, -1), C_LIGHT),
    ]))
    story.append(amt_box)
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width=W, thickness=0.8, color=C_BORDER))
    story.append(Spacer(1, 3*mm))

    # ── ④ 明細テーブル（税率区分列あり） ─────────────────────
    story.append(Paragraph(
        "単位（円）",
        _s("line_unit_note", size=10, align=TA_RIGHT, color=C_SUB, leading=13),
    ))
    story.append(_build_line_table(issuance, W))
    # 合計枠は明細の「単位」列から「金額」列までに揃える。
    total_width_ratio = 0.08 + 0.14 + 0.155
    total_row = _build_total_row(
        suffix, total, total_W=W * total_width_ratio,
    )
    story.append(_build_right_column_block(
        [total_row], W, right_width_ratio=total_width_ratio,
    ))
    story.append(Spacer(1, 2*mm))

    # ── ⑤ 下部：凡例＋支払期限（左） ／ 税率内訳（右） ────────
    left_cells: list = _build_legend(issuance)
    if due_date:
        left_cells = left_cells + [
            Spacer(1, 4*mm),
            Paragraph(f"お支払い期限：{_date_jp(due_date)}",
                      _s("due", size=10, bold=True, color=C_BLACK)),
        ]

    tax_rows = _build_tax_rows(issuance, suffix, total, tax_W=W * 0.58)
    bottom_tbl = Table([[left_cells, tax_rows]],
                        colWidths=[W * 0.42, W * 0.58])
    bottom_tbl.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(bottom_tbl)

    # ── ⑥ 振込先 ────────────────────────────────────────────
    if bank_account and bank_account.bank_name:
        story.append(Spacer(1, 3*mm))
        story.append(HRFlowable(width=W, thickness=0.5, color=C_BORDER))
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph("振込先", _s("bank_ttl", size=10, color=C_SUB)))
        story.append(_build_bank_block(bank_account, W))

    # ── ⑦ 備考 ──────────────────────────────────────────────
    _DEFAULT_NOTE = "恐れ入りますが、振込手数料は貴社にてご負担願います。"
    display_notes = notes if notes else _DEFAULT_NOTE
    story.append(Spacer(1, 3*mm))
    story.append(HRFlowable(width=W, thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("備考", _s("note_ttl", size=10, color=C_SUB)))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph(display_notes, _s("note_body", size=10, color=C_BLACK)))

    doc.build(story)
    return output_path


# ── ブロック構築ヘルパー ───────────────────────────────────

def _build_client_block(issuance, subject: str = "",
                         window_envelope: bool = False,
                         recipient_postal_code: str = "",
                         recipient_address: str = "",
                         recipient_address2: str = "",
                         show_recipient_person: bool = True) -> list:
    parts = []
    org    = issuance.recipient_organization or ""
    dept   = (getattr(issuance, "recipient_department", "") or "") if show_recipient_person else ""
    person = (issuance.recipient_name or "") if show_recipient_person else ""

    if window_envelope:
        if recipient_postal_code:
            parts.append(Paragraph(f"〒{recipient_postal_code}",
                                   _s("addr", size=9, color=C_SUB)))
        if recipient_address:
            parts.append(Paragraph(recipient_address,
                                   _s("addr2", size=9, color=C_SUB)))
        if recipient_address2:
            parts.append(Paragraph(recipient_address2,
                                   _s("addr3", size=9, color=C_SUB)))
        if recipient_postal_code or recipient_address:
            parts.append(Spacer(1, 2*mm))

    if person:
        parts.append(Paragraph(org, _s("org", size=13, bold=True)))
        if dept:
            # leftIndent で1文字分インデント（行頭スペースはReportLabに除去されるため）
            parts.append(Paragraph(dept, _s("dept", size=10, leftIndent=10)))
        # leftIndent で2文字分インデント
        parts.append(Paragraph(f"{person}　様", _s("person", size=11, leftIndent=22)))
    else:
        parts.append(Paragraph(
            f"{org}　御中" if org else "（宛名未設定）",
            _s("org", size=13, bold=True)))

    parts.append(Spacer(1, 22*mm))
    parts.append(Paragraph("下記の通り、ご請求申し上げます。",
                            _s("req", size=10, color=C_SUB)))

    if getattr(issuance, "lines", None):
        names = [l.item_name for l in issuance.lines if l.item_name]
        if len(names) > 2:
            display = "、".join(names[:2]) + "ほか"
        elif names:
            display = "、".join(names)
        else:
            display = subject
    else:
        display = subject
    if display:
        parts.append(Spacer(1, 3*mm))
        # rightIndent=30: 3文字分早く折り返し
        # leftIndent=30 + firstLineIndent=-30: 2行目以降を3文字分インデント
        parts.append(Paragraph(
            f"件名：{display}",
            _s("subj", size=10, rightIndent=30, leftIndent=30, firstLineIndent=-30)
        ))

    return parts


def _build_company_block(issuance, company, issue_str: str,
                          seal_image=None, col_w: float = None) -> list:
    _seal_src = _seal_source(seal_image)
    has_seal = _seal_src is not None and bool(col_w)
    # 押印時は通常位置から6文字分左へ寄せる。右側は印鑑と約2文字分の
    # 重なりを許容し、長い会社情報でも10ptのまま1行に収める。
    # 未押印時は従来の位置・横幅を保つ。
    left_indent = (
        11 * ISSUER_SEAL_INDENT_CHARS
        if has_seal else 11 * ISSUER_NAME_INDENT_CHARS
    )
    right_indent = (
        ISSUER_SEAL_SIZE + ISSUER_SEAL_GAP
        - 11 * ISSUER_SEAL_INDENT_CHARS
        if has_seal else 0
    )
    r_style  = _s("co_r",    size=10, align=TA_RIGHT)
    nm_style = _s(
        "co_name", size=11, bold=True,
        leftIndent=left_indent, rightIndent=right_indent)
    i_style  = _s(
        "co_info", size=10,
        leftIndent=left_indent, rightIndent=right_indent)

    co_parts = []
    if company:
        co_parts.append(Paragraph(company.name or "（自社名未設定）", nm_style))
        if company.postal_code:
            co_parts.append(Paragraph(f"〒{company.postal_code}", i_style))
        if company.address:
            co_parts.append(Paragraph(company.address, i_style))
        if company.phone:
            co_parts.append(Paragraph(f"TEL：{company.phone}", i_style))
        if company.fax:
            co_parts.append(Paragraph(f"FAX：{company.fax}", i_style))
        if company.invoice_reg_number:
            co_parts.append(Paragraph(
                f"登録番号：{company.invoice_reg_number}", i_style))
        co_parts.append(Spacer(1, 11*mm))

    if has_seal:
        co_content = [_IssuerSealOverlay(co_parts, _seal_src, col_w)]
    else:
        co_content = list(co_parts)

    return [
        Paragraph(f"No.　{issuance.doc_number}", r_style),
        Paragraph(f"請求日　{issue_str}", r_style),
        Spacer(1, 11*mm),
    ] + co_content


class _IssuerSealOverlay(Flowable):
    """発行元情報の右側へ印鑑を重ねて描画する。"""

    def __init__(self, content: list, seal_src, width: float):
        super().__init__()
        self._seal_src = seal_src
        self._block_width = width
        self._seal_size = ISSUER_SEAL_SIZE
        self._content = Table([[content]], colWidths=[width])
        self._content.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))

    def wrap(self, avail_width, avail_height):
        _, content_h = self._content.wrap(
            self._block_width, avail_height)
        self.width = self._block_width
        self.height = max(content_h, self._seal_size)
        return self.width, self.height

    def draw(self):
        _, content_h = self._content.wrap(
            self._block_width, self.height)
        try:
            self.canv.drawImage(
                self._seal_src,
                self._block_width - self._seal_size,
                self.height - self._seal_size - 2 * mm,
                self._seal_size,
                self._seal_size,
                mask="auto",
                preserveAspectRatio=True,
            )
        except Exception:
            pass
        # 文字を印鑑より後に描き、重なった箇所でも文字を手前に表示する。
        self._content.drawOn(self.canv, 0, self.height - content_h)


# 税率区分の表示文字列
# 税率区分ラベル: 課税は税率表示、非課税→非、不課税→不
_TAX_LABEL = {10: "10%", 8: "8%軽", 0: "非", -1: "不"}


def _build_line_table(issuance, W: float) -> Table:
    import html as _html
    # 税率・単価・金額を各33%縮小、数量と単位は同幅、品名を最大化
    w_tax  = W * 0.10 * (2/3) * 1.10  # 税率
    w_qty  = W * 0.08 * 0.80           # 数量
    w_unit = W * 0.08                  # 単位
    w_up   = W * 0.14                  # 単価（8桁対応）
    w_amt  = W * 0.155                 # 金額（8桁対応）
    w_name = W - w_tax - w_qty - w_unit - w_up - w_amt
    col_widths = [w_name, w_tax, w_qty, w_unit, w_up, w_amt]
    headers    = ["品名・摘要", "税率", "数量", "単位", "単価", "金額"]

    th = _s("th", size=10, bold=True, align=TA_CENTER, color=white, leading=16)
    data = [[Paragraph(h, th) for h in headers]]

    nm  = _s("nm",    size=10, leading=16)
    ct  = _s("ct",    size=10, align=TA_CENTER, leading=16)
    num = _s("num",   size=10, align=TA_RIGHT,  leading=16)
    pr  = _s("price", size=10, align=TA_RIGHT,  leading=16)

    for line in issuance.lines:
        rate    = int(line.tax_rate)
        escaped = _html.escape(str(line.item_name))
        qty     = line.quantity
        qty_str = str(int(qty)) if float(qty) == int(float(qty)) else str(qty)
        tax_lbl = _TAX_LABEL.get(rate, f"{rate}%")
        data.append([
            Paragraph(escaped,               nm),
            Paragraph(tax_lbl,               ct),
            Paragraph(qty_str,               num),
            Paragraph(line.unit or "式",      ct),
            Paragraph(_fmt(line.unit_price), pr),
            Paragraph(_fmt(line.line_total), pr),
        ])

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  C_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  white),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("LINEBELOW",     (0, 0), (-1, 0),  1,   C_DARK),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, C_PALE]),
        ("LEFTPADDING",   (0, 0), (-1, -1), 2*mm),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2*mm),
        ("TOPPADDING",    (0, 0), (-1, -1), 1.5*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5*mm),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _build_legend(issuance) -> list:
    rates  = {int(l.tax_rate) for l in issuance.lines}
    parts  = []
    if 8  in rates: parts.append("※軽：軽減税率(8%)対象")
    if 0  in rates: parts.append("非課税：消費税非課税")
    if -1 in rates: parts.append("不課税：消費税対象外")
    if not parts:
        return [Spacer(1, 0)]
    return [Paragraph("\n".join(parts),
                       _s("legend", size=8, color=C_SUB, leading=13))]


def _build_total_row(suffix: str, total: int, total_W: float = 120*mm) -> Table:
    """明細直下に表示する合計行。"""
    lbl = Paragraph(
        f"合計（{suffix}）",
        _s("total_lbl", size=10, bold=True, leading=16),
    )
    val = Paragraph(
        f"{_fmt(total)} -",
        _s("total_val", size=10, bold=True, align=TA_RIGHT, leading=16),
    )
    # 合計欄は「単位＋単価」と「金額」の境界を明細表に合わせる。
    amount_ratio = 0.155 / (0.08 + 0.14 + 0.155)
    tbl = Table(
        [[lbl, val]],
        colWidths=[
            total_W * (1 - amount_ratio),
            total_W * amount_ratio,
        ],
        hAlign="RIGHT",
    )
    tbl.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("BACKGROUND",    (0, 0), (-1, -1), C_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3*mm),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3*mm),
        ("TOPPADDING",    (0, 0), (-1, -1), 1.5*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5*mm),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _build_right_column_block(
        content: list, W: float, right_width_ratio: float = 0.58) -> Table:
    """指定幅の右カラムへ配置し、明細表の罫線位置に揃える。"""
    tbl = Table(
        [[Spacer(1, 0), content]],
        colWidths=[W * (1 - right_width_ratio), W * right_width_ratio],
    )
    tbl.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    return tbl


def _build_tax_rows(issuance, suffix: str, total: int, tax_W: float = 120*mm):
    """税額内訳テーブル（右下配置用）。 2列: ラベル | 金額"""
    lines      = issuance.lines
    tax10_incl = sum(int(l.line_total) for l in lines if int(l.tax_rate) == 10)
    tax8_incl  = sum(int(l.line_total) for l in lines if int(l.tax_rate) == 8)
    exempt     = sum(int(l.line_total) for l in lines if int(l.tax_rate) == 0)
    non_tax    = sum(int(l.line_total) for l in lines if int(l.tax_rate) == -1)
    tax10_amt  = int(tax10_incl * 10 / 110)
    tax8_amt   = int(tax8_incl  *  8 / 108)

    rows: list[tuple[str, str]] = []
    if tax10_incl:
        rows.append(("10%税率　対象小計", _fmt(tax10_incl)))
    if tax8_incl:
        rows.append(("8%税率　対象小計",  _fmt(tax8_incl)))
    if tax10_incl:
        rows.append(("10%税額",            _fmt(tax10_amt)))
    if tax8_incl:
        rows.append(("8%税額",             _fmt(tax8_amt)))
    if exempt:
        rows.append(("非課税　合計",        _fmt(exempt)))
    if non_tax:
        rows.append(("不課税　合計",        _fmt(non_tax)))
    if not rows:
        return [Spacer(1, 0)]

    lbl = _s("tx_lbl", size=10, leading=16)
    val = _s("tx_val", size=10, align=TA_RIGHT, leading=16)

    data = []
    for l, v in rows:
        data.append([
            Paragraph(l, lbl),
            Paragraph(v, val),
        ])

    lw = tax_W * 0.60
    vw = tax_W * 0.40
    tbl = Table(data, colWidths=[lw, vw], hAlign="RIGHT")
    tbl.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3*mm),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3*mm),
        ("TOPPADDING",    (0, 0), (-1, -1), 1.5*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5*mm),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [tbl]


def _build_bank_block(ba, W: float) -> Table:
    # 文字サイズは維持し、行間の余白だけを従来のおよそ4分の1にする。
    i_style = _s("bank", size=10, leading=11.5)
    rows = []
    label = f"金融機関・支店：{ba.bank_name}"
    if ba.bank_branch:
        label += f"　{ba.bank_branch}"
    rows.append([Paragraph(label, i_style)])
    if ba.bank_account_type:
        rows.append([Paragraph(f"口座種別：{ba.bank_account_type}", i_style)])
    if ba.bank_account_number:
        rows.append([Paragraph(f"口座番号：{ba.bank_account_number}", i_style)])
    if ba.bank_account_name:
        rows.append([Paragraph(f"口座名義：{ba.bank_account_name}", i_style)])
    if getattr(ba, "bank_account_name_kana", ""):
        rows.append([Paragraph(
            f"フリガナ：{_to_halfwidth_kana(ba.bank_account_name_kana)}",
            i_style)])
    tbl = Table(rows, colWidths=[W * 0.65], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 0.375*mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.375*mm),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
    ]))
    return tbl


def _to_halfwidth_kana(value: str) -> str:
    """全角カナを半角カナへ変換する（漢字などその他の文字は維持）。"""
    source = str(value or "")
    halfwidth_chars = [chr(code) for code in range(0xFF61, 0xFFA0)]
    kana_map = {
        unicodedata.normalize("NFKC", char): char
        for char in halfwidth_chars
    }
    for char in halfwidth_chars:
        for mark in ("\uFF9E", "\uFF9F"):
            halfwidth = char + mark
            normalized = unicodedata.normalize("NFKC", halfwidth)
            if len(normalized) == 1:
                kana_map[normalized] = halfwidth
    return "".join(
        " " if char == "\u3000" else kana_map.get(char, char)
        for char in source
    )
