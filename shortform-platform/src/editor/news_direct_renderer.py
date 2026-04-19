"""
뉴스 숏츠 직접 렌더링 — 완성된 MP4 생성.
기능: 테마 / 자막 청크 / 키워드 하이라이트 / Ken Burns / 수치 팝업 /
      이모지 리액션 / 크로스페이드 전환 / 진행 바 / 하단 티커 / 역할 색상
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.editor.news_themes import get_theme, apply_overrides


# ── 폰트 ──────────────────────────────────────────────────────────────────────

_FONT_SANS_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
_FONT_SANS_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
_FONT_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"


# ── 역할별 색상 ───────────────────────────────────────────────────────────────

ROLE_ACCENT_COLORS = {
    "hook":    (255, 80, 80),    # red
    "context": (180, 180, 180),  # gray
    "body":    (255, 255, 255),  # white
    "climax":  (255, 215, 0),    # gold
    "twist":   (180, 100, 255),  # purple
    "cta":     (255, 140, 0),    # orange (기본)
}

# CTA 타입별 색상 (cta_type 필드 활용)
CTA_TYPE_COLORS = {
    "follow": (255, 140, 0),    # 주황 (팔로우 버튼 느낌)
    "save":   (80, 160, 255),   # 파랑 (북마크 느낌)
    "share":  (255, 80, 140),   # 핑크 (공유 느낌)
    "engage": (255, 215, 0),    # 골드 (댓글 유도 — 강조)
}

# 감정 타깃 → 자막 톤 보정 (R,G,B 가중치)
EMOTION_TONE = {
    "curiosity": (1.0, 0.95, 0.6),    # 노란 기조
    "outrage":   (1.0, 0.5, 0.5),     # 빨간 기조
    "shock":     (1.0, 1.0, 0.3),     # 선명한 노랑
    "sympathy":  (0.6, 0.8, 1.0),     # 파란 기조
    "fomo":      (1.0, 0.7, 0.3),     # 주황 기조
}

_EMPH_COLOR = (255, 230, 0, 255)  # 강조 단어 노란색


# ── 이모지 제거 (일반 텍스트용) ─────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF\U00002700-\U000027BF\U0001F1E0-\U0001F1FF"
    "\u2300-\u23FF\u2B00-\u2BFF"
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(s: str) -> str:
    return _EMOJI_RE.sub("", s).strip() if s else s


# ── 폰트 로더 ─────────────────────────────────────────────────────────────────

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size, index=2)  # KR
    except Exception:
        return ImageFont.truetype(path, size)


def _load_emoji_font(size: int) -> ImageFont.FreeTypeFont | None:
    """NotoColorEmoji는 고정 크기 (109px). 크기 맞추려면 이미지 리사이즈."""
    try:
        return ImageFont.truetype(_FONT_EMOJI, 109)
    except Exception:
        return None


# ── 텍스트 유틸 ───────────────────────────────────────────────────────────────

def _wrap_lines(text: str, font, max_w: int, draw) -> list[str]:
    result = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            result.append("")
            continue
        words = paragraph.split(" ")
        line = ""
        for w in words:
            test = (line + " " + w).strip() if line else w
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_w:
                line = test
            else:
                if line:
                    result.append(line)
                line = w
        if line:
            result.append(line)
    return result


def _compute_area(theme: dict, area_name: str) -> tuple[int, int]:
    W, H = theme["canvas"]
    if theme["layout"] == "letterbox":
        lb = theme["letterbox"]
        if area_name == "top":
            return 0, lb["top_h"]
        if area_name == "bottom":
            return lb["top_h"] + lb["vid_h"], lb["bot_h"]
        if area_name == "video_bottom_overlay":
            overlay_h = int(lb["vid_h"] * 0.30)
            return lb["top_h"] + lb["vid_h"] - overlay_h - 40, overlay_h
        if area_name == "video_bottom_pill":
            # 알약형 자막 영역: 영상 하단 25% 부근
            pill_h = int(lb["vid_h"] * 0.25)
            return lb["top_h"] + lb["vid_h"] - pill_h - 50, pill_h
        return lb["top_h"], lb["vid_h"]
    if area_name == "top_overlay":
        return int(H * 0.12), int(H * 0.25)
    if area_name == "bottom_overlay":
        return int(H * 0.78), int(H * 0.18)
    return 0, H


def _tokenize(line: str) -> list[str]:
    return [t for t in re.split(r"(\s+)", line) if t]


def _is_emphasis(token: str, emph_words: list) -> bool:
    t = token.strip()
    if not t or not emph_words:
        return False
    return any(w.strip() and w.strip() in t for w in emph_words)


def _draw_block(draw, lines, font, area_top, area_h, W, color,
                stroke_w, stroke_color, line_spacing, emphasis_words=None,
                valign: str = "center", pad: int = 0):
    if not lines:
        return
    emphasis_words = emphasis_words or []
    line_heights = []
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln or "가", font=font, stroke_width=stroke_w)
        line_heights.append(bbox[3] - bbox[1])
    total_h = sum(line_heights) + line_spacing * (len(lines) - 1)
    if valign == "top":
        y = area_top + pad
    elif valign == "bottom":
        y = area_top + area_h - total_h - pad
    else:
        y = area_top + (area_h - total_h) // 2
    for ln, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), ln or "", font=font, stroke_width=stroke_w)
        lw = bbox[2] - bbox[0]
        x = (W - lw) // 2
        if emphasis_words:
            cursor_x = x
            for token in _tokenize(ln):
                tc = _EMPH_COLOR if _is_emphasis(token, emphasis_words) else color
                draw.text((cursor_x, y), token, font=font, fill=tc,
                          stroke_width=stroke_w, stroke_fill=stroke_color)
                tb = draw.textbbox((cursor_x, y), token, font=font, stroke_width=stroke_w)
                cursor_x = tb[2]
        else:
            draw.text((x, y), ln, font=font, fill=color,
                      stroke_width=stroke_w, stroke_fill=stroke_color)
        y += lh + line_spacing


def _draw_pill_caption(draw, lines, font, area_top, area_h, W,
                       text_color, bg=(0, 0, 0, 235),
                       pad_x: int = 40, pad_y: int = 18,
                       radius: int = 32, line_spacing: int = 8):
    """영상 위에 뜨는 알약형(rounded rect) 자막 — 각 줄마다 하나의 pill."""
    if not lines:
        return
    # 각 줄 메트릭
    metrics = []
    for ln in lines:
        if not ln.strip():
            continue
        bbox = draw.textbbox((0, 0), ln, font=font)
        metrics.append((ln, bbox[2] - bbox[0], bbox[3] - bbox[1]))
    if not metrics:
        return
    total_h = sum(lh + pad_y * 2 for _, _, lh in metrics) + line_spacing * (len(metrics) - 1)
    y = area_top + (area_h - total_h) // 2
    for ln, lw, lh in metrics:
        box_x = (W - lw) // 2 - pad_x
        box_w = lw + pad_x * 2
        box_h = lh + pad_y * 2
        draw.rounded_rectangle(
            [box_x, y, box_x + box_w, y + box_h],
            radius=radius, fill=bg,
        )
        text_x = (W - lw) // 2
        # 한글 폰트는 baseline offset 존재 — textbbox의 top(bbox[1])을 보정
        bbox2 = draw.textbbox((0, 0), ln, font=font)
        draw.text((text_x, y + pad_y - bbox2[1]), ln, font=font, fill=text_color)
        y += box_h + line_spacing


# ── 청크 2줄 맞춤 (merge + split) ─────────────────────────────────────────────

def _merge_chunks_to_target_lines(
    chunks: list[str],
    timings: list[tuple[float, float]],
    font, max_width: int, target_lines: int = 2,
) -> tuple[list[str], list[tuple[float, float]]]:
    """
    짧은 청크들을 병합해 최대 target_lines 줄에 꽉 차게 만듦.
    1줄밖에 안 차는 청크 다음에 청크가 더 있으면 붙여서 2줄로.
    """
    if not chunks:
        return [], []
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    merged: list[str] = []
    merged_t: list[tuple[float, float]] = []

    i = 0
    while i < len(chunks):
        cur = chunks[i].strip()
        cur_start, cur_end = timings[i]
        # 다음 청크들 점진적 병합 (target_lines 초과 전까지)
        while i + 1 < len(chunks):
            nxt = chunks[i + 1].strip()
            if not nxt:
                break
            combined = (cur + " " + nxt).strip()
            lines = _wrap_lines(combined, font, max_width, dummy)
            if len(lines) <= target_lines:
                cur = combined
                cur_end = timings[i + 1][1]
                i += 1
            else:
                break
        merged.append(cur)
        merged_t.append((cur_start, cur_end))
        i += 1

    return merged, merged_t


def _split_chunks_max_lines(
    chunks: list[str],
    timings: list[tuple[float, float]],
    font, max_width: int, max_lines: int = 2,
) -> tuple[list[str], list[tuple[float, float]]]:
    """
    두 단계:
      1) 짧은 청크들 병합해 2줄에 맞춤 (1줄짜리 단독 방지)
      2) 여전히 넘치는 청크는 2줄 그룹으로 분할
    """
    # 1단계: 병합
    chunks, timings = _merge_chunks_to_target_lines(chunks, timings, font, max_width, max_lines)

    # 2단계: 분할 (max_lines 초과 방지)
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    new_chunks: list[str] = []
    new_timings: list[tuple[float, float]] = []

    for chunk, (t_start, t_end) in zip(chunks, timings):
        if not chunk.strip():
            new_chunks.append(chunk)
            new_timings.append((t_start, t_end))
            continue
        lines = _wrap_lines(chunk, font, max_width, dummy)
        if len(lines) <= max_lines:
            new_chunks.append(chunk)
            new_timings.append((t_start, t_end))
            continue

        total_dur = t_end - t_start
        total_chars = sum(len(l) for l in lines) or 1
        cursor_t = t_start
        groups = [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]
        for g_idx, grp in enumerate(groups):
            sub_text = "\n".join(grp)
            sub_chars = sum(len(l) for l in grp)
            sub_dur = total_dur * sub_chars / total_chars
            sub_end = t_end if g_idx == len(groups) - 1 else cursor_t + sub_dur
            new_chunks.append(sub_text)
            new_timings.append((cursor_t, sub_end))
            cursor_t = sub_end

    return new_chunks, new_timings


# ── 이모지 렌더링 ─────────────────────────────────────────────────────────────

def _render_emoji_image(emoji: str, size: int = 180) -> Image.Image | None:
    """NotoColorEmoji로 이모지를 PNG 이미지로 렌더 (컬러)"""
    font = _load_emoji_font(109)
    if not font:
        return None
    # 1024px 캔버스에 그려서 리사이즈
    canvas = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    try:
        d.text((0, 0), emoji, font=font, embedded_color=True)
    except Exception:
        return None
    # 실제 이모지 영역만 crop
    bbox = canvas.getbbox()
    if not bbox:
        return None
    emoji_img = canvas.crop(bbox)
    # 목표 사이즈로 리사이즈
    ratio = size / max(emoji_img.size)
    new_size = (int(emoji_img.size[0] * ratio), int(emoji_img.size[1] * ratio))
    return emoji_img.resize(new_size, Image.LANCZOS)


# ── 오버레이 PNG 생성 ─────────────────────────────────────────────────────────

def _make_segment_overlay(
    title: str, caption_chunk: str, theme: dict,
    emphasis_words: list, highlight_stat: str, reaction_emoji: str,
    role_color: tuple, out_path: str,
):
    """한 청크에 대한 오버레이 PNG 생성"""
    W, H = theme["canvas"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 섹션 기본값 — override가 부분적이어도 안전하게 렌더
    def _cfg(section: str, defaults: dict) -> dict:
        base = dict(defaults)
        base.update(theme.get(section) or {})
        return base

    TITLE_DEFAULTS = {
        "font": _FONT_SANS_BOLD, "size": 88, "color": (255, 255, 255, 255),
        "stroke_w": 0, "stroke_color": (0, 0, 0, 255),
        "line_spacing": 10, "max_width": 0.88, "area": "top",
    }
    CAPTION_DEFAULTS = {
        "font": _FONT_SANS_BOLD, "size": 64, "color": (255, 240, 0, 255),
        "stroke_w": 6, "stroke_color": (0, 0, 0, 255),
        "line_spacing": 10, "max_width": 0.85, "area": "bottom",
    }

    # 1) 상단 타이틀
    if title:
        cfg = _cfg("title", TITLE_DEFAULTS)
        font = _load_font(cfg["font"], cfg["size"])
        lines = _wrap_lines(_strip_emoji(title), font, int(W * cfg["max_width"]), draw)
        a_top, a_h = _compute_area(theme, cfg["area"])
        if cfg.get("accent_last_line") and len(lines) >= 2:
            lhs = []
            for ln in lines:
                b = draw.textbbox((0, 0), ln or "가", font=font, stroke_width=cfg["stroke_w"])
                lhs.append(b[3] - b[1])
            total_h = sum(lhs) + cfg["line_spacing"] * (len(lines) - 1)
            y = a_top + (a_h - total_h) // 2
            accent = cfg.get("accent_color", (255, 240, 0, 255))
            for idx, (ln, lh) in enumerate(zip(lines, lhs)):
                b = draw.textbbox((0, 0), ln, font=font, stroke_width=cfg["stroke_w"])
                lw = b[2] - b[0]
                x = (W - lw) // 2
                color = accent if idx == len(lines) - 1 else cfg["color"]
                draw.text((x, y), ln, font=font, fill=color,
                          stroke_width=cfg["stroke_w"], stroke_fill=cfg["stroke_color"])
                y += lh + cfg["line_spacing"]
        else:
            _draw_block(draw, lines, font, a_top, a_h, W,
                        color=cfg["color"], stroke_w=cfg["stroke_w"],
                        stroke_color=cfg["stroke_color"], line_spacing=cfg["line_spacing"],
                        emphasis_words=emphasis_words)

    # 2) 자막 (청크) — 테마 area 별 렌더 방식
    if caption_chunk:
        cfg = _cfg("caption", CAPTION_DEFAULTS)
        font = _load_font(cfg["font"], cfg["size"])
        lines = _wrap_lines(_strip_emoji(caption_chunk), font, int(W * cfg["max_width"]), draw)
        a_top, a_h = _compute_area(theme, cfg["area"])
        y_off = int(cfg.get("y_offset", 0) or 0)
        a_top += y_off
        if cfg["area"] == "video_bottom_pill":
            _draw_pill_caption(
                draw, lines, font, a_top, a_h, W,
                text_color=cfg["color"],
                bg=cfg.get("pill_bg", (0, 0, 0, 235)),
                pad_x=cfg.get("pill_pad_x", 38),
                pad_y=cfg.get("pill_pad_y", 16),
                radius=cfg.get("pill_radius", 32),
                line_spacing=cfg.get("line_spacing", 8),
            )
        else:
            cap_valign = "top" if cfg["area"] == "bottom" else "center"
            cap_pad = 32 if cap_valign == "top" else 0
            _draw_block(draw, lines, font, a_top, a_h, W,
                        color=cfg["color"], stroke_w=cfg["stroke_w"],
                        stroke_color=cfg["stroke_color"], line_spacing=cfg["line_spacing"],
                        emphasis_words=emphasis_words,
                        valign=cap_valign, pad=cap_pad)

    # 2.5) 하단 브랜드 (fixed_bottom_text)
    fixed_btm = theme.get("fixed_bottom_text") or ""
    btm_cfg = theme.get("bottom_brand") or {}
    if fixed_btm:
        # 테마에 bottom_brand가 없어도 기본값으로 렌더 가능
        b_font_path = btm_cfg.get("font") or _FONT_SANS_BOLD
        b_size = btm_cfg.get("size", 78)
        b_color = btm_cfg.get("color", (255, 255, 255, 255))
        b_stroke_w = btm_cfg.get("stroke_w", 0)
        b_stroke_color = btm_cfg.get("stroke_color", (0, 0, 0, 255))
        b_line_spacing = btm_cfg.get("line_spacing", 0)
        b_max_width = btm_cfg.get("max_width", 0.8)
        b_area = btm_cfg.get("area", "bottom")
        b_font = _load_font(b_font_path, b_size)
        b_lines = _wrap_lines(fixed_btm, b_font, int(W * b_max_width), draw)
        b_top, b_h = _compute_area(theme, b_area)
        _draw_block(draw, b_lines, b_font, b_top, b_h, W,
                    color=b_color, stroke_w=b_stroke_w,
                    stroke_color=b_stroke_color,
                    line_spacing=b_line_spacing)

    # 3) 수치 팝업 — 영상 영역 하단에 작게
    if highlight_stat:
        stat_font = _load_font(_FONT_SANS_BOLD, 92)
        if theme["layout"] == "letterbox":
            lb = theme["letterbox"]
            vid_bot = lb["top_h"] + lb["vid_h"]
            y_bottom = vid_bot - 40   # 영상 하단에서 40px 위 (bottom edge 기준)
        else:
            y_bottom = int(H * 0.82)
        bbox = draw.textbbox((0, 0), highlight_stat, font=stat_font, stroke_width=5)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (W - tw) // 2
        y = y_bottom - th
        pad = 16
        draw.rounded_rectangle(
            [x - pad, y - pad, x + tw + pad, y + th + pad + 8],
            radius=16, fill=(0, 0, 0, 170),
        )
        draw.text((x, y), highlight_stat, font=stat_font,
                  fill=role_color + (255,) if len(role_color) == 3 else role_color,
                  stroke_width=5, stroke_fill=(0, 0, 0))

    # 4) 리액션 이모지 (우측 상단)
    if reaction_emoji:
        emoji_img = _render_emoji_image(_strip_emoji.__wrapped__(reaction_emoji)
                                        if False else reaction_emoji, size=200)
        if emoji_img:
            # 영상 영역 우측 상단
            if theme["layout"] == "letterbox":
                lb = theme["letterbox"]
                ex = W - emoji_img.width - 40
                ey = lb["top_h"] + 40
            else:
                ex = W - emoji_img.width - 40
                ey = 60
            img.alpha_composite(emoji_img, (ex, ey))

    img.save(out_path)


# ── 하단 티커 오버레이 (전체 영상 공용) ────────────────────────────────────────

def _make_ticker_overlay(ticker_text: str, theme: dict, out_path: str):
    """하단에 스크롤될 티커 PNG (가로 길게, 나중에 움직임)"""
    W, H = theme["canvas"]
    if not ticker_text:
        return None
    # 긴 이미지 하나 만들기 (내용 2~3번 반복해서 연속성)
    font = _load_font(_FONT_SANS_BOLD, 36)
    repeated = ("   •   ".join([ticker_text] * 3))
    tmp_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = tmp_draw.textbbox((0, 0), repeated, font=font)
    tw = bbox[2] - bbox[0]
    th = 60
    img = Image.new("RGBA", (tw + 200, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((100, 10), repeated, font=font, fill=(255, 255, 255, 255))
    img.save(out_path)
    return out_path


# ── 영상 필터: Ken Burns + 레터박스 ───────────────────────────────────────────

def _video_filter_with_kenburns(theme: dict, duration: float, direction: int) -> str:
    """
    영상용 레터박스 필터. zoompan은 동영상 프레임을 먹어버리므로 사용 금지.
    동영상의 자연스러운 움직임을 그대로 보존 — Ken Burns는 미세 zoom만 적용.
    """
    W, H = theme["canvas"]
    if theme["layout"] == "letterbox":
        lb = theme["letterbox"]
        vid_w, vid_h = W, lb["vid_h"]
    else:
        vid_w, vid_h = W, H

    # 살짝 줌인 (1.0 → 1.06) — 방향별로 시작점 살짝 다르게
    # scale로 미리 키운 후 crop x/y를 t에 따라 이동 (진짜 영상의 모션 보존)
    zoom_factor = 1.08
    scaled_w = int(vid_w * zoom_factor)
    scaled_h = int(vid_h * zoom_factor)

    # 팬 방향: 0=정적 중앙, 1=좌→우, 2=우→좌, 3=위→아래
    if direction % 4 == 0:
        x_expr = f"(iw-{vid_w})/2"
        y_expr = f"(ih-{vid_h})/2"
    elif direction % 4 == 1:
        x_expr = f"(iw-{vid_w})*t/{duration}"
        y_expr = f"(ih-{vid_h})/2"
    elif direction % 4 == 2:
        x_expr = f"(iw-{vid_w})*(1-t/{duration})"
        y_expr = f"(ih-{vid_h})/2"
    else:
        x_expr = f"(iw-{vid_w})/2"
        y_expr = f"(ih-{vid_h})*t/{duration}"

    core = (
        f"scale={vid_w}:{vid_h}:force_original_aspect_ratio=increase,"
        f"scale={scaled_w}:{scaled_h},"
        f"crop={vid_w}:{vid_h}:{x_expr}:{y_expr}"
    )
    if theme["layout"] == "letterbox":
        return f"{core},pad={W}:{H}:0:{lb['top_h']}:black,setsar=1"
    return f"{core},setsar=1"


# ── 세그먼트 렌더링 ───────────────────────────────────────────────────────────

def _render_segment(seg, theme: dict, title: str, out: str, work: Path, kb_direction: int):
    """세그먼트 하나를 렌더링: 청크 나눠서 오버레이 + 배경 + 합성"""
    W, H = theme["canvas"]
    fps = 30

    # 1) 배경 영상 (Ken Burns + 레터박스)
    # 소스가 seg.duration보다 짧으면 stream_loop -1로 자동 반복
    bg_path = str(work / f"bg_{Path(out).stem}.mp4")
    vf = _video_filter_with_kenburns(theme, seg.duration, kb_direction)
    subprocess.run([
        "ffmpeg", "-y",
        "-stream_loop", "-1",        # ← 소스 루프 (길이 부족 대응)
        "-i", seg.media_path,
        "-vf", vf,
        "-t", str(seg.duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        bg_path,
    ], capture_output=True, check=True)

    # 2) 청크 결정
    chunks = seg.caption_chunks if seg.caption_chunks else [seg.caption]
    chunks = [c for c in chunks if c]
    if not chunks:
        chunks = [""]

    # 3) 청크 타이밍 — TTS 단어 타임스탬프로 정확히 싱크
    from src.editor.news_audio import get_word_timings, compute_chunk_timings
    tts_file = getattr(seg, "_tts_file", None)
    words = get_word_timings(tts_file) if tts_file else []
    chunk_timings = compute_chunk_timings(chunks, words, seg.duration)

    # 3.5) 청크가 2줄 초과 시 자동 분할 (자막은 최대 2줄)
    cap_cfg = theme["caption"]
    cap_font = _load_font(cap_cfg["font"], cap_cfg["size"])
    cap_max_w = int(theme["canvas"][0] * cap_cfg["max_width"])
    chunks, chunk_timings = _split_chunks_max_lines(
        chunks, chunk_timings, cap_font, cap_max_w, max_lines=2,
    )

    # 4) 청크별 오버레이 PNG + 적용 시간
    # CTA 세그먼트는 cta_type별 색상 오버라이드
    if seg.role == "cta" and getattr(seg, "cta_type", ""):
        role_color = CTA_TYPE_COLORS.get(seg.cta_type, ROLE_ACCENT_COLORS["cta"])
    else:
        role_color = ROLE_ACCENT_COLORS.get(seg.role, (255, 255, 255))

    # filter_complex 구성: [0:v] [1:v]overlay enable='between(t,a,b)' ...
    overlay_inputs = []
    filter_parts = ["[0:v]format=yuva420p[bg]"]
    prev_label = "bg"

    for i, chunk in enumerate(chunks):
        ovl_path = str(work / f"ovl_{Path(out).stem}_{i}.png")
        t_start, t_end = chunk_timings[i]
        # 마지막 청크는 seg 끝까지 표시 보장
        if i == len(chunks) - 1:
            t_end = seg.duration + 0.1
        _make_segment_overlay(
            title=title,
            caption_chunk=chunk,
            theme=theme,
            emphasis_words=seg.emphasis_words or [],
            highlight_stat=seg.highlight_stat or "",
            reaction_emoji=seg.reaction_emoji or "",
            role_color=role_color,
            out_path=ovl_path,
        )
        overlay_inputs.extend(["-i", ovl_path])
        out_label = f"v{i}"
        filter_parts.append(
            f"[{prev_label}][{i+1}:v]overlay=0:0:enable='between(t,{t_start:.3f},{t_end:.3f})'[{out_label}]"
        )
        prev_label = out_label

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y", "-i", bg_path,
        *overlay_inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_label}]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-t", str(seg.duration),
        out,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


# ── 전체 렌더링 + 전역 오버레이 (진행 바, 티커) ────────────────────────────────

def _add_progress_and_ticker(
    src_video: str, total_duration: float, ticker_text: str,
    out_path: str, work: Path, W: int = 1080, H: int = 1920,
):
    """상단 진행 바 + 하단 티커 추가"""
    inputs = ["-i", src_video]
    filters = ["[0:v]"]
    chain = ""

    # 진행 바 (상단 3px 흰색, 시간에 따라 채워짐)
    chain += (
        f"drawbox=x=0:y=0:w='iw*(t/{total_duration})':h=4:color=white@0.9:t=fill"
    )

    # 티커 (있으면)
    ticker_png = None
    if ticker_text:
        ticker_png = str(work / "ticker.png")
        _make_ticker_overlay(ticker_text, {"canvas": (W, H)}, ticker_png)
        inputs.extend(["-i", ticker_png])
        # 스크롤: x = W - (W + ticker_w) * (t/total)
        chain += f"[vid0];[vid0][1:v]overlay=x='W-(W+w)*mod(t*120,W+w)/(W+w)':y={H-70}:format=auto"

    full_filter = "[0:v]" + chain

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", full_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


# ── 세그먼트 연결 (크로스페이드) ───────────────────────────────────────────────

def _concat_with_xfade(seg_files: list[str], durations: list[float], out_path: str, fade_dur: float = 0.3):
    """xfade로 크로스페이드 연결"""
    if len(seg_files) == 1:
        subprocess.run(["ffmpeg", "-y", "-i", seg_files[0], "-c", "copy", out_path],
                       capture_output=True, check=True)
        return

    # xfade는 두 입력을 합치고 offset 지점부터 페이드. 연쇄 구성:
    inputs = []
    for f in seg_files:
        inputs.extend(["-i", f])
    filters = []
    prev = "[0:v]"
    offset = 0.0
    for i in range(1, len(seg_files)):
        offset += durations[i - 1] - fade_dur
        out_label = f"v{i}"
        filters.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={fade_dur}:offset={offset:.3f}[{out_label}]"
        )
        prev = f"[{out_label}]"
    filter_complex = ";".join(filters)
    final = prev.strip("[]")

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{final}]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def render_news_shorts(
    news_script,
    output_path: str,
    theme_id: str = "samprotv",
    ticker_text: str = "",
    enable_transitions: bool = True,
    enable_tts: bool = True,
    enable_bgm: bool = True,
    tts_provider: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    theme_overrides: dict | None = None,
) -> str:
    theme = apply_overrides(get_theme(theme_id), theme_overrides)

    # 감정 타깃에 따른 자막 색 보정
    emotion = getattr(news_script, "emotion_target", "curiosity")
    tone = EMOTION_TONE.get(emotion)
    if tone and isinstance(theme.get("caption", {}).get("color"), tuple):
        base = theme["caption"]["color"]
        adjusted = tuple(
            min(255, int(base[i] * tone[i])) if i < 3 else base[i]
            for i in range(len(base))
        )
        # 얕은 복사로 테마 수정
        theme = {**theme, "caption": {**theme["caption"], "color": adjusted}}
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    use_fixed_title = theme.get("fixed_title", False)
    fixed_title_text = (
        getattr(news_script, "hook_phrase", "") or news_script.title
        if use_fixed_title else ""
    )

    total_duration = sum(s.duration for s in news_script.segments)

    with tempfile.TemporaryDirectory(prefix="news_render_") as tmp:
        work = Path(tmp)
        seg_files = []
        durations = []

        for idx, seg in enumerate(news_script.segments):
            seg_out = str(work / f"seg_{idx:02d}.mp4")
            title = fixed_title_text if use_fixed_title else (seg.text_content or "")
            try:
                _render_segment(
                    seg=seg, theme=theme, title=title,
                    out=seg_out, work=work, kb_direction=idx,
                )
            except Exception as e:
                print(f"  segment {idx} 렌더 실패: {e}")
                raise
            seg_files.append(seg_out)
            durations.append(seg.duration)

        # 연결 (xfade or concat)
        concat_path = str(work / "concat.mp4")
        if enable_transitions and len(seg_files) > 1:
            try:
                _concat_with_xfade(seg_files, durations, concat_path)
            except Exception as e:
                print(f"  xfade 실패 → concat: {e}")
                list_file = work / "list.txt"
                list_file.write_text("\n".join(f"file '{f}'" for f in seg_files), encoding="utf-8")
                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(list_file), "-c", "copy", concat_path,
                ], capture_output=True, check=True)
        else:
            list_file = work / "list.txt"
            list_file.write_text("\n".join(f"file '{f}'" for f in seg_files), encoding="utf-8")
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_file), "-c", "copy", concat_path,
            ], capture_output=True, check=True)

        # 진행 바 + 티커
        W, H = theme["canvas"]
        overlay_path = str(work / "overlayed.mp4")
        try:
            _add_progress_and_ticker(concat_path, total_duration, ticker_text,
                                      overlay_path, work, W=W, H=H)
        except Exception as e:
            print(f"  진행바/티커 실패 (원본 사용): {e}")
            overlay_path = concat_path

        # 오디오 (TTS + BGM)
        final_path = overlay_path
        if enable_tts or enable_bgm:
            try:
                from src.editor.news_audio import (
                    generate_tts_for_segments, mix_audio_into_video, default_bgm,
                )
                tts_files = []
                tts_offsets = []
                if enable_tts:
                    tts_files = generate_tts_for_segments(
                        news_script.segments, work,
                        provider=tts_provider, edge_voice=tts_voice,
                    )
                    # transition이 있으면 offset은 crossfade 반영
                    offset = 0.0
                    fade = 0.3 if enable_transitions else 0.0
                    for i, dur in enumerate(durations):
                        tts_offsets.append(offset)
                        offset += dur - (fade if i < len(durations) - 1 else 0)
                bgm = default_bgm() if enable_bgm else None
                if any(tts_files) or bgm:
                    audio_out = str(work / "with_audio.mp4")
                    mix_audio_into_video(
                        video_path=overlay_path,
                        tts_files=tts_files,
                        tts_offsets=tts_offsets,
                        total_duration=total_duration,
                        out_path=audio_out,
                        bgm_path=bgm,
                    )
                    final_path = audio_out
            except Exception as e:
                print(f"  오디오 믹스 실패 (무음 유지): {e}")

        import shutil
        shutil.copy(final_path, out)

    return str(out)
