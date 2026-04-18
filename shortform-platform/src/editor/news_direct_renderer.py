"""
뉴스 숏츠 직접 렌더링 — CapCut 없이 완성된 MP4 생성.
테마 기반으로 레이아웃/글꼴/크기가 결정됨.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.editor.news_themes import get_theme

# 이모지 제거 (NotoSansCJK 미지원 → 두부박스 방지)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "\u2300-\u23FF"
    "\u2B00-\u2BFF"
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(s: str) -> str:
    return _EMOJI_RE.sub("", s).strip() if s else s


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """TTC는 index=2가 KR (JP=0, HK=1, KR=2)"""
    try:
        return ImageFont.truetype(path, size, index=2)
    except Exception:
        return ImageFont.truetype(path, size)


def _wrap_lines(text: str, font, max_w: int, draw) -> list[str]:
    """\n은 강제 줄바꿈, 그 외엔 max_w에 맞춰 단어 단위 자동 줄바꿈."""
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
    """area 이름 → (area_top, area_h) 픽셀 좌표"""
    W, H = theme["canvas"]
    if theme["layout"] == "letterbox":
        lb = theme["letterbox"]
        if area_name == "top":
            return 0, lb["top_h"]
        if area_name == "bottom":
            return lb["top_h"] + lb["vid_h"], lb["bot_h"]
        if area_name == "video_bottom_overlay":
            # 영상 영역 하단 35% 위에 오버레이 (스티커 자막)
            overlay_h = int(lb["vid_h"] * 0.30)
            return lb["top_h"] + lb["vid_h"] - overlay_h - 40, overlay_h
        # center (영상 영역 전체)
        return lb["top_h"], lb["vid_h"]
    # fullscreen
    if area_name == "top_overlay":
        return int(H * 0.12), int(H * 0.25)
    if area_name == "bottom_overlay":
        return int(H * 0.78), int(H * 0.18)
    return 0, H


_EMPH_COLOR = (255, 230, 0, 255)  # 강조 단어 노란색


def _tokenize_with_spaces(line: str) -> list[str]:
    """공백을 보존한 토큰 리스트 (공백도 별도 토큰으로)"""
    import re as _re
    return [t for t in _re.split(r"(\s+)", line) if t]


def _is_emphasis(token: str, emphasis_words: list) -> bool:
    """토큰이 강조 단어 중 하나에 해당하는지 (부분 매칭 허용)"""
    if not emphasis_words:
        return False
    t = token.strip()
    if not t:
        return False
    for w in emphasis_words:
        w = (w or "").strip()
        if w and w in t:
            return True
    return False


def _draw_block(draw, lines, font, area_top, area_h, W, color, stroke_w, stroke_color,
                line_spacing, emphasis_words: list = None):
    if not lines:
        return
    emphasis_words = emphasis_words or []

    line_heights = []
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln or "가", font=font, stroke_width=stroke_w)
        line_heights.append(bbox[3] - bbox[1])
    total_h = sum(line_heights) + line_spacing * (len(lines) - 1)
    y = area_top + (area_h - total_h) // 2

    for ln, lh in zip(lines, line_heights):
        # 줄 전체 너비 계산해서 centering
        bbox = draw.textbbox((0, 0), ln or "", font=font, stroke_width=stroke_w)
        lw = bbox[2] - bbox[0]
        x = (W - lw) // 2

        # 강조 단어가 있으면 토큰별 색상 분기 렌더
        if emphasis_words:
            cursor_x = x
            for token in _tokenize_with_spaces(ln):
                token_color = _EMPH_COLOR if _is_emphasis(token, emphasis_words) else color
                draw.text(
                    (cursor_x, y), token, font=font, fill=token_color,
                    stroke_width=stroke_w, stroke_fill=stroke_color,
                )
                # 다음 토큰 위치
                tb = draw.textbbox((cursor_x, y), token, font=font, stroke_width=stroke_w)
                cursor_x = tb[2]
        else:
            draw.text(
                (x, y), ln, font=font, fill=color,
                stroke_width=stroke_w, stroke_fill=stroke_color,
            )
        y += lh + line_spacing


def _make_overlay_png(title: str, caption: str, theme: dict, out_path: str,
                      emphasis_words: list = None):
    W, H = theme["canvas"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    emphasis_words = emphasis_words or []

    texts_to_draw = [
        ("title", _strip_emoji(title), emphasis_words),  # 제목만 강조 적용
        ("caption", _strip_emoji(caption), []),          # 자막은 단색 유지
    ]
    if theme.get("bottom_brand") and theme.get("fixed_bottom_text"):
        texts_to_draw.append(("bottom_brand", theme["fixed_bottom_text"], []))

    for key, text, emph in texts_to_draw:
        if not text:
            continue
        cfg = theme[key]
        font = _load_font(cfg["font"], cfg["size"])
        lines = _wrap_lines(text, font, int(W * cfg["max_width"]), draw)
        area_top, area_h = _compute_area(theme, cfg["area"])
        _draw_block(
            draw, lines, font, area_top, area_h, W,
            color=cfg["color"],
            stroke_w=cfg["stroke_w"],
            stroke_color=cfg["stroke_color"],
            line_spacing=cfg["line_spacing"],
            emphasis_words=emph,
        )

    img.save(out_path)


def _video_filter(theme: dict) -> str:
    """레이아웃에 따른 비디오 전처리 filter"""
    W, H = theme["canvas"]
    if theme["layout"] == "letterbox":
        lb = theme["letterbox"]
        # 어떤 크기 입력이든 W x vid_h 영역에 cover로 맞춘 뒤 상/하 검정 패드
        return (
            f"scale={W}:{lb['vid_h']}:force_original_aspect_ratio=increase,"
            f"crop={W}:{lb['vid_h']},"
            f"pad={W}:{H}:0:{lb['top_h']}:black,setsar=1"
        )
    # fullscreen: 원본을 캔버스에 맞춤
    return (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},setsar=1"
    )


def _render_segment(src: str, title: str, caption: str, duration: float,
                    theme: dict, out: str, work: Path, emphasis_words: list = None):
    overlay_png = str(work / f"ovl_{Path(out).stem}.png")
    _make_overlay_png(title, caption, theme, overlay_png, emphasis_words=emphasis_words)

    vf = _video_filter(theme)
    cmd = [
        "ffmpeg", "-y",
        "-i", src,
        "-i", overlay_png,
        "-filter_complex",
        f"[0:v]{vf}[bg];[bg][1:v]overlay=0:0,format=yuv420p[v]",
        "-map", "[v]",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", "30",
        out,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def render_news_shorts(news_script, output_path: str, theme_id: str = "samprotv") -> str:
    """NewsScript → 완성된 MP4 렌더링 (테마 선택 가능)"""
    theme = get_theme(theme_id)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 고정 제목 여부 — 모든 세그먼트에 뉴스 전체 제목을 표시
    use_fixed_title = theme.get("fixed_title", False)
    fixed_title_text = news_script.title if use_fixed_title else ""

    with tempfile.TemporaryDirectory(prefix="news_render_") as tmp:
        work = Path(tmp)
        seg_files = []
        for idx, seg in enumerate(news_script.segments):
            seg_out = str(work / f"seg_{idx:02d}.mp4")
            title = fixed_title_text if use_fixed_title else (seg.text_content or "")
            emph = getattr(seg, "emphasis_words", None) or []
            _render_segment(
                src=seg.media_path,
                title=title,
                caption=seg.caption or "",
                duration=seg.duration,
                theme=theme,
                out=seg_out,
                work=work,
                emphasis_words=emph,
            )
            seg_files.append(seg_out)

        concat_list = work / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{f}'" for f in seg_files), encoding="utf-8",
        )
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(out),
        ], capture_output=True, check=True)

    return str(out)
