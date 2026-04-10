"""
FFmpeg를 사용해 영상을 자르고 9:16 세로형으로 변환합니다.
Phase 3: 애니메이션 자막(ASS) + 썸네일 자동 생성 포함.
"""

import subprocess
import os
from pathlib import Path
from dataclasses import dataclass, field

from src.selector.claude_selector import SelectedClip


@dataclass
class EditResult:
    output_path: str
    clip_index: int
    start: float
    end: float
    hook: str
    hashtags: list[str]
    thumbnail_path: str | None = None


def export_clips(
    video_path: str,
    clips: list[SelectedClip],
    output_dir: str = "output",
    vertical: bool = True,
    caption_mode: str = "word_pop",   # "word_pop" | "line_fade" | None
    segments=None,                     # 자막 세그먼트 (애니메이션 자막용)
    make_thumbnail: bool = True,
) -> list[EditResult]:
    """
    선택된 클립들을 영상에서 잘라 저장합니다.

    Args:
        video_path:     원본 영상 경로
        clips:          Claude가 선택한 클립 목록
        output_dir:     저장 경로
        vertical:       True면 9:16 세로형으로 크롭
        caption_mode:   "word_pop" | "line_fade" | None (자막 없음)
        segments:       전체 자막 세그먼트 (caption_mode != None 일 때 필요)
        make_thumbnail: True면 썸네일 자동 생성

    Returns:
        저장된 파일 정보 목록
    """
    from src.editor.caption_builder import build_ass
    from src.editor.thumbnail import generate as gen_thumb

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    stem = Path(video_path).stem

    for i, clip in enumerate(clips, start=1):
        raw_path   = str(out / f"{stem}_clip{i:02d}_raw.mp4")
        final_path = str(out / f"{stem}_clip{i:02d}.mp4")
        thumb_path = str(out / f"{stem}_clip{i:02d}_thumb.jpg")

        # 1) 영상 자르기 + 세로 변환
        _cut_clip(
            video_path=video_path,
            start=clip.start,
            end=clip.end,
            output_path=raw_path,
            vertical=vertical,
        )

        # 2) 애니메이션 자막 삽입
        if caption_mode and segments:
            ass_path = str(out / f"{stem}_clip{i:02d}.ass")
            build_ass(
                segments=segments,
                clip_start=clip.start,
                clip_end=clip.end,
                output_path=ass_path,
                mode=caption_mode,
            )
            _burn_ass(raw_path, ass_path, final_path)
            Path(raw_path).unlink(missing_ok=True)   # 중간 파일 삭제
        else:
            Path(raw_path).rename(final_path)

        # 3) 썸네일 생성
        thumbnail = None
        if make_thumbnail:
            try:
                thumbnail = gen_thumb(
                    video_path=final_path,
                    hook=clip.hook,
                    output_path=thumb_path,
                    at_second=3.0,
                )
            except Exception as e:
                print(f"  [clip {i}] 썸네일 생성 실패: {e}")

        results.append(
            EditResult(
                output_path=final_path,
                clip_index=i,
                start=clip.start,
                end=clip.end,
                hook=clip.hook,
                hashtags=clip.hashtags,
                thumbnail_path=thumbnail,
            )
        )
        print(f"  [clip {i}] 저장 완료: {final_path}")

    return results


def _cut_clip(
    video_path: str,
    start: float,
    end: float,
    output_path: str,
    vertical: bool,
) -> None:
    """FFmpeg로 구간을 자르고 선택적으로 9:16 크롭을 적용합니다."""
    duration = end - start

    vf_filters = []

    if vertical:
        # 9:16 세로형: 중앙 기준으로 크롭
        # 원본 높이 기준으로 너비 = height * 9/16
        vf_filters.append(
            "crop=ih*9/16:ih:(iw-ih*9/16)/2:0"
        )
        vf_filters.append("scale=1080:1920")

    cmd = [
        "ffmpeg",
        "-y",                          # 덮어쓰기
        "-ss", str(start),             # 시작점 (fast seek)
        "-i", video_path,
        "-t", str(duration),           # 길이
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",     # 웹 스트리밍 최적화
    ]

    if vf_filters:
        cmd += ["-vf", ",".join(vf_filters)]

    cmd.append(output_path)

    subprocess.run(cmd, check=True, capture_output=True)


def _burn_ass(video_path: str, ass_path: str, output_path: str) -> None:
    """ASS 자막 파일을 영상에 하드코딩합니다."""
    # Windows 경로 → FFmpeg 호환
    escaped = ass_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"ass='{escaped}'",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
