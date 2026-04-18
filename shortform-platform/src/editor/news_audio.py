"""
뉴스 숏츠 오디오 처리: TTS + BGM + SFX 믹싱
"""

import os
import subprocess
from pathlib import Path

# 환경변수
_OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
_GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# BGM/SFX 자산 디렉토리 (있으면 사용)
_ASSETS = Path(os.environ.get("NEWS_AUDIO_ASSETS", "/app/assets/news_audio"))
_BGM_DEFAULT = _ASSETS / "bgm_default.mp3"
_SFX_WHOOSH = _ASSETS / "sfx_whoosh.mp3"
_SFX_IMPACT = _ASSETS / "sfx_impact.mp3"
_SFX_DING = _ASSETS / "sfx_ding.mp3"


def tts_korean(text: str, out_path: str, voice: str = "nova",
               provider: str = "edge",
               edge_voice: str = "ko-KR-SunHiNeural",
               gemini_voice: str = "Kore") -> str | None:
    """
    한국어 TTS.
    provider:
      edge   (기본, 무료/무제한)
      openai (저렴, 크레딧 필요)
      gemini (무료 티어 하루 15회 제한)
    실패 시 자동으로 Edge로 fallback (최소 실패율 보장).
    """
    if not text.strip():
        return None

    # 지정 provider 먼저 시도
    if provider == "openai":
        r = _tts_openai(text, out_path, voice)
        if r:
            return r
        print(f"  [TTS] OpenAI 실패 → Edge로 fallback")
    elif provider == "gemini":
        r = _tts_gemini(text, out_path, gemini_voice)
        if r:
            return r
        print(f"  [TTS] Gemini 실패 → Edge로 fallback")

    # 기본값/최종 fallback: Edge TTS
    return _tts_edge(text, out_path, edge_voice)


def _tts_edge(text: str, out_path: str, voice: str = "ko-KR-SunHiNeural") -> str | None:
    """Microsoft Edge TTS 무료 사용. 한국어 음성: SunHi(여), InJoon(남), HyunsuMultilingual"""
    try:
        import asyncio
        import edge_tts
        async def _run():
            communicate = edge_tts.Communicate(
                text, voice,
                rate="+20%",   # 숏츠용 약간 빠르게
                volume="+0%",
            )
            await communicate.save(out_path)
        asyncio.run(_run())
        if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
            return out_path
    except Exception as e:
        print(f"  edge-tts 실패: {e}")
    return None


def _tts_gemini(text: str, out_path: str, voice_name: str = "Kore") -> str | None:
    """
    Google Gemini 2.5 Flash TTS (무료 티어).
    voice_name: Kore(한국적 중립) | Aoede(여, 따뜻) | Puck(남, 활기) | Charon(남, 차분)
                Zephyr(여, 밝음) | Fenrir(남, 깊음) 등 30+ 목소리
    출력: wav(PCM 24kHz) → ffmpeg로 mp3 변환
    """
    if not _GEMINI_KEY:
        return None
    try:
        from google import genai
        from google.genai import types
        import base64, wave, subprocess

        client = genai.Client(api_key=_GEMINI_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name,
                        ),
                    ),
                ),
            ),
        )
        # 응답 파싱: inline_data.data는 base64 인코딩된 PCM
        part = response.candidates[0].content.parts[0]
        pcm_data = part.inline_data.data  # bytes
        if isinstance(pcm_data, str):
            pcm_data = base64.b64decode(pcm_data)

        # PCM → WAV → MP3
        tmp_wav = out_path.replace(".mp3", ".wav")
        with wave.open(tmp_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm_data)

        subprocess.run([
            "ffmpeg", "-y", "-i", tmp_wav,
            "-c:a", "libmp3lame", "-q:a", "3",
            out_path,
        ], capture_output=True, check=True)
        os.unlink(tmp_wav)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
            return out_path
    except Exception as e:
        print(f"  Gemini TTS 실패: {e}")
    return None


def _tts_openai(text: str, out_path: str, voice: str = "nova") -> str | None:
    if not _OPENAI_KEY:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=_OPENAI_KEY)
        response = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
            speed=1.1,
        )
        with open(out_path, "wb") as f:
            f.write(response.content)
        return out_path
    except Exception as e:
        print(f"  OpenAI TTS 실패: {e}")
        return None


def generate_tts_for_segments(segments, work_dir: Path, provider: str = "edge",
                               edge_voice: str = "ko-KR-SunHiNeural") -> list[str | None]:
    """각 세그먼트 caption을 TTS로 병렬 생성. 실패한 세그먼트는 None.

    이미 `_tts_file`이 있는 세그먼트는 재사용 (worker에서 사전 생성 시 활용).
    """
    # 사전 생성된 TTS 재사용
    if all(getattr(s, "_tts_file", None) for s in segments):
        return [s._tts_file for s in segments]
    # edge-tts는 asyncio 네이티브 → async batch
    if provider == "edge":
        return _generate_tts_edge_batch(segments, work_dir, edge_voice)
    # Gemini/OpenAI는 ThreadPoolExecutor (동기 SDK)
    from concurrent.futures import ThreadPoolExecutor
    results = [None] * len(segments)

    def _one(idx_seg):
        idx, seg = idx_seg
        text = seg.caption or ""
        if not text:
            return idx, None
        out = str(work_dir / f"tts_{idx:02d}.mp3")
        return idx, tts_korean(text, out, provider=provider, edge_voice=edge_voice)

    with ThreadPoolExecutor(max_workers=5) as ex:
        for idx, r in ex.map(_one, enumerate(segments)):
            results[idx] = r
    return results


def _generate_tts_edge_batch(segments, work_dir: Path, voice: str) -> list[str | None]:
    """Edge TTS 병렬 생성 (asyncio) + 단어별 타임스탬프 json 저장."""
    import asyncio
    import edge_tts
    import json as _json

    async def _one(idx, seg):
        text = (seg.caption or "").strip()
        if not text:
            return idx, None
        out_mp3 = str(work_dir / f"tts_{idx:02d}.mp3")
        out_json = str(work_dir / f"tts_{idx:02d}_words.json")
        try:
            communicate = edge_tts.Communicate(text, voice, rate="+20%")
            words = []  # [{text, offset_ms, duration_ms}]
            with open(out_mp3, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append({
                            "text": chunk["text"],
                            "offset_ms": chunk["offset"] / 10000,  # 100ns → ms
                            "duration_ms": chunk["duration"] / 10000,
                        })
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 500:
                with open(out_json, "w", encoding="utf-8") as f:
                    _json.dump(words, f, ensure_ascii=False)
                return idx, out_mp3
        except Exception as e:
            print(f"  [TTS {idx}] 실패: {e}")
        return idx, None

    async def _all():
        return await asyncio.gather(*[_one(i, s) for i, s in enumerate(segments)])

    results = [None] * len(segments)
    try:
        pairs = asyncio.run(_all())
        for idx, path in pairs:
            results[idx] = path
    except Exception as e:
        print(f"  TTS batch 실패: {e}")
    return results


def get_word_timings(tts_mp3_path: str) -> list[dict]:
    """TTS mp3에 대응하는 단어 타임스탬프 json 로드. 없으면 빈 리스트."""
    import json as _json
    json_path = tts_mp3_path.replace(".mp3", "_words.json")
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return []


def compute_chunk_timings(chunks: list[str], words: list[dict],
                           seg_duration: float) -> list[tuple[float, float]]:
    """
    각 자막 청크가 화면에 표시될 (start, end) 초 단위 반환.
    1) 단어 타임스탬프 있으면: 청크의 첫 단어 시작~다음 청크 첫 단어 직전
    2) 없으면: 글자 수 비례 분배
    """
    if not chunks:
        return []
    n = len(chunks)

    if words:
        # 단어 타임스탬프 기반 — 각 청크의 첫 단어 위치 찾기
        word_texts = [w["text"] for w in words]
        chunk_start_times = []
        search_from = 0
        for c in chunks:
            # 청크의 첫 번째 "단어-스러운" 토큰
            c_tokens = c.strip().split()
            if not c_tokens:
                chunk_start_times.append(None)
                continue
            first_tok = c_tokens[0]
            # 뒤에서부터 검색 (이미 찾은 위치 이후)
            found = -1
            for j in range(search_from, len(word_texts)):
                # 부분 일치 허용 (구두점 차이)
                if first_tok in word_texts[j] or word_texts[j] in first_tok:
                    found = j
                    break
            if found >= 0:
                chunk_start_times.append(words[found]["offset_ms"] / 1000.0)
                search_from = found + 1
            else:
                chunk_start_times.append(None)

        # None인 항목은 이전/다음 기준으로 보간
        if chunk_start_times[0] is None:
            chunk_start_times[0] = 0.0
        for i in range(1, n):
            if chunk_start_times[i] is None:
                # 이전 + (남은 시간 / 남은 청크 수) 로 보간
                remaining_chunks = n - i
                chunk_start_times[i] = chunk_start_times[i - 1] + (
                    (seg_duration - chunk_start_times[i - 1]) / remaining_chunks
                )

        timings = []
        for i in range(n):
            end = chunk_start_times[i + 1] if i + 1 < n else seg_duration
            timings.append((chunk_start_times[i], end))
        return timings

    # Fallback: 글자 수 비례
    total_chars = sum(len(c) for c in chunks) or 1
    timings = []
    cum = 0.0
    for c in chunks:
        dur = seg_duration * len(c) / total_chars
        timings.append((cum, cum + dur))
        cum += dur
    # 마지막은 seg_duration까지 확장
    if timings:
        timings[-1] = (timings[-1][0], seg_duration)
    return timings


def get_audio_duration(path: str) -> float:
    """ffprobe로 오디오 길이 (초)"""
    try:
        out = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", path,
        ], capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def mix_audio_into_video(
    video_path: str,
    tts_files: list[str | None],
    tts_offsets: list[float],
    total_duration: float,
    out_path: str,
    bgm_path: str | None = None,
    bgm_volume: float = 0.15,   # 배경음 15% 볼륨
    tts_volume: float = 1.0,
) -> str:
    """TTS 파일들을 타임라인 위치에 배치하고 BGM과 믹스"""
    inputs = ["-i", video_path]

    # TTS 입력들
    tts_inputs_count = 0
    tts_filter_parts = []
    for i, (tts, offset) in enumerate(zip(tts_files, tts_offsets)):
        if tts and os.path.exists(tts):
            inputs.extend(["-i", tts])
            idx = 1 + tts_inputs_count
            tts_inputs_count += 1
            # 각 TTS를 해당 offset에 배치
            tts_filter_parts.append(
                f"[{idx}:a]adelay={int(offset*1000)}|{int(offset*1000)},"
                f"volume={tts_volume}[a_tts_{idx}]"
            )

    # BGM 입력
    bgm_idx = None
    if bgm_path and os.path.exists(bgm_path):
        inputs.extend(["-i", bgm_path])
        bgm_idx = 1 + tts_inputs_count
        tts_filter_parts.append(
            f"[{bgm_idx}:a]aloop=loop=-1:size=2e+09,"
            f"atrim=0:{total_duration},"
            f"volume={bgm_volume}[a_bgm]"
        )

    # 전부 믹스
    mix_labels = [f"[a_tts_{1+i}]" for i in range(tts_inputs_count)]
    if bgm_idx is not None:
        mix_labels.append("[a_bgm]")

    if not mix_labels:
        # 오디오 소스 없음 → 원본 복사
        return video_path

    mix_inputs = "".join(mix_labels)
    tts_filter_parts.append(
        f"{mix_inputs}amix=inputs={len(mix_labels)}:duration=longest:dropout_transition=0[aout]"
    )

    filter_complex = ";".join(tts_filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return out_path


# ── 자산 파일 헬퍼 ────────────────────────────────────────────────────────────

def default_bgm() -> str | None:
    return str(_BGM_DEFAULT) if _BGM_DEFAULT.exists() else None


def sfx_whoosh() -> str | None:
    return str(_SFX_WHOOSH) if _SFX_WHOOSH.exists() else None


def sfx_impact() -> str | None:
    return str(_SFX_IMPACT) if _SFX_IMPACT.exists() else None


def sfx_ding() -> str | None:
    return str(_SFX_DING) if _SFX_DING.exists() else None
