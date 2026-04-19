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


# ── 저작권 안전 유튜브 채널 화이트리스트 ──
# uploader 문자열에 각 key가 포함되면 그 라이선스 규칙 적용.
# 민간 방송사(YTN·JTBC·KBS 등)는 저작권 보호 → 사용 금지.
YT_SAFE_CHANNELS: dict[str, dict] = {
    "KTV":          {"credit": "출처: KTV", "license": "공공누리 1유형"},
    "국민방송":      {"credit": "출처: KTV", "license": "공공누리 1유형"},
    "국회방송":      {"credit": "출처: 국회방송", "license": "공공저작물"},
    "NATV":         {"credit": "출처: 국회방송", "license": "공공저작물"},
    "VOA":          {"credit": "출처: VOA", "license": "US Federal / Public Domain"},
    "한국정책방송":   {"credit": "출처: KTV", "license": "공공누리 1유형"},
    "NASA":         {"credit": "출처: NASA", "license": "Public Domain"},
    "WhiteHouse":   {"credit": "출처: 백악관", "license": "US Federal / Public Domain"},
    "UnitedNations":{"credit": "출처: 유엔", "license": "CC BY 3.0 IGO"},
}


def _match_safe_channel(uploader: str) -> dict | None:
    """uploader 문자열이 화이트리스트 어느 항목이라도 포함하면 해당 메타 반환."""
    if not uploader:
        return None
    u = uploader.replace(" ", "")
    for key, meta in YT_SAFE_CHANNELS.items():
        if key.replace(" ", "") in u:
            return meta
    return None


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
    subject_name: str = "",                 # 핵심 인물·기관 (Wikimedia 검색용)
    news_og_image: str | None = None,       # 원문 페이지 og:image URL (있으면 폴백)
    article_pool: "ArticleImagePool | None" = None,  # 기사 본문 이미지 풀 (per-job)
    enable_ai_image: bool = False,          # AI 이미지 생성 (DALL-E 3) — UI 토글
) -> tuple[str | None, str | None]:
    """
    미디어를 검색/생성하고 (영상 파일 경로, 출처 크레딧) 튜플 반환.
    실패 시 여러 소스 fallback. 모든 출력은 mp4.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    kw_en = keyword or "news concept"
    kw_ko = keyword_ko or keyword  # 한글 없으면 영어로 fallback
    subject = (subject_name or "").strip()
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
    # subject_name도 ref_terms 맨 앞에 — 안전 채널 매칭률 ↑
    if subject and subject not in ref_terms:
        ref_terms.insert(0, subject)

    def yt_fn(k, o, f, d):
        return _fetch_yt_video(
            kw_ko, o, f, d,
            used_ids=used_ids, ref_terms=ref_terms, must_terms=must_terms,
        )

    def _wrap(fn):
        def _inner(k, o, f, d):
            r = fn(k, o, f, d, used_ids=used_ids, ref_terms=ref_terms)
            return (r, None) if r else (None, None)
        return _inner

    pexels_v = _wrap(_fetch_pexels_video)
    pexels_p = _wrap(_fetch_pexels_photo)
    pixabay_v = _wrap(_fetch_pixabay_video)
    pixabay_p = _wrap(_fetch_pixabay_photo)

    def wiki_fn(k, o, f, d):
        # subject 있을 때만 호출됨. context = 뉴스 제목 + 캡션(동명이인 disambiguation)
        ctx = (ref_title or "") + " " + (ref_caption or "")
        return _fetch_wikimedia_image(subject, o, f, d, used_ids=used_ids, context=ctx)

    def og_fn(k, o, f, d):
        if not news_og_image:
            return None, None
        return _fetch_og_image(news_og_image, o, f, d, used_ids=used_ids)

    def article_fn(k, o, f, d):
        """기사 본문 이미지 풀에서 1장 take. 비면 (None, None)."""
        if not article_pool:
            return None, None
        u = article_pool.take()
        if not u:
            return None, None
        return _fetch_og_image(u, o, f, d, used_ids=used_ids)

    def wiki_commons_fn(k, o, f, d):
        """Wikimedia Commons 키워드 검색 (인물 외 사물·장소·이벤트)."""
        return _fetch_wikimedia_commons(k, o, f, d, used_ids=used_ids)

    def ai_fn(k, o, f, d):
        if not enable_ai_image:
            return None, None
        return _fetch_ai_generated_image(k, kw_ko, o, f, d, used_ids=used_ids)

    # ── 체인 구성 (관련성 높은 순) ──
    # 공통 1순위: 기사 본문 이미지 (한국 뉴스 정확 매칭 핵심)
    # subject 있으면: Wikimedia 인물 → 본문 → og → safe channel → Commons → AI → 스톡
    # subject 없으면: 본문 → og → safe channel → Commons → AI → 스톡
    chain: list[tuple[str, callable]] = []
    if subject:
        chain.append(("wikimedia(person)", wiki_fn))
    if article_pool:
        chain.append(("article-img", article_fn))
    if news_og_image:
        chain.append(("og:image", og_fn))
    chain.append(("yt-dlp(safe)", yt_fn))
    chain.append(("wikimedia(commons)", wiki_commons_fn))
    if enable_ai_image:
        chain.append(("ai-gen", ai_fn))
    if subject:
        # 스톡 폴백은 "장면 b-roll"로 — 인물 단어 제거
        kw_en_scene = _strip_subject_from_keyword(kw_en, subject)
        def pexels_scene(k, o, f, d):
            return _wrap(_fetch_pexels_video)(kw_en_scene, o, f, d)
        def pixabay_scene(k, o, f, d):
            return _wrap(_fetch_pixabay_video)(kw_en_scene, o, f, d)
        chain += [("pexels-bg(scene)", pexels_scene), ("pixabay-bg(scene)", pixabay_scene)]
    elif media_type == "video":
        chain += [
            ("pexels-video", pexels_v), ("pixabay-video", pixabay_v),
            ("pexels-photo", pexels_p), ("pixabay-photo", pixabay_p),
        ]
    else:
        chain += [
            ("pixabay-photo", pixabay_p), ("pexels-photo", pexels_p),
            ("pixabay-video", pixabay_v), ("pexels-video", pexels_v),
        ]

    for source_name, fn in chain:
        try:
            kw_use = kw_ko if source_name.startswith("yt-dlp") else kw_en
            path, meta = fn(kw_use, out, filename, duration)
            if path:
                credit = (meta or {}).get("credit") if meta else None
                suffix = f" [{credit}]" if credit else ""
                print(f"  [{filename}] {source_name}: OK ({kw_use}){suffix}")
                return path, credit
        except Exception as e:
            print(f"  [{filename}] {source_name} 실패: {e}")
            continue

    print(f"  [{filename}] 모든 소스 실패 — 검정 영상 생성")
    return _make_black_fallback(out / f"{filename}.mp4", duration), None


def _strip_subject_from_keyword(kw: str, subject: str) -> str:
    """스톡 fallback용: 영문 키워드에서 인물 한글 제거 → 장면·물체 위주만 남김."""
    if not kw or not subject:
        return kw
    # 한글 subject가 영어 키워드에 들어 있을 일은 거의 없지만, 영문 변환 케이스 대비
    parts = [p for p in kw.split() if subject.lower() not in p.lower()]
    return " ".join(parts) or "news scene background"


# ── yt-dlp 비디오 (뉴스 채널 우선 + 품질 필터 + 다단계 fallback) ───────────────

# 뉴스 키워드 보강: 영어 금융/정치 뉴스 채널 계열로 편향
_NEWS_SEARCH_BOOSTS = ["news", "news footage", "b-roll news"]


def _yt_list_candidates(query: str) -> list[dict]:
    """ytsearch 쿼리에서 후보 메타데이터 나열 (다운로드 안 함). uploader도 수집."""
    cmd = [
        "yt-dlp", query,
        "--flat-playlist",
        "--print", "%(id)s|%(title)s|%(duration)s|%(view_count)s|%(uploader)s|%(channel)s",
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
        parts = line.split("|", 5)
        if len(parts) < 6:
            continue
        vid, title, dur_s, vc_s, uploader, channel = parts
        try:
            dur = float(dur_s) if dur_s and dur_s != "NA" else 0.0
        except ValueError:
            dur = 0.0
        try:
            vc = int(vc_s) if vc_s and vc_s != "NA" else 0
        except ValueError:
            vc = 0
        # uploader 또는 channel 중 하나라도 식별에 쓰일 수 있도록 합쳐서 저장
        up = (uploader or "").strip() if uploader and uploader != "NA" else ""
        ch = (channel or "").strip() if channel and channel != "NA" else ""
        cands.append({
            "id": vid, "title": title or "", "dur": dur, "vc": vc,
            "uploader": up or ch,
        })
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
) -> tuple[str | None, dict | None]:
    """
    화이트리스트(공공누리/정부/PD) 채널만 허용.
    반환: (영상 경로, 채널 메타). 둘 다 None이면 미발견.
    """
    ref_terms = ref_terms or []
    must_terms = must_terms or []
    # 화이트리스트 채널 대상 쿼리 — 채널명 힌트 + 더 큰 샘플(20)
    if _is_korean(keyword):
        queries = [
            f"ytsearch20:{keyword} KTV",
            f"ytsearch20:{keyword} 국회방송",
            f"ytsearch20:{keyword} VOA 한국어",
            f"ytsearch20:{keyword} 정부 브리핑",
        ]
    else:
        queries = [
            f"ytsearch20:{keyword} VOA",
            f"ytsearch20:{keyword} NASA",
            f"ytsearch20:{keyword} White House",
            f"ytsearch20:{keyword} UN",
        ]

    seen: dict[str, dict] = {}
    rejected_count = 0
    for q in queries:
        for c in _yt_list_candidates(q):
            vid = c["id"]
            if not vid or vid in seen:
                continue
            if c["dur"] and c["dur"] < 15:
                continue
            # 화이트리스트 채널만 통과
            meta = _match_safe_channel(c.get("uploader", ""))
            if not meta:
                rejected_count += 1
                continue
            c["license_meta"] = meta
            c["score"] = _title_score(c["title"], ref_terms)
            c["must_hit"] = _title_score(c["title"], must_terms) if must_terms else 1
            seen[vid] = c

    if not seen:
        print(f"  [yt] '{keyword}' — 화이트리스트 채널 매칭 0개 (비화이트 {rejected_count}개 거절) → Pexels로 폴백")
        return None, None

    # 화이트리스트 통과분이 이미 극소수 → must_terms 완화 (최소 1개 매칭)
    # 뉴스 고유명사가 제목에 안 들어있는 안전 채널 영상도 허용
    if must_terms:
        strict = [c for c in seen.values() if c["must_hit"] >= 1]
        pool = strict if strict else list(seen.values())
    else:
        pool = list(seen.values())

    print(f"  [yt] '{keyword}' — 안전채널 후보 {len(seen)}개, must_hit≥1 {len([c for c in seen.values() if c['must_hit']>=1])}개")

    ranked = sorted(pool, key=lambda c: (-c["score"], -c["vc"]))
    for c in ranked[:5]:
        vid = c["id"]
        if used_ids and not used_ids.try_reserve(vid):
            continue
        result = _yt_download_by_id(vid, out, filename, duration)
        if result:
            meta = c["license_meta"]
            print(f"  [yt✅안전] '{c['title'][:40]}' ({c.get('uploader','?')}) {meta['license']}")
            return result, meta
        if used_ids:
            used_ids.release(vid)
    return None, None


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


# ── Wikimedia Commons / 위키백과 인물 사진 ─────────────────────────────────
# 정치인·유명 기업·기관의 공식 사진 (CC 라이선스). subject_name 1개당 1장.
# 동명이인 처리: search API로 컨텍스트 가중치 부여 → 가장 적합한 페이지 선택.

# 직책 키워드 — context에서 이 단어만 추출해 disambiguation 검색에 사용 (노이즈 컷)
_TITLE_KEYWORDS_KO = [
    "대통령", "총리", "장관", "차관", "비서실장", "청장", "위원장",
    "시장", "도지사", "군수", "구청장", "의장", "원장",
    "의원", "대표", "회장", "사장", "CEO", "총재",
    "감독", "선수", "배우", "가수", "아나운서", "기자",
]


def _extract_title_keyword(context: str, subject: str) -> str:
    """context 문자열에서 가장 먼저 나오는 직책 키워드 1개 추출. subject는 제외."""
    if not context:
        return ""
    # subject 토큰은 제거 (자기 이름으로 검색하지 않게)
    ctx = context.replace(subject, " ")
    for kw in _TITLE_KEYWORDS_KO:
        if kw in ctx:
            return kw
    return ""


def _looks_like_person_page(title: str, subject: str) -> bool:
    """위키 검색 결과 title이 '인물 페이지'처럼 보이는지 엄격 휴리스틱.

    인물 페이지 패턴 (수락):
      - `subject` (정확히 일치)              예: "손흥민"
      - `subject (...)` (괄호 disambig)      예: "이장우 (1965년)", "박지원 (아나운서)"
    사건·선거 페이지 패턴 (거절):
      - `subject 대통령 취임식`               (괄호 없는 추가 토큰)
      - `2021년 도널드 트럼프 ...`           (subject 앞에 prefix)
    """
    if not title:
        return False
    if title == subject:
        return True
    # 괄호 disambig만 허용 — 공백+토큰 추가는 사건 페이지일 가능성 높음
    return title.startswith(f"{subject} (") or title.startswith(f"{subject}(")


def _wiki_search_top_title(api_base: str, query: str, subject: str = "") -> str | None:
    """search API로 가장 관련도 높은 페이지 title 반환.
    subject 주어지면 인물 페이지 형태(`subject (...)`)인 결과만 선택 → 사건·선거 페이지 배제.
    """
    try:
        q = urllib.parse.quote(query)
        url = (
            f"{api_base}?action=query&format=json&list=search"
            f"&srsearch={q}&srlimit=8&srprop=snippet"
        )
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        results = (data.get("query") or {}).get("search") or []
        # 동음이의 제외 + 인물 페이지 휴리스틱 통과한 첫 결과만 채택.
        # 통과 결과 없으면 None 반환 → 다음 fallback(og:image, 안전채널, 스톡)으로.
        # 관대 모드 없음 — 잘못된 인물(추미애·탄핵 페이지 등) 매칭이 더 큰 사고.
        for r in results:
            title = r.get("title", "")
            snippet = (r.get("snippet") or "").lower()
            if "disambiguation" in snippet or "동음이의" in snippet:
                continue
            if subject and not _looks_like_person_page(title, subject):
                continue
            if title:
                return title
    except Exception:
        return None
    return None


def _wiki_pageimage_by_title(api_base: str, title: str) -> str | None:
    """주어진 정확한 title에 대한 page main image URL."""
    try:
        q = urllib.parse.quote(title)
        url = (
            f"{api_base}?action=query&format=json&prop=pageimages"
            f"&titles={q}&pithumbsize=1280&redirects=1"
        )
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        pages = (data.get("query") or {}).get("pages") or {}
        for _, page in pages.items():
            thumb = (page.get("thumbnail") or {}).get("source")
            if thumb:
                return thumb
    except Exception:
        return None
    return None


def _wiki_resolve(api_base: str, subject: str, context: str) -> tuple[str | None, str | None]:
    """search → top title → pageimage. (resolved_title, image_url) 반환.
    결과는 30일 캐시 (Wikipedia 인물 페이지·사진 URL은 거의 안 바뀜).
    """
    # ── 캐시 확인 ──
    try:
        from src.common.media_cache import get_media_cache
        cache = get_media_cache()
        cache_key = f"{api_base}|{subject}|{_extract_title_keyword(context, subject)}"
        cached = cache.get("wiki_resolve", cache_key)
        if cached is not None:
            return tuple(cached) if isinstance(cached, list) else cached
    except Exception:
        cache = None
        cache_key = None

    job = _extract_title_keyword(context, subject)
    query = f"{subject} {job}".strip() if job else subject
    title = _wiki_search_top_title(api_base, query, subject=subject)
    if not title and job:
        title = _wiki_search_top_title(api_base, subject, subject=subject)
    if not title:
        img = _wiki_pageimage_by_title(api_base, subject)
        result = (subject if img else None, img)
    else:
        img = _wiki_pageimage_by_title(api_base, title)
        result = (title if img else None, img)

    # ── 캐시 저장 ──
    if cache and cache_key:
        try:
            cache.put("wiki_resolve", cache_key, list(result), ttl_days=30.0)
        except Exception:
            pass
    return result


def _fetch_wikimedia_image(
    subject: str, out: Path, filename: str, duration: float,
    used_ids: UsedMediaSet | None = None,
    context: str = "",
) -> tuple[str | None, dict | None]:
    """ko.wikipedia → en.wikipedia 순서로 인물 사진. context로 동명이인 disambiguation."""
    if not subject:
        return None, None
    title, img_url = _wiki_resolve("https://ko.wikipedia.org/w/api.php", subject, context)
    lang_used = "ko"
    if not img_url:
        title, img_url = _wiki_resolve("https://en.wikipedia.org/w/api.php", subject, context)
        lang_used = "en"
    if not img_url:
        print(f"  [wiki] '{subject}' (컨텍스트: {context[:30]}) 페이지 이미지 없음")
        return None, None
    hid = f"wiki-{lang_used}-{img_url}"
    if used_ids and not used_ids.try_reserve(hid):
        return None, None
    try:
        img_path = out / f"{filename}.jpg"
        req = urllib.request.Request(img_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            img_path.write_bytes(resp.read())
        if img_path.stat().st_size < 5_000:
            return None, None
        mp4 = _image_to_video(str(img_path), out / f"{filename}.mp4", duration)
        # credit에 실제 매칭된 제목 포함 → 동명이인 매칭 오류 즉시 발견 가능
        credit_label = title if title and title != subject else subject
        meta = {
            "credit": f"출처: 위키백과 ({credit_label})",
            "license": "CC-BY-SA / Public Domain",
        }
        return mp4, meta
    except Exception as e:
        print(f"  [wiki] 다운로드 실패: {e}")
        if used_ids:
            used_ids.release(hid)
        return None, None


# ── 원문 페이지 og:image (per-job 1회 추출 → 모든 세그먼트 공유 폴백) ───────

def _absolutize(u: str, base_url: str) -> str:
    """상대 URL을 base 기준 절대 URL로 변환."""
    if not u:
        return u
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        m = re.match(r"^https?://[^/]+", base_url or "")
        if m:
            return m.group(0) + u
    return u


def fetch_news_og_image(news_url: str) -> str | None:
    """뉴스 URL의 <meta property="og:image"> 추출. 실패 시 None."""
    if not news_url:
        return None
    try:
        req = urllib.request.Request(news_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read(200_000).decode("utf-8", errors="ignore")
        for pat in (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        ):
            m = re.search(pat, html, re.I)
            if m:
                return _absolutize(m.group(1).strip(), news_url)
    except Exception:
        return None
    return None


# 작은 썸네일 URL 패턴 — 사이드바/추천/관련기사 영역 (실제 본문 사진 아님)
_SMALL_IMG_URL_PATTERNS = [
    re.compile(r"/\d{1,3}x\d{1,3}/", re.I),       # /90x67/, /120x90/ — 명시적 작은 크기
    re.compile(r"mnews\d{1,3}x\d{1,3}", re.I),    # nateimg mnews 90x67 등
    re.compile(r"_thumb[s]?[._/-]", re.I),        # _thumb. _thumbs/ _thumb-
    re.compile(r"[._/-]thumb[._/-]", re.I),       # /thumb/, .thumb.
    re.compile(r"[._/-]small[._/-]", re.I),       # /small., _small_
    re.compile(r"_s\.(jpe?g|png|webp)$", re.I),   # foo_s.jpg
    re.compile(r"-\d{2,3}x\d{2,3}\.", re.I),      # foo-150x100.jpg (워드프레스)
    re.compile(r"/(thumb|thumbnail|tn)/", re.I),  # /thumb/, /thumbnail/, /tn/
    re.compile(r"resize/\d{1,3}/", re.I),         # /resize/100/
]

# 본문 컨테이너 검출 패턴 — 한국 뉴스 사이트 (Naver, Nate, 조선·중앙·매경·연합 등)
_ARTICLE_CONTAINER_PATTERNS = [
    re.compile(r"<article\b[^>]*>(.*?)</article>", re.I | re.S),
    re.compile(r'<div[^>]+id=["\'][^"\']*(?:articleBody|articeBody|articleContent|article_content|news[_-]?body|news[_-]?content)[^"\']*["\'][^>]*>(.*?)</div>', re.I | re.S),
    re.compile(r'<div[^>]+class=["\'][^"\']*(?:article[_-]?body|article[_-]?view|article[_-]?content|news[_-]?body|news[_-]?content|view[_-]?body)[^"\']*["\'][^>]*>(.*?)</div>', re.I | re.S),
]


def _extract_article_section(html: str) -> str | None:
    """본문 영역 HTML chunk만 추출. 못 찾으면 None."""
    if not html:
        return None
    for pat in _ARTICLE_CONTAINER_PATTERNS:
        # finditer로 가장 큰(가장 본문스러운) chunk 선택
        best = ""
        for m in pat.finditer(html):
            chunk = m.group(1) or ""
            if len(chunk) > len(best):
                best = chunk
        if len(best) > 500:  # 너무 짧은 컨테이너는 헤더·푸터일 가능성
            return best
    return None


def _is_small_image_url(url: str) -> bool:
    """URL 자체에 작은 크기 marker 있으면 True"""
    return any(p.search(url) for p in _SMALL_IMG_URL_PATTERNS)


def _img_width_attr(img_tag: str) -> int | None:
    """<img ... width="100"> → 100. 없으면 None."""
    m = re.search(r'\bwidth\s*=\s*["\']?(\d{1,4})', img_tag, re.I)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def fetch_news_article_images(news_url: str, limit: int = 12) -> list[str]:
    """기사 본문 페이지에서 **본문 이미지만** 정확 추출.

    수집 전략 (사이드바·추천·광고 썸네일 차단):
      1) og:image / twitter:image (항상 #1 — 대표 사진 보장)
      2) <article>·.article-body·#articleBody 등 본문 컨테이너 안의 <img>만 스코프
      3) URL 패턴 필터 — /90x67/, _thumb, mnews\\dx\\d 등 거름
      4) <img width="100"> 같은 명시 작은 크기 거름
      5) 본문 컨테이너 못 찾으면 — body 전체에서 위 필터 강하게 적용
    """
    if not news_url:
        return []
    urls: list[str] = []
    seen: set[str] = set()

    def _add(u: str, tag_html: str = "") -> bool:
        if not u:
            return False
        u = _absolutize(u.strip(), news_url)
        if not u or u in seen:
            return False
        low = u.lower()
        # 명확한 아이콘·로고·placeholder
        if any(skip in low for skip in (
            "icon", "logo", "favicon", "sprite", "blank.gif", "spacer",
            "1x1.gif", "pixel.gif", "noimg", "no-image", "default-",
            "btn_", "button_", "share_", "advert", "/ad/", "_ad_",
            "/reporter/", "/writer/", "/byline/", "profile_", "_profile.",
            "avatar", "/author/",
        )):
            return False
        if low.endswith(".svg") or low.endswith(".gif") or low.startswith("data:"):
            return False
        # URL 작은 크기 마커
        if _is_small_image_url(u):
            return False
        # img 태그에 명시된 width < 200
        if tag_html:
            w = _img_width_attr(tag_html)
            if w is not None and w < 200:
                return False
        seen.add(u)
        urls.append(u)
        return True

    try:
        req = urllib.request.Request(news_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read(800_000).decode("utf-8", errors="ignore")

        # ── 1) og:image / twitter:image 항상 1순위로 ──
        for pat in (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        ):
            for m in re.finditer(pat, html, re.I):
                _add(m.group(1))  # og는 사이즈 패턴 통과해도 추가

        # ── 2) 본문 컨테이너 스코프 ──
        article_html = _extract_article_section(html)
        scoped = article_html or html  # 못 찾으면 body 전체로 폴백 (필터 더 강함)
        scope_label = "article-section" if article_html else "body-fallback"

        # 본문 안의 <img> + lazy-load 속성
        img_attrs = ("src", "data-src", "data-lazy-src", "data-original", "data-image-src")
        # <img ...> 태그 전체를 캡처해서 width 속성도 검사
        for m in re.finditer(r'<img\b([^>]+)>', scoped, re.I):
            tag_inner = m.group(1)
            for attr in img_attrs:
                m2 = re.search(rf'\b{attr}\s*=\s*["\']([^"\']+)["\']', tag_inner, re.I)
                if m2:
                    if _add(m2.group(1), tag_html=tag_inner):
                        break  # 같은 태그에서 한 URL만 채택

        # <source srcset> (picture/figure 내)
        for m in re.finditer(r'<source[^>]+srcset=["\']([^"\']+)["\']', scoped, re.I):
            first = m.group(1).split(",")[0].strip().split(" ")[0]
            _add(first)

        print(f"  [article-images] scope={scope_label}, 수집 {len(urls)}장")
    except Exception as e:
        print(f"  [article-images] 추출 실패 무시: {e}")
        return urls[:limit]

    return urls[:limit]


class ArticleImagePool:
    """기사 본문 이미지를 세그먼트별로 dispense (FIFO, threadsafe).

    잡 시작 시 1회 추출 → 여러 세그먼트가 take()로 1장씩 가져감. 비면 None 반환.
    """
    def __init__(self, urls: list[str]):
        self._q: list[str] = list(urls or [])
        self._lock = threading.Lock()

    def take(self) -> str | None:
        with self._lock:
            return self._q.pop(0) if self._q else None

    def remaining(self) -> int:
        with self._lock:
            return len(self._q)


def _fetch_og_image(
    img_url: str, out: Path, filename: str, duration: float,
    used_ids: UsedMediaSet | None = None,
) -> tuple[str | None, dict | None]:
    """og:image URL → 다운로드 → 정지영상 mp4. 출처는 '원문 페이지'로 표기."""
    if not img_url:
        return None, None
    hid = f"og-{img_url}"
    if used_ids and not used_ids.try_reserve(hid):
        return None, None
    try:
        img_path = out / f"{filename}_og.jpg"
        req = urllib.request.Request(img_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            img_path.write_bytes(resp.read())
        if not img_path.exists() or img_path.stat().st_size < 5_000:
            return None, None
        mp4 = _image_to_video(str(img_path), out / f"{filename}.mp4", duration)
        return mp4, {"credit": "출처: 기사 원문", "license": "Editorial / 인용"}
    except Exception:
        if used_ids:
            used_ids.release(hid)
        return None, None


# ── Wikimedia Commons 키워드 이미지 검색 (사물·장소·이벤트) ─────────────────
# 인물 외 카테고리 (오월드, 한화 이글스, 강남, 청와대 등) 공식 사진.

def _wiki_commons_search_files(keyword: str, limit: int = 8) -> list[str]:
    """commons.wikimedia.org 파일 검색 → File: 제목 리스트."""
    try:
        q = urllib.parse.quote(keyword)
        url = (
            "https://commons.wikimedia.org/w/api.php"
            f"?action=query&format=json&list=search"
            f"&srsearch={q}&srnamespace=6&srlimit={limit}"
        )
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return [r.get("title", "") for r in (data.get("query") or {}).get("search") or [] if r.get("title")]
    except Exception:
        return []


def _wiki_commons_imageinfo(file_title: str) -> str | None:
    """File:xxx.jpg → 실제 이미지 URL."""
    try:
        q = urllib.parse.quote(file_title)
        url = (
            "https://commons.wikimedia.org/w/api.php"
            f"?action=query&format=json&titles={q}&prop=imageinfo&iiprop=url&iiurlwidth=1280"
        )
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        pages = (data.get("query") or {}).get("pages") or {}
        for _, page in pages.items():
            for ii in page.get("imageinfo") or []:
                u = ii.get("thumburl") or ii.get("url")
                if u:
                    return u
    except Exception:
        return None
    return None


def _fetch_wikimedia_commons(
    keyword: str, out: Path, filename: str, duration: float,
    used_ids: UsedMediaSet | None = None,
) -> tuple[str | None, dict | None]:
    """commons 키워드 검색 → 첫 매칭 이미지 다운로드 → mp4 변환."""
    if not keyword:
        return None, None
    titles = _wiki_commons_search_files(keyword, limit=8)
    for title in titles:
        # SVG·PDF는 제외 (애니메이션/문서)
        low = title.lower()
        if low.endswith((".svg", ".pdf", ".djvu", ".tif", ".tiff")):
            continue
        url = _wiki_commons_imageinfo(title)
        if not url:
            continue
        hid = f"commons-{title}"
        if used_ids and not used_ids.try_reserve(hid):
            continue
        try:
            img_path = out / f"{filename}.jpg"
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                img_path.write_bytes(resp.read())
            if img_path.stat().st_size < 5_000:
                if used_ids:
                    used_ids.release(hid)
                continue
            mp4 = _image_to_video(str(img_path), out / f"{filename}.mp4", duration)
            label = title.replace("File:", "").rsplit(".", 1)[0][:40]
            return mp4, {"credit": f"출처: Wikimedia Commons ({label})", "license": "CC / Public Domain"}
        except Exception:
            if used_ids:
                used_ids.release(hid)
            continue
    return None, None


# ── AI 이미지 생성 (DALL-E 3) — UI 토글 enable_ai_image=True 일 때만 호출 ────

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")


def _fetch_ai_generated_image(
    keyword_en: str, keyword_ko: str, out: Path, filename: str, duration: float,
    used_ids: UsedMediaSet | None = None,
) -> tuple[str | None, dict | None]:
    """DALL-E 3로 9:16 이미지 생성 → mp4 변환. 비용: 약 $0.04/장."""
    if not OPENAI_KEY:
        print("  [ai-gen] OPENAI_API_KEY 없음 — 스킵")
        return None, None
    # 프롬프트: 한국 뉴스 b-roll에 적합한 시네마틱 이미지로 유도
    prompt_text = (
        f"Cinematic news b-roll style photo: {keyword_en}. "
        f"Korean context: {keyword_ko}. "
        "Vertical 9:16 composition, natural lighting, photorealistic, no text, no logos, no watermarks. "
        "Documentary photojournalism quality."
    )
    hid = f"ai-{prompt_text[:60]}"
    if used_ids and not used_ids.try_reserve(hid):
        return None, None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)
        result = client.images.generate(
            model="dall-e-3",
            prompt=prompt_text,
            size="1024x1792",   # 9:16 세로
            quality="standard", # "hd"는 2배 비싸짐
            n=1,
        )
        img_url = result.data[0].url
        img_path = out / f"{filename}_ai.png"
        req = urllib.request.Request(img_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            img_path.write_bytes(resp.read())
        if not img_path.exists() or img_path.stat().st_size < 10_000:
            if used_ids:
                used_ids.release(hid)
            return None, None
        mp4 = _image_to_video(str(img_path), out / f"{filename}.mp4", duration)
        return mp4, {"credit": "AI 생성 (DALL-E 3)", "license": "Generated"}
    except Exception as e:
        print(f"  [ai-gen] 실패: {e}")
        if used_ids:
            used_ids.release(hid)
        return None, None


# ── Smart crop: 얼굴 기반 수평 중심 X 추정 ────────────────────────────────────

_FACE_CASCADE = None


def _get_face_cascade():
    """Haar cascade 캐싱. 첫 호출만 cv2 import 비용 발생."""
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        try:
            import cv2
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            _FACE_CASCADE = cv2.CascadeClassifier(path)
        except Exception as e:
            print(f"  [smart-crop] cv2 로드 실패 (무시): {e}")
            _FACE_CASCADE = False
    return _FACE_CASCADE if _FACE_CASCADE is not False else None


def detect_face_center_x(video_path: str, sample_frames: int = 10) -> float | None:
    """
    영상에서 N개 프레임 샘플링 → 얼굴 중심 X 위치(0.0~1.0, 가로방향 비율) 반환.
    얼굴 검출 실패 시 None (호출측에서 중앙 크롭으로 폴백).

    가로 영상에서만 의미 있음 (세로는 이미 9:16 근처라 중앙으로 충분).
    """
    cascade = _get_face_cascade()
    if cascade is None:
        return None
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total < 5:
            cap.release()
            return None
        step = max(1, total // max(1, sample_frames))
        centers: list[float] = []
        weights: list[float] = []
        for i in range(sample_frames):
            idx = i * step
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60),
            )
            if len(faces) == 0:
                continue
            # 가장 큰 얼굴 하나 선택 (뉴스 영상은 보통 앵커 1명 대형)
            x, y, w, h = max(faces, key=lambda f: int(f[2]) * int(f[3]))
            cx = (x + w / 2) / frame.shape[1]
            centers.append(float(cx))
            weights.append(float(w * h))
        cap.release()
        if not centers:
            return None
        total_w = sum(weights) or 1.0
        return sum(c * w for c, w in zip(centers, weights)) / total_w
    except Exception as e:
        print(f"  [smart-crop] 검출 실패 (무시): {e}")
        return None


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
