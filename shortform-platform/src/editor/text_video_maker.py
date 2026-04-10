"""
블로그 스크립트 → 숏폼 영상 생성 모듈
edge-tts로 나레이션 음성을 생성하고 FFmpeg로 텍스트 영상과 합칩니다.
"""

import asyncio
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.extractor.transcript import Segment
from src.selector.blog_script_generator import BlogScript


@dataclass
class TextVideoResult:
    output_path: str
    clip_index: int
    start: float
    end: float
    hook: str
    hashtags: list[str]
    thumbnail_path: str | None = None


# 한국어 TTS 음성 (Microsoft Edge TTS)
_VOICE = "ko-KR-SunHiNeural"

# 배경 그라데이션 색 (어두운 네이비)
_BG_COLOR = "0x0d1117"


def make_videos(
    scripts: list[BlogScript],
    output_dir: str,
    job_stem: str = "blog",
    make_thumbnail: bool = True,
) -> list[TextVideoResult]:
    """
    스크립트 목록에서 세로형 숏폼 영상을 생성합니다.

    Args:
        scripts:       BlogScript 목록
        output_dir:    저장 폴더
        job_stem:      출력 파일 이름 접두사
        make_thumbnail: 썸네일 자동 생성 여부

    Returns:
        TextVideoResult 목록
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    for i, script in enumerate(scripts, start=1):
        result = _make_one(script, i, out, job_stem, make_thumbnail)
        results.append(result)
        print(f"  [clip {i}] 저장 완료: {result.output_path}")

    return results


def _make_one(
    script: BlogScript,
    index: int,
    out: Path,
    job_stem: str,
    make_thumbnail: bool,
) -> TextVideoResult:
    audio_path = str(out / f"{job_stem}_clip{index:02d}.mp3")
    ass_path   = str(out / f"{job_stem}_clip{index:02d}.ass")
    final_path = str(out / f"{job_stem}_clip{index:02d}.mp4")
    thumb_path = str(out / f"{job_stem}_clip{index:02d}_thumb.jpg")

    # 1) TTS 음성 생성 (word-boundary로 타임스탬프 보정)
    actual_segments = _run_tts(script.narration, audio_path, script.segments)

    # 2) ASS 자막 생성
    total_duration = actual_segments[-1].end if actual_segments else 60.0
    _build_ass(actual_segments, ass_path)

    # 3) FFmpeg: 배경 + 음성 + 자막 합성
    _compose_video(audio_path, ass_path, final_path, total_duration)

    # 4) 썸네일
    thumbnail = None
    if make_thumbnail:
        try:
            from src.editor.thumbnail import generate as gen_thumb
            thumbnail = gen_thumb(
                video_path=final_path,
                hook=script.hook,
                output_path=thumb_path,
                at_second=2.0,
            )
        except Exception as e:
            print(f"  [clip {index}] 썸네일 생성 실패: {e}")

    return TextVideoResult(
        output_path=final_path,
        clip_index=index,
        start=0.0,
        end=total_duration,
        hook=script.hook,
        hashtags=script.hashtags,
        thumbnail_path=thumbnail,
    )


# ── TTS ─────────────────────────────────────────────────────────────────────

def _run_tts(narration: str, audio_path: str, fallback_segments: list[Segment]) -> list[Segment]:
    """
    edge-tts로 음성을 생성하고 단어 경계 타임스탬프로 세그먼트를 보정합니다.
    edge-tts가 없으면 추정 세그먼트를 그대로 사용합니다.
    """
    try:
        import edge_tts
        return asyncio.run(_tts_async(narration, audio_path, fallback_segments))
    except ImportError:
        raise ImportError(
            "edge-tts가 설치되지 않았습니다. 'pip install edge-tts' 실행 후 재시도하세요."
        )
    except Exception as e:
        print(f"  TTS 생성 실패: {e}")
        return fallback_segments


async def _tts_async(
    narration: str,
    audio_path: str,
    fallback_segments: list[Segment],
) -> list[Segment]:
    import edge_tts

    communicate = edge_tts.Communicate(narration, _VOICE)
    submaker = edge_tts.SubMaker()

    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    srt_content = submaker.get_srt()
    if srt_content.strip():
        segments = _parse_srt(srt_content)
        if segments:
            return segments

    return fallback_segments


def _parse_srt(srt: str) -> list[Segment]:
    """edge-tts SubMaker가 반환하는 SRT를 Segment 목록으로 변환합니다."""
    import re
    segments = []
    blocks = re.split(r"\n\s*\n", srt.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            start, end = _parse_srt_time(lines[1])
            text = " ".join(lines[2:]).strip()
            if text:
                segments.append(Segment(start=start, end=end, text=text))
        except Exception:
            continue
    return segments


def _parse_srt_time(line: str):
    import re
    m = re.match(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)",
        line.strip(),
    )
    if not m:
        raise ValueError(f"타임코드 파싱 실패: {line}")
    h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, m.groups())
    start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
    end   = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
    return start, end


# ── ASS 자막 ─────────────────────────────────────────────────────────────────

_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,68,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,2,0,1,4,2,2,80,80,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _build_ass(segments: list[Segment], ass_path: str):
    events = []
    fade_ms = 120
    for seg in segments:
        text = seg.text.replace("\n", r"\N")
        line = (
            r"{\an2}" +
            rf"{{\fad({fade_ms},{fade_ms})}}" +
            text
        )
        events.append(
            f"Dialogue: 0,{_ts(seg.start)},{_ts(seg.end)},"
            f"Default,,0,0,0,,{line}"
        )
    Path(ass_path).write_text(_ASS_HEADER + "\n".join(events) + "\n", encoding="utf-8")


def _ts(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = seconds % 60
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


# ── FFmpeg 합성 ──────────────────────────────────────────────────────────────

def _compose_video(audio_path: str, ass_path: str, output_path: str, duration: float):
    """
    단색 배경 + MP3 오디오 + ASS 자막을 합성해 1080×1920 세로 영상을 만듭니다.
    """
    escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        # 배경 (색상 생성기)
        "-f", "lavfi",
        "-i", f"color=c={_BG_COLOR}:size=1080x1920:rate=30",
        # 오디오
        "-i", audio_path,
        # 자막 오버레이
        "-vf", f"ass='{escaped_ass}'",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-shortest",   # 오디오 길이에 맞춰 영상 종료
        output_path,
    ]

    subprocess.run(cmd, check=True, capture_output=True)
