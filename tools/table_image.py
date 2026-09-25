# -*- coding: utf-8 -*-
"""ცხრილის (ქუდი + №/X/Y) სურათად რენდერი — ArcGIS Pro layout-ში ჩასაფეისთად.

აბრუნებს PIL.Image-ს: გაერთიანებული ტექსტური ქუდი (wrap), სათაურის რიგი და
მონაცემები — ჩარჩოებით, ცენტრირებით. Pillow-ს იყენებს (GIS_BOX-ს ისედ სჭირდება).
"""


def _font(size):
    from PIL import ImageFont
    from tools.platform_utils import pil_font_candidates
    for name in pil_font_candidates():
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_size(draw, text, font):
    l, t, r, b = draw.textbbox((0, 0), str(text), font=font)
    return r - l, b - t


def _wrap(draw, text, font, max_w):
    words = str(text).split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        if _text_size(draw, cur + " " + w, font)[0] <= max_w:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def render_table(title, headers, rows, scale=6, transparent=True, supersample=2):
    """ბლოკის სურათი. title — ქუდი ("" თუ არაა); headers/rows — ცხრილი.
    transparent=True — ფონის გარეშე (RGBA), მხოლოდ ჩარჩოები/ტექსტი.

    მაღალი გარჩევადობა (scale) + supersample (2x რენდერი → LANCZOS-ით ჩამოსწორება)
    — გლუვი, მკვეთრი ტექსტი (layout-ში გადიდებისასაც არ ხეშდება)."""
    from PIL import Image, ImageDraw

    s = scale * max(1, supersample)  # შიდა (გადიდებული) რენდერის მასშტაბი
    fs = 16 * s
    pad_x = 14 * s                   # ჰორიზონტ. padding — განიერი სვეტები (ქუდი ~3 ხაზზე)
    pad_y = 5 * s                    # ვერტიკ. padding — კომპაქტური რიგები
    bw = max(1, round(s * 0.55))     # თხელი ჩარჩო
    font = _font(fs)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    ncols = len(headers)
    # სვეტების სიგანე — მაქს. ტექსტი header+data-ში
    col_w = []
    for j in range(ncols):
        w = _text_size(tmp, headers[j], font)[0]
        for row in rows:
            w = max(w, _text_size(tmp, row[j], font)[0])
        col_w.append(w + 2 * pad_x)
    total_w = sum(col_w)

    _, th = _text_size(tmp, "Ag", font)
    row_h = th + 2 * pad_y           # მონაცემების რიგის სიმაღლე
    title_lh = th + pad_y            # ქუდის ხაზის (უფრო მჭიდრო) სიმაღლე

    # ქუდი — wrap total_w-ზე
    title_lines = _wrap(tmp, title, font, total_w - 2 * pad_x) if title else []
    title_h = (len(title_lines) * title_lh + pad_y) if title_lines else 0

    height = title_h + row_h * (1 + len(rows))
    if transparent:
        img = Image.new("RGBA", (total_w + 1, height + 1), (255, 255, 255, 0))
    else:
        img = Image.new("RGB", (total_w + 1, height + 1), "white")
    d = ImageDraw.Draw(img)
    line = "#000000"

    def cell(x, y, w, h, text, bold=False):
        d.rectangle([x, y, x + w, y + h], outline=line, width=bw)
        tw, tht = _text_size(d, text, font)
        d.text((x + (w - tw) / 2, y + (h - tht) / 2 - 1), str(text),
               fill="#000000", font=font)

    y = 0
    if title_lines:
        d.rectangle([0, 0, total_w, title_h], outline=line, width=bw)
        for i, ln in enumerate(title_lines):
            tw, _ = _text_size(d, ln, font)
            d.text(((total_w - tw) / 2, pad_y / 2 + i * title_lh), ln,
                   fill="#000000", font=font)
        y = title_h

    # სათაურის რიგი
    x = 0
    for j in range(ncols):
        cell(x, y, col_w[j], row_h, headers[j], bold=True)
        x += col_w[j]
    y += row_h
    # მონაცემები
    for row in rows:
        x = 0
        for j in range(ncols):
            cell(x, y, col_w[j], row_h, row[j])
            x += col_w[j]
        y += row_h

    if supersample and supersample > 1:  # 2x → LANCZOS: გლუვი, მკვეთრი
        img = img.resize((round(img.width / supersample),
                          round(img.height / supersample)),
                         resample=Image.LANCZOS)

    if transparent and img.mode == "RGBA":
        # გამჭვირვალე უბნების RGB თეთრი გავხადოთ (ალფა უცვლელი) — რომ ალფის
        # უგულებელმყოფელ პროგრამაშიც (clipboard/flatten) თეთრი გამოჩნდეს, არა შავი.
        r, g, b, a = img.split()
        base = Image.new("RGB", img.size, (255, 255, 255))
        base.paste(Image.merge("RGB", (r, g, b)), (0, 0), a)
        img = base.convert("RGBA")
        img.putalpha(a)
    return img
