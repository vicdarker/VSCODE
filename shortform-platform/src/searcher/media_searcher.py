"""
미디어 검색 및 다운로드 (PIL 그래픽 제거 — 항상 실제 영상/사진 확보)

Fallback 체인:
  VIDEO 요청:  yt-dlp → Pexels video → Pixabay video → Pexels photo → Pixabay photo
  PHOTO 요청:  Pixabay photo → Pexels photo → Pixabay video → Pexels video
"""

import os
import re
import subprocess
import threading
import urllib.request
import urllib.parse
import json
from pathlib import Path


class UsedMediaSet:
    """job 전체에서 이미 사용된 미디어 id(유튜브 videoId / 스톡 url)를 공유 — 중복 방지."""
    def __init__(self):
        self._ids: set[str] = set()
        self._lock = threading.Lock()

    def try_reserve(self, mid: str) -> bool:
        if not mid:
            return True
        with self._lock:
            if mid in self._ids:
                return False
            self._ids.add(mid)
            return True

    def release(self, mid: str):
        if not mid:
            return
        with self._lock:
            self._ids.discard(mid)


# 한국어 조사/어미 (뒤에서 벗겨내기용). 긴 것부터 시도.
_KO_JOSAS = sorted([
    "으로써", "으로서", "에서는", "에게는", "이라고", "라고", "이라는", "라는",
    "으로", "에서", "에게", "한테", "부터", "까지", "이다", "입니다", "이며", "였다",
    "했다", "하는", "하며", "되는", "되어", "됐다", "라며", "라는",
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만", "로",
    "나", "야", "고",
], key=len, reverse=True)

# 너무 일반적이라 관련성 평가에 도움 안 되는 단어 (한글)
_KO_STOPWORDS = {
    # 지시/부사
    "이런", "그런", "저런", "있다", "없다", "하지만", "그런데", "그리고", "이제",
    "오늘", "내일", "어제", "처음", "마지막", "이번", "지난", "현재", "당시", "최근",
    "때문", "위해", "통해", "대해", "관련", "이상", "이하", "정도", "사실", "모두",
    "것이", "것을", "것은", "그것", "이것", "저것", "이걸", "저걸",
    # 뉴스 일반 어휘 (어떤 뉴스에나 붙는 단어 — 변별력 0)
    "뉴스", "사건", "상황", "결과", "문제", "방송", "보도", "소식", "기사", "영상",
    "경찰", "검찰", "수사", "조사", "발생", "발표", "특정", "확인", "공개", "공표",
    "논란", "파문", "의혹", "제기", "진행", "마무리", "발견", "체포", "구속", "기소",
    "판결", "법원", "처벌", "혐의", "피해", "가해", "피해자", "가해자", "피의자",
    "용의자", "범행", "범죄", "부상", "사망", "증언",
}


def _strip_ko_josa(word: str) -> str:
    for j in _KO_JOSAS:
        if word.endswith(j) and len(word) - len(j) >= 2:
            return word[: -len(j)]
    return word


def _ref_terms(caption: str, limit: int = 20) -> list[str]:
    """caption → 제목 매칭용 키 토큰. josa 제거, 스톱워드 컷, 상위 limit개."""
    if not caption:
        return []
    tokens = re.findall(r"[\w가-힣]+", caption)
    out = []
    seen = set()
    for t in tokens:
        has_kor = any("\uac00" <= ch <= "\ud7a3" for ch in t)
        if has_kor and len(t) >= 2:
            key = _strip_ko_josa(t)
            if len(key) < 2 or key in _KO_STOPWORDS:
                continue
        elif t.isdigit() and len(t) >= 2:
            key = t
        elif t.isascii() and t.isalpha() and len(t) >= 3:
            key = t.lower()
            if key in {"the", "and", "for", "with", "this", "that", "news"}:
                continue
        else:
            continue
        if key not in seen:
            seen.add(key)
            out.append(key)
        if len(out) >= limit:
            break
    return out


def _title_score(title: str, ref_terms: list[str]) -> int:
    if not title or not ref_terms:
        return 0
    t = title.lower()
    return sum(1 for w in ref_terms if w.lower() in t)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
# Pexels는 Mozilla UA를 차단 — 간단한 UA 사용
_PEXELS_HEADERS_BASE = {"User-Agent": "shortform-platform/1.0", "Accept": "*/*"}

PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")


# 샷 타입별 영어/한글 키워드 보강
_SHOT_MOD_EN = {
    "wide": "wide shot aerial",
    "close-up": "close up face detail",
    "chart": "stock chart graph financial",
    "portrait": "portrait person formal",
    "b-roll": "b-roll footage background",
}
_SHOT_MOD_KO = {
    "wide": "전경",
    "close-up": "클로즈업",
    "chart": "차트 그래프",
    "portrait": "인물",
    "b-roll": "현장 영상",
}


def fetch_media(
    media_type: str,
    keyword: str,
    output_dir: str,
    filename: str,
    duration: float = 4.0,
    graphic_style: str = "dark_navy",
    keyword_ko: str = "",    # 한국 뉴스 유튜브 검색용 한글 키워드
    shot_type: str = "",     # wide | close-up | chart | portrait | b-roll
    used_ids: UsedMediaSet | None = None,   # job 공유 — 세그먼트 간 중복 방지
    ref_caption: str = "",                  # 제목 관련성 스코어링용
    ref_title: str = "",                    # 뉴스 전체 제목 — 고유명사 추출원
) -> str:
    """
    미디어를 검색/생성하고 영상 파일 경로를 반환.
    실패 시 여러 소스 fallback. 모든 출력은 mp4.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    kw_en = keyword or "news concept"
    kw_ko = keyword_ko or keyword  # 한글 없으면 영어로 fallback
    # 샷 타입으로 키워드 보강 (검색 품질 향상)
    if shot_type and shot_type in _SHOT_MOD_EN:
        kw_en = f"{kw_en} {_SHOT_MOD_EN[shot_type]}"
        kw_ko = f"{kw_ko} {_SHOT_MOD_KO[shot_type]}"

    # 필수 포함어 = 뉴스 제목의 고유명사 (있으면)
    must_terms = _ref_terms(ref_title)
    caption_terms = _ref_terms(ref_caption)
    # 합치기 (중복 제거)
    ref_terms = list(must_terms)
    for t in caption_terms:
        if t not in ref_terms:
            ref_terms.append(t)

    def yt_fn(k, o, f, d):
        return _fetch_yt_video(
            kw_ko, o, f, d,
            used_ids=used_ids, ref_terms=ref_terms, must_terms=must_terms,
        )

    def _wrap(fn):
        def _inner(k, o, f, d):
            return fn(k, o, f, d, used_ids=used_ids, ref_terms=ref_terms)
        return _inner

    pexels_v = _wrap(_fetch_pexels_video)
    pexels_p = _wrap(_fetch_pexels_photo)
    pixabay_v = _wrap(_fetch_pixabay_video)
    pixabay_p = _wrap(_fetch_pixabay_photo)

    if media_type == "video":
        chain = [
            ("yt-dlp(KR)", yt_fn),
            ("pexels-video", pexels_v),
            ("pixabay-video", pixabay_v),
            ("pexels-photo", pexels_p),
            ("pixabay-photo", pixabay_p),
        ]
    else:  # photo
        chain = [
            ("yt-dlp(KR)", yt_fn),
            ("pexels-video", pexels_v),
            ("pixabay-photo", pixabay_p),
            ("pexels-photo", pexels_p),
            ("pixabay-video", pixabay_v),
        ]

    for source_name, fn in chain:
        try:
            kw_use = kw_ko if source_name.startswith("yt-dlp") else kw_en
            result = fn(kw_use, out, filename, duration)
            if result:
                print(f"  [{filename}] {source_name}: OK ({kw_use})")
                return result
        except Exception as e:
            print(f"  [{filename}] {source_name} 실패: {e}")
            continue

    # 모든 소스 실패: 최소한 검정 화면이라도 반환 (PIL 그래픽 아님)
    print(f"  [{filename}] 모든 소스 실패 — 검정 영상 생성")
    return _make_black_fallback(out / f"{filename}.mp4", duration)


# ── yt-dlp 비디오 (뉴스 채널 우선 + 품질 필터 + 다단계 fallback) ───────────────

# 뉴스 키워드 보강: 영어 금융/정치 뉴스 채널 계열로 편향
_NEWS_SEARCH_BOOSTS = ["news", "news footage", "b-roll news"]


def _yt_list_candidates(query: str) -> list[dict]:
    """ytsearch 쿼리에서 후보 메타데이터 나열 (다운로드 안 함)."""
    cmd = [
        "yt-dlp", query,
        "--flat-playlist",
        "--print", "%(id)s|%(title)s|%(duration)s|%(view_count)s",
        "--no-warnings",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=web_safari,web",
    ]
    try:
        r = subprocess.run(cmd, check=True, capture_output=True, timeout=45, text=True)
    except Exception as e:
        print(f"  yt-list 실패 [{query}]: {e}")
        return []
    cands = []
    for line in r.stdout.splitlines():
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        vid, title, dur_s, vc_s = parts
        try:
            dur = float(dur_s) if dur_s and dur_s != "NA" else 0.0
        except ValueError:
            dur = 0.0
        try:
            vc = int(vc_s) if vc_s and vc_s != "NA" else 0
        except ValueError:
            vc = 0
        cands.append({"id": vid, "title": title or "", "dur": dur, "vc": vc})
    return cands


def _yt_download_by_id(video_id: str, out: Path, filename: str, duration: float) -> str | None:
    raw_name = f"{filename}_raw"
    template = str(out / f"{raw_name}.%(ext)s")
    clip_sec = max(15, int(duration) + 6)
    skip = 3
    cmd = [
        "yt-dlp",
        f"https://www.youtube.com/watch?v={video_id}",
        "-f", "mp4[height<=720]/best[height<=720]/best",
        "--no-playlist",
        "-o", template,
        "--merge-output-format", "mp4",
        "--download-sections", f"*{skip}-{clip_sec + skip}",
        "--max-filesize", "30m",
        "--no-warnings",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=web_safari,web",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=90)
    except Exception:
        for f in out.glob(f"{raw_name}.*"):
            f.unlink(missing_ok=True)
        return None

    raw = None
    for f in out.glob(f"{raw_name}.*"):
        if f.suffix in (".mp4", ".mkv", ".webm") and f.stat().st_size > 10_000:
            raw = f
            break
    if not raw:
        return None

    mp4 = out / f"{filename}.mp4"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(raw),
            "-vf", "scale='if(gt(iw,ih),-2,1280)':'if(gt(iw,ih),1280,-2)',"
                   "pad='ceil(iw/2)*2':'ceil(ih/2)*2',setsar=1",
            "-t", str(max(15, duration + 6)),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-an",
            str(mp4),
        ], capture_output=True, check=True)
        raw.unlink(missing_ok=True)
        if mp4.exists() and mp4.stat().st_size > 10_000:
            return str(mp4)
    except Exception:
        for f in out.glob(f"{raw_name}.*"):
            f.unlink(missing_ok=True)
    return None


def _is_korean(text: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in text)


def _fetch_yt_video(
    keyword: str, out: Path, filename: str, duration: float,
    used_ids: UsedMediaSet | None = None,
    ref_terms: list[str] | None = None,
    must_terms: list[str] | None = None,
) -> str | None:
    """
    YouTube 검색 → 후보 나열 → (1) 필수 고유명사 포함 필터 → (2) 제목 관련성 점수 → 다운로드.
      must_terms: 뉴스 제목에서 뽑은 고유명사 — 후보 제목에 1개 이상 들어 있어야 통과
      ref_terms:  전체 키 토큰 (must + caption) — 랭킹 점수
    """
    ref_terms = ref_terms or []
    must_terms = must_terms or []
    if _is_korean(keyword):
        queries = [
            f"ytsearch10:{keyword} 뉴스",
            f"ytsearch10:YTN {keyword}",
            f"ytsearch10:JTBC {keyword}",
            f"ytsearch10:연합뉴스TV {keyword}",
            f"ytsearch10:MBN {keyword}",
            f"ytsearch10:KBS뉴스 {keyword}",
            f"ytsearch10:{keyword}",
        ]
    else:
        queries = [
            f"ytsearch10:{keyword} news",
            f"ytsearch10:{keyword}",
        ]

    # 후보 수집 (id 중복 제거)
    seen: dict[str, dict] = {}
    for q in queries:
        for c in _yt_list_candidates(q):
            vid = c["id"]
            if not vid or vid in seen:
                continue
            if c["dur"] and c["dur"] < 15:
                continue
            c["score"] = _title_score(c["title"], ref_terms)
            c["must_hit"] = _title_score(c["title"], must_terms) if must_terms else 1
            seen[vid] = c

    if not seen:
        return None

    # 1차 필터: must_terms 개수에 따라 최소 매칭 수 adaptive 적용
    # must가 풍부하면 1개만 맞는 건 약함 — 2개 이상 요구
    if must_terms:
        threshold = 2 if len(must_terms) >= 6 else 1
        strict = [c for c in seen.values() if c["must_hit"] >= threshold]
        if not strict:
            sample = sorted(seen.values(), key=lambda c: -c["must_hit"])[0]
            print(f"  [yt] must_hit<{threshold} 전부 탈락 "
                  f"(must={must_terms[:5]}, best='{sample['title'][:40]}' hit={sample['must_hit']})")
            return None
        pool = strict
    else:
        pool = list(seen.values())

    # 2차 랭킹: 점수 desc → 조회수 desc
    ranked = sorted(pool, key=lambda c: (-c["score"], -c["vc"]))

    # 상위 5개 다운로드 시도
    for c in ranked[:5]:
        vid = c["id"]
        if used_ids and not used_ids.try_reserve(vid):
            continue
        result = _yt_download_by_id(vid, out, filename, duration)
        if result:
            print(f"  [yt] '{c['title'][:50]}' (score={c['score']}, must={c['must_hit']}, views={c['vc']})")
            return result
        if used_ids:
            used_ids.release(vid)
    return None


# ── Pixabay 사진 ─────────────────────────────────────────────────────────────

def _keyword_variants(keyword: str) -> list[str]:
    words = keyword.split()
    variants = [keyword]
    if len(words) > 3:
        variants.append(" ".join(words[:3]))
    if len(words) > 2:
        variants.append(" ".join(words[:2]))
    if len(words) > 1:
        variants.append(words[0])
    # 중복 제거, 순서 유지
    seen = set()
    return [v for v in variants if not (v in seen or seen.add(v))]


def _rank_stock_hits(hits: list[dict], title_keys: tuple[str, ...],
                     ref_terms: list[str]) -> list[dict]:
    """스톡 API hit 배열을 (태그·제목 관련도, 원래 순서)로 정렬."""
    scored = []
    for idx, h in enumerate(hits):
        blob = " ".join(str(h.get(k, "")) for k in title_keys)
        scored.append((-_title_score(blob, ref_terms), idx, h))
    scored.sort()
    return [h for _, _, h in scored]


def _fetch_pixabay_photo(keyword: str, out: Path, filename: str, duration: float,
                         used_ids: UsedMediaSet | None = None,
                         ref_terms: list[str] | None = None) -> str | None:
    if not PIXABAY_KEY:
        return None
    for q_str in _keyword_variants(keyword):
        try:
            q = urllib.parse.quote(q_str)
            api_url = (
                f"https://pixabay.com/api/?key={PIXABAY_KEY}"
                f"&q={q}&image_type=photo&min_width=500&per_page=15&safesearch=true"
            )
            req = urllib.request.Request(api_url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            hits = data.get("hits", [])
            if not hits:
                continue
            hits = _rank_stock_hits(hits, ("tags",), ref_terms or [])
            for h in hits:
                hid = f"pixabay-photo-{h.get('id', '')}"
                if used_ids and not used_ids.try_reserve(hid):
                    continue
                img_url = h.get("webformatURL") or h.get("largeImageURL")
                if not img_url:
                    if used_ids:
                        used_ids.release(hid)
                    continue
                try:
                    img_path = out / f"{filename}.jpg"
                    req2 = urllib.request.Request(img_url, headers=_HEADERS)
                    with urllib.request.urlopen(req2, timeout=15) as resp2:
                        img_path.write_bytes(resp2.read())
                    return _image_to_video(str(img_path), out / f"{filename}.mp4", duration)
                except Exception:
                    if used_ids:
                        used_ids.release(hid)
                    continue
        except Exception:
            continue
    return None


# ── Pixabay 동영상 ───────────────────────────────────────────────────────────

def _fetch_pixabay_video(keyword: str, out: Path, filename: str, duration: float,
                         used_ids: UsedMediaSet | None = None,
                         ref_terms: list[str] | None = None) -> str | None:
    if not PIXABAY_KEY:
        return None
    for q_str in _keyword_variants(keyword):
        try:
            q = urllib.parse.quote(q_str)
            api_url = (
                f"https://pixabay.com/api/videos/?key={PIXABAY_KEY}"
                f"&q={q}&per_page=15&safesearch=true"
            )
            req = urllib.request.Request(api_url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            hits = data.get("hits", [])
            if not hits:
                continue
            hits = _rank_stock_hits(hits, ("tags",), ref_terms or [])
            for h in hits:
                hid = f"pixabay-video-{h.get('id', '')}"
                if used_ids and not used_ids.try_reserve(hid):
                    continue
                videos = h.get("videos", {})
                vid_url = (videos.get("medium") or videos.get("small") or {}).get("url")
                if not vid_url:
                    if used_ids:
                        used_ids.release(hid)
                    continue
                try:
                    return _download_and_crop_video(vid_url, out, filename, duration)
                except Exception:
                    if used_ids:
                        used_ids.release(hid)
                    continue
        except Exception:
            continue
    return None


# ── Pexels 사진 ──────────────────────────────────────────────────────────────

def _fetch_pexels_photo(keyword: str, out: Path, filename: str, duration: float,
                        used_ids: UsedMediaSet | None = None,
                        ref_terms: list[str] | None = None) -> str | None:
    if not PEXELS_KEY:
        return None
    for q_str in _keyword_variants(keyword):
        try:
            q = urllib.parse.quote(q_str)
            api_url = f"https://api.pexels.com/v1/search?query={q}&per_page=15"
            req = urllib.request.Request(api_url, headers={**_PEXELS_HEADERS_BASE, "Authorization": PEXELS_KEY})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            photos = data.get("photos", [])
            if not photos:
                continue
            photos = _rank_stock_hits(photos, ("alt", "url"), ref_terms or [])
            for p in photos:
                hid = f"pexels-photo-{p.get('id', '')}"
                if used_ids and not used_ids.try_reserve(hid):
                    continue
                img_url = p.get("src", {}).get("large") or p.get("src", {}).get("original")
                if not img_url:
                    if used_ids:
                        used_ids.release(hid)
                    continue
                try:
                    img_path = out / f"{filename}.jpg"
                    req2 = urllib.request.Request(img_url, headers=_HEADERS)
                    with urllib.request.urlopen(req2, timeout=15) as resp2:
                        img_path.write_bytes(resp2.read())
                    return _image_to_video(str(img_path), out / f"{filename}.mp4", duration)
                except Exception:
                    if used_ids:
                        used_ids.release(hid)
                    continue
        except Exception:
            continue
    return None


# ── Pexels 동영상 ────────────────────────────────────────────────────────────

def _fetch_pexels_video(keyword: str, out: Path, filename: str, duration: float,
                        used_ids: UsedMediaSet | None = None,
                        ref_terms: list[str] | None = None) -> str | None:
    if not PEXELS_KEY:
        return None
    for q_str in _keyword_variants(keyword):
        try:
            q = urllib.parse.quote(q_str)
            api_url = f"https://api.pexels.com/videos/search?query={q}&per_page=15"
            req = urllib.request.Request(api_url, headers={**_PEXELS_HEADERS_BASE, "Authorization": PEXELS_KEY})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            vids = data.get("videos", [])
            if not vids:
                continue
            vids = _rank_stock_hits(vids, ("url", "user", "tags"), ref_terms or [])
            for v in vids:
                hid = f"pexels-video-{v.get('id', '')}"
                if used_ids and not used_ids.try_reserve(hid):
                    continue
                files = v.get("video_files", [])
                files_sorted = sorted(files, key=lambda f: abs(f.get("height", 0) - 720))
                if not files_sorted:
                    if used_ids:
                        used_ids.release(hid)
                    continue
                vid_url = files_sorted[0].get("link")
                if not vid_url:
                    if used_ids:
                        used_ids.release(hid)
                    continue
                try:
                    return _download_and_crop_video(vid_url, out, filename, duration)
                except Exception:
                    if used_ids:
                        used_ids.release(hid)
                    continue
        except Exception:
            continue
    return None


# ── 공용 유틸 ────────────────────────────────────────────────────────────────

def _download_and_crop_video(url: str, out: Path, filename: str, duration: float) -> str | None:
    raw = out / f"{filename}_src.mp4"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw.write_bytes(resp.read())
    if not raw.exists() or raw.stat().st_size < 10_000:
        return None
    mp4 = out / f"{filename}.mp4"
    # 최소 15초 확보 (TTS가 예상보다 길어질 가능성 대비)
    target_dur = max(15, duration + 6)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw),
        "-vf", "scale='if(gt(iw,ih),-2,1280)':'if(gt(iw,ih),1280,-2)',"
               "pad='ceil(iw/2)*2':'ceil(ih/2)*2',setsar=1",
        "-t", str(target_dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-an",
        str(mp4),
    ], capture_output=True, check=True)
    raw.unlink(missing_ok=True)
    if mp4.exists() and mp4.stat().st_size > 10_000:
        return str(mp4)
    return None


def _image_to_video(image_path: str, output_path: Path, duration: float) -> str:
    """사진 → 영상. 원본 비율 유지, 큰 해상도로 뽑아 렌더러가 최종 크기 결정."""
    # 최소 15초 확보 (TTS 길어질 때 대응)
    target_dur = max(15, duration + 6)
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-t", str(target_dur),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-vf", "scale='if(gt(iw,ih),-2,1280)':'if(gt(iw,ih),1280,-2)',"
               "pad='ceil(iw/2)*2':'ceil(ih/2)*2',setsar=1",
        str(output_path),
    ], capture_output=True, check=True)
    return str(output_path)


def _make_black_fallback(output_path: Path, duration: float) -> str:
    """최후 수단: 검정 영상 (PIL 그래픽 아님 — 단순 검정)"""
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=black:s=1080x1920:r=30:d={duration}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ], capture_output=True, check=True)
    return str(output_path)
