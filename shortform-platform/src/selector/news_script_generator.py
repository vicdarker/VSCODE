"""
뉴스 텍스트 → 숏츠 스크립트 기획 (미디어 타입 포함)
"""

import json
import os
from dataclasses import dataclass, field

import anthropic


@dataclass
class MediaSegment:
    text_content: str             # 화면에 크게 표시할 텍스트 (2~3줄)
    caption: str                  # 읽히는 자막
    media_type: str               # "video" | "photo"
    search_keyword: str           # 검색 키워드
    duration: float               # 이 구간 길이 (초)
    graphic_style: str = "dark_navy"
    # 확장 필드 (기획 품질 향상)
    role: str = "body"            # hook | context | body | climax | twist | cta
    emphasis_words: list = field(default_factory=list)  # 강조할 단어 (노란색)
    pivot_phrase: str = ""        # 다음 세그먼트 연결어 (그런데/하지만/진짜 포인트는)
    media_path: str = ""          # 수집 후 채워짐


@dataclass
class NewsScript:
    title: str
    description: str
    hashtags: list[str]
    segments: list[MediaSegment]


def generate_news_script(
    text: str,
    title: str = "",
    style: str = "general",
    target_duration: int = 60,
) -> NewsScript:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""당신은 바이럴 숏폼 PD입니다. 뉴스를 자극적이고 중독성 있는 숏츠로 재구성하세요.

## 뉴스 제목
{title or "(없음)"}

## 뉴스 내용
{text}

## 절대 원칙 (위반 시 실패)

### 1. 스토리 아크 (기승전결)
세그먼트는 반드시 다음 "역할"을 순서대로 배치:
- `hook` (1개, 맨 앞, 2초): 시청자를 0.5초 만에 붙잡는 충격/질문/대비
- `context` (1~2개, 3초): "왜 중요한가" 배경 설명
- `body` (3~6개, 3~4초): 핵심 팩트를 임팩트 순으로 (약→강)
- `climax` (1개, 5초): 가장 놀라운 한 방. "근데 진짜 충격은" 같은 pivot으로 도입
- `twist` (0~2개, 3초): 반전/의외 정보
- `cta` (1개, 맨 끝, 2.5초): 팔로우 유도

총 길이: **{target_duration}초 내외** (duration 합)

### 2. Hook 작성 규칙 (1번 세그먼트)
4가지 공식 중 하나 사용:
- **충격 수치**: "하루 만에 1조 원이 사라졌다"
- **대비**: "주식은 폭등 / 유가는 폭락"
- **질문**: "이란이 한마디 한 게 왜 월가를 흔들었을까?"
- **역대급 프레임**: "33년 만의 사건이 벌어졌다"
Hook 세그먼트의 `text_content`는 최대 2줄, 단어 적게.

### 3. Pivot 문구 필수 (2번~마지막 세그먼트)
각 세그먼트의 `pivot_phrase` 필드에 전환어 지정:
- `그런데`, `하지만`, `그리고`, `왜냐하면`, `진짜 포인트는`, `더 충격적인 건`, `그 이유는`, `결론부터`

### 4. 캡션(자막) 톤 — 아나운서 금지
- ❌ "~했습니다", "발표했습니다", "밝혔습니다" (TV뉴스 말투)
- ✅ "~한 거예요", "~이래요", "여러분", 반말 섞기 OK
- 예: ❌ "이란 외무장관이 호르무즈 해협 완전 개방을 선언했습니다."
     ✅ "이란이 딱 한마디 한 거예요. 호르무즈 해협, 전면 개방."

### 5. 강조 단어 (`emphasis_words`)
각 세그먼트에서 `text_content` 안의 **가장 임팩트 있는 단어 1~3개**를 뽑아 리스트에 담기.
렌더러가 이 단어를 노란색으로 칠함.
- 예: text_content="나스닥\\n13일 연속 상승" → emphasis_words=["나스닥", "13일"]

### 6. 미디어 타입·검색어
- `media_type`: `video` (움직임/현장) 또는 `photo` (인물/차트/건물). **graphic 금지**.
- `search_keyword`: 영어, 2~5단어, 구체적. 모든 세그먼트 필수. 세그먼트마다 다르게.
- 예시: `stock market trading floor`, `crude oil barrel falling`, `Trump press conference`, `Islamabad city aerial`, `smartphone news app follow`

### 7. Duration 리듬 (단조롭지 않게)
역할별 기본값:
- hook: 2.0초, context: 3.0초, body: 3.0~4.0초, climax: 5.0초, twist: 3.0초, cta: 2.5초
- 같은 역할 반복 시 0.5초씩 변주

## 출력 형식 (JSON만, 설명 금지)

```json
{{
  "title": "3초 안에 클릭하게 만드는 제목 (물음표/숫자/충격어 활용)",
  "description": "업로드용 2~3줄 설명",
  "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5"],
  "segments": [
    {{
      "role": "hook",
      "text_content": "화면 문구\\n2~3줄",
      "caption": "내레이션 전문 (구어체)",
      "emphasis_words": ["임팩트", "단어"],
      "pivot_phrase": "",
      "media_type": "video",
      "search_keyword": "stock market shock trading floor",
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
        segments.append(MediaSegment(
            text_content=s["text_content"],
            caption=s.get("caption", ""),
            media_type=mt,
            search_keyword=s.get("search_keyword", "") or "news concept abstract",
            duration=float(s.get("duration", 3.0)),
            graphic_style=s.get("graphic_style", "dark_navy"),
            role=s.get("role", "body"),
            emphasis_words=emph if isinstance(emph, list) else [],
            pivot_phrase=s.get("pivot_phrase", ""),
        ))
    return NewsScript(
        title=data.get("title", ""),
        description=data.get("description", ""),
        hashtags=data.get("hashtags", []),
        segments=segments,
    )
