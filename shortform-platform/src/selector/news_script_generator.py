"""
뉴스 텍스트 → 숏츠 스크립트 기획 (미디어 타입 포함)
"""

import json
import os
from dataclasses import dataclass, field

import anthropic


@dataclass
class MediaSegment:
    text_content: str    # 화면에 크게 표시할 텍스트 (2~3줄)
    caption: str         # 읽히는 자막
    media_type: str      # "video" | "photo" | "graphic"
    search_keyword: str  # 검색 키워드 (graphic이면 빈 문자열)
    duration: float      # 이 구간 길이 (초)
    graphic_style: str   # "dark_navy"|"dark_red"|"dark_green"|"dark_gold" (graphic일 때)
    media_path: str = "" # 수집 후 채워짐


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

    prompt = f"""당신은 숏폼 영상 전문 PD입니다.
아래 뉴스 내용을 분석해서 TikTok/Reels/Shorts 스타일의 숏츠 한 편을 기획해 주세요.

## 스타일 레퍼런스
- "동남아 기준으로 환산한 한국 군사력" 같은 비교/통계 중심 숏츠
- 각 장면: 굵은 텍스트 + 배경 미디어 조합
- 빠른 컷 (2~5초/장면)
- 숫자, 비교, 놀라운 팩트 강조

## 뉴스 제목
{title or "(없음)"}

## 뉴스 내용
{text}

## 기획 원칙
- 전체 길이: {target_duration}초 내외
- 각 segment의 duration 합산이 목표 길이가 되도록
- text_content: 화면에 크게 표시할 핵심 문구 (2~3줄, 짧고 임팩트 있게)
- caption: 내레이션/자막으로 읽힐 전체 문장
- media_type: 장면에 어울리는 미디어 타입
  - "video": 실제 동작이 중요한 장면 (시위, 폭발, 군사훈련, 시장 현장 등)
  - "photo": 인물, 장소, 통계/숫자/차트 장면 — 배경 사진/차트 위에 텍스트를 올림. 주가, 지수, 퍼센트, 유가 등 숫자 데이터는 반드시 photo 사용
  - "graphic": 오직 영상의 첫 인트로 또는 마지막 팔로우 유도 장면에만 사용. 절대 중간 장면에 사용 금지. 전체 영상에서 최대 2개만 허용
- search_keyword: 반드시 영어로 작성 (YouTube/Pixabay 검색용). graphic이면 빈 문자열. photo/video는 반드시 구체적인 영어 키워드 필수
  - 주가/지수 장면: "stock market chart green", "nasdaq index chart rising", "S&P 500 stock chart"
  - 유가 장면: "oil price chart falling", "crude oil barrel price drop"
  - 인물: "Trump press conference", "diplomat meeting"
  - 장소: "New York Stock Exchange floor", "city skyline"
- graphic_style: graphic일 때만
  - "dark_navy" (파랑 계열)
  - "dark_red" (빨강 계열)
  - "dark_green" (초록 계열)
  - "dark_gold" (금색 계열)

## 출력 (JSON만, 설명 없이)
```json
{{
  "title": "시청자를 사로잡는 숏츠 제목",
  "description": "업로드용 설명 2~3줄",
  "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5"],
  "segments": [
    {{
      "text_content": "화면에 표시할\\n핵심 문구",
      "caption": "내레이션으로 읽힐 전체 문장입니다.",
      "media_type": "graphic",
      "search_keyword": "",
      "duration": 3.0,
      "graphic_style": "dark_navy"
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

    segments = [
        MediaSegment(
            text_content=s["text_content"],
            caption=s.get("caption", ""),
            media_type=s.get("media_type", "graphic"),
            search_keyword=s.get("search_keyword", ""),
            duration=float(s.get("duration", 3.0)),
            graphic_style=s.get("graphic_style", "dark_navy"),
        )
        for s in data["segments"]
    ]
    return NewsScript(
        title=data.get("title", ""),
        description=data.get("description", ""),
        hashtags=data.get("hashtags", []),
        segments=segments,
    )
