# -*- coding: utf-8 -*-
"""
CCI請求書システム アイコン生成スクリプト
4種類のデザインを assets/icons/ に PNG + ICO で出力する
"""
import os
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUTPUT_DIR = "assets/icons"
SIZES = [16, 32, 48, 64, 128, 256]


def save_ico(images: list, path: str):
    """複数サイズの Image リストを ICO として保存"""
    images[0].save(
        path,
        format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:],
    )


def make_all_sizes(draw_fn) -> list:
    """各サイズの Image を生成して返す"""
    result = []
    for size in SIZES:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw_fn(img, size)
        result.append(img)
    return result


# ─── Design A: グラデーション × CCI テキスト ───────────────────────────────

def design_a(img: Image.Image, size: int):
    """濃紺→青のグラデーション背景に白い 'CCI' テキスト"""
    draw = ImageDraw.Draw(img)
    r = size // 8

    # 角丸矩形（グラデーション擬似）
    for y in range(size):
        t = y / size
        rr = int(30 + t * (59 - 30))
        gg = int(58 + t * (130 - 58))
        bb = int(138 + t * (246 - 138))
        draw.line([(0, y), (size, y)], fill=(rr, gg, bb, 255))

    # 角丸マスク
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    img.putalpha(mask)

    # テキスト
    draw = ImageDraw.Draw(img)
    text = "CCI"
    font_size = max(int(size * 0.38), 8)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]

    # シャドウ
    if size >= 32:
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 80, 120))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))


# ─── Design B: 請求書ドキュメント ────────────────────────────────────────────

def design_b(img: Image.Image, size: int):
    """白い書類アイコン（折り角付き）on 青背景"""
    draw = ImageDraw.Draw(img)
    r = size // 8

    # 背景
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r,
                           fill=(37, 99, 235, 255))

    # 書類本体
    pad = size * 0.18
    fold = size * 0.22
    doc_l = int(pad)
    doc_t = int(pad)
    doc_r = int(size - pad)
    doc_b = int(size - pad)

    # 折り角なし部分（多角形）
    pts = [
        (doc_l, doc_t),
        (doc_r - fold, doc_t),
        (doc_r, doc_t + fold),
        (doc_r, doc_b),
        (doc_l, doc_b),
    ]
    draw.polygon(pts, fill=(255, 255, 255, 240))

    # 折り角の三角形（影）
    fold_pts = [
        (doc_r - fold, doc_t),
        (doc_r, doc_t + fold),
        (doc_r - fold, doc_t + fold),
    ]
    draw.polygon(fold_pts, fill=(180, 210, 255, 255))

    # テキスト行（横線）
    if size >= 32:
        line_color = (100, 150, 230, 200)
        margin = size * 0.08
        lx1 = int(doc_l + margin)
        lx2 = int(doc_r - margin)
        n_lines = 3 if size < 64 else 4
        y_start = int(doc_t + fold + size * 0.08)
        y_end = int(doc_b - size * 0.1)
        for i in range(n_lines):
            t = i / max(n_lines - 1, 1)
            ly = int(y_start + t * (y_end - y_start))
            lw = max(1, size // 32)
            short = 0 if i < n_lines - 1 else int(size * 0.15)
            draw.line([(lx1, ly), (lx2 - short, ly)], fill=line_color, width=lw)


# ─── Design C: シール風 丸バッジ ─────────────────────────────────────────────

def design_c(img: Image.Image, size: int):
    """金色の円形バッジ（「請」文字）"""
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r_outer = int(size * 0.48)
    r_inner = int(size * 0.40)

    # 外枠リング（金）
    draw.ellipse(
        [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
        fill=(212, 175, 55, 255),
    )
    # 内側（濃紺）
    draw.ellipse(
        [cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
        fill=(30, 58, 138, 255),
    )

    # 文字「請」
    char = "請"
    font_size = max(int(size * 0.42), 8)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msgothic.ttc", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", font_size)
        except Exception:
            font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), char, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = cx - tw // 2 - bbox[0]
    y = cy - th // 2 - bbox[1]
    draw.text((x, y), char, font=font, fill=(212, 175, 55, 255))

    # 外周ドット装飾（大サイズのみ）
    if size >= 64:
        n_dots = 12
        dot_r = max(2, size // 40)
        dot_d = int(size * 0.465)
        for i in range(n_dots):
            angle = 2 * math.pi * i / n_dots
            dx = int(cx + dot_d * math.cos(angle))
            dy = int(cy + dot_d * math.sin(angle))
            draw.ellipse(
                [dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r],
                fill=(212, 175, 55, 255),
            )


# ─── Design D: モダンフラット（¥ マーク） ──────────────────────────────────

def design_d(img: Image.Image, size: int):
    """緑のグラデーション背景に白い ¥ マーク"""
    draw = ImageDraw.Draw(img)
    r = size // 8

    # グラデーション（緑系）
    for y in range(size):
        t = y / size
        rr = int(4 + t * (5 - 4))
        gg = int(120 + t * (150 - 120))
        bb = int(87 + t * (100 - 87))
        draw.line([(0, y), (size, y)], fill=(rr, gg, bb, 255))

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    img.putalpha(mask)

    draw = ImageDraw.Draw(img)

    # ¥ 記号
    char = "¥"
    font_size = max(int(size * 0.55), 8)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), char, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1] - int(size * 0.03)

    if size >= 32:
        draw.text((x + 1, y + 1), char, font=font, fill=(0, 60, 0, 100))
    draw.text((x, y), char, font=font, fill=(255, 255, 255, 255))


# ─── メイン ──────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    designs = [
        ("A_CCI_blue",     design_a, "A: 濃紺グラデーション × CCI テキスト"),
        ("B_document",     design_b, "B: 請求書ドキュメント on 青背景"),
        ("C_seal",         design_c, "C: 金色シール × 請の字"),
        ("D_yen_green",    design_d, "D: 緑グラデーション × 円マーク"),
    ]

    for name, draw_fn, desc in designs:
        images = make_all_sizes(draw_fn)

        # プレビュー PNG（256px）
        png_path = os.path.join(OUTPUT_DIR, f"{name}_preview.png")
        images[-1].save(png_path)

        # ICO（全サイズ）
        ico_path = os.path.join(OUTPUT_DIR, f"{name}.ico")
        save_ico(images, ico_path)

        print(f"[{name}] {desc}")
        print(f"  PNG: {png_path}")
        print(f"  ICO: {ico_path}")

    print(f"\n完了: {OUTPUT_DIR}/ に {len(designs)} デザイン × 各2ファイルを生成しました。")
    print("気に入ったデザインの .ico を assets/app_icon.ico にコピーしてください。")


if __name__ == "__main__":
    main()
