"""
블로그 콘텐츠에서 숏폼 스크립트를 생성합니다.
Claude가 흥미로운 주제를 추출해 TTS용 나레이션 스크립트를 작성합니다.
"""

import json
import os
from dataclasses import dataclass

import anthropic

from src.extractor.blog_extractor import BlogContent
from src.extractor.transcript import Segment


@dataclass
class BlogScript:
    hook: str               # 첫 3초 훅 문장
    narration: str          # TTS로 읽을 전체 나레이션
    segments: list[Segment] # 타임스탬프 추정 세그먼트
    hashtags: list[str]
    topic: str              # 선택된 주제 요약


def generate_scripts(
    content: BlogContent,
    num_scripts: int = 1,
    duration_sec: int = 60,
    style: str = "general",
) -> list[BlogScript]:
    """
    블로그 콘텐츠에서 숏폼 스크립트 목록을 생성합니다.

    Args:
        content:     블로그 내용
        num_scripts: 생성할 스크립트 수 (= 영상 수)
        duration_sec: 목표 영상 길이 (초)
        style:       콘텐츠 스타일

    Returns:
        BlogScript 목록
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = _build_prompt(content, num_scripts, duration_sec, style)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    return _parse_response(raw)


def _build_prompt(
    content: BlogContent,
    num_scripts: int,
    duration_sec: int,
    style: str,
) -> str:
    style_guide = {
        "general":       "흥미롭고 공유하고 싶어지는 내용",
        "education":     "유용한 지식이나 인사이트를 쉽게 전달",
        "entertainment": "재미있고 감정을 자극하는 이야기",
        "news":          "핵심 사실과 중요한 포인트만 간결하게",
    }.get(style, "흥미롭고 공유하고 싶어지는 내용")

    # 분당 약 150단어(한국어 기준 약 200자) 기준으로 목표 글자 수 산출
    target_chars = int(duration_sec * (200 / 60))

    return f"""당신은 숏폼 영상 전문 스크립트 작가입니다.
아래 블로그 글에서 가장 흥미로운 주제 {num_scripts}개를 골라 TikTok/YouTube Shorts용 스크립트를 작성하세요.

## 블로그 제목
{content.title}

## 블로그 내용
{content.text}

## 작성 기준
- 스타일: {style_guide}
- 나레이션 길이: 약 {target_chars}자 ({duration_sec}초 분량)
- 첫 문장(훅)은 3초 안에 시청자를 사로잡아야 함
- 자연스럽게 말하는 구어체로 작성
- 각 문장은 30자 이하로 짧게 끊기
- 주제가 서로 다른 {num_scripts}개를 선택

## 응답 형식 (JSON만, 다른 설명 없이)

```json
[
  {{
    "topic": "선택한 주제 한 줄 요약",
    "hook": "시청자를 사로잡는 첫 문장 (강렬하고 짧게)",
    "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5"],
    "sentences": [
      "첫 번째 문장.",
      "두 번째 문장.",
      "..."
    ]
  }}
]
```

sentences는 나레이션을 문장 단위로 쪼갠 배열입니다.
"""


def _parse_response(raw: str) -> list[BlogScript]:
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    data = json.loads(text.strip())
    scripts = []

    for item in data:
        sentences = item.get("sentences", [])
        narration = " ".join(sentences)
        segments = _sentences_to_segments(sentences)

        scripts.append(BlogScript(
            hook=item.get("hook", ""),
            narration=narration,
            segments=segments,
            hashtags=item.get("hashtags", []),
            topic=item.get("topic", ""),
        ))

    return scripts


def _sentences_to_segments(sentences: list[str]) -> list[Segment]:
    """
    문장 목록을 타임스탬프 세그먼트로 변환합니다.
    한국어 기준 분당 약 200자(3.3자/초) 속도로 추정합니다.
    """
    CHARS_PER_SEC = 3.5
    MIN_DUR = 1.5   # 문장 최소 표시 시간
    GAP = 0.15       # 문장 사이 간격

    segments = []
    cursor = 0.0

    for sentence in sentences:
        if not sentence.strip():
            continue
        chars = len(sentence)
        duration = max(chars / CHARS_PER_SEC, MIN_DUR)
        segments.append(Segment(
            start=cursor,
            end=cursor + duration,
            text=sentence.strip(),
        ))
        cursor += duration + GAP

    return segments
