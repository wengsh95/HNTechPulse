#!/usr/bin/env python3
"""
Generate a 3:4 Xiaohongshu-style cover from HN TechPulse daily story metadata.
Style: dark tech gradient with orange accents, clear Chinese typography.
"""

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def interpolate(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_gradient_bg(draw, width, height, c1, c2, direction="diagonal"):
    """Draw a smooth linear gradient background."""
    if direction == "diagonal":
        for y in range(height):
            for x in range(width):
                t = (x / width + y / height) / 2
                draw.point((x, y), fill=interpolate(c1, c2, t))
    else:
        for y in range(height):
            t = y / height
            draw.line([(0, y), (width, y)], fill=interpolate(c1, c2, t))


def draw_tech_grid(draw, width, height, color, spacing=60, alpha=40):
    """Draw subtle perspective-ish grid lines."""
    for x in range(0, width, spacing):
        draw.line([(x, 0), (x, height)], fill=(*color, alpha), width=1)
    for y in range(0, height, spacing):
        draw.line([(0, y), (width, y)], fill=(*color, alpha), width=1)


def draw_rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    x1, y1, x2, y2 = xy
    r = radius
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def load_font(name, size):
    font_dir = Path("C:/Windows/Fonts")
    candidates = {
        "bold": ["Noto Sans SC Bold (TrueType).otf", "msyhbd.ttc", "simhei.ttf"],
        "medium": ["Noto Sans SC Medium (TrueType).otf", "msyh.ttc", "simsun.ttc"],
        "regular": ["Noto Sans SC (TrueType).otf", "msyh.ttc", "simsun.ttc"],
    }
    for cand in candidates.get(name, candidates["regular"]):
        path = font_dir / cand
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_cover(
    date_str: str,
    main_title: str,
    sub_title: str,
    bullets: list[str],
    footer: str,
    out_path: str,
    width: int = 900,
    height: int = 1200,
):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # Colors
    c_black = hex_to_rgb("#141414")
    c_orange = hex_to_rgb("#FF6B35")
    c_orange_dark = hex_to_rgb("#C2410C")
    c_white = hex_to_rgb("#FFFFFF")
    c_gray = hex_to_rgb("#A3A3A3")
    c_light_orange = hex_to_rgb("#FDBA74")

    # 1. Background gradient: top-left dark -> bottom-right orange
    draw_gradient_bg(draw, width, height, c_black, c_orange_dark, direction="diagonal")

    # 2. Large soft glow top-right
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for r in range(400, 0, -10):
        alpha = int(25 * (1 - r / 400))
        glow_draw.ellipse(
            [(width - 250 - r, -100 - r), (width - 250 + r, -100 + r)],
            fill=(*c_orange, alpha),
        )
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # 3. Very subtle grid
    draw_tech_grid(draw, width, height, c_white, spacing=90, alpha=6)

    # 4. Diagonal accent bar
    draw.polygon(
        [(width, height - 300), (width - 120, height), (width, height)],
        fill=(*c_orange, 200),
    )

    # Fonts
    font_brand = load_font("medium", 28)
    font_date = load_font("regular", 22)
    font_title = load_font("bold", 78)
    font_sub = load_font("medium", 34)
    font_bullet = load_font("regular", 26)
    font_footer = load_font("regular", 22)

    # 5. Top brand bar
    margin = 50
    brand_text = "HN每日观察"
    draw.text((margin, margin), brand_text, font=font_brand, fill=(*c_white, 230))
    date_text = date_str.replace("-", ".")
    bbox = draw.textbbox((0, 0), brand_text, font=font_brand)
    brand_w = bbox[2] - bbox[0]
    draw.text(
        (margin + brand_w + 20, margin + 3),
        date_text,
        font=font_date,
        fill=(*c_gray, 200),
    )
    draw.line(
        [(margin, margin + 45), (margin + brand_w + 110, margin + 45)],
        fill=(*c_orange, 200),
        width=2,
    )

    # 6. Main title (line-wrapped)
    title_y = 220
    title_lines = main_title.split("\n")
    for idx, line in enumerate(title_lines):
        bbox = draw.textbbox((0, 0), line, font=font_title)
        line_w = bbox[2] - bbox[0]
        x = (width - line_w) // 2
        title_color = c_light_orange if idx == 1 else c_white
        # drop shadow
        draw.text((x + 3, title_y + 3), line, font=font_title, fill=(0, 0, 0, 120))
        draw.text((x, title_y), line, font=font_title, fill=(*title_color, 255))
        title_y += 100

    # 7. Sub title
    sub_y = title_y + 20
    bbox = draw.textbbox((0, 0), sub_title, font=font_sub)
    sub_w = bbox[2] - bbox[0]
    x = (width - sub_w) // 2
    draw.text((x, sub_y), sub_title, font=font_sub, fill=(*c_light_orange, 240))

    # 8. Decorative divider
    divider_y = sub_y + 70
    draw.line(
        [(width // 2 - 60, divider_y), (width // 2 + 60, divider_y)],
        fill=(*c_orange, 200),
        width=3,
    )

    # 9. Bullet points inside translucent cards
    bullet_y = divider_y + 60
    card_w = width - margin * 2
    for idx, bullet in enumerate(bullets, 1):
        # card background
        card_h = 80
        card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card)
        card_draw.rounded_rectangle(
            [(0, 0), (card_w, card_h)],
            radius=16,
            fill=(20, 20, 20, 160),
            outline=(*c_orange, 120),
            width=1,
        )
        img.paste(card, (margin, bullet_y), card)

        # number badge
        badge_size = 36
        badge_x = margin + 18
        badge_y = bullet_y + (card_h - badge_size) // 2
        draw.rounded_rectangle(
            [(badge_x, badge_y), (badge_x + badge_size, badge_y + badge_size)],
            radius=8,
            fill=(*c_orange, 230),
        )
        num = str(idx)
        bbox = draw.textbbox((0, 0), num, font=font_bullet)
        nw = bbox[2] - bbox[0]
        nh = bbox[3] - bbox[1]
        draw.text(
            (badge_x + (badge_size - nw) // 2, badge_y + (badge_size - nh) // 2 - 3),
            num,
            font=font_bullet,
            fill=(0, 0, 0, 255),
        )

        # text (wrap if too long)
        text_x = badge_x + badge_size + 16
        max_text_w = card_w - (text_x - margin) - 20
        words = list(bullet)
        lines = []
        current = ""
        for ch in words:
            test = current + ch
            bbox = draw.textbbox((0, 0), test, font=font_bullet)
            if bbox[2] - bbox[0] > max_text_w and current:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)

        line_h = 32
        text_start_y = bullet_y + (card_h - line_h * len(lines)) // 2
        for i, ln in enumerate(lines):
            draw.text(
                (text_x, text_start_y + i * line_h),
                ln,
                font=font_bullet,
                fill=(*c_white, 230),
            )

        bullet_y += card_h + 18

    # 10. Footer CTA
    footer_y = height - 80
    bbox = draw.textbbox((0, 0), footer, font=font_footer)
    fw = bbox[2] - bbox[0]
    draw.text(
        ((width - fw) // 2, footer_y), footer, font=font_footer, fill=(*c_gray, 200)
    )

    # 11. Small decorative dots
    for i in range(6):
        x = width - 60 - i * 25
        y = height - 120
        r = 5 + (i % 3) * 2
        draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=(*c_orange, 150 - i * 15))

    # Convert to RGB and save
    final = img.convert("RGB")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    final.save(out_path, "PNG", quality=95)
    print(f"Saved cover to {out_path} ({width}x{height})")


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_xhs_cover.py <date> [out_path]")
        sys.exit(1)

    date_str = sys.argv[1]
    month_dir = f"{date_str[:4]}-{date_str[5:7]}"
    out_path = (
        sys.argv[2]
        if len(sys.argv) > 2
        else f"data/{month_dir}/{date_str}/publish/xhs_cover_3x4.png"
    )

    # Build components from publish guide if available
    guide_path = Path(
        f"data/{date_str[:4]}-{date_str[5:7]}/{date_str}/publish/publish_guide.md"
    )
    bullets = [
        "月之暗面 K3 承认蒸馏开源 Fable，社区吵翻",
        "陶哲轩带 ChatGPT 探索雅可比猜想反例",
        "LG 拟封住宅代理，Reddit 限制纯 HTML",
    ]
    if guide_path.exists():
        text = guide_path.read_text(encoding="utf-8")
        # simple extraction of cover subtitle lines
        if "陶哲轩" in text and "ChatGPT" in text:
            bullets = [
                "月之暗面 K3 承认蒸馏开源 Fable，社区吵翻",
                "陶哲轩带 ChatGPT 探索雅可比猜想反例",
                "LG / Reddit 等平台政策边界继续收紧",
            ]

    make_cover(
        date_str=date_str,
        main_title="K3 承认蒸馏 Fable\n开源社区炸了锅",
        sub_title="今天 HN 上吵翻天的 3 件事",
        bullets=bullets,
        footer="海外科技真实讨论 · 收藏=追更",
        out_path=out_path,
    )


if __name__ == "__main__":
    main()
