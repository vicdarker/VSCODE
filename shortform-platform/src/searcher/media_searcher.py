"""
미디어 검색 및 다운로드
- video: yt-dlp YouTube 검색
- photo: Pixabay API
- graphic: PIL 그라데이션 배경 생성
"""

import os
import subprocess
import urllib.request
import urllib.parse
import json
from pathlib import Path

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")


def fetch_media(
    media_type: str,
    keyword: str,
    output_dir: str,
    filename: str,
    duration: float = 4.0,
    graphic_style: str = "dark_navy",
) -> str:
    """
    미디어를 검색/생성하고 영상 파일 경로를 반환합니다.
    모든 타입을 최종적으로 mp4로 반환합니다 (CapCut 호환).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if media_type == "video":
        result = _fetch_video(keyword, out, filename, duration)
        if result:
            return result
        # video 실패 → photo 시도
        media_type = "photo"

    if media_type == "photo":
        img_path = _fetch_photo(keyword, out, filename)
        if img_path:
            return _image_to_video(img_path, out / f"{filename}.mp4", duration)
        # photo 실패 → graphic

    return _make_graphic(graphic_style or "dark_navy", out / f"{filename}.mp4", duration)


# ── 영상 검색 ─────────────────────────────────────────────────────────────────

def _fetch_video(keyword: str, out: Path, filename: str, duration: float) -> str:
    raw_name = f"{filename}_raw"
    template = str(out / f"{raw_name}.%(ext)s")
    clip_sec = int(duration) + 3

    skip = 3  # 인트로/타이틀카드 스킵 (초)
    cmd = [
        "yt-dlp",
        f"ytsearch3:{keyword}",
        "-f", "mp4[height<=720]/best[height<=720]/best",
        "--no-playlist",
        "-o", template,
        "--merge-output-format", "mp4",
        "--download-sections", f"*{skip}-{clip_sec + skip}",
        "--max-filesize", "30m",
        "--match-filter", "duration>15",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        raw = None
        for f in out.glob(f"{raw_name}.*"):
            if f.suffix in (".mp4", ".mkv", ".webm") and f.stat().st_size > 10_000:
                raw = f
                break
        if raw:
            mp4 = out / f"{filename}.mp4"
            crop_cmd = [
                "ffmpeg", "-y", "-i", str(raw),
                "-vf", "scale=-2:1920,crop=1080:1920,setsar=1",
                "-t", str(duration + 1),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-an",
                str(mp4),
            ]
            subprocess.run(crop_cmd, capture_output=True, check=True)
            raw.unlink(missing_ok=True)
            if mp4.exists() and mp4.stat().st_size > 10_000:
                return str(mp4)
    except Exception:
        for f in out.glob(f"{raw_name}.*"):
            f.unlink(missing_ok=True)
    return None


# ── 사진 검색 ─────────────────────────────────────────────────────────────────

def _fetch_photo(keyword: str, out: Path, filename: str) -> str | None:
    if not PIXABAY_KEY:
        return None
    words = keyword.split()
    candidates = [
        keyword,
        " ".join(words[:3]) if len(words) > 3 else None,
        " ".join(words[:2]) if len(words) > 2 else None,
        words[0] if len(words) > 1 else None,
    ]
    for q_str in candidates:
        if not q_str:
            continue
        try:
            q = urllib.parse.quote(q_str)
            api_url = (
                f"https://pixabay.com/api/?key={PIXABAY_KEY}"
                f"&q={q}&image_type=photo"
                f"&min_width=500&per_page=10&safesearch=true"
            )
            req = urllib.request.Request(api_url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            hits = data.get("hits", [])
            if not hits:
                continue

            img_url = hits[0].get("webformatURL") or hits[0].get("largeImageURL")
            if not img_url:
                continue

            img_path = out / f"{filename}.jpg"
            req2 = urllib.request.Request(img_url, headers=_HEADERS)
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                img_path.write_bytes(resp2.read())
            return str(img_path)
        except Exception:
            continue
    return None


# ── 그래픽 생성 ───────────────────────────────────────────────────────────────

_STYLES = {
    "dark_navy":  {"top": (5, 10, 60),   "bot": (20, 60, 180),  "accent": (80, 160, 255),  "bright": (140, 200, 255)},
    "dark_red":   {"top": (60, 5, 5),    "bot": (180, 30, 30),  "accent": (255, 80, 80),   "bright": (255, 160, 160)},
    "dark_green": {"top": (5, 50, 20),   "bot": (20, 160, 60),  "accent": (60, 240, 120),  "bright": (150, 255, 180)},
    "dark_gold":  {"top": (60, 35, 5),   "bot": (180, 120, 10), "accent": (255, 200, 40),  "bright": (255, 230, 140)},
}


def _make_graphic(style: str, output_path: Path, duration: float) -> str:
    jpg_path = str(output_path).replace(".mp4", ".jpg")

    palette = _STYLES.get(style, _STYLES["dark_navy"])
    top, bot, accent, bright = palette["top"], palette["bot"], palette["accent"], palette["bright"]

    try:
        import math
        import random
        from PIL import Image, ImageDraw, ImageFilter

        w, h = 1080, 1920
        img = Image.new("RGB", (w, h))
        draw_bg = ImageDraw.Draw(img)

        # 수직 그라데이션: 수평 밴드 4픽셀 단위로
        for y in range(0, h, 4):
            t = y / h
            rc = int(top[0] + t * (bot[0] - top[0]))
            gc = int(top[1] + t * (bot[1] - top[1]))
            bc = int(top[2] + t * (bot[2] - top[2]))
            draw_bg.rectangle([0, y, w, y + 4], fill=(rc, gc, bc))
        draw = ImageDraw.Draw(img, "RGBA")

        # 굵은 수평 스트라이프 (밝은 줄기)
        for gy in range(0, h, 120):
            draw.rectangle([0, gy, w, gy + 1], fill=(*accent, 60))
        for gy in range(0, h, 480):
            draw.rectangle([0, gy, w, gy + 3], fill=(*bright, 120))

        # 굵은 수직 줄기 (좌우 강조)
        for gx in [0, w // 4, w // 2, 3 * w // 4, w]:
            draw.rectangle([gx, 0, gx + 2, h], fill=(*accent, 50))

        # 대각선 빛 줄기 (밝고 선명하게)
        rng = random.Random(42)
        for _ in range(5):
            sx = rng.randint(100, w - 100)
            alpha = rng.randint(50, 90)
            draw.polygon(
                [(sx - 30, 0), (sx + 30, 0), (sx + 250, h), (sx - 250, h)],
                fill=(*accent, alpha),
            )

        # 중앙 원형 글로우 (밝고 강하게)
        glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        cy_glow = int(h * 0.45)
        for radius, alpha in [(500, 40), (350, 70), (200, 100), (100, 130)]:
            gd.ellipse(
                [w // 2 - radius, cy_glow - radius, w // 2 + radius, cy_glow + radius],
                fill=(*bright, alpha),
            )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(80))
        img = Image.alpha_composite(img.convert("RGBA"), glow_layer).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")

        # 상단/하단 굵은 강조 바
        draw.rectangle([0, 0, w, 12], fill=(*bright, 255))
        draw.rectangle([0, h - 12, w, h], fill=(*bright, 255))

        # 상단 장식 라인 2개
        draw.rectangle([0, 18, w, 22], fill=(*accent, 180))
        draw.rectangle([0, 28, w, 30], fill=(*accent, 100))

        # 테두리
        draw.rectangle([0, 0, w - 1, h - 1], outline=(*bright, 180), width=4)
        draw.rectangle([15, 15, w - 16, h - 16], outline=(*accent, 100), width=2)

        # 코너 브라켓
        bracket, bw = 80, 6
        for cx_, cy_ in [(40, 45), (w - 40, 45), (40, h - 45), (w - 40, h - 45)]:
            dx = 1 if cx_ < w / 2 else -1
            dy = 1 if cy_ < h / 2 else -1
            x2, y2h = cx_ + dx * bracket, cy_ + dy * bw
            x2b, y2v = cx_ + dx * bw, cy_ + dy * bracket
            draw.rectangle([min(cx_, x2), min(cy_, y2h), max(cx_, x2), max(cy_, y2h)], fill=(*bright, 220))
            draw.rectangle([min(cx_, x2b), min(cy_, y2v), max(cx_, x2b), max(cy_, y2v)], fill=(*bright, 220))

        img.save(jpg_path, quality=88)
    except Exception:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=0x{top[0]:02X}{top[1]:02X}{top[2]:02X}:s=1080x1920:r=30",
            "-frames:v", "1", jpg_path,
        ], capture_output=True)

    return _image_to_video(jpg_path, output_path, duration)


def _image_to_video(image_path: str, output_path: Path, duration: float) -> str:
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1080:1920",
        str(output_path),
    ], capture_output=True, check=True)
    return str(output_path)
