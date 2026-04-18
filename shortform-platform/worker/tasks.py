"""
파이프라인 실행 모듈
- USE_CELERY=true  → Celery 워커로 실행 (Redis 필요)
- USE_CELERY=false → 백그라운드 스레드로 실행 (기본, Redis 불필요)
"""

import asyncio
import os
from pathlib import Path
from api.models import job_store, JobStatus, ClipInfo
from api.ws_manager import ws_manager
from src.downloader.youtube import download
from src.extractor.transcript import load as load_transcript
from src.selector.claude_selector import select_clips, plan_shorts
from src.editor.ffmpeg_editor import export_clips


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
        else:
            edited = _run_youtube_pipeline(job_id, req, num_clips, duration, style, make_thumbnail)

        def _to_url(p: str | None) -> str | None:
            if not p:
                return None
            # `output/...` 경로 전체를 URL 경로로 (하위 폴더 포함)
            norm = p.replace("\\", "/")
            if norm.startswith("output/"):
                return "/" + norm
            return f"/output/{os.path.basename(norm)}"

        clip_infos = []
        for e in edited:
            clip_infos.append(ClipInfo(
                index=e.clip_index,
                output_path=e.output_path,
                video_url=_to_url(e.output_path),
                thumbnail_url=_to_url(e.thumbnail_path),
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


def _run_news_pipeline(job_id, req, duration, style):
    """뉴스 텍스트/URL → Claude 기획 → 미디어 수집 → MP4 렌더링"""
    import re as _re
    from src.selector.news_script_generator import generate_news_script
    from src.searcher.media_searcher import fetch_media, UsedMediaSet
    from src.editor.news_direct_renderer import render_news_shorts
    from src.editor.news_themes import get_theme

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

    # 병렬 미디어 수집 (최대 5개 동시)
    from concurrent.futures import ThreadPoolExecutor, as_completed

    used_media = UsedMediaSet()
    # 고유명사 추출원 = 뉴스 제목 + hook + 본문 앞부분 (가장 정확한 사건명·인명)
    ref_title_blob = " ".join([
        news_title or script.title or "",
        script.hook_phrase or "",
        (news_text or "")[:600],   # 리드 문단에 인명/사건명이 집중
    ])

    def _fetch_one(idx_seg):
        i, seg = idx_seg
        path = fetch_media(
            media_type=seg.media_type,
            keyword=seg.search_keyword,
            keyword_ko=getattr(seg, "search_keyword_ko", ""),
            shot_type=getattr(seg, "shot_type", ""),
            output_dir=media_dir,
            filename=f"seg_{i:02d}",
            duration=seg.duration,
            graphic_style=seg.graphic_style,
            used_ids=used_media,
            ref_caption=seg.caption,
            ref_title=ref_title_blob,
        )
        return i, path

    _progress(job_id, JobStatus.EDITING, 40,
              f"미디어 {total}개 병렬 수집 중 (최대 5개 동시)...")
    done = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(_fetch_one, (i, seg)) for i, seg in enumerate(script.segments)]
        for f in as_completed(futures):
            try:
                i, path = f.result()
                script.segments[i].media_path = path
            except Exception as e:
                print(f"  세그먼트 수집 실패: {e}")
            done += 1
            pct = 40 + int(done / total * 40)
            _progress(job_id, JobStatus.EDITING, pct,
                      f"미디어 수집 {done}/{total} 완료")

    mp4_path = f"output/news/{stem}.mp4"
    enable_tts = req.get("enable_tts", True)
    enable_bgm = req.get("enable_bgm", True)
    enable_transitions = req.get("enable_transitions", True)
    enable_highlight_stat = req.get("enable_highlight_stat", False)
    # 끄기: 모든 세그먼트의 highlight_stat 비움
    if not enable_highlight_stat:
        for seg in script.segments:
            seg.highlight_stat = ""
    tts_provider = req.get("tts_provider", "edge")
    tts_voice = req.get("tts_voice", "ko-KR-SunHiNeural")
    enable_ticker = req.get("enable_ticker", False)
    ticker_text = req.get("ticker_text", "") or (script.description.split(".")[0] if enable_ticker else "")

    # ── TTS 사전 생성 + 실제 발화 시간에 맞춰 세그먼트 duration 조정 ──
    # 자막/음성 싱크 맞추기: TTS가 길면 세그먼트를 늘리고, 짧으면 최소 2초 보장
    if enable_tts:
        _progress(job_id, JobStatus.EDITING, 82, "TTS 내레이션 생성 중 (싱크 맞춤)...")
        from src.editor.news_audio import generate_tts_for_segments, get_audio_duration
        tts_dir = Path(media_dir) / "tts"
        tts_dir.mkdir(exist_ok=True)
        tts_files = generate_tts_for_segments(
            script.segments, tts_dir,
            provider=tts_provider, edge_voice=tts_voice,
        )
        for seg, tts in zip(script.segments, tts_files):
            if tts:
                tts_dur = get_audio_duration(tts)
                # TTS 발화 시간 + 0.3초 여유를 최소 duration으로
                new_dur = round(max(seg.duration, tts_dur + 0.3), 2)
                if abs(new_dur - seg.duration) > 0.1:
                    print(f"  [싱크] seg duration {seg.duration:.1f}s → {new_dur:.1f}s (TTS {tts_dur:.1f}s)")
                seg.duration = new_dur
                seg._tts_file = tts
            else:
                seg._tts_file = None

    # 썸네일 생성 (API 결과에서 클릭 유도 — Thumbnail 데이터 사용)
    thumb_path = None
    try:
        from src.editor.news_thumbnail import generate_thumbnail
        thumb_path = f"output/news/{stem}_thumb.jpg"
        generate_thumbnail(script.thumbnail, thumb_path)
        _progress(job_id, JobStatus.EDITING, 85, "썸네일 생성 완료")
    except Exception as e:
        print(f"  썸네일 생성 실패 (무시): {e}")

    _progress(job_id, JobStatus.EDITING, 88, f"MP4 렌더링 중 (테마: {theme_id})...")
    print(f"[pipeline] theme_id={theme_id} overrides={req.get('theme_overrides')}")

    theme_obj = get_theme(theme_id)

    def _render_pil(tid: str):
        render_news_shorts(
            news_script=script, output_path=mp4_path, theme_id=tid,
            ticker_text=ticker_text,
            enable_transitions=enable_transitions,
            enable_tts=enable_tts,
            enable_bgm=enable_bgm,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            theme_overrides=req.get("theme_overrides"),
        )

    if theme_obj.get("engine") == "remotion":
        try:
            from src.editor.news_remotion_renderer import render_news_shorts_remotion
            remotion_theme = theme_obj.get("remotion_theme_id", "samprotv")
            render_news_shorts_remotion(
                news_script=script, output_path=mp4_path,
                theme_id=remotion_theme,
                enable_tts=enable_tts,
                enable_bgm=enable_bgm,
                tts_provider=tts_provider,
                tts_voice=tts_voice,
            )
        except Exception as e:
            fallback_id = theme_obj.get("remotion_theme_id", "viral_pill")
            print(f"  Remotion 렌더 실패 ({e}) → PIL 테마 '{fallback_id}'로 fallback")
            _progress(job_id, JobStatus.EDITING, 90,
                      f"Remotion 실패 — PIL 테마({fallback_id})로 대체 렌더 중...")
            _render_pil(fallback_id)
    else:
        try:
            _render_pil(theme_id)
        except Exception as e:
            print(f"  MP4 렌더링 실패: {e}")
            raise

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
        output_path=mp4_path,
        hook=script.title,
        hashtags=script.hashtags,
        thumbnail_path=thumb_path,
    )]


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
