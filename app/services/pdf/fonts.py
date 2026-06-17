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
