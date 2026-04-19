"""
Remotion 기반 뉴스 숏츠 렌더러.
React 컴포넌트로 복잡한 애니메이션 (슬라이드인, 스프링 바운스, 줌 등) 구현.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Callable, Optional

ProgressCb = Optional[Callable[[int, str], None]]


import time

# Remotion stdout 진행률 파서 — `\r`로 갱신되는 ANSI 라인까지 처리.
_RE_BUNDLING_START = re.compile(r"\bBundling\b", re.I)
_RE_BUNDLED_DONE   = re.compile(r"\bBundled\b", re.I)
_RE_BROWSER        = re.compile(r"\b(launch(?:ing|ed)?|browser|chromium|chrome|page|tab)\b", re.I)
_RE_COMPOSITION    = re.compile(r"\b(composition|metadata|calculated)\b", re.I)
# "Rendering frames 12/300" / "Rendered 50/300 frames" / "Rendered frames: 150 / 300" 모두 처리
_RE_RENDER_FRAMES  = re.compile(r"Render(?:ing|ed)\s+(?:frames?\s*[:\-]?\s*)?(\d+)\s*/\s*(\d+)", re.I)
_RE_ENCODE_FRAMES  = re.compile(r"Encod(?:ing|ed)\s+(?:frames?\s*[:\-]?\s*)?(\d+)\s*/\s*(\d+)", re.I)
_RE_GENERIC_PCT    = re.compile(r"(\d{1,3})(?:\.\d+)?\s*%")

# 번들링 단계 라벨·소비 % (base_pct에서 +0~+1 범위, 텍스트 위주 변화)
_PRE_RENDER_LABELS = {
    "bundling":     ("Remotion 번들링 중",        0),
    "bundled":      ("번들 완료 → Chromium 부팅",  1),
    "browser":      ("Chromium 준비 → 컴포지션 분석", 1),
    "composition":  ("컴포지션 분석 완료 → 첫 프레임 대기", 1),
}


def _stream_remotion_progress(proc: subprocess.Popen, cb: ProgressCb,
                              base_pct: int = 88, span_pct: int = 9) -> tuple[str, str]:
    """
    Remotion 자식 프로세스의 stdout/stderr를 실시간 읽어 progress_cb로 보고.
    base_pct ~ base_pct+span_pct (기본 88~97%) 구간에 매핑.

    번들링 단계는 (1) 키워드 라벨 + (2) 2초 heartbeat(경과시간) 두 가지로 가시화.
    반환: (stdout_buf, stderr_buf) — 실패 진단용.
    """
    out_buf: list[str] = []
    err_buf: list[str] = []
    last_pct = base_pct
    last_msg = ""
    state = {
        "phase": "bundling",       # bundling → bundled → browser → composition → rendering → encoding
        "phase_started_at": time.monotonic(),
        "heartbeat_stop": False,
    }
    lock = threading.Lock()

    def _emit(pct: int, msg: str):
        nonlocal last_pct, last_msg
        pct = max(base_pct, min(base_pct + span_pct, int(pct)))
        with lock:
            if not cb:
                return
            if pct == last_pct and msg == last_msg:
                return
            last_pct, last_msg = pct, msg
        try:
            cb(pct, msg)
        except Exception:
            pass

    def _set_phase(name: str):
        if state["phase"] == name:
            return
        state["phase"] = name
        state["phase_started_at"] = time.monotonic()
        label, off = _PRE_RENDER_LABELS.get(name, (name, 0))
        _emit(base_pct + off, label)

    def _heartbeat():
        # 렌더링 시작 전까지만 — 2초마다 경과시간 갱신
        while not state["heartbeat_stop"]:
            time.sleep(2.0)
            if state["heartbeat_stop"]:
                return
            phase = state["phase"]
            if phase in ("rendering", "encoding"):
                return
            elapsed = int(time.monotonic() - state["phase_started_at"])
            label, off = _PRE_RENDER_LABELS.get(phase, (phase, 0))
            _emit(base_pct + off, f"{label} ({elapsed}초 경과)")

    def _parse(line: str, sink: list[str]):
        sink.append(line)
        m = _RE_RENDER_FRAMES.search(line)
        if m:
            state["phase"] = "rendering"
            cur, total = int(m.group(1)), max(1, int(m.group(2)))
            ratio = cur / total
            # 렌더 단계 = span의 30~70% 구간
            pct = base_pct + int(span_pct * (0.30 + 0.40 * ratio))
            _emit(pct, f"Remotion 프레임 렌더 {cur}/{total}")
            return
        m = _RE_ENCODE_FRAMES.search(line)
        if m:
            state["phase"] = "encoding"
            cur, total = int(m.group(1)), max(1, int(m.group(2)))
            ratio = cur / total
            # 인코딩 단계 = span의 70~95%
            pct = base_pct + int(span_pct * (0.70 + 0.25 * ratio))
            _emit(pct, f"Remotion 인코딩 {cur}/{total}")
            return
        # 단계 라벨 파싱 (순서 중요: 더 진행된 단계가 우선)
        if _RE_COMPOSITION.search(line):
            _set_phase("composition")
            return
        if _RE_BROWSER.search(line):
            _set_phase("browser")
            return
        if _RE_BUNDLED_DONE.search(line):
            _set_phase("bundled")
            return
        if _RE_BUNDLING_START.search(line):
            _set_phase("bundling")
            return
        # 일반 % fallback (렌더 단계에서만)
        m = _RE_GENERIC_PCT.search(line)
        if m and state["phase"] == "rendering":
            try:
                p = int(m.group(1))
                pct = base_pct + int(span_pct * (0.30 + 0.40 * (p / 100.0)))
                _emit(pct, f"Remotion 프레임 렌더 {p}%")
            except Exception:
                pass

    def _reader(stream, sink):
        # `\r` 갱신도 잡히도록 한 글자씩 읽고 줄바꿈/CR로 나눠 파싱.
        buf = ""
        try:
            while True:
                ch = stream.read(1)
                if not ch:
                    if buf:
                        _parse(buf, sink)
                    return
                if ch in ("\n", "\r"):
                    if buf.strip():
                        _parse(buf, sink)
                    buf = ""
                else:
                    buf += ch
        except Exception:
            return

    t_hb  = threading.Thread(target=_heartbeat, daemon=True)
    t_out = threading.Thread(target=_reader, args=(proc.stdout, out_buf), daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, err_buf), daemon=True)
    t_hb.start(); t_out.start(); t_err.start()
    proc.wait()
    state["heartbeat_stop"] = True
    t_out.join(timeout=2)
    t_err.join(timeout=2)
    t_hb.join(timeout=2)
    return "".join(out_buf), "".join(err_buf)


from src.common.paths import remotion_dir
_REMOTION_DIR = remotion_dir()
_REMOTION_ENTRY = _REMOTION_DIR / "src" / "index.ts"
_PUBLIC_DIR = _REMOTION_DIR / "public"


def _rgba_to_css(c):
    """PIL tuple/list → CSS color 문자열. None 또는 잘못된 포맷이면 None."""
    if not c or not isinstance(c, (list, tuple)) or len(c) < 3:
        return None
    r, g, b = int(c[0]), int(c[1]), int(c[2])
    a = int(c[3]) if len(c) >= 4 else 255
    if a >= 255:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"rgba({r},{g},{b},{a/255:.2f})"


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


def _resolve_theme_default_font_ids() -> dict:
    """기본 테마의 폰트 경로 → font_id 3개(caption/title/brand)."""
    try:
        from src.editor.news_themes import get_default_theme, _path_to_font_id
        t = get_default_theme()
    except Exception:
        return {}
    out = {}
    cap_path = (t.get("caption") or {}).get("font", "")
    if cap_path:
        fid = _path_to_font_id(cap_path)
        if fid:
            out["caption"] = fid
    ttl_path = (t.get("title") or {}).get("font", "")
    if ttl_path:
        fid = _path_to_font_id(ttl_path)
        if fid:
            out["title"] = fid
    brand_path = (t.get("bottom_brand") or {}).get("font", "")
    if brand_path:
        fid = _path_to_font_id(brand_path)
        if fid:
            out["brand"] = fid
    return out


def _to_props(news_script, fps: int = 30,
              theme_overrides: dict | None = None,
              enable_transitions: bool = True):
    """NewsScript → (Remotion props, public_job_dir)"""
    media_paths = [os.path.abspath(s.media_path) for s in news_script.segments]
    rel_urls, job_dir = _stage_media_to_public(media_paths)

    # TTS 단어 타임스탬프로 청크별 정확한 (start, end) 계산 헬퍼
    from src.editor.news_audio import get_word_timings, compute_chunk_timings
    from src.editor.news_themes import resolve_font
    from PIL import Image, ImageDraw, ImageFont

    # 자막 폰트·크기 (오버라이드 있으면 그대로, 없으면 기본값)
    _ov_cap = (theme_overrides or {}).get("caption") or {}
    _cap_size = int(_ov_cap.get("size") or 72)
    _cap_font_id = _ov_cap.get("font_id") or "black_han_sans"
    try:
        _pil_font = ImageFont.truetype(resolve_font(_cap_font_id), _cap_size)
    except Exception:
        _pil_font = ImageFont.load_default()
    # Remotion 캔버스 1080 - padding 120 - 여유 20 = 940 (한 줄)
    # 2줄까지 허용: 총 텍스트 폭이 2*_max_line_px 이하면 그대로. 초과 시 단어 경계에서 분리.
    _max_line_px = 940
    _max_2line_px = _max_line_px * 2  # 1880
    _dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    def _subsplit_to_max_two_lines(chunk: str) -> list[str]:
        """공백 기준 greedy: 2줄 분량까지 누적. 초과 시 분리.
        CSS가 자동 wrap 하므로 각 서브청크는 최대 2줄로 표시됨."""
        tokens = chunk.split()
        if not tokens:
            return [chunk]
        subs: list[str] = []
        cur = ""
        for tk in tokens:
            cand = f"{cur} {tk}".strip() if cur else tk
            bbox = _dummy.textbbox((0, 0), cand, font=_pil_font)
            w = bbox[2] - bbox[0]
            if w <= _max_2line_px or not cur:
                cur = cand
            else:
                subs.append(cur)
                cur = tk
        if cur:
            subs.append(cur)
        return subs

    segments = []
    for seg, rel in zip(news_script.segments, rel_urls):
        orig_chunks = seg.caption_chunks if seg.caption_chunks else [seg.caption or ""]
        # ① 청크를 최대 2줄 분량으로 쪼갬 (단어 경계 유지)
        flat_chunks: list[str] = []
        for c in orig_chunks:
            flat_chunks.extend(_subsplit_to_max_two_lines(c))
        if not flat_chunks:
            flat_chunks = [seg.caption or ""]

        seg_dict = {
            "mediaPath": rel,
            "caption": seg.caption or "",
            "captionChunks": flat_chunks,
            "emphasisWords": seg.emphasis_words or [],
            "highlightStat": seg.highlight_stat or "",
            "reactionEmoji": seg.reaction_emoji or "",
            "role": seg.role or "body",
            "duration": float(seg.duration),
        }
        # ② TTS 단어 타임스탬프로 서브청크 각각의 정확한 (start, end) 계산
        tts_file = getattr(seg, "_tts_file", None)
        if tts_file:
            try:
                words = get_word_timings(tts_file)
                # 이제 flat_chunks의 각 청크는 공백 기준으로 분할된 상태 →
                # compute_chunk_timings가 첫 단어 매칭으로 정확한 시작 시간 찾음
                timings = compute_chunk_timings(flat_chunks, words, float(seg.duration))
                if timings:
                    seg_dict["chunkTimings"] = [[float(s), float(e)] for s, e in timings]
            except Exception as _e:
                pass  # 실패해도 균등 분할로 폴백
        chart_values = getattr(seg, "chart_values", None) or []
        if chart_values:
            seg_dict["chartValues"] = [float(v) for v in chart_values]
        # Smart crop: 얼굴 중심 X 비율 (0.0~1.0) — CSS object-position에 사용
        face_x = getattr(seg, "_face_x", None)
        if face_x is not None:
            try:
                seg_dict["videoObjectPosX"] = float(face_x)
            except (ValueError, TypeError):
                pass
        # 저작권 출처 크레딧 (화이트리스트 채널 영상만)
        credit = getattr(seg, "_source_credit", None)
        if credit:
            seg_dict["sourceCredit"] = str(credit)
        segments.append(seg_dict)
    hook = getattr(news_script, "hook_phrase", "") or news_script.title or ""
    # "속보" 배너: shock/outrage 감정이면 자동 ON
    emotion = getattr(news_script, "emotion_target", "")
    breaking_news = emotion in ("shock", "outrage")
    props = {
        "hookPhrase": hook,
        "segments": segments,
        "fps": fps,
        "breakingNews": breaking_news,
    }
    # theme_overrides → Remotion props 전부 매핑
    ov = theme_overrides or {}

    # 레이아웃 비율
    lay_ov = ov.get("layout") or {}
    if lay_ov.get("top_h") is not None:
        try: props["layoutTopH"] = int(lay_ov["top_h"])
        except (ValueError, TypeError): pass
    if lay_ov.get("vid_h") is not None:
        try: props["layoutVidH"] = int(lay_ov["vid_h"])
        except (ValueError, TypeError): pass
    if lay_ov.get("bot_h") is not None:
        try: props["layoutBotH"] = int(lay_ov["bot_h"])
        except (ValueError, TypeError): pass

    # 자막
    cap_ov = ov.get("caption") or {}
    if cap_ov.get("y_offset") is not None:
        try: props["captionYOffset"] = int(cap_ov["y_offset"])
        except (ValueError, TypeError): pass
    if cap_ov.get("size"):
        try: props["captionSize"] = int(cap_ov["size"])
        except (ValueError, TypeError): pass
    if cap_ov.get("area"):
        props["captionArea"] = str(cap_ov["area"])
    cap_color = _rgba_to_css(cap_ov.get("color"))
    if cap_color: props["captionColor"] = cap_color
    cap_stroke = _rgba_to_css(cap_ov.get("stroke_color"))
    if cap_stroke: props["captionStrokeColor"] = cap_stroke
    if cap_ov.get("stroke_w") is not None:
        try: props["captionStrokeW"] = int(cap_ov["stroke_w"])
        except (ValueError, TypeError): pass
    if cap_ov.get("font_id"):
        props["captionFontId"] = str(cap_ov["font_id"])

    # 타이틀
    ttl_ov = ov.get("title") or {}
    if ttl_ov.get("size"):
        try: props["titleSize"] = int(ttl_ov["size"])
        except (ValueError, TypeError): pass
    ttl_color = _rgba_to_css(ttl_ov.get("color"))
    if ttl_color: props["titleColor"] = ttl_color
    if ttl_ov.get("accent_last_line") is not None:
        props["titleAccentLastLine"] = bool(ttl_ov["accent_last_line"])
    ttl_accent = _rgba_to_css(ttl_ov.get("accent_color"))
    if ttl_accent: props["titleAccentColor"] = ttl_accent
    if ttl_ov.get("font_id"):
        props["titleFontId"] = str(ttl_ov["font_id"])

    # 하단 브랜드
    if ov.get("fixed_bottom_text"):
        props["bottomBrandText"] = str(ov["fixed_bottom_text"])
    brand_ov = ov.get("bottom_brand") or {}
    if brand_ov.get("size"):
        try: props["bottomBrandSize"] = int(brand_ov["size"])
        except (ValueError, TypeError): pass
    if brand_ov.get("font_id"):
        props["bottomBrandFontId"] = str(brand_ov["font_id"])

    # 전환 토글
    props["enableTransitions"] = bool(enable_transitions)

    # ─ "테마 기본" 폰트 폴백 ─
    theme_defaults = _resolve_theme_default_font_ids()
    if "captionFontId" not in props and theme_defaults.get("caption"):
        props["captionFontId"] = theme_defaults["caption"]
    if "titleFontId" not in props and theme_defaults.get("title"):
        props["titleFontId"] = theme_defaults["title"]
    if "bottomBrandFontId" not in props and theme_defaults.get("brand"):
        props["bottomBrandFontId"] = theme_defaults["brand"]

    return props, job_dir


def render_news_shorts_remotion(
    news_script,
    output_path: str,
    fps: int = 30,
    enable_tts: bool = True,
    enable_bgm: bool = True,
    tts_provider: str = "edge",
    tts_voice: str = "ko-KR-SunHiNeural",
    theme_overrides: dict | None = None,
    enable_transitions: bool = True,
    progress_cb: ProgressCb = None,
) -> str:
    """
    Remotion으로 렌더링. 결과 mp4 경로 반환.
    """
    # Remotion은 cwd=/app/remotion/에서 실행 → 출력 경로는 반드시 절대경로로
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    props, job_dir = _to_props(news_script, fps=fps,
                                theme_overrides=theme_overrides,
                                enable_transitions=enable_transitions)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False)
        props_path = f.name

    # 1) Remotion으로 영상만 먼저 렌더 (무음) — 자식 프로세스 stdout 실시간 파싱
    video_silent = str(out.parent / f"{out.stem}__silent.mp4")
    try:
        if progress_cb:
            progress_cb(88, "Remotion 시작 중 (Chromium 부팅)...")
        cmd = [
            "npx", "--yes", "remotion", "render",
            str(_REMOTION_ENTRY),
            "NewsShort",
            video_silent,
            "--props", props_path,
            # 진행률 파싱을 위해 info 레벨 유지 (--log=error 제거)
            "--concurrency=1",
        ]
        env = os.environ.copy()
        env["PATH"] = "/usr/local/bin:" + env.get("PATH", "")
        env.setdefault("REMOTION_CHROME_DISABLE_SANDBOX", "1")
        # CI 모드 강제 — TTY 의존 progress bar 대신 line 단위 출력 유도
        env["CI"] = "1"
        proc = subprocess.Popen(
            cmd, cwd=str(_REMOTION_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env, bufsize=1,
        )
        try:
            stdout_str, stderr_str = _stream_remotion_progress(
                proc, progress_cb, base_pct=88, span_pct=9,
            )
        except Exception:
            proc.kill()
            raise
        rc = proc.returncode
        if rc != 0:
            print("[Remotion stderr]", (stderr_str or "")[-3000:])
            print("[Remotion stdout]", (stdout_str or "")[-1000:])
            raise RuntimeError(f"Remotion 렌더 실패 (rc={rc})")
        if not Path(video_silent).exists() or Path(video_silent).stat().st_size < 10_000:
            print("[Remotion stderr]", (stderr_str or "")[-2000:])
            print("[Remotion stdout]", (stdout_str or "")[-2000:])
            raise RuntimeError(f"Remotion 출력 파일 없음: {video_silent}")
        print(f"[Remotion] 렌더 OK ({Path(video_silent).stat().st_size // 1024}KB)")
        if progress_cb:
            progress_cb(97, "Remotion 렌더 완료 → 오디오 믹스 단계")
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
                n_segs = len(news_script.segments)
                # TransitionSeries overlap: 전환 켜져 있으면 세그먼트 경계마다
                # 8프레임씩 겹쳐서 영상이 그만큼 짧아짐. TTS 오프셋도 동일하게 당김.
                TRANSITION_FRAMES = 8
                trans_sec = (TRANSITION_FRAMES / fps) if enable_transitions and n_segs >= 2 else 0.0
                total_duration = sum(s.duration for s in news_script.segments) - trans_sec * max(0, n_segs - 1)
                tts_files = []
                tts_offsets = []
                if enable_tts:
                    tts_files = generate_tts_for_segments(
                        news_script.segments, work,
                        provider=tts_provider, edge_voice=tts_voice,
                    )
                    # 각 세그먼트의 TTS 시작 시각 = "전환이 끝나고 완전히 보일 때"
                    # i=0: 0
                    # i>=1: cum(D[0:i]) - (i-1)*T
                    #       ≈ 이전 세그먼트 end - T (= 페이드아웃 시작 시점) + T (= 전환 완료)
                    #       = 이전 세그먼트의 "논리적 끝"
                    offset = 0.0
                    for i, s in enumerate(news_script.segments):
                        if i == 0:
                            tts_offsets.append(0.0)
                        else:
                            tts_offsets.append(max(0.0, offset - (i - 1) * trans_sec))
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

    # 오디오 없음 또는 믹스 실패 → 무음 버전을 최종 출력으로
    if not Path(video_silent).exists():
        raise RuntimeError(f"silent.mp4 사라짐 (예상 경로: {video_silent})")
    shutil.move(video_silent, out)
    return str(out)
