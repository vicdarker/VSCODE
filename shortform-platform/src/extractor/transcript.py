"""
자막(SRT) 파싱 + Whisper STT 폴백 모듈
SRT 파일이 있으면 파싱, 없으면 Whisper로 전사합니다.
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float   # seconds
    end: float     # seconds
    text: str


def load(video_path: str, subtitle_path: str | None = None) -> list[Segment]:
    """
    자막 세그먼트 목록을 반환합니다.
    subtitle_path가 있으면 SRT 파싱, 없으면 Whisper STT를 사용합니다.
    """
    if subtitle_path and Path(subtitle_path).exists():
        return parse_srt(subtitle_path)
    return transcribe_whisper(video_path)


def parse_srt(path: str) -> list[Segment]:
    """SRT 파일을 파싱해 Segment 목록으로 변환합니다."""
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", text.strip())

    segments = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            # 두 번째 줄: 타임코드
            start, end = _parse_timecode_line(lines[1])
            content = " ".join(lines[2:]).strip()
            content = re.sub(r"<[^>]+>", "", content)  # HTML 태그 제거
            if content:
                segments.append(Segment(start=start, end=end, text=content))
        except (ValueError, IndexError):
            continue

    return segments


def transcribe_whisper(video_path: str) -> list[Segment]:
    """OpenAI Whisper API로 영상을 전사합니다."""
    import os
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai 패키지가 없습니다. 'pip install openai' 실행 후 재시도하세요.")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다. .env 파일에 추가해주세요.")

    client = OpenAI(api_key=api_key)

    with open(video_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.mp4", f),
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments = []
    for seg in (response.segments or []):
        segments.append(
            Segment(
                start=float(seg.start),
                end=float(seg.end),
                text=seg.text.strip(),
            )
        )
    return segments


def to_full_text(segments: list[Segment]) -> str:
    """세그먼트 목록을 타임스탬프 포함 텍스트로 변환합니다."""
    lines = []
    for seg in segments:
        start = _fmt_time(seg.start)
        end = _fmt_time(seg.end)
        lines.append(f"[{start} -> {end}] {seg.text}")
    return "\n".join(lines)


def _parse_timecode_line(line: str) -> tuple[float, float]:
    """'00:01:23,456 --> 00:01:26,789' 형식을 초 단위로 변환합니다."""
    pattern = r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
    m = re.match(pattern, line.strip())
    if not m:
        raise ValueError(f"타임코드 파싱 실패: {line}")
    h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
    start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
    end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
    return start, end


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"
