"""
숏폼 자동 생성 플랫폼 - Phase 1 CLI
사용법: python main.py <YouTube URL> [옵션]
"""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
from src.downloader.youtube import download
from src.extractor.transcript import load as load_transcript
from src.selector.claude_selector import select_clips
from src.editor.ffmpeg_editor import export_clips


def main():
    parser = argparse.ArgumentParser(
        description="YouTube 영상에서 숏폼을 자동으로 생성합니다."
    )
    parser.add_argument("url", help="YouTube 영상 URL")
    parser.add_argument(
        "--duration", type=int, default=60,
        help="숏폼 길이 (초, 기본값: 60)"
    )
    parser.add_argument(
        "--clips", type=int, default=3,
        help="추출할 클립 수 (기본값: 3)"
    )
    parser.add_argument(
        "--style", choices=["general", "education", "entertainment", "news"],
        default="general", help="콘텐츠 스타일 (기본값: general)"
    )
    parser.add_argument(
        "--no-vertical", action="store_true",
        help="9:16 세로 변환 비활성화 (원본 비율 유지)"
    )
    parser.add_argument(
        "--output", default="output",
        help="출력 폴더 (기본값: output)"
    )
    parser.add_argument(
        "--temp", default="temp",
        help="임시 파일 폴더 (기본값: temp)"
    )
    args = parser.parse_args()

    # API 키 확인
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[오류] ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
        print("  .env 파일에 ANTHROPIC_API_KEY=sk-ant-... 를 추가해 주세요.")
        sys.exit(1)

    print(f"\n{'='*50}")
    print("  숏폼 자동 생성 플랫폼 - Phase 1")
    print(f"{'='*50}\n")

    # Step 1: 다운로드
    print("[1/4] YouTube 영상 다운로드 중...")
    result = download(url=args.url, output_dir=args.temp)
    print(f"  제목: {result.title}")
    print(f"  길이: {result.duration:.0f}초 ({result.duration/60:.1f}분)")
    print(f"  자막: {'있음' if result.subtitle_path else '없음 (Whisper 사용)'}")

    # Step 2: 자막 로드
    print("\n[2/4] 자막 분석 중...")
    segments = load_transcript(
        video_path=result.video_path,
        subtitle_path=result.subtitle_path,
    )
    print(f"  세그먼트 수: {len(segments)}개")

    if not segments:
        print("[오류] 자막을 추출할 수 없습니다.")
        sys.exit(1)

    # Step 3: Claude로 구간 선택
    print(f"\n[3/4] Claude AI가 최적 구간 {args.clips}개 선택 중...")
    clips = select_clips(
        segments=segments,
        title=result.title,
        duration_sec=args.duration,
        num_clips=args.clips,
        style=args.style,
    )

    print(f"  선택된 클립:")
    for i, clip in enumerate(clips, 1):
        print(f"    [{i}] {clip.start:.1f}s ~ {clip.end:.1f}s | {clip.reason[:50]}...")
        print(f"         훅: {clip.hook}")
        print(f"         태그: {' '.join(clip.hashtags)}")

    print(f"\n[4/4] 영상 편집 및 저장 중... ({args.output}/)")
    edited = export_clips(
            video_path=result.video_path,
            clips=clips,
            output_dir=args.output,
            vertical=not args.no_vertical,
        )

        # 완료 요약
        print(f"\n{'='*50}")
        print(f"  완료! {len(edited)}개 클립 생성됨")
        print(f"{'='*50}")
        for e in edited:
            print(f"  clip {e.clip_index}: {e.output_path}")
            print(f"    훅: {e.hook}")
            print(f"    해시태그: {' '.join(e.hashtags)}")

if __name__ == "__main__":
    main()
