"""印鑑画像をPDF描画用に読み込む共通処理。"""

import os
from io import BytesIO

from PIL import Image
from reportlab.lib.utils import ImageReader


def _make_white_transparent(image: Image.Image) -> Image.Image:
    """白い用紙背景を除去し、印影の濃淡と輪郭を残したRGBA画像を返す。"""
    rgba = image.convert("RGBA")

    # 既に実用的な透過情報があるPNG等は、そのまま尊重する。
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] < 250:
        return rgba

    pixels = []
    source_pixels = (
        rgba.get_flattened_data()
        if hasattr(rgba, "get_flattened_data")
        else rgba.getdata()
    )
    for red, green, blue, _ in source_pixels:
        # 白からの距離。JPEGノイズは透明、印影の薄い縁は半透明にする。
        distance = max(255 - red, 255 - green, 255 - blue)
        opacity = max(0, min(255, round((distance - 10) * 255 / 70)))
        pixels.append((red, green, blue, opacity))
    rgba.putdata(pixels)
    return rgba


def seal_image_reader(seal_image):
    """DBのBLOBまたは画像パスから、白背景を透過したImageReaderを返す。"""
    if seal_image is None:
        return None

    data = getattr(seal_image, "image_data", None)
    if data:
        source = BytesIO(data)
    else:
        path = getattr(seal_image, "path", None)
        if not path or not os.path.exists(path):
            return None
        source = path

    try:
        with Image.open(source) as image:
            transparent = _make_white_transparent(image)
            output = BytesIO()
            transparent.save(output, format="PNG")
            output.seek(0)
            return ImageReader(output)
    except (OSError, ValueError):
        return None
