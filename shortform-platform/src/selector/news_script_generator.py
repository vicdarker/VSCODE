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
    cta_type: str = ""                    # cta 세그먼트만: follow | engage | save | share
    # ── 시각 요소 ──
    emphasis_words: list = field(default_factory=list)  # 노란색 강조 단어
    highlight_stat: str = ""              # 화면 중앙 팝업 숫자
    reaction_emoji: str = ""              # climax/twist 이모지
    shot_type: str = ""                   # wide | close-up | chart | portrait | b-roll
    # ── 미디어 검색 ──
    search_keyword: str = ""              # 영어 (Pixabay/Pexels)
    search_keyword_ko: str = ""           # 한글 (YouTube 한국뉴스)
    subject_name: str = ""                # 핵심 인물·기관·브랜드 (Wikimedia·이미지 검색)
    # ── Remotion 애니메이션 (선택) ──
    chart_values: list = field(default_factory=list)  # 꺾은선 그래프 값 배열
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
    return_raw: bool = False,
) -> NewsScript | tuple:
    """뉴스 텍스트 → NewsScript.
    return_raw=True면 (script, prompt, raw_response_text) 튜플 반환.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if target_duration <= 15:
        role_section = (
            f"### ⚡ 초단축 모드 (목표 {target_duration}초 — **반드시 준수**)\n"
            "- 세그먼트 **정확히 3개**: hook(1.5초) + body 1개(3.0초) + cta(1.5초) = 총 **6.0초**\n"
            "- 각 세그먼트 `duration`은 위 숫자 그대로. 초과 금지.\n"
            "- **caption**은 각 18자 이내 (TTS가 duration 안에 끝나야 함). 긴 서술 금지.\n"
            "- **caption_chunks**는 세그먼트당 1~2개, 각 청크 10자 이내.\n"
            "- context·climax·twist 생략. body도 1개만.\n"
            "- 단, `chart_values`·`highlight_stat`·`emotion_target=shock`은 "
            "본문에 해당 요소가 있으면 반드시 포함 (Remotion 애니메이션 테스트용).\n"
        )
    else:
        role_section = (
            "| role | 개수 | duration | 설명 |\n"
            "|------|-----|----------|------|\n"
            "| `hook` | 1개 (맨 앞) | 2.0초 | 0.5초 안에 시청자 붙잡기 |\n"
            "| `context` | 1~2개 | 3.0초 | \"왜 중요한가\" |\n"
            "| `body` | 3~6개 | 3.0~4.0초 | 핵심 팩트 (약→강 배열) |\n"
            "| `climax` | 1개 | 5.0초 | 가장 놀라운 한 방 |\n"
            "| `twist` | 0~2개 | 3.0초 | 반전/의외 |\n"
            "| `cta` | 1개 (맨 끝) | 2.5초 | 팔로우 유도 |\n\n"
            "같은 역할 반복 시 duration을 0.5초씩 변주."
        )

    # ── 동적 입력 (캐시 안 됨) ──
    user_input = f"""## 입력
- **뉴스 제목**: {title or "(없음)"}
- **뉴스 내용**: {text}
- **목표 길이**: {target_duration}초 (각 segment의 duration 합)

위 뉴스로 시스템 프롬프트의 모든 규칙을 따라 JSON만 출력하세요."""

    # ── 시스템 프롬프트 (Anthropic prompt cache로 캐시됨) ──
    system_prompt = f"""당신은 바이럴 숏폼 PD입니다. 입력 뉴스를 아래 규칙에 따라 자극적이고 중독성 있는 숏츠로 재구성하세요.

## ⚠️ 절대 원칙: 사실 검증
- 본문에 **명시된 수치/이름/날짜/따옴표**만 사용. 추측 금지
- 본문에 없는 "전문가들은...", "많은 사람이..." 같은 일반화 금지
- 본문에서 인용한 경우 원문 표현 보존
- 본문이 짧으면 본문 범위 내에서만 다룰 것

## A. 스토리 구조

### A1. 세그먼트 역할 (role) — 순서대로 배치
{role_section}

### A2. Hook 바이럴 템플릿 (1번 세그먼트) — 뉴스 성격에 맞는 패턴 택1

**자극형** (충격·사건·부조리 뉴스):
- **충격 수치**: "하루 만에 1조 원이 사라졌다"
- **대비**: "주식은 폭등 / 유가는 폭락"
- **질문**: "이란이 한마디 한 게 왜 월가를 흔들었을까?"
- **역대급 프레임**: "33년 만의 사건이 벌어졌다"
- **비밀 폭로**: "99%가 모르는 {{주제}}의 진실"
- **금기 프레임**: "{{인물}}이 절대 말하지 않는 이유"
- **실용 미끼**: "이거 하나만 알면 돼요"
- **인간 감정**: "보자마자 분노가 터졌다"

**정보형** (정책·외교·경제 일반 뉴스 — 자극 낮지만 관심 유발):
- **간결 정의**: "하루에 3조원씩 빠져나가는 이유"
- **시의성**: "오늘부터 바뀌는 3가지"
- **숫자 배열**: "96조 계약 3가지 의미"
- **조용한 충격**: "아무도 주목 안 했지만"

★ 사실이 밋밋한 정책·외교 뉴스에는 **자극형 억지 사용 금지** — 정보형 선택.

### A3. Pivot 문구 (2번~마지막, `pivot_phrase` 필드)
각 세그먼트 시작 전환어 — 흐름 연결 필수:
`그런데`, `하지만`, `그리고`, `왜냐하면`, `진짜 포인트는`, `더 충격적인 건`, `그 이유는`, `결론부터`

### A4. 유지율 강화 (`viewer_retention_line`, body 중반 1~2개)
영상 이탈 방지용 클리프행어 — body 중간 세그먼트에 넣기. 빈 문자열 OK.
- "근데 진짜 충격은 영상 끝에 있어요"
- "마지막 팩트 놓치면 안 돼요"
- "영상 끝에 진짜 반전이..."
- "이게 끝이 아니에요"

### A5. CTA 타입 (`cta_type`, cta 세그먼트만) ★ 일반 템플릿 금지

**❌ 절대 금지 (Claude가 자주 베끼는 죽은 카피)**:
- "팔로우하면 다음 뉴스 바로 알려드려요" ← 모든 채널이 씀, 알고리즘에서 묻힘
- "헷갈릴 땐 저장해두세요" ← 무엇을 저장할지 불명확
- "주변에 알려야 할 사람 있으면 공유" ← 주체 불분명
- "구독·좋아요 부탁드려요" ← 시청자가 가장 무시하는 문구

**✅ 원칙**: 본문의 **구체 stakes**(날짜·인물·지역·결과)와 결합. "이 뉴스가 나와 무슨 상관?"에 즉답.

#### `cta_type` 4가지 (택1)

| 타입 | 트리거 조건 | 좋은 카피 패턴 |
|------|----------|--------------|
| **`follow`** | 후속 결과·다음 편 약속 가능할 때 | "{{날짜}} 결과 나오면 다시 영상 올릴게요" / "이 인물 다음 행보 추적합니다" / "이 시리즈 다음 편 {{주제}}" |
| **`engage`** | 댓글로 의견 갈리는 이슈 (정치·찬반·예측) | "{{후보A}} vs {{후보B}} 누가 이길 거 같아요?" / "{{지역}}민이면 댓글 한 마디" / "이거 어떻게 생각해요?" |
| **`save`** | 정보·날짜·체크리스트 (실용성 ↑) | "{{날짜}} 까먹지 말고 저장" / "이 3가지만 기억해두세요" / "투표 전에 다시 보세요" |
| **`share`** | 주변에 직접 영향 받는 사람 있는 뉴스 (정책·세금·부동산) | "{{대상자}} 친구한테 보내주세요" / "{{지역}} 거주자한테 알려주세요" |

#### 작성 규칙
- **인물명·지역명·날짜** 1개 이상 포함 (본문에 있는 것만)
- **engage 우선 검토** — 댓글 유발이 알고리즘 가장 강함 (찬반·예측 가능 뉴스면 무조건 engage)
- "팔로우/저장/공유" 단어 자체는 카피 끝부분에만 1번 (낚시 느낌 줄이기)

#### 뉴스 유형별 좋은 예 (이 표의 패턴을 본문에 맞춰 변형)

| 뉴스 유형 | 추천 cta_type | 좋은 카피 예 |
|---------|------------|--------------|
| **선거·정치** (강원지사 출마) | engage | "우상호 vs 김진태 누가 이길 것 같아요? 댓글 ↓" |
| **부동산·시세** (강남 집값 폭락) | engage | "지금이 매수 타이밍일까요 더 떨어질까요?" |
| **정책 시행** (트럼프 관세 4월 2일) | save | "4월 2일 시행, 까먹지 말고 저장해두세요" |
| **세금·법률 변경** (종합소득세 개정) | share | "사업하는 친구한테 꼭 보내주세요" |
| **인사·발표** (이재명 개각) | follow | "발표되는 장관 명단 영상으로 정리할게요" |
| **국제·외교** (UAE 96조 계약) | follow | "후속 계약 진행되면 다시 다룰게요" |
| **스포츠·연예** (손흥민 부상) | engage | "다음 경기 출전 가능할까요? 의견 ↓" |
| **사건·판결** (이태원 1심 선고) | follow | "2심·최종 선고 나오면 다시 올릴게요" |
| **재난·사고** (피해자 있는 뉴스) | (CTA 자제) | 가벼운 톤 금지. 사실 전달로 마무리 |

**공통 패턴 — 어느 뉴스든 적용 가능**:
- engage: "{{양자택일/예측}} 댓글 ↓" — 의견 갈리는 이슈
- save: "{{구체 날짜}} 까먹지 말고 저장" — 시행일·발표일 있는 뉴스
- follow: "{{후속사건}} 나오면 다시 영상 올릴게요" — 결과 대기 중인 뉴스
- share: "{{대상자}} 친구한테 보내주세요" — 특정 직군·지역 영향 뉴스

**❌ 금지 카피 재확인**:
- "팔로우하면 바로 알려드려요" / "구독·좋아요 부탁드려요" / "도움 됐다면 좋아요"

### A6. 정보 분배 원칙 ★ 중복 금지
- 각 세그먼트는 **새로운 사실 1개 이상** 포함해야 함
- 같은 수치·인용·사건을 여러 세그먼트에서 반복 금지 (hook에서 예고한 건 body/climax에서 확장은 OK, 복사는 ❌)
- 본문에 팩트가 적으면 **세그먼트 개수를 줄여라** — 억지로 채우지 말 것
- context = "왜 중요한가" / body = "무슨 일이" / climax = "가장 놀라운" / twist = "예상 밖" — 역할마다 **다른 각도**

### A7. Duration 합계 검증
- 모든 segment.duration 합 = **target_duration ± 2초 이내**
- 계산 후 넘치면: body 하나 빼거나 각 duration 0.5초씩 줄여서 맞출 것
- 짧으면: body 추가 (단, 새로운 팩트가 있을 때만 — A6 원칙)

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
- 각 청크 **12~20자 (한글 기준, 어절 단위로 끊기)**. 화면은 최대 2줄까지 허용되니 억지로 쪼개지 말 것.
- 호흡 지점 우선: 쉼표·마침표 > 조사 경계 > 접속어 앞

**좋은 예**: caption="이란이 딱 한마디 던졌어요. 호르무즈 해협, 전면 개방이라고."
→ `["이란이 딱 한마디 던졌어요.", "호르무즈 해협, 전면 개방이라고."]`
**나쁜 예** (너무 짧음): `["이란이", "한마디", "던졌어요", "호르무즈", "해협", "전면", "개방"]`

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
  "big_text": "월가 폭발\\n33년 만에",   // 2줄 권장 (각 줄 4~12자)
  "keyword_highlight": "폭발",         // 노란 동그라미 강조 단어
  "emoji": "💥",                        // 장식 이모지 1개
  "bg_style": "shock"                  // shock | money | warning | question | breaking
}}
```

**big_text 작성 규칙 (썸네일 v2)**:
- ✅ **2줄 권장** — `\\n`으로 구분. 1줄: 핵심 / 2줄: 보강 (수치·시점·반전)
  - "월가 폭발\\n33년 만에"
  - "강남 집값\\n33% 사라졌다"
  - "이재명 개각\\n7명 교체"
- ✅ **숫자·강조어 포함** — keyword_highlight에 노란 동그라미 자동 그려짐
- ✅ 한 줄만 쓸 거면 2~6자 큰 글씨 (예전 모드)
- ❌ "오늘의 뉴스 정리" 같은 일반어 — 클릭 유발 0
- ❌ 18자 초과 — 너무 작아짐

**시스템 자동 처리**:
- 인물 뉴스(`subject_name` 있음) → 인물 사진을 좌측에 배치, 우측에 텍스트 split 레이아웃
- 일반 뉴스 → 기사 og:image 또는 climax 영상 프레임 위에 텍스트
- keyword_highlight → 노란 손그림 동그라미 자동 추가

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

### C6.5 `chart_values` (세그먼트, 선택) — 꺾은선 그래프 데이터
시계열 **숫자 흐름**이 기사에 나오면 배열로. 최소 3개, 최대 10개. 단위 무시하고 raw 숫자만.
- 예: 주봉 시세 → `[7.0, 6.5, 5.8, 5.1, 4.6]`
- 예: 월별 판매량 → `[120, 135, 98, 150, 210]`
- 없으면 빈 배열 `[]` — 억지로 만들지 말 것.

### C7. `shot_type` (세그먼트) — 선호 샷
- `wide`: 전경·장소 (거리, 빌딩, 시장)
- `close-up`: 근접 (인물 얼굴, 손)
- `chart`: 차트·그래프
- `portrait`: 인물 정면
- `b-roll`: 보조 영상 (물체·상황)

## C.8 메타데이터 품질 가이드

### `description` (최상위, 2~3줄)
1. **1줄**: 핵심 한 문장 요약
2. **2줄**: 가장 놀라운 수치·팩트 1개
3. **3줄**: 행동 유도 ("팔로우 + 저장")

### `hashtags` (최상위, 정확히 5개)
5개 조합 원칙:
1. **대주제** — #경제, #외교, #IT, #사회, #정치
2. **세부 사건** — #UAE방산, #호르무즈, #반도체수출
3. **인물·기관** — #강훈식, #백악관, #삼성전자
4. **감정·반응** — #충격, #대반전, #논란
5. **트렌드** — #숏츠뉴스, #뉴스요약, #오늘뉴스

## D. 미디어 검색

### D1. `media_type` — `video` 또는 `photo` (graphic 금지)
- `video`: 움직임 (시위·현장·인터뷰)
- `photo`: 정적 (인물·차트·건물)

### D2. 검색어 — 두 언어 모두 필수 ★ 가장 중요 (영상 매칭 품질 결정)

**원칙: 기사의 고유명사(인물·회사·지명·사건명·시점)를 반드시 1개 이상 포함**
일반 카테고리만 넣으면 다른 사건의 영상이 잘못 매칭됨.

#### `search_keyword_ko` (한글 2~5단어) — YouTube 공식 채널 매칭 ★
이 시스템은 **저작권 안전 채널**만 허용합니다: KTV 국민방송 · 국회방송 NATV · VOA 한국어 · NASA · 백악관 · UN.
민간 방송(YTN·JTBC·MBC 등)은 자동 탈락 → 사용 불가.

**공식 발화 키워드를 적극 포함해서 매칭률 높이기**:
- 정부·외교 뉴스: **"브리핑", "발표", "성명", "설명회", "기자회견"**
- 국회 뉴스: **"국정감사", "대정부질문", "본회의", "법안", "상임위"**
- 경제 뉴스: **"통계청", "한국은행", "금통위", "재정부", "금감원"**
- 국제 뉴스(영어권): VOA 매칭을 위해 영문 키워드도 `search_keyword`에 의도적 배치

**예시**:
- ❌ "뉴욕증시 폭등" (민간 방송 뉴스) → 매칭 0
- ✅ "이재명 경제정책 브리핑" → 정부·국회 채널 매칭
- ❌ "삼성전자 실적" → 민간 뉴스만
- ✅ "반도체 수출 통계청 발표" → 정부 공식 채널 매칭
- ❌ "이란 호르무즈" (일반 뉴스) → 민간 채널만
- ✅ "호르무즈 외교부 성명" → 안전 채널 매칭
- 세그먼트마다 각도 다르게 (사건→인물→결과→배경→반응)

#### `search_keyword` (영어 2~5단어) — Pexels/Pixabay 스톡 매칭 ★ 시각 명사만
스톡 사이트는 **카메라로 실제 촬영 가능한 사물·장면**만 있음. 추상·은유·감정어 금지.

**금지 패턴 (스톡 결과 0건 또는 무관)**:
- ❌ 추상어: "shock", "concept", "abstract", "idea", "future", "trend"
- ❌ 감정어: "anger crowd", "fear market", "happy news"
- ❌ 한국 고유명사 영문: "Iran Hormuz", "Samsung earnings", "Hanwha Eagles"
- ❌ 사건 추상화: "policy change reaction", "diplomatic tension"
- ❌ 형용사 남발: "amazing shocking incredible scene"

**필수 패턴 (실제 촬영 영상 존재)**:
- ✅ 구체 사물 1~2개 + 장소·동작:
  - "oil tanker strait night" (배+해협+밤)
  - "semiconductor clean room workers" (반도체+공장+사람)
  - "wolf walking forest snow" (늑대+숲+눈)
  - "bakery bread display window" (빵집+빵+진열창)
  - "baseball stadium crowd cheering" (야구장+군중+환호)
  - "LED billboard street night seoul" (전광판+거리+밤)
- ✅ Pexels에 검색해서 결과 나오는지 머릿속 시뮬레이션 — 안 나올 것 같으면 더 일반적 단어로 치환

**치환 예 (한국 뉴스 → 스톡 매칭 가능)**:
| 뉴스 주제 | ❌ 한국명 | ✅ 시각 명사 |
|---------|--------|--------------|
| 오월드 늑대 탈출 | "Owolf zoo escape Daejeon" | "wolf running forest tracks" |
| 한화 이글스 승리 | "Hanwha Eagles victory" | "baseball stadium fans cheering" |
| 대전 빵집 콜라보 | "Daejeon bakery collab" | "bakery bread queue customers" |
| 강남 집값 폭락 | "Gangnam apartment crash" | "modern apartment building korea" |

### D2.5 `subject_name` (세그먼트, 선택) ★ 인물·기관 정확 매칭
이 세그먼트가 **특정 인물·기관·브랜드**를 다루면 명시. Wikimedia Commons / 위키백과 인물 사진 검색에 사용됨 (CC 라이선스).

#### 기본 규칙
- ✅ 한국 정치인: "이재명", "한동훈"
- ✅ 외국 정치인 (한글표기): "트럼프", "푸틴", "시진핑"
- ✅ 기업: "삼성전자", "테슬라", "애플"
- ✅ 기관: "백악관", "한국은행", "통계청"
- ❌ 일반 사건만 다루는 세그먼트 → **빈 문자열** (억지로 만들지 말 것)
- ❌ 여러 명 나열 → 가장 핵심 인물 1명만
- 모르는 인물·신생 인물(Wikimedia에 없을 가능성) → 빈 문자열 권장

#### ★ 동명이인 disambiguation — 가장 중요
이름만 쓰면 더 유명한 동명이인이 매칭됩니다 (예: "이장우" → 연예인 vs 대전시장). **직책·기관·소속을 함께 명시**하세요.

| ❌ 위험 (동명이인 충돌) | ✅ 안전 (직책 포함) |
|----------------------|------------------|
| "이장우" | "이장우 대전시장" |
| "김민재" (축구·배우 동명) | "김민재 축구선수" |
| "박지원" (정치인·배우 동명) | "박지원 의원" |
| "이정현" (가수·정치인·배우 동명) | "이정현 의원" 또는 "이정현 가수" |
| "강호동" (1명뿐 — 그대로 OK) | "강호동" |

**판단 기준**:
- 한국에서 흔한 이름(2글자 성씨+1글자 이름) → **반드시 직책 추가**
- 시스템이 이 문자열로 위키 검색 → 첫 번째 결과 선택. 가장 유명한 사람이 1순위라 직책 없으면 **연예인이 정치인보다 우선** 매칭됨

#### 사용 흐름
시스템이 subject_name으로 위키 검색 → 안 나오면 og:image → 그 다음 안전 채널 영상. 빈값이면 스톡 b-roll 직행.

### D3. 외국 인물 처리 ★ 인물 불일치 방지
외국 정치인·유명인(수지 와일스, 칼둔, 엘론 머스크 등) 이름을 `search_keyword_ko`에 넣어도 KTV/국회방송에 없어서 매칭 실패 → Pexels에서 **엉뚱한 외국인 얼굴** 나옴 → 시청자가 실제 인물로 오인.

**대응**:
- 외국 인물은 이름보다 **직책·조직·상황**을 전면에
  - ❌ "수지 와일스 면담" → ✅ "백악관 비서실장 면담" (VOA/백악관 매칭 가능)
  - ❌ "칼둔 UAE 회의" → ✅ "UAE 경제개발국 회의"
- `search_keyword`(영문)는 **얼굴 안 보이는 각도**로 유도:
  - ❌ "US official meeting" → 특정 인물로 보일 위험
  - ✅ "diplomat handshake bilateral", "podium briefing US flag", "motorcade arrival airport"
- `shot_type`도 `wide` 또는 `b-roll`로 설정해 클로즈업 회피

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
      "chart_values": [],
      "pivot_phrase": "",
      "viewer_retention_line": "",
      "cta_type": "",
      "shot_type": "b-roll",
      "media_type": "video",
      "search_keyword": "stock market shock trading floor",
      "search_keyword_ko": "뉴욕증시 폭등",
      "subject_name": "",
      "duration": 2.0
    }}
  ]
}}
```
"""

    # 시스템 프롬프트는 Anthropic prompt cache 사용 (5분 TTL)
    # → 같은 시스템 프롬프트 재사용 시 토큰 비용 ~90% 절감 + 지연 단축
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_input}],
    )

    raw_response = message.content[0].text
    script = _parse(raw_response)
    # 디버깅·로그 호환을 위해 합친 prompt 텍스트도 반환
    full_prompt = f"<<SYSTEM>>\n{system_prompt}\n\n<<USER>>\n{user_input}"
    if return_raw:
        return script, full_prompt, raw_response
    return script


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
            subject_name=(s.get("subject_name", "") or "").strip(),
            duration=float(s.get("duration", 3.0)),
            graphic_style=s.get("graphic_style", "dark_navy"),
            role=s.get("role", "body"),
            emphasis_words=emph if isinstance(emph, list) else [],
            pivot_phrase=s.get("pivot_phrase", ""),
            viewer_retention_line=s.get("viewer_retention_line", ""),
            cta_type=s.get("cta_type", ""),
            highlight_stat=_strip_date_stat(s.get("highlight_stat", "")),
            chart_values=[float(v) for v in (s.get("chart_values") or []) if isinstance(v, (int, float))],
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
