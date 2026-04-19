"""
파이프라인 실행 모듈
- USE_CELERY=true  → Celery 워커로 실행 (Redis 필요)
- USE_CELERY=false → 백그라운드 스레드로 실행 (기본, Redis 불필요)

진입점 _run_pipeline에서:
- 잡별 로그 파일(output/news/scripts/{ts}_{stem}/run.log)에 모든 stdout 캡처
- 시작 시 오래된 temp/scripts 자동 정리
- 친화적 에러 메시지 매핑
"""

import asyncio
import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from api.models import job_store, JobStatus, ClipInfo
from api.ws_manager import ws_manager
from src.common.logging_setup import get_logger, job_log_handler
from src.common.cleanup import cleanup_all
from src.downloader.youtube import download
from src.extractor.transcript import load as load_transcript
from src.selector.claude_selector import select_clips, plan_shorts
from src.editor.ffmpeg_editor import export_clips

log = get_logger(__name__)


# ── 친화적 에러 메시지 매핑 ──
def _friendly_error(exc: Exception) -> str:
    """raw exception → 사용자에게 보일 한국어 메시지."""
    s = str(exc)
    name = exc.__class__.__name__
    # 환경변수 누락
    if "ANTHROPIC_API_KEY" in s:
        return "Claude API 키가 설정되지 않았습니다 (ANTHROPIC_API_KEY)."
    if "OPENAI_API_KEY" in s:
        return "OpenAI API 키가 설정되지 않았습니다 (OPENAI_API_KEY)."
    if "PEXELS_API_KEY" in s or "PIXABAY_API_KEY" in s:
        return "스톡 미디어 API 키 누락 — 본문 사진/위키만 시도됩니다."
    # 파싱
    if "JSONDecodeError" in name or "json.decoder" in s:
        return "Claude 응답 파싱 실패 — 잠시 후 재시도해주세요."
    # 네트워크
    if "Timeout" in name or "timed out" in s.lower():
        return "외부 API 응답 지연 — 잠시 후 재시도해주세요."
    if "ConnectionError" in name or "Connection refused" in s:
        return "네트워크 연결 실패 — 인터넷 연결을 확인해주세요."
    # 입력
    if "뉴스 내용을 가져올 수 없습니다" in s:
        return s  # 이미 한국어
    if "자막을 추출할 수 없습니다" in s:
        return s
    # ffmpeg
    if "ffmpeg" in s.lower() and "returned non-zero" in s.lower():
        return "영상 인코딩 실패 — ffmpeg 오류. 로그를 확인해주세요."
    # 기본 — 첫 줄만
    first_line = s.split("\n", 1)[0][:200]
    return f"{name}: {first_line}"


def _safe_stem(text: str, fallback: str = "news") -> str:
    s = re.sub(r"[^\w]", "_", (text or "")[:30])
    return s or fallback


def _job_log_path(job_id: str, req: dict) -> Path:
    """잡별 run.log 경로 결정 — script.json과 같은 폴더로."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = (req.get("news_title") or req.get("news_text", "")[:20]
             or req.get("url", "") or req.get("blog_url", "") or job_id[:8])
    stem = _safe_stem(title)
    return Path("output/news/scripts") / f"{ts}_{stem}_{job_id[:6]}" / "run.log"


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
    """실제 파이프라인 로직 (스레드/Celery 양쪽에서 호출)
    - 잡별 run.log 자동 첨부
    - 시작 시 오래된 temp/scripts cleanup
    - 친화적 에러 메시지로 사용자 알림
    """
    job = job_store.get(job_id)
    if not job:
        return
    req = job["request"]

    # 1) 오래된 임시·로그 정리 (최신 30개 + 7일 이내 유지)
    try:
        cleanup_all(max_keep=30, max_age_days=7.0)
    except Exception as e:
        log.warning("cleanup 실패 무시: %s", e)

    # 2) 잡별 로그 파일 경로 결정 + JobStore에 기록
    log_path = _job_log_path(job_id, req)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    job_store.update(job_id, log_path=str(log_path))

    with job_log_handler(job_id, log_path):
        log.info("파이프라인 시작: job_id=%s, source=%s", job_id, req.get("source_type"))
        try:
            source_type    = req.get("source_type", "youtube")
            duration       = req["duration"]
            num_clips      = req["clips"]
            style          = req["style"]
            make_thumbnail = req.get("make_thumbnail", True)

            if source_type == "news":
                edited = _run_news_pipeline(job_id, req, duration, style)
            elif source_type == "blog":
                edited = _run_blog_pipeline(job_id, req, num_clips, duration, style, make_thumbnail)
            else:
                edited = _run_youtube_pipeline(job_id, req, num_clips, duration, style, make_thumbnail)

            def _to_url(p: str | None) -> str | None:
                if not p:
                    return None
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

            job_store.update(job_id, status=JobStatus.DONE, progress=100,
                             message="완료!", clips=clip_infos)
            _notify(job_id, "done", {"clips": clip_infos})
            log.info("파이프라인 완료: job_id=%s, clips=%d", job_id, len(clip_infos))

        except Exception as exc:
            tb = traceback.format_exc()
            log.error("파이프라인 실패: %s\n%s", exc, tb)
            friendly = _friendly_error(exc)
            job_store.update(job_id, status=JobStatus.FAILED, progress=0,
                             message="실패", error=friendly)
            _notify(job_id, "error", {"message": friendly})


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

    news_text  = req.get("news_text", "")
    news_url   = req.get("news_url", "")
    news_title = req.get("news_title", "")

    if news_url and not news_text:
        _progress(job_id, JobStatus.DOWNLOADING, 10, "뉴스 페이지 수집 중...")
        from src.extractor.blog_extractor import extract as extract_blog
        content = extract_blog(url=news_url, text="")
        news_text  = content.text
        news_title = news_title or content.title

    if not news_text:
        raise ValueError("뉴스 내용을 가져올 수 없습니다.")

    _progress(job_id, JobStatus.SELECTING, 25, "Claude AI가 숏츠 구성을 기획 중...")
    script, claude_prompt, claude_raw = generate_news_script(
        text=news_text, title=news_title, style=style, target_duration=duration,
        return_raw=True,
    )

    stem = _re.sub(r"[^\w]", "_", script.title[:20]) or "news"

    # ─ 기획 결과(NewsScript) JSON 로그 — job별 폴더 생성 ─
    import json as _json
    from dataclasses import asdict
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir = Path("output/news/scripts") / f"{ts}_{stem}"
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        script_data = {
            "job_id": job_id,
            "created_at": datetime.now().isoformat(),
            "source_url": news_url,
            "source_title": news_title,
            # 전체 뉴스 원문은 news_input.json에 저장됨
            "style": style,
            "target_duration_sec": duration,
            "title": script.title,
            "hook_phrase": script.hook_phrase,
            "hook_phrase_alternatives": getattr(script, "hook_phrase_alternatives", []),
            "emotion_target": getattr(script, "emotion_target", ""),
            "description": getattr(script, "description", ""),
            "hashtags": list(getattr(script, "hashtags", []) or []),
            "thumbnail": asdict(script.thumbnail) if getattr(script, "thumbnail", None) else None,
            "segment_count": len(script.segments),
        }
        (job_dir / "script.json").write_text(
            _json.dumps(script_data, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        # ① 입력 뉴스 원본 전체 저장
        news_input = {
            "url": news_url,
            "title": news_title,
            "text": news_text,
            "style": style,
            "target_duration_sec": duration,
            "captured_at": datetime.now().isoformat(),
        }
        (job_dir / "news_input.json").write_text(
            _json.dumps(news_input, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        # ② Claude 프롬프트 원본
        (job_dir / "claude_prompt.txt").write_text(claude_prompt, encoding="utf-8")
        # ③ Claude 응답 원본 (JSON 파싱 전 텍스트)
        (job_dir / "claude_response.txt").write_text(claude_raw, encoding="utf-8")
        # 초기 시점의 각 세그먼트(Claude 기획만) 저장 — 런타임 정보는 나중에 덮어씀
        for i, seg in enumerate(script.segments):
            seg_data = {k: v for k, v in asdict(seg).items() if not k.startswith("_")}
            seg_data["segment_index"] = i
            (job_dir / f"seg_{i:02d}.json").write_text(
                _json.dumps(seg_data, ensure_ascii=False, indent=2), encoding="utf-8",
            )
        print(f"[script saved] {job_dir}/ ({len(script.segments)}개 세그먼트 + 뉴스원문 + Claude prompt/response)")
    except Exception as _e:
        print(f"[script save 실패 무시] {_e}")
        job_dir = None

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

    # ── 원문 페이지 이미지 풀 추출 (뉴스 URL이 있을 때만 1회) ──
    news_og_image = None
    article_pool = None
    enable_ai_image = bool(req.get("enable_ai_image", False))
    if news_url:
        _progress(job_id, JobStatus.SELECTING, 35, "원문 페이지 이미지 전체 추출 중...")
        try:
            from src.searcher.media_searcher import (
                fetch_news_og_image, fetch_news_article_images, ArticleImagePool,
            )
            news_og_image = fetch_news_og_image(news_url)
            article_imgs = fetch_news_article_images(news_url, limit=12)
            article_pool = ArticleImagePool(article_imgs)
            if news_og_image:
                print(f"  [og:image] {news_og_image[:80]}")
            print(f"  [article-images] {len(article_imgs)}장 수집 → 풀 적재")
        except Exception as e:
            print(f"  [원문 이미지 추출 실패 무시] {e}")

    def _seg_label(seg, idx: int) -> str:
        """진행 메시지에 표시할 세그먼트 짧은 라벨."""
        cap = (seg.caption or "").strip().replace("\n", " ")
        snippet = cap[:24] + ("…" if len(cap) > 24 else "")
        subj = getattr(seg, "subject_name", "") or ""
        head = f"#{idx+1}"
        if subj:
            return f"{head} [{subj}] {snippet}"
        return f"{head} {snippet}"

    def _fetch_one(idx_seg):
        i, seg = idx_seg
        path, credit = fetch_media(
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
            subject_name=getattr(seg, "subject_name", ""),
            news_og_image=news_og_image,
            article_pool=article_pool,
            enable_ai_image=enable_ai_image,
        )
        # Smart crop: 얼굴 중심 X 비율 감지 (세로 크롭 시 좌우 위치 결정용)
        face_x = None
        if path:
            try:
                from src.searcher.media_searcher import detect_face_center_x
                face_x = detect_face_center_x(path)
            except Exception:
                face_x = None
        return i, path, face_x, credit

    _progress(job_id, JobStatus.EDITING, 40,
              f"미디어 {total}개 병렬 수집 시작 (최대 5개 동시)")
    done = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_fetch_one, (i, seg)): (i, seg)
                   for i, seg in enumerate(script.segments)}
        for f in as_completed(futures):
            i, seg = futures[f]
            label = _seg_label(seg, i)
            try:
                ri, path, face_x, credit = f.result()
                script.segments[ri].media_path = path
                script.segments[ri]._face_x = face_x   # smart crop 메타
                script.segments[ri]._source_credit = credit  # 저작권 출처 표기
                src_tag = f" · 출처: {credit}" if credit else ""
                msg_extra = f"{label}{src_tag}"
            except Exception as e:
                print(f"  세그먼트 수집 실패: {e}")
                msg_extra = f"{label} · 실패"
            done += 1
            pct = 40 + int(done / total * 40)
            _progress(job_id, JobStatus.EDITING, pct,
                      f"미디어 수집 {done}/{total} — {msg_extra}")

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
    if enable_tts:
        from src.editor.news_audio import generate_tts_for_segments, get_audio_duration
        tts_dir = Path(media_dir) / "tts"
        tts_dir.mkdir(exist_ok=True)
        n_tts = len(script.segments)
        _progress(job_id, JobStatus.EDITING, 81,
                  f"TTS 내레이션 생성 중 (0/{n_tts})...")

        def _tts_progress(done: int, total: int):
            # 81~84% 사이를 세그먼트별로 보간
            pct = 81 + int(3 * done / max(1, total))
            _progress(job_id, JobStatus.EDITING, pct,
                      f"TTS 내레이션 생성 {done}/{total}")

        tts_files = generate_tts_for_segments(
            script.segments, tts_dir,
            provider=tts_provider, edge_voice=tts_voice,
            progress_cb=_tts_progress,
        )
        for ti, (seg, tts) in enumerate(zip(script.segments, tts_files)):
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
        _progress(job_id, JobStatus.EDITING, 84,
                  f"TTS 완료 ({sum(1 for t in tts_files if t)}/{n_tts}) — 싱크 정렬 완료")

    # ─ 각 세그먼트 런타임 정보로 per-segment JSON 덮어쓰기 ─
    if job_dir is not None:
        try:
            for i, seg in enumerate(script.segments):
                seg_data = {k: v for k, v in asdict(seg).items() if not k.startswith("_")}
                seg_data["segment_index"] = i
                seg_data["runtime"] = {
                    "media_path": getattr(seg, "media_path", ""),
                    "tts_file": getattr(seg, "_tts_file", None),
                    "face_x": getattr(seg, "_face_x", None),
                    "source_credit": getattr(seg, "_source_credit", None),
                    "final_duration_sec": float(seg.duration),
                }
                (job_dir / f"seg_{i:02d}.json").write_text(
                    _json.dumps(seg_data, ensure_ascii=False, indent=2), encoding="utf-8",
                )
            print(f"[segments updated] {job_dir}/ (런타임 정보 포함)")
        except Exception as _e:
            print(f"[segments save 실패 무시] {_e}")

    # 썸네일 생성 (API 결과에서 클릭 유도)
    # v2: 인물 사진(Wikimedia) → og:image → climax 프레임 → gradient 폴백
    thumb_path = None
    try:
        from src.editor.news_thumbnail import generate_thumbnail
        thumb_path = f"output/news/{stem}_thumb.jpg"
        generate_thumbnail(
            script.thumbnail, thumb_path,
            news_script=script,
            news_og_image=news_og_image,
        )
        _progress(job_id, JobStatus.EDITING, 85, "썸네일 생성 완료")
    except Exception as e:
        print(f"  썸네일 생성 실패 (무시): {e}")

    enable_remotion_flag = req.get("enable_remotion", False)
    engine = "Remotion" if enable_remotion_flag else "PIL"
    _progress(job_id, JobStatus.EDITING, 88, f"MP4 렌더링 중 ({engine})...")
    print(f"[pipeline] engine={engine} overrides={req.get('theme_overrides')}")

    def _render_pil():
        render_news_shorts(
            news_script=script, output_path=mp4_path,
            ticker_text=ticker_text,
            enable_transitions=enable_transitions,
            enable_tts=enable_tts,
            enable_bgm=enable_bgm,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            theme_overrides=req.get("theme_overrides"),
        )

    def _remotion_progress(pct: int, msg: str):
        # renderer에서 88~97% 구간을 실시간 보고
        _progress(job_id, JobStatus.EDITING, pct, msg)

    if enable_remotion_flag:
        try:
            from src.editor.news_remotion_renderer import render_news_shorts_remotion
            render_news_shorts_remotion(
                news_script=script, output_path=mp4_path,
                enable_tts=enable_tts,
                enable_bgm=enable_bgm,
                tts_provider=tts_provider,
                tts_voice=tts_voice,
                theme_overrides=req.get("theme_overrides"),
                enable_transitions=enable_transitions,
                progress_cb=_remotion_progress,
            )
            _progress(job_id, JobStatus.EDITING, 98, "오디오 믹스 + 최종 인코딩 완료")
        except Exception as e:
            print(f"  Remotion 렌더 실패 ({e}) → PIL로 fallback")
            _progress(job_id, JobStatus.EDITING, 90, "Remotion 실패 — PIL로 대체 렌더 중...")
            _render_pil()
    else:
        try:
            _render_pil()
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
