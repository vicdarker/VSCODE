"""
Remotion 기반 뉴스 숏츠 렌더러.
React 컴포넌트로 복잡한 애니메이션 (슬라이드인, 스프링 바운스, 줌 등) 구현.
"""

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path


_REMOTION_DIR = Path("/app/remotion")
_REMOTION_ENTRY = _REMOTION_DIR / "src" / "index.ts"
_PUBLIC_DIR = _REMOTION_DIR / "public"


def _stage_media_to_public(seg_media_paths: list[str]) -> list[str]:
    """미디어 파일을 remotion/public/{job_id}/ 에 복사하고 상대 URL 반환"""
    _PUBLIC_DIR.mkdir(exist_ok=True)
    job_id = uuid.uuid4().hex[:8]
    job_dir = _PUBLIC_DIR / job_id
    job_dir.mkdir(exist_ok=True)
    rel_urls = []
    for i, src in enumerate(seg_media_paths):
        ext = Path(src).suffix or ".mp4"
        dst = job_dir / f"seg_{i:02d}{ext}"
        shutil.copy(src, dst)
        # Remotion은 staticFile() URL처럼 상대 경로 사용
        rel_urls.append(f"{job_id}/seg_{i:02d}{ext}")
    return rel_urls, job_dir


def _to_props(news_script, theme_id: str = "samprotv", fps: int = 30):
    """NewsScript → (Remotion props, public_job_dir)"""
    media_paths = [os.path.abspath(s.media_path) for s in news_script.segments]
    rel_urls, job_dir = _stage_media_to_public(media_paths)

    segments = []
    for seg, rel in zip(news_script.segments, rel_urls):
        segments.append({
            "mediaPath": rel,                 # 상대 URL (staticFile로 resolve)
            "caption": seg.caption or "",
            "captionChunks": seg.caption_chunks if seg.caption_chunks else [seg.caption or ""],
            "emphasisWords": seg.emphasis_words or [],
            "highlightStat": seg.highlight_stat or "",
            "reactionEmoji": seg.reaction_emoji or "",
            "role": seg.role or "body",
            "duration": float(seg.duration),
        })
    hook = getattr(news_script, "hook_phrase", "") or news_script.title or ""
    props = {
        "hookPhrase": hook,
        "segments": segments,
        "theme": theme_id if theme_id in ("samprotv", "youtuber") else "samprotv",
        "fps": fps,
    }
    return props, job_dir


def render_news_shorts_remotion(
    news_script,
    output_path: str,
    theme_id: str = "samprotv",
    fps: int = 30,
    enable_tts: bool = True,
    enable_bgm: bool = True,
    tts_provider: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
) -> str:
    """
    Remotion으로 렌더링. 결과 mp4 경로 반환.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    props, job_dir = _to_props(news_script, theme_id=theme_id, fps=fps)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False)
        props_path = f.name

    # 1) Remotion으로 영상만 먼저 렌더 (무음)
    video_silent = str(out.parent / f".{out.stem}_silent.mp4")
    try:
        cmd = [
            "npx", "--yes", "remotion", "render",
            str(_REMOTION_ENTRY),
            "NewsShort",
            video_silent,
            "--props", props_path,
            "--log=error",
        ]
        env = os.environ.copy()
        env["PATH"] = "/usr/local/bin:" + env.get("PATH", "")
        result = subprocess.run(
            cmd, cwd=str(_REMOTION_DIR),
            capture_output=True, text=True, env=env, timeout=600,
        )
        if result.returncode != 0:
            print("[Remotion stderr]", result.stderr[-2000:])
            raise RuntimeError(f"Remotion 렌더 실패 (rc={result.returncode})")
    finally:
        try:
            os.unlink(props_path)
        except Exception:
            pass
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            pass

    # 2) TTS + BGM 믹스 (news_direct_renderer의 오디오 파이프라인 재사용)
    if enable_tts or enable_bgm:
        try:
            from src.editor.news_audio import (
                generate_tts_for_segments, mix_audio_into_video, default_bgm,
            )
            with tempfile.TemporaryDirectory(prefix="remo_audio_") as tmp:
                work = Path(tmp)
                total_duration = sum(s.duration for s in news_script.segments)
                tts_files = []
                tts_offsets = []
                if enable_tts:
                    tts_files = generate_tts_for_segments(
                        news_script.segments, work,
                        provider=tts_provider, edge_voice=tts_voice,
                    )
                    offset = 0.0
                    for s in news_script.segments:
                        tts_offsets.append(offset)
                        offset += s.duration
                bgm = default_bgm() if enable_bgm else None
                if any(tts_files) or bgm:
                    mix_audio_into_video(
                        video_path=video_silent,
                        tts_files=tts_files,
                        tts_offsets=tts_offsets,
                        total_duration=total_duration,
                        out_path=str(out),
                        bgm_path=bgm,
                    )
                    os.unlink(video_silent)
                    return str(out)
        except Exception as e:
            print(f"  Remotion 오디오 믹스 실패 (무음으로 저장): {e}")

    # 오디오 없으면 무음 버전을 최종 출력으로
    shutil.move(video_silent, out)
    return str(out)
