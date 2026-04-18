"""
Claude API를 사용해 긴 영상을 숏츠 한 편으로 기획합니다.
단순 구간 선택이 아닌, 여러 구간을 조합한 내러티브 스크립트를 생성합니다.
"""

import json
import os
from dataclasses import dataclass

import anthropic

from src.extractor.transcript import Segment, to_full_text


# ── 기존 모델 (MP4 직접 렌더 파이프라인용) ──────────────────────────────────

@dataclass
class SelectedClip:
    start: float
    end: float
    reason: str
    hook: str
    hashtags: list[str]


# ── 숏츠 기획 모델 ──

@dataclass
class ScriptSegment:
    start: float       # 원본 영상 기준 시작 (초)
    end: float         # 원본 영상 기준 종료 (초)
    caption: str       # 이 구간에 표시할 자막
    text_overlay: str  # 강조 오버레이 텍스트 (없으면 빈 문자열)
    role: str          # "hook" | "content" | "outro"


@dataclass
class ShortsScript:
    title: str                    # 숏츠 제목 (훅 문구)
    description: str              # 업로드용 설명
    hashtags: list[str]
    segments: list[ScriptSegment] # 타임라인 순서대로 조합할 구간들


# ── 숏츠 기획 파이프라인 ──

def plan_shorts(
    segments: list[Segment],
    title: str,
    target_duration: int = 60,
    style: str = "general",
) -> ShortsScript:
    """
    전체 자막을 분석해 숏츠 한 편의 기획을 반환합니다.
    여러 구간을 원본과 다른 순서로 조합할 수 있습니다.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    transcript_text = to_full_text(segments)

    prompt = _build_plan_prompt(title, transcript_text, target_duration, style)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_script(message.content[0].text)


def _build_plan_prompt(title: str, transcript: str, target_duration: int, style: str) -> str:
    style_guide = {
        "general":       "흥미롭고 임팩트 있는 구성",
        "education":     "핵심 개념을 명확하게 전달하는 구성",
        "entertainment": "웃음·감동·놀라움으로 끝까지 보게 만드는 구성",
        "news":          "핵심 팩트를 빠르게 전달하는 구성",
    }.get(style, "흥미롭고 임팩트 있는 구성")

    return f"""당신은 숏폼 영상 전문 PD입니다.
아래 긴 영상의 자막 전체를 분석해서, 숏츠(TikTok/Reels/Shorts) 한 편을 기획해 주세요.

## 기획 원칙
- 단순히 연속된 구간을 자르는 게 아니라, 영상의 여러 부분에서 가장 임팩트 있는 순간들을 골라 재조합하세요
- 전체 길이: {target_duration}초 내외 (각 segment의 duration 합산)
- 스타일: {style_guide}
- 구성: 강렬한 훅(hook) → 핵심 내용 → 마무리 CTA
- **자연스러운 컷을 위해**: start는 반드시 새 문장/발화가 시작되는 시점, end는 문장이 완전히 끝난 직후로 설정하세요. 단어 중간이나 문장 중간에서 자르지 마세요.

## 영상 제목
{title}

## 전체 자막 (타임스탬프 포함)
{transcript}

## 출력 형식 (JSON만, 설명 없이)
```json
{{
  "title": "시청자를 사로잡는 숏츠 제목",
  "description": "업로드할 때 쓸 설명문 (2~3줄)",
  "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5"],
  "segments": [
    {{
      "start": 123.4,
      "end": 131.2,
      "caption": "이 구간에 표시될 자막 텍스트",
      "text_overlay": "강조할 큰 텍스트 (없으면 빈 문자열)",
      "role": "hook"
    }},
    {{
      "start": 45.0,
      "end": 58.5,
      "caption": "자막 텍스트",
      "text_overlay": "",
      "role": "content"
    }},
    {{
      "start": 210.0,
      "end": 220.0,
      "caption": "마무리 자막",
      "text_overlay": "구독 & 좋아요",
      "role": "outro"
    }}
  ]
}}
```

segments는 타임라인 순서대로 나열하세요. start/end는 원본 영상 기준 초 단위입니다.
"""


def _parse_script(raw: str) -> ShortsScript:
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    data = json.loads(text.strip())

    segments = [
        ScriptSegment(
            start=float(s["start"]),
            end=float(s["end"]),
            caption=s.get("caption", ""),
            text_overlay=s.get("text_overlay", ""),
            role=s.get("role", "content"),
        )
        for s in data["segments"]
    ]

    return ShortsScript(
        title=data.get("title", ""),
        description=data.get("description", ""),
        hashtags=data.get("hashtags", []),
        segments=segments,
    )


# ── 기존 파이프라인 (MP4 렌더용, 하위 호환) ─────────────────────────────────

def select_clips(
    segments: list[Segment],
    title: str,
    duration_sec: int = 60,
    num_clips: int = 3,
    style: str = "general",
) -> list[SelectedClip]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    transcript_text = to_full_text(segments)
    prompt = _build_select_prompt(title, transcript_text, duration_sec, num_clips, style)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_clips(message.content[0].text)


def _build_select_prompt(title, transcript, duration_sec, num_clips, style):
    style_guide = {
        "general":       "시청자의 관심을 끄는 흥미롭고 임팩트 있는 구간",
        "education":     "핵심 개념이나 인사이트가 담긴 교육적 구간",
        "entertainment": "웃음, 감동, 놀라움 등 감정을 자극하는 구간",
        "news":          "핵심 팩트나 중요한 발언이 담긴 구간",
    }.get(style, "흥미롭고 임팩트 있는 구간")

    return f"""당신은 숏폼 영상 전문 편집자입니다.
아래 영상의 자막을 분석해 TikTok/YouTube Shorts/Instagram Reels에 적합한 구간을 선택해 주세요.

## 영상 제목
{title}

## 선택 기준
- {style_guide}
- 각 클립은 약 {duration_sec}초 분량
- 시작은 강렬한 훅(hook)으로 시작해야 함

## 자막 (타임스탬프 포함)
{transcript}

## 요청
숏폼에 가장 적합한 구간 {num_clips}개를 선택하고, 아래 JSON 형식으로만 응답해 주세요.

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


def _parse_clips(raw: str) -> list[SelectedClip]:
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    data = json.loads(text.strip())
    return [
        SelectedClip(
            start=float(item["start"]),
            end=float(item["end"]),
            reason=item.get("reason", ""),
            hook=item.get("hook", ""),
            hashtags=item.get("hashtags", []),
        )
        for item in data
    ]
