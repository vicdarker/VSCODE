"""
미디어 검색 및 다운로드 (PIL 그래픽 제거 — 항상 실제 영상/사진 확보)

Fallback 체인:
  VIDEO 요청:  yt-dlp → Pexels video → Pixabay video → Pexels photo → Pixabay photo
  PHOTO 요청:  Pixabay photo → Pexels photo → Pixabay video → Pexels video
"""

import os
import subprocess
import urllib.request
import urllib.parse
import json
from pathlib import Path

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
# Pexels는 Mozilla UA를 차단 — 간단한 UA 사용
_PEXELS_HEADERS_BASE = {"User-Agent": "shortform-platform/1.0", "Accept": "*/*"}

PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")


def fetch_media(
    media_type: str,
    keyword: str,
    output_dir: str,
    filename: str,
    duration: float = 4.0,
    graphic_style: str = "dark_navy",  # 하위호환 (무시됨)
) -> str:
    """
    미디어를 검색/생성하고 영상 파일 경로를 반환.
    실패 시 여러 소스 fallback. 모든 출력은 mp4.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    kw = keyword or "news concept"

    # 요청 타입에 따라 우선순위 조정
    if media_type == "video":
        chain = [
            ("yt-dlp", _fetch_yt_video),
            ("pexels-video", _fetch_pexels_video),
            ("pixabay-video", _fetch_pixabay_video),
            ("pexels-photo", _fetch_pexels_photo),
            ("pixabay-photo", _fetch_pixabay_photo),
        ]
    else:  # photo
        chain = [
            ("pixabay-photo", _fetch_pixabay_photo),
            ("pexels-photo", _fetch_pexels_photo),
            ("pixabay-video", _fetch_pixabay_video),
            ("pexels-video", _fetch_pexels_video),
            ("yt-dlp", _fetch_yt_video),
        ]

    for source_name, fn in chain:
        try:
            result = fn(kw, out, filename, duration)
            if result:
                print(f"  [{filename}] {source_name}: OK")
                return result
        except Exception as e:
            print(f"  [{filename}] {source_name} 실패: {e}")
            continue

    # 모든 소스 실패: 최소한 검정 화면이라도 반환 (PIL 그래픽 아님)
    print(f"  [{filename}] 모든 소스 실패 — 검정 영상 생성")
    return _make_black_fallback(out / f"{filename}.mp4", duration)


# ── yt-dlp 비디오 ────────────────────────────────────────────────────────────

def _fetch_yt_video(keyword: str, out: Path, filename: str, duration: float) -> str | None:
    raw_name = f"{filename}_raw"
    template = str(out / f"{raw_name}.%(ext)s")
    clip_sec = int(duration) + 3
    skip = 3

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
        if not raw:
            return None
        mp4 = out / f"{filename}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(raw),
            "-vf", "scale='if(gt(iw,ih),-2,1280)':'if(gt(iw,ih),1280,-2)',"
               "pad='ceil(iw/2)*2':'ceil(ih/2)*2',setsar=1",
            "-t", str(duration + 1),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-an",
            str(mp4),
        ], capture_output=True, check=True)
        raw.unlink(missing_ok=True)
        if mp4.exists() and mp4.stat().st_size > 10_000:
            return str(mp4)
    except Exception:
        for f in out.glob(f"{raw_name}.*"):
            f.unlink(missing_ok=True)
    return None


# ── Pixabay 사진 ─────────────────────────────────────────────────────────────

def _keyword_variants(keyword: str) -> list[str]:
    words = keyword.split()
    variants = [keyword]
    if len(words) > 3:
        variants.append(" ".join(words[:3]))
    if len(words) > 2:
        variants.append(" ".join(words[:2]))
    if len(words) > 1:
        variants.append(words[0])
    # 중복 제거, 순서 유지
    seen = set()
    return [v for v in variants if not (v in seen or seen.add(v))]


def _fetch_pixabay_photo(keyword: str, out: Path, filename: str, duration: float) -> str | None:
    if not PIXABAY_KEY:
        return None
    for q_str in _keyword_variants(keyword):
        try:
            q = urllib.parse.quote(q_str)
            api_url = (
                f"https://pixabay.com/api/?key={PIXABAY_KEY}"
                f"&q={q}&image_type=photo&min_width=500&per_page=10&safesearch=true"
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
            return _image_to_video(str(img_path), out / f"{filename}.mp4", duration)
        except Exception:
            continue
    return None


# ── Pixabay 동영상 ───────────────────────────────────────────────────────────

def _fetch_pixabay_video(keyword: str, out: Path, filename: str, duration: float) -> str | None:
    if not PIXABAY_KEY:
        return None
    for q_str in _keyword_variants(keyword):
        try:
            q = urllib.parse.quote(q_str)
            api_url = (
                f"https://pixabay.com/api/videos/?key={PIXABAY_KEY}"
                f"&q={q}&per_page=10&safesearch=true"
            )
            req = urllib.request.Request(api_url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            hits = data.get("hits", [])
            if not hits:
                continue
            videos = hits[0].get("videos", {})
            vid_url = (videos.get("medium") or videos.get("small") or {}).get("url")
            if not vid_url:
                continue
            return _download_and_crop_video(vid_url, out, filename, duration)
        except Exception:
            continue
    return None


# ── Pexels 사진 ──────────────────────────────────────────────────────────────

def _fetch_pexels_photo(keyword: str, out: Path, filename: str, duration: float) -> str | None:
    if not PEXELS_KEY:
        return None
    for q_str in _keyword_variants(keyword):
        try:
            q = urllib.parse.quote(q_str)
            api_url = f"https://api.pexels.com/v1/search?query={q}&per_page=10"
            req = urllib.request.Request(api_url, headers={**_PEXELS_HEADERS_BASE, "Authorization": PEXELS_KEY})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            photos = data.get("photos", [])
            if not photos:
                continue
            img_url = photos[0].get("src", {}).get("large") or photos[0].get("src", {}).get("original")
            if not img_url:
                continue
            img_path = out / f"{filename}.jpg"
            req2 = urllib.request.Request(img_url, headers=_HEADERS)
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                img_path.write_bytes(resp2.read())
            return _image_to_video(str(img_path), out / f"{filename}.mp4", duration)
        except Exception:
            continue
    return None


# ── Pexels 동영상 ────────────────────────────────────────────────────────────

def _fetch_pexels_video(keyword: str, out: Path, filename: str, duration: float) -> str | None:
    if not PEXELS_KEY:
        return None
    for q_str in _keyword_variants(keyword):
        try:
            q = urllib.parse.quote(q_str)
            api_url = f"https://api.pexels.com/videos/search?query={q}&per_page=10"
            req = urllib.request.Request(api_url, headers={**_PEXELS_HEADERS_BASE, "Authorization": PEXELS_KEY})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            vids = data.get("videos", [])
            if not vids:
                continue
            # HD 또는 SD 파일 중 적당한 거
            files = vids[0].get("video_files", [])
            # 높이 720 전후 선호
            files_sorted = sorted(
                files, key=lambda f: abs(f.get("height", 0) - 720)
            )
            if not files_sorted:
                continue
            vid_url = files_sorted[0].get("link")
            if not vid_url:
                continue
            return _download_and_crop_video(vid_url, out, filename, duration)
        except Exception:
            continue
    return None


# ── 공용 유틸 ────────────────────────────────────────────────────────────────

def _download_and_crop_video(url: str, out: Path, filename: str, duration: float) -> str | None:
    raw = out / f"{filename}_src.mp4"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw.write_bytes(resp.read())
    if not raw.exists() or raw.stat().st_size < 10_000:
        return None
    mp4 = out / f"{filename}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw),
        "-vf", "scale='if(gt(iw,ih),-2,1280)':'if(gt(iw,ih),1280,-2)',"
               "pad='ceil(iw/2)*2':'ceil(ih/2)*2',setsar=1",
        "-t", str(duration + 1),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-an",
        str(mp4),
    ], capture_output=True, check=True)
    raw.unlink(missing_ok=True)
    if mp4.exists() and mp4.stat().st_size > 10_000:
        return str(mp4)
    return None


def _image_to_video(image_path: str, output_path: Path, duration: float) -> str:
    """사진 → 영상. 원본 비율 유지, 큰 해상도로 뽑아 렌더러가 최종 크기 결정."""
    # 짧은 변을 1280으로 맞춘 뒤 짝수로 보정 (테마가 1080x810이든 1080x1320이든 대응 가능)
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-vf", "scale='if(gt(iw,ih),-2,1280)':'if(gt(iw,ih),1280,-2)',"
               "pad='ceil(iw/2)*2':'ceil(ih/2)*2',setsar=1",
        str(output_path),
    ], capture_output=True, check=True)
    return str(output_path)


def _make_black_fallback(output_path: Path, duration: float) -> str:
    """최후 수단: 검정 영상 (PIL 그래픽 아님 — 단순 검정)"""
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=black:s=1080x1920:r=30:d={duration}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ], capture_output=True, check=True)
    return str(output_path)
