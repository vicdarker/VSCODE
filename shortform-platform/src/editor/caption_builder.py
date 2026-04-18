"""
Reels/Shorts 스타일 애니메이션 자막 생성기
SRT 세그먼트를 ASS 포맷으로 변환하고 단어별 팝업 효과를 추가합니다.
FFmpeg가 ASS를 하드코딩해 최종 영상에 굽습니다.
"""

import re
from pathlib import Path
from src.extractor.transcript import Segment


# ASS 파일 헤더 템플릿
_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans CJK KR,62,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,120,1
Style: Highlight,Noto Sans CJK KR,62,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass(
    segments: list[Segment],
    clip_start: float,
    clip_end: float,
    output_path: str,
    mode: str = "word_pop",
) -> str:
    """
    클립 구간에 해당하는 세그먼트를 ASS 자막 파일로 저장합니다.

    Args:
        segments: 전체 자막 세그먼트
        clip_start: 클립 시작 시간 (초, 원본 기준)
        clip_end:   클립 종료 시간 (초, 원본 기준)
        output_path: 저장할 .ass 파일 경로
        mode: "word_pop" | "line_fade"

    Returns:
        저장된 ASS 파일 경로
    """
    # 클립 구간에 걸치는 세그먼트만 필터링, 타임스탬프를 클립 기준으로 재조정
    clipped = []
    for seg in segments:
        if seg.end <= clip_start or seg.start >= clip_end:
            continue
        clipped.append(Segment(
            start=max(seg.start - clip_start, 0),
            end=min(seg.end - clip_start, clip_end - clip_start),
            text=seg.text,
        ))

    if mode == "word_pop":
        events = _word_pop_events(clipped)
    else:
        events = _line_fade_events(clipped)

    content = _ASS_HEADER + "\n".join(events) + "\n"
    Path(output_path).write_text(content, encoding="utf-8")
    return output_path


# ── 모드 1: 단어별 순차 팝업 (TikTok 스타일) ──────────────────────────────

def _word_pop_events(segments: list[Segment]) -> list[str]:
    """
    각 세그먼트를 단어 단위로 쪼개 순차적으로 나타납니다.
    현재 단어는 노란색(Highlight), 나머지는 흰색(Default)으로 표시합니다.
    """
    events = []
    for seg in segments:
        words = seg.text.split()
        if not words:
            continue

        total = seg.end - seg.start
        word_dur = total / len(words)

        for idx, word in enumerate(words):
            w_start = seg.start + idx * word_dur
            w_end   = w_start + word_dur

            # 이전 단어(흰색) + 현재 단어(노란색) + 이후 단어(흰색)
            before = " ".join(words[:idx])
            after  = " ".join(words[idx + 1:])

            parts = []
            if before:
                parts.append(before + " ")
            parts.append(r"{\c&H00FFFF&}" + word + r"{\c&HFFFFFF&}")
            if after:
                parts.append(" " + after)

            line = "".join(parts)

            # 팝업 효과: \t(scale 120→100) 로 통통 튀는 느낌
            animated = (
                r"{\an2\fscx120\fscy120\t(\fscx100\fscy100)}" + line
            )

            events.append(
                f"Dialogue: 0,{_ts(w_start)},{_ts(w_end)},"
                f"Default,,0,0,0,,{animated}"
            )

    return events


# ── 모드 2: 줄 단위 페이드인 ────────────────────────────────────────────

def _line_fade_events(segments: list[Segment]) -> list[str]:
    """세그먼트 단위로 페이드인/페이드아웃을 적용합니다."""
    events = []
    fade_ms = 150  # ms

    for seg in segments:
        text = seg.text.replace("\n", r"\N")
        animated = (
            r"{\an2}" +
            rf"{{\fad({fade_ms},{fade_ms})}}" +
            text
        )
        events.append(
            f"Dialogue: 0,{_ts(seg.start)},{_ts(seg.end)},"
            f"Default,,0,0,0,,{animated}"
        )

    return events


# ── 헬퍼 ────────────────────────────────────────────────────────────────

def _ts(seconds: float) -> str:
    """초 단위를 ASS 타임스탬프 H:MM:SS.cc 로 변환합니다."""
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = seconds % 60
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"
