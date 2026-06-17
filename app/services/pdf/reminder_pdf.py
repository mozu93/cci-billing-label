# app/services/pdf/reminder_pdf.py
import os
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from app.services.pdf.fonts import register_fonts, FONT_NORMAL, FONT_BOLD

C_BLUE = HexColor("#1E40AF")
C_SUB  = HexColor("#64748B")


def generate_reminder_pdf(issuance, company, output_path: str,
                           custom_message: str = "") -> str:
    register_fonts()
    parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=25*mm, rightMargin=25*mm,
        topMargin=25*mm, bottomMargin=25*mm,
    )

    def s(name, size=11, bold=False, align=TA_LEFT, color=None):
        return ParagraphStyle(
            name=name,
            fontName=FONT_BOLD if bold else FONT_NORMAL,
            fontSize=size, leading=size * 1.6,
            alignment=align,
            textColor=color or black,
        )

    story = []
    story.append(Paragraph(date.today().strftime("%Y年%m月%d日"),
                            s("date", size=10, color=C_SUB)))
    story.append(Spacer(1, 6*mm))

    recipient = (issuance.recipient_organization or issuance.recipient_name or "").strip()
    story.append(Paragraph(f"{recipient} 様", s("recipient", size=13, bold=True)))
    story.append(Spacer(1, 8*mm))

    story.append(Paragraph("お支払いのお願い",
                            s("title", size=18, bold=True, align=TA_CENTER, color=C_BLUE)))
    story.append(HRFlowable(width="100%", color=C_BLUE, thickness=2))
    story.append(Spacer(1, 8*mm))

    default_msg = (
        f"平素より大変お世話になっております。{company.name or '商工会議所'}でございます。<br/>"
        "<br/>"
        "下記の件につきまして、いまだお支払いが確認できておりません。<br/>"
        "ご多忙のところ恐れ入りますが、お早めにお手続きいただきますよう、<br/>"
        "何卒よろしくお願い申し上げます。"
    )
    story.append(Paragraph(custom_message or default_msg, s("body")))
    story.append(Spacer(1, 8*mm))

    proj_name = ""
    if hasattr(issuance, 'project') and issuance.project:
        proj_name = issuance.project.name

    info_data = [
        ["書類番号", issuance.doc_number],
        ["件名", proj_name],
        ["金額", f"¥{int(issuance.amount):,}（税込）"],
    ]
    info_table = Table(info_data, colWidths=[40*mm, 100*mm])
    info_table.setStyle(TableStyle([
        ("FONTNAME",    (0,0), (-1,-1), FONT_NORMAL),
        ("FONTNAME",    (0,0), (0,-1), FONT_BOLD),
        ("FONTSIZE",    (0,0), (-1,-1), 10),
        ("BACKGROUND",  (0,0), (0,-1), HexColor("#EFF6FF")),
        ("GRID",        (0,0), (-1,-1), 0.5, HexColor("#CBD5E1")),
        ("TOPPADDING",  (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10*mm))

    story.append(HRFlowable(width="100%", color=HexColor("#E2E8F0"), thickness=0.5))
    story.append(Spacer(1, 4*mm))

    for line in [
        company.name or "",
        f"〒{company.postal_code}  {company.address}" if company.postal_code else company.address,
        f"TEL：{company.phone}" if company.phone else "",
    ]:
        if line and line.strip():
            story.append(Paragraph(line, s("issuer", size=9, color=C_SUB)))

    doc.build(story)
    return output_path
