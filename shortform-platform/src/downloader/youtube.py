"""
YouTube 영상 다운로드 + 자막 추출 모듈
yt-dlp를 사용해 영상 파일과 자막(SRT)을 가져옵니다.
"""

import os
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass
class DownloadResult:
    video_path: str
    subtitle_path: str | None
    title: str
    duration: float  # seconds


def download(url: str, output_dir: str = "temp") -> DownloadResult:
    """
    YouTube URL에서 영상과 자막을 다운로드합니다.

    Args:
        url: YouTube 영상 URL
        output_dir: 저장 경로

    Returns:
        DownloadResult (영상 경로, 자막 경로, 제목, 길이)
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    template = str(out / "%(id)s.%(ext)s")

    # 1. 영상 정보 먼저 조회
    info = _get_info(url)
    video_id = info["id"]
    title = info.get("title", video_id)
    duration = float(info.get("duration", 0))

    # 2. 영상 다운로드 (최대 1080p mp4)
    video_path = _download_video(url, template, out, video_id)

    # 3. 자막 다운로드 (유튜브 자막 우선, 없으면 자동 자막)
    subtitle_path = _download_subtitles(url, out, video_id)

    return DownloadResult(
        video_path=video_path,
        subtitle_path=subtitle_path,
        title=title,
        duration=duration,
    )


def _get_info(url: str) -> dict:
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-playlist",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _download_video(url: str, template: str, out: Path, video_id: str) -> str:
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "-o", template,
        url,
    ]
    subprocess.run(cmd, check=True)

    # 저장된 파일 찾기
    for f in out.glob(f"{video_id}.*"):
        if f.suffix in (".mp4", ".mkv", ".webm"):
            return str(f)

    raise FileNotFoundError(f"다운로드된 영상 파일을 찾을 수 없습니다: {video_id}")


def _download_subtitles(url: str, out: Path, video_id: str) -> str | None:
    """자막 다운로드. 수동 자막 → 자동 자막 순으로 시도."""
    base_cmd = [
        "yt-dlp",
        "--skip-download",
        "--no-playlist",
        "-o", str(out / "%(id)s.%(ext)s"),
    ]

    # 수동 자막 시도
    result = subprocess.run(
        base_cmd + ["--write-sub", "--sub-lang", "ko,en", "--sub-format", "srt", url],
        capture_output=True,
        text=True,
    )

    srt = _find_subtitle(out, video_id)
    if srt:
        return srt

    # 자동 자막 시도
    subprocess.run(
        base_cmd + ["--write-auto-sub", "--sub-lang", "ko,en", "--sub-format", "srt", url],
        capture_output=True,
        text=True,
    )

    return _find_subtitle(out, video_id)


def _find_subtitle(out: Path, video_id: str) -> str | None:
    for lang in ("ko", "en"):
        for f in out.glob(f"{video_id}.{lang}*.srt"):
            return str(f)
    return None
