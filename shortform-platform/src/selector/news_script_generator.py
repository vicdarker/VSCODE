"""
뉴스 텍스트 → 숏츠 스크립트 기획 (미디어 타입 포함)
"""

import json
import os
import re
from dataclasses import dataclass, field

import anthropic


def _auto_chunk_caption(caption: str, target_chunks: int = 3) -> list[str]:
    """
    caption을 자연스러운 위치(마침표/쉼표/물음표)에서 분할.
    결과 청크는 항상 caption의 **정확한 연속 부분 문자열**이라 TTS와 완벽 동기화.
    """
    text = caption.strip()
    if not text:
        return []

    # 1) 마침표/물음표/느낌표 기준
    parts = [p.strip() for p in re.split(r"(?<=[.!?。])\s+", text) if p.strip()]
    # 너무 짧으면 쉼표로 재분할
    if len(parts) < target_chunks:
        all_parts = []
        for p in parts:
            sub = [s.strip() for s in re.split(r"(?<=[,、])\s+", p) if s.strip()]
            all_parts.extend(sub if sub else [p])
        parts = all_parts
    # 여전히 적으면 공백 기준으로 균등 분할
    if len(parts) < 2:
        words = text.split()
        n = min(target_chunks, max(1, len(words) // 2))
        per = max(1, len(words) // n)
        parts = [" ".join(words[i:i + per]) for i in range(0, len(words), per)]
    return [p for p in parts if p]


_DATE_PATTERNS = [
    re.compile(r"\d{4}[./\-년]"),           # 2024.10, 2024-10, 2024년
    re.compile(r"\d{1,2}[./\-]\d{1,2}"),    # 10.20, 10/20
    re.compile(r"\d{1,2}\s*월\s*\d{1,2}"),  # 10월 20
    re.compile(r"\d{1,2}\s*시"),            # 3시
]


def _strip_date_stat(val: str) -> str:
    """highlight_stat에서 날짜류 값 제거 (영상 가리는 문제 방지)."""
    if not val:
        return ""
    for p in _DATE_PATTERNS:
        if p.search(val):
            return ""
    return val


def _validate_or_regen_chunks(caption: str, chunks: list[str]) -> list[str]:
    """
    chunks가 caption의 연속 부분 문자열인지 검증. 아니면 자동 재생성.
    — 구두점/공백 차이는 허용 (정규화 후 비교).
    """
    if not caption:
        return chunks or []
    if not chunks:
        return _auto_chunk_caption(caption)
    norm = re.sub(r"[^\w가-힣]", "", caption)  # 구두점 제거
    for c in chunks:
        c_norm = re.sub(r"[^\w가-힣]", "", c)
        if c_norm and c_norm not in norm:
            # Claude가 paraphrase함 → 자동 생성으로 대체
            return _auto_chunk_caption(caption)
    return chunks


@dataclass
class MediaSegment:
    # ── 핵심 ──
    caption: str                          # TTS가 읽을 문장
    caption_chunks: list                  # 자막 표시용 청크 (caption의 부분 문자열)
    media_type: str                       # "video" | "photo"
    duration: float                       # 이 구간 길이 (초)
    # ── 스토리 구조 ──
    role: str = "body"                    # hook | context | body | climax | twist | cta
    pivot_phrase: str = ""                # 다음 세그먼트 연결어
    viewer_retention_line: str = ""       # body 중반: 마지막까지 끌고가는 예고 문구
    cta_type: str = ""                    # cta 세그먼트만: follow | save | share
    # ── 시각 요소 ──
    emphasis_words: list = field(default_factory=list)  # 노란색 강조 단어
    highlight_stat: str = ""              # 화면 중앙 팝업 숫자
    reaction_emoji: str = ""              # climax/twist 이모지
    shot_type: str = ""                   # wide | close-up | chart | portrait | b-roll
    # ── 미디어 검색 ──
    search_keyword: str = ""              # 영어 (Pixabay/Pexels)
    search_keyword_ko: str = ""           # 한글 (YouTube 한국뉴스)
    # ── 런타임 채움 ──
    media_path: str = ""                  # 수집된 영상/사진 파일 경로
    # ── 하위호환 (사용 안함, 유지만) ──
    text_content: str = ""
    graphic_style: str = "dark_navy"


@dataclass
class Thumbnail:
    big_text: str = ""              # 썸네일 대문자 (2~6자)
    keyword_highlight: str = ""     # 빨간색 강조할 단어
    emoji: str = ""                 # 장식 이모지
    bg_style: str = "shock"         # shock | money | warning | question | breaking


@dataclass
class NewsScript:
    title: str
    description: str
    hashtags: list[str]
    segments: list[MediaSegment]
    hook_phrase: str = ""                             # 영상 상단 고정 후킹
    hook_phrase_alternatives: list = field(default_factory=list)  # A/B용 대안 2개
    emotion_target: str = "curiosity"                 # curiosity | outrage | shock | sympathy | fomo
    thumbnail: Thumbnail = field(default_factory=Thumbnail)


def generate_news_script(
    text: str,
    title: str = "",
    style: str = "general",
    target_duration: int = 60,
) -> NewsScript:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""당신은 바이럴 숏폼 PD입니다. 아래 뉴스를 자극적이고 중독성 있는 숏츠로 재구성하세요.

## 입력
- **뉴스 제목**: {title or "(없음)"}
- **뉴스 내용**: {text}
- **목표 길이**: {target_duration}초 (각 segment의 duration 합)

## ⚠️ 절대 원칙: 사실 검증
- 본문에 **명시된 수치/이름/날짜/따옴표**만 사용. 추측 금지
- 본문에 없는 "전문가들은...", "많은 사람이..." 같은 일반화 금지
- 본문에서 인용한 경우 원문 표현 보존
- 본문이 짧으면 본문 범위 내에서만 다룰 것

## A. 스토리 구조

### A1. 세그먼트 역할 (role) — 순서대로 배치
| role | 개수 | duration | 설명 |
|------|-----|----------|------|
| `hook` | 1개 (맨 앞) | 2.0초 | 0.5초 안에 시청자 붙잡기 |
| `context` | 1~2개 | 3.0초 | "왜 중요한가" |
| `body` | 3~6개 | 3.0~4.0초 | 핵심 팩트 (약→강 배열) |
| `climax` | 1개 | 5.0초 | 가장 놀라운 한 방 |
| `twist` | 0~2개 | 3.0초 | 반전/의외 |
| `cta` | 1개 (맨 끝) | 2.5초 | 팔로우 유도 |

같은 역할 반복 시 duration을 0.5초씩 변주.

### A2. Hook 바이럴 템플릿 (1번 세그먼트) — 증명된 패턴 중 택1
- **충격 수치**: "하루 만에 1조 원이 사라졌다"
- **대비**: "주식은 폭등 / 유가는 폭락"
- **질문**: "이란이 한마디 한 게 왜 월가를 흔들었을까?"
- **역대급 프레임**: "33년 만의 사건이 벌어졌다"
- **비밀 폭로**: "99%가 모르는 {{주제}}의 진실"
- **금기 프레임**: "{{인물}}이 절대 말하지 않는 이유"
- **실용 미끼**: "이거 하나만 알면 돼요"
- **인간 감정**: "보자마자 분노가 터졌다"

### A3. Pivot 문구 (2번~마지막, `pivot_phrase` 필드)
각 세그먼트 시작 전환어 — 흐름 연결 필수:
`그런데`, `하지만`, `그리고`, `왜냐하면`, `진짜 포인트는`, `더 충격적인 건`, `그 이유는`, `결론부터`

### A4. 유지율 강화 (`viewer_retention_line`, body 중반 1~2개)
영상 이탈 방지용 클리프행어 — body 중간 세그먼트에 넣기. 빈 문자열 OK.
- "근데 진짜 충격은 영상 끝에 있어요"
- "마지막 팩트 놓치면 안 돼요"
- "영상 끝에 진짜 반전이..."
- "이게 끝이 아니에요"

### A5. CTA 타입 (`cta_type`, cta 세그먼트만)
다음 중 택1:
- `follow`: "팔로우하면 다음 뉴스 바로 알려드려요"
- `save`: "헷갈릴 땐 저장해두세요"
- `share`: "주변에 알려야 할 사람 있으면 공유"

## B. 내레이션 / 자막

### B1. `caption` (TTS가 읽을 문장)
**아나운서 말투 금지** — 구어체:
- ❌ "선언했습니다", "발표했습니다"
- ✅ "선언한 거예요", "~이래요", "여러분"
- **숫자 구체성**: "많이", "엄청", "크게" 금지 → 구체 수치·시점·비율로 (본문 기반)
- **존댓말 통일**: 한 영상 내 반말/존댓말 섞지 말 것
- **한글 우선**: 나스닥 ✓ / Nasdaq ❌, 월가 ✓ / Wall Street ❌, 연준 ✓
  단, 약어·브랜드 허용: WTI, S&P500, GDP, Apple, Tesla

### B2. `caption_chunks` — caption의 부분 문자열만!
caption을 호흡 지점(쉼표·마침표)에서 2~4개로 자름.
- chunks를 이으면 caption과 동일 (구두점·공백 차이만 허용)
- 단어 **추가/수정/생략 금지**
- 각 청크 10자 이내 권장

**좋은 예**: caption="이란이 딱 한마디 던졌어요. 호르무즈 해협, 전면 개방이라고."
→ `["이란이 딱 한마디 던졌어요.", "호르무즈 해협,", "전면 개방이라고."]`

### B3. `emphasis_words` — 핵심 단어 1~3개 (노란색 강조)
caption 안의 임팩트 단어. 예: "나스닥 13일 연속" → `["나스닥", "13일"]`

## C. 시각 요소

### C1. `hook_phrase` (최상위 필드) — 영상 상단 고정 제목
전 세그먼트 동안 동일하게 표시. 2~3줄, 줄당 12자 이내.
- ❌ "미국-이란 종전 기대에 증시 폭등"
- ✅ "이란 한 마디에\\n월가가 폭발했다"
- ✅ "왜 갑자기 나스닥이\\n13일 연속 터졌을까?"

### C2. `hook_phrase_alternatives` (최상위) — A/B 테스트용 대안 2개
같은 훅을 다른 앵글로. 배열 [alt_1, alt_2].
예: main="이란 한 마디에\\n월가가 폭발했다"
→ alts=["주식은 폭등\\n유가는 폭락", "33년 만의\\n나스닥 대기록"]

### C3. `thumbnail` (최상위) — 썸네일 제안 ★ CTR 결정적
```json
"thumbnail": {{
  "big_text": "월가 폭발",       // 2~6자, 썸네일 대문자
  "keyword_highlight": "폭발",   // 빨간색 강조 단어
  "emoji": "💥",                  // 장식 이모지 1개
  "bg_style": "shock"            // shock | money | warning | question | breaking
}}
```

### C4. `emotion_target` (최상위) — 타겟 감정
시청자에게 유도할 감정 1개:
- `curiosity`: 호기심 유발 (의문·미스터리 뉴스)
- `outrage`: 분노 유발 (부정·부조리 뉴스)
- `shock`: 충격 (극단적 수치·사건)
- `sympathy`: 공감·안타까움 (피해자·약자)
- `fomo`: 놓치면 손해 (투자·경제 기회)

### C5. `highlight_stat` (세그먼트) — 화면 중앙 팝업 숫자
caption에 **충격 수치**가 있을 때만 큰 글씨 팝업. 없으면 빈 문자열.
허용 예: "+1.79%", "-11.45%", "$83.85", "869포인트", "13일 연속", "7,100 돌파", "6명→1명"
❌ **날짜·시각·연월일 금지** — "2024.10.20", "10월 20일", "2023년", "오후 3시" 절대 안 됨.
   (날짜는 caption 본문에 서술형으로만. 팝업으로 뜨면 영상을 가려서 흉함)
❌ 일반 명사·인물·장소 금지 — 오직 **숫자·비율·증감**만.

### C6. `reaction_emoji` (climax/twist 세그먼트만)
💥 폭발 / 😱 충격 / 🚀 급등 / 📉 급락 / ⚠️ 경고 / 💰 돈 / 🔥 화제 / 👀 주목

### C7. `shot_type` (세그먼트) — 선호 샷
- `wide`: 전경·장소 (거리, 빌딩, 시장)
- `close-up`: 근접 (인물 얼굴, 손)
- `chart`: 차트·그래프
- `portrait`: 인물 정면
- `b-roll`: 보조 영상 (물체·상황)

## D. 미디어 검색

### D1. `media_type` — `video` 또는 `photo` (graphic 금지)
- `video`: 움직임 (시위·현장·인터뷰)
- `photo`: 정적 (인물·차트·건물)

### D2. 검색어 — 두 언어 모두 필수 ★ 가장 중요 (영상 매칭 품질 결정)

**원칙: 기사의 고유명사(인물·회사·지명·사건명·시점)를 반드시 1개 이상 포함**
일반 카테고리만 넣으면 다른 사건의 영상이 잘못 매칭됨.

#### `search_keyword_ko` (한글 2~5단어) — YouTube 한국 뉴스 매칭
뉴스 방송 자막·제목에 실제로 쓰일 법한 조합으로:
- ❌ "뉴욕증시 폭등" → 아무 날의 증시 뉴스 → 사건 불일치
- ✅ "이란 호르무즈 폐쇄 경고" → 이 사건 전용 리포트 매칭
- ❌ "주가 하락" → 1000개 중 무작위
- ✅ "삼성전자 4분기 실적" → 특정 기업·시점
- ❌ "기후 재앙" → 추상적
- ✅ "제주 폭우 산사태 2024" → 특정 지역·현상·시점
- 세그먼트마다 **각도를 다르게** (사건→인물→결과→배경→반응) — 같은 키워드 금지

#### `search_keyword` (영어 2~5단어) — Pexels/Pixabay 스톡 매칭
스톡 사이트는 인물·사건명이 없음. **시각적 장면**으로:
- ❌ "Iran Hormuz" → 스톡 결과 0건
- ✅ "oil tanker ship strait" (실제 촬영 가능한 물체·장면)
- ❌ "Samsung earnings" → 없음
- ✅ "semiconductor factory clean room"
- 인물·기업명 대신 **물체·배경·행동**으로 치환

## 출력 (JSON만, 설명 금지)

```json
{{
  "title": "업로드용 제목",
  "hook_phrase": "이란 한 마디에\\n월가가 폭발했다",
  "hook_phrase_alternatives": [
    "주식은 폭등\\n유가는 폭락",
    "33년 만의\\n나스닥 대기록"
  ],
  "emotion_target": "shock",
  "thumbnail": {{
    "big_text": "월가 폭발",
    "keyword_highlight": "폭발",
    "emoji": "💥",
    "bg_style": "shock"
  }},
  "description": "업로드용 2~3줄 설명",
  "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5"],
  "segments": [
    {{
      "role": "hook",
      "caption": "이란이 딱 한마디 한 거예요. 월가가 폭발했어요.",
      "caption_chunks": ["이란이 딱 한마디 한 거예요.", "월가가 폭발했어요."],
      "emphasis_words": ["월가"],
      "highlight_stat": "",
      "reaction_emoji": "💥",
      "pivot_phrase": "",
      "viewer_retention_line": "",
      "cta_type": "",
      "shot_type": "b-roll",
      "media_type": "video",
      "search_keyword": "stock market shock trading floor",
      "search_keyword_ko": "뉴욕증시 폭등",
      "duration": 2.0
    }}
  ]
}}
```
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse(message.content[0].text)


def _parse(raw: str) -> NewsScript:
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text.strip())

    segments = []
    for s in data["segments"]:
        mt = s.get("media_type", "photo")
        if mt == "graphic":
            mt = "photo"
        emph = s.get("emphasis_words", [])
        if isinstance(emph, str):
            emph = [w.strip() for w in emph.split(",") if w.strip()]
        chunks = s.get("caption_chunks", [])
        if not isinstance(chunks, list):
            chunks = []
        # ★ 자막/음성 싱크 보장: chunks가 caption의 부분 문자열이어야 함
        # 아니면 자동으로 caption에서 분할
        chunks = _validate_or_regen_chunks(s.get("caption", ""), chunks)
        segments.append(MediaSegment(
            text_content=s.get("text_content", ""),
            caption=s.get("caption", ""),
            media_type=mt,
            search_keyword=s.get("search_keyword", "") or "news concept abstract",
            search_keyword_ko=s.get("search_keyword_ko", "") or s.get("search_keyword", ""),
            duration=float(s.get("duration", 3.0)),
            graphic_style=s.get("graphic_style", "dark_navy"),
            role=s.get("role", "body"),
            emphasis_words=emph if isinstance(emph, list) else [],
            pivot_phrase=s.get("pivot_phrase", ""),
            viewer_retention_line=s.get("viewer_retention_line", ""),
            cta_type=s.get("cta_type", ""),
            highlight_stat=_strip_date_stat(s.get("highlight_stat", "")),
            reaction_emoji=s.get("reaction_emoji", ""),
            shot_type=s.get("shot_type", ""),
            caption_chunks=chunks,
        ))

    # 썸네일 파싱
    tn = data.get("thumbnail", {}) or {}
    thumbnail = Thumbnail(
        big_text=tn.get("big_text", ""),
        keyword_highlight=tn.get("keyword_highlight", ""),
        emoji=tn.get("emoji", ""),
        bg_style=tn.get("bg_style", "shock"),
    )

    # A/B hook_phrase 대안 정규화
    alts = data.get("hook_phrase_alternatives", [])
    if not isinstance(alts, list):
        alts = []

    return NewsScript(
        title=data.get("title", ""),
        hook_phrase=data.get("hook_phrase", "") or data.get("title", ""),
        hook_phrase_alternatives=[a for a in alts if a],
        emotion_target=data.get("emotion_target", "curiosity"),
        thumbnail=thumbnail,
        description=data.get("description", ""),
        hashtags=data.get("hashtags", []),
        segments=segments,
    )
