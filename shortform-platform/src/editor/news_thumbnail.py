"""
뉴스 숏츠 썸네일 생성기 (1080x1920)
bg_style: shock | money | warning | question | breaking
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont


_FONT_SANS_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
_FONT_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

W, H = 1080, 1920


# bg_style → (배경 그라데이션 상, 하, 강조색)
_BG_STYLES = {
    "shock":    ((180, 15, 15),  (50, 5, 5),    (255, 210, 0)),   # 빨강-검정, 노랑강조
    "money":    ((20, 140, 60),  (5, 60, 20),   (255, 215, 0)),   # 초록, 금색
    "warning":  ((220, 140, 10), (80, 40, 0),   (255, 255, 100)), # 주황, 노랑
    "question": ((80, 40, 180),  (20, 10, 60),  (200, 150, 255)), # 보라, 연보라
    "breaking": ((220, 30, 30),  (100, 0, 0),   (255, 255, 255)), # 빨강, 흰색
}


def _load_font(path: str, size: int, index: int = 2) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        return ImageFont.truetype(path, size)


def _draw_gradient(img: Image.Image, top: tuple, bot: tuple):
    """수직 그라데이션"""
    draw = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        t = y / H
        r = int(top[0] + t * (bot[0] - top[0]))
        g = int(top[1] + t * (bot[1] - top[1]))
        b = int(top[2] + t * (bot[2] - top[2]))
        draw.rectangle([0, y, W, y + 4], fill=(r, g, b))


def _draw_decorations(img: Image.Image, style: str, accent: tuple):
    """스타일별 데코레이션"""
    draw = ImageDraw.Draw(img, "RGBA")

    # 상단/하단 강조 바
    draw.rectangle([0, 0, W, 18], fill=(*accent, 255))
    draw.rectangle([0, H - 18, W, H], fill=(*accent, 255))

    # 코너 브라켓
    bracket = 100
    bw = 10
    for cx_, cy_, dx, dy in [
        (50, 80, 1, 1), (W - 50, 80, -1, 1),
        (50, H - 80, 1, -1), (W - 50, H - 80, -1, -1),
    ]:
        x2h, y2h = cx_ + dx * bracket, cy_ + dy * bw
        x2v, y2v = cx_ + dx * bw, cy_ + dy * bracket
        draw.rectangle(
            [min(cx_, x2h), min(cy_, y2h), max(cx_, x2h), max(cy_, y2h)],
            fill=(*accent, 220),
        )
        draw.rectangle(
            [min(cx_, x2v), min(cy_, y2v), max(cx_, x2v), max(cy_, y2v)],
            fill=(*accent, 220),
        )

    # "BREAKING" 라벨 (breaking 스타일만)
    if style == "breaking":
        lbl_font = _load_font(_FONT_SANS_BOLD, 72)
        label = "BREAKING"
        bbox = draw.textbbox((0, 0), label, font=lbl_font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        y = 150
        draw.rectangle([x - 40, y - 10, x + tw + 40, y + 100],
                       fill=(255, 0, 0, 255))
        draw.text((x, y), label, font=lbl_font, fill=(255, 255, 255))


def _render_emoji(emoji: str, size: int = 300) -> Image.Image | None:
    """컬러 이모지 렌더"""
    if not emoji:
        return None
    try:
        font = ImageFont.truetype(_FONT_EMOJI, 109)
    except Exception:
        return None
    canvas = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    try:
        d.text((0, 0), emoji, font=font, embedded_color=True)
    except Exception:
        return None
    bbox = canvas.getbbox()
    if not bbox:
        return None
    cropped = canvas.crop(bbox)
    ratio = size / max(cropped.size)
    return cropped.resize(
        (int(cropped.size[0] * ratio), int(cropped.size[1] * ratio)),
        Image.LANCZOS,
    )


def _draw_big_text(
    img: Image.Image, text: str, highlight_word: str = "",
    highlight_color: tuple = (255, 230, 0),
):
    """대문자 2~6자 큰 글씨. 강조어는 별도 색."""
    draw = ImageDraw.Draw(img, "RGBA")

    # 글자 수에 따라 폰트 크기 자동 조정
    n = len(text.replace(" ", ""))
    if n <= 3:
        size = 380
    elif n <= 5:
        size = 280
    else:
        size = 220
    font = _load_font(_FONT_SANS_BOLD, size)

    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=12)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (W - tw) // 2
    y = (H - th) // 2 - 50

    # 반투명 검정 배경
    pad = 40
    draw.rounded_rectangle(
        [x - pad, y - pad, x + tw + pad, y + th + pad + 20],
        radius=40, fill=(0, 0, 0, 180),
    )

    # 강조어 있으면 토큰별 색 구분
    if highlight_word:
        cursor_x = x
        import re
        tokens = re.split(r"(\s+)", text)
        for tk in tokens:
            color = highlight_color if highlight_word in tk else (255, 255, 255)
            draw.text(
                (cursor_x, y), tk, font=font, fill=color,
                stroke_width=12, stroke_fill=(0, 0, 0),
            )
            tb = draw.textbbox((cursor_x, y), tk, font=font, stroke_width=12)
            cursor_x = tb[2]
    else:
        draw.text(
            (x, y), text, font=font, fill=(255, 255, 255),
            stroke_width=12, stroke_fill=(0, 0, 0),
        )


def generate_thumbnail(
    thumbnail_data,
    output_path: str,
) -> str:
    """
    thumbnail_data: Thumbnail 객체 또는 dict
    출력: 1080x1920 JPG 썸네일
    """
    # dict/object 모두 허용
    get = (lambda k, d="": thumbnail_data.get(k, d)) if isinstance(thumbnail_data, dict) \
        else (lambda k, d="": getattr(thumbnail_data, k, d))

    big_text = get("big_text", "") or "뉴스"
    highlight = get("keyword_highlight", "")
    emoji = get("emoji", "")
    style = get("bg_style", "shock")

    top, bot, accent = _BG_STYLES.get(style, _BG_STYLES["shock"])

    img = Image.new("RGB", (W, H))
    _draw_gradient(img, top, bot)

    # 방사형 글로우 (중앙에)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W // 2 - 500, H // 2 - 500, W // 2 + 500, H // 2 + 500],
               fill=(*accent, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(100))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    _draw_decorations(img, style, accent)

    # 이모지 (하단 우측)
    if emoji:
        emoji_img = _render_emoji(emoji, size=320)
        if emoji_img:
            img_rgba = img.convert("RGBA")
            ex = W - emoji_img.width - 60
            ey = H - emoji_img.height - 200
            img_rgba.alpha_composite(emoji_img, (ex, ey))
            img = img_rgba.convert("RGB")

    _draw_big_text(img, big_text, highlight, highlight_color=accent)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=92)
    return output_path
