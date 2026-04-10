"""
Claude API를 사용해 자막에서 숏폼에 적합한 구간을 선택합니다.
"""

import json
import os
from dataclasses import dataclass

import anthropic

from src.extractor.transcript import Segment, to_full_text


@dataclass
class SelectedClip:
    start: float       # seconds
    end: float         # seconds
    reason: str        # Claude가 선택한 이유
    hook: str          # 훅 문장 (첫 3초 자막)
    hashtags: list[str]


def select_clips(
    segments: list[Segment],
    title: str,
    duration_sec: int = 60,
    num_clips: int = 3,
    style: str = "general",
) -> list[SelectedClip]:
    """
    전체 자막 세그먼트에서 숏폼에 적합한 구간을 선택합니다.

    Args:
        segments: 전체 자막 세그먼트
        title: 영상 제목
        duration_sec: 목표 숏폼 길이 (초)
        num_clips: 추출할 클립 수
        style: 콘텐츠 스타일 (general / education / entertainment / news)

    Returns:
        선택된 클립 목록
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    transcript_text = to_full_text(segments)

    prompt = _build_prompt(
        title=title,
        transcript=transcript_text,
        duration_sec=duration_sec,
        num_clips=num_clips,
        style=style,
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    return _parse_response(raw)


def _build_prompt(
    title: str,
    transcript: str,
    duration_sec: int,
    num_clips: int,
    style: str,
) -> str:
    style_guide = {
        "general": "시청자의 관심을 끄는 흥미롭고 임팩트 있는 구간",
        "education": "핵심 개념이나 인사이트가 담긴 교육적 구간",
        "entertainment": "웃음, 감동, 놀라움 등 감정을 자극하는 구간",
        "news": "핵심 팩트나 중요한 발언이 담긴 구간",
    }.get(style, "흥미롭고 임팩트 있는 구간")

    return f"""당신은 숏폼 영상 전문 편집자입니다.
아래 영상의 자막을 분석해 TikTok/YouTube Shorts/Instagram Reels에 적합한 구간을 선택해 주세요.

## 영상 제목
{title}

## 선택 기준
- {style_guide}
- 각 클립은 약 {duration_sec}초 분량
- 시작은 강렬한 훅(hook)으로 시작해야 함
- 중간에 끊기지 않고 완결된 내용을 담아야 함

## 자막 (타임스탬프 포함)
{transcript}

## 요청
위 자막에서 숏폼에 가장 적합한 구간 {num_clips}개를 선택하고, 아래 JSON 형식으로만 응답해 주세요.
다른 설명 없이 JSON만 반환하세요.

```json
[
  {{
    "start": 123.4,
    "end": 183.4,
    "reason": "선택 이유",
    "hook": "시청자를 사로잡는 첫 문장",
    "hashtags": ["#태그1", "#태그2", "#태그3"]
  }}
]
```
"""


def _parse_response(raw: str) -> list[SelectedClip]:
    # 코드블록 제거
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    data = json.loads(text.strip())

    clips = []
    for item in data:
        clips.append(
            SelectedClip(
                start=float(item["start"]),
                end=float(item["end"]),
                reason=item.get("reason", ""),
                hook=item.get("hook", ""),
                hashtags=item.get("hashtags", []),
            )
        )
    return clips
