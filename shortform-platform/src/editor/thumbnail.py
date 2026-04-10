"""
썸네일 자동 생성 모듈
FFmpeg로 클립 중간 프레임을 추출하고 훅 텍스트를 오버레이합니다.
Pillow가 없어도 FFmpeg만으로 동작합니다.
"""

import subprocess
import textwrap
from pathlib import Path


def generate(
    video_path: str,
    hook: str,
    output_path: str,
    at_second: float = 3.0,
) -> str:
    """
    썸네일을 생성하고 저장합니다.

    Args:
        video_path:  클립 영상 경로
        hook:        상단에 표시할 훅 텍스트
        output_path: 저장 경로 (.jpg)
        at_second:   썸네일로 사용할 시간 (초)

    Returns:
        저장된 썸네일 경로
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 텍스트 줄바꿈 (한 줄 최대 18자)
    wrapped = _wrap_text(hook, width=18)
    escaped = _escape_ffmpeg_text(wrapped)

    # drawtext 필터: 상단 중앙, 반투명 검정 박스 배경
    drawtext = (
        f"drawtext="
        f"fontfile=/Windows/Fonts/arialbd.ttf:"
        f"text='{escaped}':"
        f"fontsize=72:"
        f"fontcolor=white:"
        f"borderw=4:"
        f"bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"y=120:"
        f"line_spacing=12:"
        f"box=1:"
        f"boxcolor=black@0.45:"
        f"boxborderw=20"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(at_second),
        "-i", video_path,
        "-vframes", "1",
        "-vf", drawtext,
        "-q:v", "2",          # JPEG 품질 (1=최고, 31=최저)
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True)

    # drawtext 실패 시 (폰트 없음 등) 텍스트 없이 프레임만 추출
    if result.returncode != 0:
        cmd_fallback = [
            "ffmpeg", "-y",
            "-ss", str(at_second),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            output_path,
        ]
        subprocess.run(cmd_fallback, check=True, capture_output=True)

    return output_path


def _wrap_text(text: str, width: int) -> str:
    """텍스트를 width 글자 단위로 줄바꿈합니다."""
    lines = textwrap.wrap(text, width=width)
    return r"\n".join(lines)   # ASS/drawtext 개행 이스케이프


def _escape_ffmpeg_text(text: str) -> str:
    """FFmpeg drawtext 필터에서 특수문자를 이스케이프합니다."""
    return (
        text
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )
