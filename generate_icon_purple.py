# -*- coding: utf-8 -*-
"""
紫グラデーション x フラットラインアート（書類 + 円記号 + 鉛筆）アイコン生成
"""
import os
import math
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = "assets/icons"
SIZES = [16, 32, 48, 64, 128, 256]


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 256

    # ── 紫グラデーション背景 ──────────────────────────────────────────────
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(124 + t * (109 - 124))   # #7C -> #6D
        g = int(58  + t * (40  - 58))    # #3A -> #28
        b = int(237 + t * (217 - 237))   # #ED -> #D9
        draw.line([(0, y), (size - 1, y)], fill=(r, g, b, 255))

    # 角丸マスク
    rad = max(int(size * 0.15), 2)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=rad, fill=255
    )
    img.putalpha(mask)
    draw = ImageDraw.Draw(img)

    white = (255, 255, 255, 255)
    lw = max(1, round(size / 26))  # 線幅

    # ── 書類アウトライン ──────────────────────────────────────────────────
    dl = int(52 * s);  dt = int(32 * s)
    dr = int(178 * s); db = int(202 * s)
    fold = int(28 * s)

    # 書類ポリゴン (折り角あり)
    doc = [
        (dl, dt),
        (dr - fold, dt),
        (dr, dt + fold),
        (dr, db),
        (dl, db),
        (dl, dt),
    ]
    draw.line(doc, fill=white, width=lw)
    # 折り角の折れ目
    draw.line([(dr - fold, dt), (dr - fold, dt + fold), (dr, dt + fold)],
              fill=white, width=lw)

    # ── テキスト行（横線） ───────────────────────────────────────────────
    lx1 = int(120 * s)
    lx2 = int(168 * s)
    for base_y in [70, 103, 136, 167]:
        y = int(base_y * s)
        if y < db - int(8 * s):
            draw.line([(lx1, y), (lx2, y)], fill=white, width=lw)

    # ── 円記号（¥ in circle） ────────────────────────────────────────────
    cx = int(93 * s)
    cy = int(132 * s)
    cr = int(32 * s)   # 円は元のサイズ
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr],
                 outline=white, width=lw)

    # ¥ 文字（円より大きく、2倍サイズ）
    fs = max(int(cr * 2.1), 6)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", fs)
    except Exception:
        font = ImageFont.load_default()

    char = "\xa5"  # ¥
    bbox = draw.textbbox((0, 0), char, font=font)
    tx = cx - (bbox[2] - bbox[0]) // 2 - bbox[0]
    ty = cy - (bbox[3] - bbox[1]) // 2 - bbox[1]
    draw.text((tx, ty), char, font=font, fill=white)

    # ── 鉛筆 ─────────────────────────────────────────────────────────────
    if size >= 32:
        angle = math.pi / 4  # 45度
        dx = math.cos(angle)
        dy = -math.sin(angle)
        px = math.sin(angle)   # 垂直方向
        py = math.cos(angle)

        hw    = int(11 * s)    # 半幅
        L     = int(80 * s)    # 本体長
        tip_x = int(155 * s)
        tip_y = int(220 * s)
        ex = tip_x + int(dx * L)
        ey = tip_y + int(dy * L)
        # 先端（鋭い頂点）
        tip_sharp_x = tip_x + int(dx * (-18 * s))
        tip_sharp_y = tip_y + int(dy * (-18 * s))

        # 本体四隅
        A = (tip_x + int(px * hw), tip_y + int(py * hw))  # 本体tip側・右
        B = (tip_x - int(px * hw), tip_y - int(py * hw))  # 本体tip側・左
        C = (ex   - int(px * hw), ey   - int(py * hw))    # 消しゴム側・左
        D = (ex   + int(px * hw), ey   + int(py * hw))    # 消しゴム側・右

        # 本体
        draw.line([A, D], fill=white, width=lw)
        draw.line([D, C], fill=white, width=lw)
        draw.line([C, B], fill=white, width=lw)
        # 本体 tip 側は開いて三角に繋ぐ

        # 先端三角
        draw.line([A, (tip_sharp_x, tip_sharp_y)], fill=white, width=lw)
        draw.line([B, (tip_sharp_x, tip_sharp_y)], fill=white, width=lw)

        # 仕切り線（本体と先端部分の境界）
        draw.line([A, B], fill=white, width=lw)

        # 消しゴム仕切り線（本体末端に小さな帯）
        eraser_offset = int(10 * s)
        E = (ex + int(dx * eraser_offset) + int(px * hw),
             ey + int(dy * eraser_offset) + int(py * hw))
        F = (ex + int(dx * eraser_offset) - int(px * hw),
             ey + int(dy * eraser_offset) - int(py * hw))
        draw.line([D, E], fill=white, width=lw)
        draw.line([E, F], fill=white, width=lw)
        draw.line([F, C], fill=white, width=lw)

    return img


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    images = [draw_icon(sz) for sz in SIZES]

    # プレビュー PNG
    png_path = os.path.join(OUTPUT_DIR, "E_purple_invoice_preview.png")
    images[-1].save(png_path)
    print(f"Preview: {png_path}")

    # ICO（全サイズ込み）
    ico_path = os.path.join(OUTPUT_DIR, "E_purple_invoice.ico")
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:],
    )
    print(f"ICO:     {ico_path}")
    print("完了")


if __name__ == "__main__":
    main()
