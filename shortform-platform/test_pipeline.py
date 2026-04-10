"""
파이프라인 단계별 테스트 스크립트
Celery/Redis 없이 동기 방식으로 실행합니다.

사용법:
  python test_pipeline.py <YouTube URL>
  python test_pipeline.py <YouTube URL> --step download   # 1단계만
  python test_pipeline.py <YouTube URL> --step transcript  # 2단계까지
  python test_pipeline.py <YouTube URL> --step select      # 3단계까지
  python test_pipeline.py <YouTube URL> --step edit        # 전체 (기본)
"""

import sys
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

# ── ffmpeg PATH 자동 설정 ───────────────────────────────────────────────
FFMPEG_WINGET = (
    Path.home()
    / "AppData/Local/Microsoft/WinGet/Packages"
    / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    / "ffmpeg-8.1-full_build/bin"
)
if FFMPEG_WINGET.exists():
    os.environ["PATH"] = str(FFMPEG_WINGET) + os.pathsep + os.environ.get("PATH", "")

load_dotenv()

STEPS = ["download", "transcript", "select", "edit"]


def run(url: str, stop_at: str, duration: int, num_clips: int, style: str):
    stop_idx = STEPS.index(stop_at)

    # ── Step 1: 다운로드 ─────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print("[1/4] YouTube 영상 다운로드")
    print(f"{'='*55}")

    from src.downloader.youtube import download
    result = download(url=url, output_dir="temp")

    print(f"  제목   : {result.title}")
    print(f"  길이   : {result.duration:.0f}초 ({result.duration/60:.1f}분)")
    print(f"  영상   : {result.video_path}")
    print(f"  자막   : {result.subtitle_path or '없음 → Whisper 사용'}")

    if stop_idx < 1:
        return

    # ── Step 2: 자막 로드 ─────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print("[2/4] 자막 분석")
    print(f"{'='*55}")

    from src.extractor.transcript import load as load_transcript, to_full_text
    segments = load_transcript(
        video_path=result.video_path,
        subtitle_path=result.subtitle_path,
    )

    if not segments:
        print("[오류] 자막을 추출할 수 없습니다.")
        sys.exit(1)

    print(f"  세그먼트 수: {len(segments)}개")
    print("\n  처음 5개 미리보기:")
    for seg in segments[:5]:
        print(f"    [{seg.start:.1f}s] {seg.text[:60]}")

    if stop_idx < 2:
        return

    # ── Step 3: Claude 구간 선택 ──────────────────────────────────────────
    print(f"\n{'='*55}")
    print("[3/4] Claude AI 구간 선택")
    print(f"{'='*55}")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[오류] ANTHROPIC_API_KEY 환경변수가 없습니다. .env 파일을 확인하세요.")
        sys.exit(1)

    from src.selector.claude_selector import select_clips
    clips = select_clips(
        segments=segments,
        title=result.title,
        duration_sec=duration,
        num_clips=num_clips,
        style=style,
    )

    for i, clip in enumerate(clips, 1):
        print(f"\n  [클립 {i}]")
        print(f"    구간  : {clip.start:.1f}s ~ {clip.end:.1f}s ({clip.end-clip.start:.0f}초)")
        print(f"    이유  : {clip.reason}")
        print(f"    훅    : {clip.hook}")
        print(f"    태그  : {' '.join(clip.hashtags)}")

    if stop_idx < 3:
        return

    # ── Step 4: FFmpeg 편집 ───────────────────────────────────────────────
    print(f"\n{'='*55}")
    print("[4/4] 영상 편집 (자막 + 썸네일)")
    print(f"{'='*55}")

    try:
        from src.editor.ffmpeg_editor import export_clips
        edited = export_clips(
            video_path=result.video_path,
            clips=clips,
            output_dir="output",
            vertical=True,
            caption_mode="word_pop",
            segments=segments,
            make_thumbnail=True,
        )

        print(f"\n  완료! output/ 폴더에 {len(edited)}개 저장됨")
        for e in edited:
            thumb = e.thumbnail_path or "없음"
            print(f"\n  [clip {e.clip_index}]")
            print(f"    영상     : {e.output_path}")
            print(f"    썸네일   : {thumb}")
            print(f"    훅       : {e.hook}")
            print(f"    해시태그 : {' '.join(e.hashtags)}")

    except FileNotFoundError as err:
        if "ffmpeg" in str(err).lower():
            print("[오류] ffmpeg를 찾을 수 없습니다.")
            print("  해결: 새 터미널을 열거나 PATH를 확인하세요.")
        else:
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="파이프라인 단계별 테스트")
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument("--step",     default="edit",
                        choices=STEPS, help="어느 단계까지 실행할지 (기본: edit = 전체)")
    parser.add_argument("--duration", type=int, default=60,  help="숏폼 길이 초 (기본 60)")
    parser.add_argument("--clips",    type=int, default=2,   help="클립 수 (기본 2)")
    parser.add_argument("--style",    default="general",
                        choices=["general", "education", "entertainment", "news"])
    args = parser.parse_args()

    run(
        url=args.url,
        stop_at=args.step,
        duration=args.duration,
        num_clips=args.clips,
        style=args.style,
    )
