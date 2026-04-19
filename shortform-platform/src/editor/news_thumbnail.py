"""
뉴스 숏츠 썸네일 생성기 (1080x1920) — v2

개선 (v2):
- A. 실제 사진 배경 — Wikimedia 인물 / og:image / 세그먼트 climax 프레임에서 추출
- B. 인물 클로즈업 split layout — subject_name 있을 때 자동
- C. 2줄 긴 텍스트 + 자동 줄바꿈 (16~24자 가능)
- E. 시각 강조 — 노란 동그라미 (highlight word) + 빨간 화살표 (옵션)
"""

import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont


from src.common.paths import find_font
_FONT_SANS_BOLD = find_font("noto_sans_kr_bold") or "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
_FONT_EMOJI = find_font("noto_emoji") or "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

W, H = 1080, 1920


# bg_style → (배경 그라데이션 상, 하, 강조색)
_BG_STYLES = {
    "shock":    ((180, 15, 15),  (50, 5, 5),    (255, 210, 0)),
    "money":    ((20, 140, 60),  (5, 60, 20),   (255, 215, 0)),
    "warning":  ((220, 140, 10), (80, 40, 0),   (255, 255, 100)),
    "question": ((80, 40, 180),  (20, 10, 60),  (200, 150, 255)),
    "breaking": ((220, 30, 30),  (100, 0, 0),   (255, 255, 255)),
}

_HEADERS = {"User-Agent": "Mozilla/5.0 shortform-platform/1.0"}


# ── 유틸 ────────────────────────────────────────────────────────────

def _load_font(path: str, size: int, index: int = 2) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()


def _draw_gradient(img: Image.Image, top: tuple, bot: tuple):
    """수직 그라데이션 (배경 폴백)"""
    draw = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        t = y / H
        r = int(top[0] + t * (bot[0] - top[0]))
        g = int(top[1] + t * (bot[1] - top[1]))
        b = int(top[2] + t * (bot[2] - top[2]))
        draw.rectangle([0, y, W, y + 4], fill=(r, g, b))


def _fit_cover(img: Image.Image, target_w: int = W, target_h: int = H) -> Image.Image:
    """이미지를 target 크기에 cover (가운데 크롭)"""
    iw, ih = img.size
    scale = max(target_w / iw, target_h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - target_w) // 2
    top = (nh - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _darken(img: Image.Image, alpha: float = 0.55) -> Image.Image:
    """전체 어둡게 — 텍스트 가독성"""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, int(255 * alpha)))
    base = img.convert("RGBA")
    return Image.alpha_composite(base, overlay).convert("RGB")


def _bottom_gradient_overlay(img: Image.Image, height_ratio: float = 0.55) -> Image.Image:
    """하단부터 위로 어두워지는 그라데이션 — 하단 텍스트 영역 확보"""
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    h = base.size[1]
    start_y = int(h * (1.0 - height_ratio))
    for y in range(start_y, h, 4):
        t = (y - start_y) / max(1, h - start_y)
        a = int(220 * t)
        od.rectangle([0, y, base.size[0], y + 4], fill=(0, 0, 0, a))
    return Image.alpha_composite(base, overlay).convert("RGB")


def _right_gradient_overlay(img: Image.Image, width_ratio: float = 0.55) -> Image.Image:
    """우측부터 좌로 어두워지는 그라데이션 — split layout용 (좌:사진 / 우:텍스트)"""
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    w = base.size[0]
    start_x = int(w * (1.0 - width_ratio))
    for x in range(start_x, w, 4):
        t = (x - start_x) / max(1, w - start_x)
        a = int(230 * t)
        od.rectangle([x, 0, x + 4, base.size[1]], fill=(0, 0, 0, a))
    return Image.alpha_composite(base, overlay).convert("RGB")


def _top_gradient_overlay(img: Image.Image, height_ratio: float = 0.30,
                          peak_alpha: int = 200) -> Image.Image:
    """상단부터 아래로 어두워지는 그라데이션 — 페이지 nav bar/로고 묻기용.
    height_ratio: 위쪽 몇 %를 덮을지 (기본 30%)
    peak_alpha: 맨 위 alpha (가장 어두움). 아래로 갈수록 0.
    """
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    h = base.size[1]
    end_y = int(h * height_ratio)
    for y in range(0, end_y, 4):
        t = 1.0 - (y / max(1, end_y))   # y=0 → 1.0, y=end_y → 0.0
        a = int(peak_alpha * t)
        od.rectangle([0, y, base.size[0], y + 4], fill=(0, 0, 0, a))
    return Image.alpha_composite(base, overlay).convert("RGB")


# ── 배경 사진 수집 ──────────────────────────────────────────────────

def _extract_video_frame(video_path: str, time_offset: float = 1.0) -> Image.Image | None:
    """ffmpeg로 mp4에서 프레임 1장 → PIL Image"""
    if not video_path or not os.path.exists(video_path):
        return None
    if not video_path.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
        try:
            return Image.open(video_path).convert("RGB")
        except Exception:
            return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(time_offset), "-i", video_path,
             "-vframes", "1", "-q:v", "2", tmp],
            capture_output=True, check=True, timeout=10,
        )
        img = Image.open(tmp).convert("RGB").copy()
        os.unlink(tmp)
        return img
    except Exception:
        return None


def _download_image(url: str) -> Image.Image | None:
    """URL → PIL Image"""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 5_000:
            return None
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(data)
            tmp = f.name
        img = Image.open(tmp).convert("RGB").copy()
        os.unlink(tmp)
        return img
    except Exception:
        return None


def _fetch_subject_person_photo(subject: str, context: str) -> Image.Image | None:
    """subject_name → Wikimedia 인물 사진 (PIL Image)"""
    if not subject:
        return None
    try:
        from src.searcher.media_searcher import _wiki_resolve
    except Exception:
        return None
    for api in ("https://ko.wikipedia.org/w/api.php", "https://en.wikipedia.org/w/api.php"):
        title, img_url = _wiki_resolve(api, subject, context)
        if img_url:
            img = _download_image(img_url)
            if img:
                return img
    return None


def _pick_climax_segment(segments):
    """climax → twist → hook → 첫 세그먼트 순으로 픽"""
    for role in ("climax", "twist", "hook"):
        for s in segments:
            if getattr(s, "role", "") == role and getattr(s, "media_path", ""):
                return s
    for s in segments:
        if getattr(s, "media_path", ""):
            return s
    return None


def _pick_background_photo(news_script, news_og_image: str | None,
                           context_text: str) -> tuple[Image.Image | None, bool]:
    """배경 사진 수집. 우선순위:
       1) subject_name → Wikimedia 인물 사진 (split layout 가능)
       2) news_og_image → 기사 대표 사진
       3) climax 세그먼트 mp4 프레임
    반환: (PIL Image, is_person_photo)"""
    # 1) 인물 사진 (split 레이아웃 트리거)
    if news_script and getattr(news_script, "segments", None):
        # 우선 climax/hook/body 순회하며 첫 subject_name 찾기
        subj = ""
        for role_pri in ("climax", "hook", "body"):
            for s in news_script.segments:
                if getattr(s, "role", "") == role_pri and getattr(s, "subject_name", ""):
                    subj = s.subject_name
                    break
            if subj:
                break
        if not subj:
            for s in news_script.segments:
                if getattr(s, "subject_name", ""):
                    subj = s.subject_name
                    break
        if subj:
            person_img = _fetch_subject_person_photo(subj, context_text)
            if person_img:
                return person_img, True

    # 2) og:image
    if news_og_image:
        og_img = _download_image(news_og_image)
        if og_img:
            return og_img, False

    # 3) climax 세그먼트 영상 프레임
    if news_script and getattr(news_script, "segments", None):
        cl = _pick_climax_segment(news_script.segments)
        if cl:
            frame = _extract_video_frame(cl.media_path, time_offset=1.5)
            if frame:
                return frame, False

    return None, False


# ── 텍스트 처리 ────────────────────────────────────────────────────

def _split_text_for_thumbnail(text: str, max_per_line: int = 12) -> list[str]:
    """텍스트를 2줄로 분리. 명시적 \\n 우선, 없으면 어절 기준 자동 wrap."""
    text = (text or "").strip()
    if not text:
        return []
    if "\n" in text:
        return [ln.strip() for ln in text.split("\n") if ln.strip()][:2]
    # 글자수 짧으면 1줄
    if len(text) <= max_per_line:
        return [text]
    # 어절 기준 greedy 2줄 분배 (한글 길이 기반)
    tokens = text.split()
    if len(tokens) == 1:
        # 어절 1개 너무 길면 강제 분리
        mid = len(text) // 2
        return [text[:mid], text[mid:]]
    line1, line2 = "", ""
    for tk in tokens:
        cand = (line1 + " " + tk).strip()
        if len(cand) <= max_per_line and not line2:
            line1 = cand
        else:
            line2 = (line2 + " " + tk).strip()
    if not line2 and len(line1) > max_per_line:
        # 한 줄에 다 들어감 → 어절 절반에서 분리
        half = len(tokens) // 2
        line1 = " ".join(tokens[:half])
        line2 = " ".join(tokens[half:])
    return [line1, line2] if line2 else [line1]


def _font_size_for_lines(lines: list[str]) -> int:
    """줄 수·최대 줄 길이로 초기 폰트 크기 추정 (이후 _fit_font_size에서 축소)."""
    if not lines:
        return 200
    max_len = max(len(ln) for ln in lines)
    n_lines = len(lines)
    if n_lines == 1:
        if max_len <= 4:    return 380
        if max_len <= 6:    return 300
        if max_len <= 10:   return 240
        return 200
    # 2줄
    if max_len <= 6:    return 260
    if max_len <= 10:   return 220
    if max_len <= 14:   return 180
    return 150


def _fit_font_size(lines: list[str], max_width: int, font_path: str,
                   initial_size: int, stroke_w: int = 10,
                   min_size: int = 90, step: int = 8) -> int:
    """가장 긴 라인이 max_width 안에 들어가는 최대 폰트 크기.
    초기값에서 시작해 step px씩 줄여가며 측정. min_size 이하로는 안 떨어짐.
    """
    if not lines:
        return initial_size
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    size = initial_size
    while size > min_size:
        font = _load_font(font_path, size)
        max_w = 0
        for ln in lines:
            bb = dummy.textbbox((0, 0), ln, font=font, stroke_width=stroke_w)
            max_w = max(max_w, bb[2] - bb[0])
        if max_w <= max_width:
            return size
        size -= step
    return min_size


def _draw_multiline_text(
    img: Image.Image, lines: list[str], highlight_word: str = "",
    highlight_color: tuple = (255, 230, 0),
    box_left: int = 60, box_right: int = W - 60,
    box_top: int = 0, box_bottom: int = H,
    bg_pad: bool = True,
) -> tuple[int, int, int, int]:
    """주어진 박스 내 중앙에 멀티라인 텍스트 렌더. 강조어 색 분기.
    반환: 렌더된 텍스트 영역 bbox (x1, y1, x2, y2) — 동그라미 위치 계산용"""
    if not lines:
        return (0, 0, 0, 0)
    draw = ImageDraw.Draw(img, "RGBA")
    box_w = box_right - box_left
    # 초기 크기 추정 → 실제 픽셀 폭 측정해 박스 안에 들어가는 최대 크기로 축소
    initial = _font_size_for_lines(lines)
    size = _fit_font_size(lines, max_width=box_w - 40,  # 좌우 20px 여유
                          font_path=_FONT_SANS_BOLD, initial_size=initial)
    font = _load_font(_FONT_SANS_BOLD, size)
    line_h = int(size * 1.2)
    total_h = line_h * len(lines)
    box_h = box_bottom - box_top
    start_y = box_top + (box_h - total_h) // 2

    # 모든 라인 폭 측정
    measured = []
    for ln in lines:
        bb = draw.textbbox((0, 0), ln, font=font, stroke_width=10)
        measured.append((ln, bb[2] - bb[0], bb[3] - bb[1]))

    overall_left = min(box_left + (box_w - w) // 2 for _, w, _ in measured) - 30
    overall_right = max(box_left + (box_w - w) // 2 + w for _, w, _ in measured) + 30
    overall_top = start_y - 20
    overall_bottom = start_y + total_h + 20

    # 반투명 배경 박스 (옵션)
    if bg_pad:
        draw.rounded_rectangle(
            [overall_left, overall_top, overall_right, overall_bottom],
            radius=30, fill=(0, 0, 0, 140),
        )

    # 라인별 렌더 + 강조어 색 분기
    highlight_bbox = None
    cy = start_y
    for ln, lw, _ in measured:
        x = box_left + (box_w - lw) // 2
        if highlight_word and highlight_word in ln:
            # 토큰별 색
            cursor_x = x
            tokens = re.split(r"(\s+)", ln)
            for tk in tokens:
                color = highlight_color if (highlight_word and highlight_word in tk) else (255, 255, 255)
                draw.text((cursor_x, cy), tk, font=font, fill=color,
                          stroke_width=10, stroke_fill=(0, 0, 0))
                tb = draw.textbbox((cursor_x, cy), tk, font=font, stroke_width=10)
                if highlight_word and highlight_word in tk and not highlight_bbox:
                    highlight_bbox = tb
                cursor_x = tb[2]
        else:
            draw.text((x, cy), ln, font=font, fill=(255, 255, 255),
                      stroke_width=10, stroke_fill=(0, 0, 0))
        cy += line_h

    return highlight_bbox or (overall_left, overall_top, overall_right, overall_bottom)


# ── 시각 강조 (노란 동그라미·빨간 화살표) ─────────────────────────────

def _draw_yellow_circle(img: Image.Image, bbox: tuple, accent: tuple = (255, 230, 0)):
    """강조어 bbox 둘레에 손그림 느낌 노란 원"""
    if not bbox:
        return
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    rx = max((x2 - x1) // 2 + 35, 80)
    ry = max((y2 - y1) // 2 + 25, 60)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    # 손그림 느낌 — 약간 비뚤어진 타원 (2번 겹쳐 그리기)
    for offset, w in [((0, 0), 12), ((4, 2), 8)]:
        ox, oy = offset
        od.ellipse(
            [cx - rx + ox, cy - ry + oy, cx + rx + ox, cy + ry + oy],
            outline=(*accent, 255), width=w,
        )
    base = img.convert("RGBA")
    img.paste(Image.alpha_composite(base, overlay).convert("RGB"))


def _draw_corner_badge(img: Image.Image, text: str, accent: tuple):
    """좌상단 컬러 라벨 (BREAKING / 속보 등)"""
    draw = ImageDraw.Draw(img, "RGBA")
    font = _load_font(_FONT_SANS_BOLD, 64)
    bb = draw.textbbox((0, 0), text, font=font)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]
    pad_x, pad_y = 36, 18
    # 좌상단 비스듬한 띠
    draw.polygon(
        [(0, 0), (tw + pad_x * 2 + 60, 0),
         (tw + pad_x * 2, 30 + th + pad_y), (0, 30 + th + pad_y)],
        fill=(*accent, 255),
    )
    draw.text((pad_x, 12), text, font=font, fill=(0, 0, 0))


def _render_emoji(emoji: str, size: int = 320) -> Image.Image | None:
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


# ── 메인 ─────────────────────────────────────────────────────────────

def generate_thumbnail(
    thumbnail_data,
    output_path: str,
    news_script=None,           # NewsScript (선택) — 인물·세그먼트 정보용
    news_og_image: str | None = None,  # 기사 og:image URL (선택)
) -> str:
    """1080x1920 JPG 썸네일.

    레이아웃 선택:
      - 인물 사진 잡히면 → split (좌:사진 / 우:텍스트 + 노란 동그라미)
      - 사진만 있으면    → full bleed (사진 위 어둡게 + 하단 텍스트)
      - 사진 없음        → gradient (기존 추상 배경)
    """
    get = (lambda k, d="": thumbnail_data.get(k, d)) if isinstance(thumbnail_data, dict) \
        else (lambda k, d="": getattr(thumbnail_data, k, d))

    big_text = get("big_text", "") or "뉴스"
    highlight = get("keyword_highlight", "")
    emoji = get("emoji", "")
    style = get("bg_style", "shock")

    top, bot, accent = _BG_STYLES.get(style, _BG_STYLES["shock"])

    # 컨텍스트 = 뉴스 제목 (Wikimedia disambiguation용)
    context_text = ""
    if news_script:
        context_text = (getattr(news_script, "title", "") or "") + " " + \
                       (getattr(news_script, "hook_phrase", "") or "")

    bg_photo, is_person = _pick_background_photo(news_script, news_og_image, context_text)

    # 텍스트 2줄 분리
    lines = _split_text_for_thumbnail(big_text, max_per_line=12)

    if bg_photo and is_person:
        # ─ Split 레이아웃: 좌 사진 / 우 텍스트 ─
        img = _fit_cover(bg_photo, W, H)
        img = _right_gradient_overlay(img, width_ratio=0.65)
        # 상단 25%도 살짝 어둡게 (페이지 nav·헤더 묻기)
        img = _top_gradient_overlay(img, height_ratio=0.25, peak_alpha=140)
        # 우측 55% 영역에 텍스트
        text_box = (int(W * 0.40), 0, W - 40, H)
        hl_bbox = _draw_multiline_text(
            img, lines, highlight, accent,
            box_left=text_box[0], box_right=text_box[2],
            box_top=text_box[1], box_bottom=text_box[3],
            bg_pad=False,
        )
        if highlight and hl_bbox:
            _draw_yellow_circle(img, hl_bbox, accent)
    elif bg_photo:
        # ─ Full bleed: 상단도 어둡게 (nav bar 묻기) + 하단 텍스트 ─
        img = _fit_cover(bg_photo, W, H)
        img = _top_gradient_overlay(img, height_ratio=0.32, peak_alpha=200)
        img = _bottom_gradient_overlay(img, height_ratio=0.65)
        hl_bbox = _draw_multiline_text(
            img, lines, highlight, accent,
            box_left=60, box_right=W - 60,
            box_top=int(H * 0.55), box_bottom=H - 80,
            bg_pad=False,
        )
        if highlight and hl_bbox:
            _draw_yellow_circle(img, hl_bbox, accent)
    else:
        # ─ Fallback: 기존 그라데이션 ─
        img = Image.new("RGB", (W, H))
        _draw_gradient(img, top, bot)
        # 방사형 글로우
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([W // 2 - 500, H // 2 - 500, W // 2 + 500, H // 2 + 500],
                   fill=(*accent, 80))
        glow = glow.filter(ImageFilter.GaussianBlur(100))
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
        hl_bbox = _draw_multiline_text(
            img, lines, highlight, accent,
            box_left=60, box_right=W - 60,
            box_top=0, box_bottom=H,
            bg_pad=True,
        )
        if highlight and hl_bbox:
            _draw_yellow_circle(img, hl_bbox, accent)

    # 좌상단 컬러 배지 (BREAKING / 속보)
    if style == "breaking":
        _draw_corner_badge(img, "속보", (255, 30, 30))

    # 이모지 — 우상단 배치 (텍스트 영역과 충돌 회피).
    # 사이즈 축소(260 → 180)로 본문 덮지 않게.
    if emoji:
        emoji_img = _render_emoji(emoji, size=180)
        if emoji_img:
            img_rgba = img.convert("RGBA")
            ex = W - emoji_img.width - 60
            # split 레이아웃이면 우측 텍스트 박스가 우상단까지 차지 → 좌상단으로
            # full bleed면 우상단 (텍스트는 하단)
            if bg_photo and is_person:
                ex = 60   # 좌상단 (split 레이아웃의 사진 위)
                ey = 80
            else:
                ey = 60   # 우상단
            img_rgba.alpha_composite(emoji_img, (ex, ey))
            img = img_rgba.convert("RGB")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=92)
    return output_path
