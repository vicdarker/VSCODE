"""
파이프라인 실행 모듈
- USE_CELERY=true  → Celery 워커로 실행 (Redis 필요)
- USE_CELERY=false → 백그라운드 스레드로 실행 (기본, Redis 불필요)
"""

import asyncio
import os
from api.models import job_store, JobStatus, ClipInfo
from api.ws_manager import ws_manager
from src.downloader.youtube import download
from src.extractor.transcript import load as load_transcript
from src.selector.claude_selector import select_clips, plan_shorts
from src.editor.ffmpeg_editor import export_clips
from src.editor.capcut_exporter import export_script_to_capcut


_main_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _notify(job_id: str, event: str, data: dict):
    """WebSocket 이벤트 전송 (동기 컨텍스트에서 호출)"""
    if not _main_loop:
        return
    try:
        asyncio.run_coroutine_threadsafe(
            ws_manager.send(job_id, event, data), _main_loop
        )
    except Exception:
        pass


def _progress(job_id: str, status: JobStatus, progress: int, message: str):
    job_store.update(job_id, status=status, progress=progress, message=message)
    _notify(job_id, "progress", {"status": status, "progress": progress, "message": message})


def _run_pipeline(job_id: str):
    """실제 파이프라인 로직 (스레드/Celery 양쪽에서 호출)"""
    try:
        job = job_store.get(job_id)
        if not job:
            return

        req = job["request"]
        source_type    = req.get("source_type", "youtube")
        duration       = req["duration"]
        num_clips      = req["clips"]
        style          = req["style"]
        make_thumbnail = req.get("make_thumbnail", True)

        output_format = req.get("output_format", "mp4")

        if source_type == "news":
            edited = _run_news_pipeline(job_id, req, duration, style)
        elif source_type == "blog":
            edited = _run_blog_pipeline(job_id, req, num_clips, duration, style, make_thumbnail)
        elif output_format == "capcut":
            edited = _run_capcut_pipeline(job_id, req, duration, style)
        else:
            edited = _run_youtube_pipeline(job_id, req, num_clips, duration, style, make_thumbnail)

        clip_infos = []
        for e in edited:
            thumb_url = (
                f"/output/{os.path.basename(e.thumbnail_path)}"
                if e.thumbnail_path else None
            )
            clip_infos.append(ClipInfo(
                index=e.clip_index,
                output_path=e.output_path,
                video_url=f"/output/{os.path.basename(e.output_path)}",
                thumbnail_url=thumb_url,
                start=e.start,
                end=e.end,
                hook=e.hook,
                hashtags=e.hashtags,
            ).model_dump())

        job_store.update(job_id, status=JobStatus.DONE, progress=100, message="완료!", clips=clip_infos)
        _notify(job_id, "done", {"clips": clip_infos})

    except Exception as exc:
        job_store.update(job_id, status=JobStatus.FAILED, progress=0, message="실패", error=str(exc))
        _notify(job_id, "error", {"message": str(exc)})


def _run_youtube_pipeline(job_id, req, num_clips, duration, style, make_thumbnail):
    vertical     = req["vertical"]
    caption_mode = req.get("caption_mode", "word_pop")

    _progress(job_id, JobStatus.DOWNLOADING, 10, "YouTube 영상 다운로드 중...")
    result = download(url=req["url"], output_dir="temp")

    _progress(job_id, JobStatus.TRANSCRIBING, 30, "자막 분석 중...")
    segments = load_transcript(
        video_path=result.video_path,
        subtitle_path=result.subtitle_path,
    )
    if not segments:
        raise ValueError("자막을 추출할 수 없습니다.")

    _progress(job_id, JobStatus.SELECTING, 55, f"Claude AI가 최적 구간 {num_clips}개 선택 중...")
    clips = select_clips(
        segments=segments,
        title=result.title,
        duration_sec=duration,
        num_clips=num_clips,
        style=style,
    )

    _progress(job_id, JobStatus.EDITING, 75, "영상 편집 및 자막/썸네일 생성 중...")
    return export_clips(
        video_path=result.video_path,
        clips=clips,
        output_dir="output",
        vertical=vertical,
        caption_mode=None if caption_mode == "none" else caption_mode,
        segments=segments,
        make_thumbnail=make_thumbnail,
    )


def _run_capcut_pipeline(job_id, req, duration, style):
    """YouTube 영상 → Claude 숏츠 기획 → CapCut JSON"""
    _progress(job_id, JobStatus.DOWNLOADING, 10, "YouTube 영상 다운로드 중...")
    result = download(url=req["url"], output_dir="temp")

    _progress(job_id, JobStatus.TRANSCRIBING, 30, "자막 분석 중...")
    segments = load_transcript(
        video_path=result.video_path,
        subtitle_path=result.subtitle_path,
    )
    if not segments:
        raise ValueError("자막을 추출할 수 없습니다.")

    _progress(job_id, JobStatus.SELECTING, 55, "Claude AI가 숏츠 전체 구성을 기획 중...")
    script = plan_shorts(
        segments=segments,
        title=result.title,
        target_duration=duration,
        style=style,
    )

    _progress(job_id, JobStatus.EDITING, 80, "CapCut 프로젝트 파일 생성 중...")
    project_dir = export_script_to_capcut(
        video_path=result.video_path,
        script=script,
        output_dir="output/capcut",
    )

    from dataclasses import dataclass

    @dataclass
    class _FakeResult:
        output_path: str
        clip_index: int = 1
        start: float = 0
        end: float = 0
        hook: str = ""
        hashtags: list = None
        thumbnail_path: str = None

        def __post_init__(self):
            if self.hashtags is None:
                self.hashtags = []

    return [_FakeResult(
        output_path=project_dir,
        hook=script.title,
        hashtags=script.hashtags,
    )]


def _run_news_pipeline(job_id, req, duration, style):
    """뉴스 텍스트/URL → Claude 기획 → 미디어 수집 → MP4 렌더링 + CapCut 프로젝트"""
    import re as _re
    from src.selector.news_script_generator import generate_news_script
    from src.searcher.media_searcher import fetch_media
    from src.editor.capcut_exporter import export_news_to_capcut
    from src.editor.news_direct_renderer import render_news_shorts

    news_text  = req.get("news_text", "")
    news_url   = req.get("news_url", "")
    news_title = req.get("news_title", "")
    theme_id   = req.get("theme_id", "samprotv")

    if news_url and not news_text:
        _progress(job_id, JobStatus.DOWNLOADING, 10, "뉴스 페이지 수집 중...")
        from src.extractor.blog_extractor import extract as extract_blog
        content = extract_blog(url=news_url, text="")
        news_text  = content.text
        news_title = news_title or content.title

    if not news_text:
        raise ValueError("뉴스 내용을 가져올 수 없습니다.")

    _progress(job_id, JobStatus.SELECTING, 25, "Claude AI가 숏츠 구성을 기획 중...")
    script = generate_news_script(
        text=news_text, title=news_title, style=style, target_duration=duration,
    )

    stem = _re.sub(r"[^\w]", "_", script.title[:20]) or "news"
    media_dir = f"temp/news_{stem}"
    total = len(script.segments)

    for i, seg in enumerate(script.segments):
        pct = 40 + int(i / total * 40)
        _progress(job_id, JobStatus.EDITING, pct,
                  f"미디어 수집 중... ({i+1}/{total}) [{seg.media_type}] {seg.search_keyword or '그래픽'}")
        seg.media_path = fetch_media(
            media_type=seg.media_type,
            keyword=seg.search_keyword,
            output_dir=media_dir,
            filename=f"seg_{i:02d}",
            duration=seg.duration,
            graphic_style=seg.graphic_style,
        )

    _progress(job_id, JobStatus.EDITING, 85, "CapCut 프로젝트 파일 생성 중...")
    project_dir = export_news_to_capcut(news_script=script, output_dir="output/capcut")

    _progress(job_id, JobStatus.EDITING, 92, f"MP4 렌더링 중 (테마: {theme_id})...")
    mp4_path = f"output/news/{stem}.mp4"
    try:
        render_news_shorts(news_script=script, output_path=mp4_path, theme_id=theme_id)
    except Exception as e:
        print(f"  MP4 렌더링 실패 (무시): {e}")
        mp4_path = project_dir  # fallback

    from dataclasses import dataclass

    @dataclass
    class _FakeResult:
        output_path: str
        clip_index: int = 1
        start: float = 0
        end: float = 0
        hook: str = ""
        hashtags: list = None
        thumbnail_path: str = None

        def __post_init__(self):
            if self.hashtags is None:
                self.hashtags = []

    return [_FakeResult(output_path=mp4_path, hook=script.title, hashtags=script.hashtags)]


def _run_blog_pipeline(job_id, req, num_scripts, duration, style, make_thumbnail):
    from src.extractor.blog_extractor import extract as extract_blog
    from src.selector.blog_script_generator import generate_scripts
    from src.editor.text_video_maker import make_videos

    _progress(job_id, JobStatus.DOWNLOADING, 10, "블로그 콘텐츠 수집 중...")
    content = extract_blog(url=req.get("blog_url", ""), text=req.get("blog_text", ""))
    if not content.text:
        raise ValueError("블로그 내용을 추출할 수 없습니다.")

    _progress(job_id, JobStatus.SELECTING, 40, f"Claude AI가 흥미로운 주제 {num_scripts}개 추출 중...")
    scripts = generate_scripts(
        content=content,
        num_scripts=num_scripts,
        duration_sec=duration,
        style=style,
    )

    _progress(job_id, JobStatus.EDITING, 70, "TTS 음성 생성 및 영상 제작 중...")
    import re
    stem = re.sub(r"[^\w]", "_", content.title[:20]) or "blog"
    return make_videos(
        scripts=scripts,
        output_dir="output",
        job_stem=stem,
        make_thumbnail=make_thumbnail,
    )


# ── Celery 설정 (USE_CELERY=true 일 때만 사용) ──────────────────────────

def _make_celery():
    from celery import Celery
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    app = Celery("shortform", broker=REDIS_URL, backend=REDIS_URL)
    app.conf.update(task_serializer="json", result_serializer="json",
                    accept_content=["json"], timezone="Asia/Seoul")
    return app


if os.environ.get("USE_CELERY", "false").lower() == "true":
    celery_app = _make_celery()

    @celery_app.task(bind=True, name="worker.tasks.generate_shortform")
    def generate_shortform(self, job_id: str):
        _run_pipeline(job_id)
else:
    # 스텁 — 스레드 모드에서는 호출되지 않음
    class _Stub:
        def delay(self, *a, **kw): pass
    generate_shortform = _Stub()
