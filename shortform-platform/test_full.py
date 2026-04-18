"""모든 기능 통합 테스트"""
import sys; sys.path.insert(0, '/app')
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Seg:
    media_path: str
    text_content: str = ""
    caption: str = ""
    duration: float = 3.0
    role: str = "body"
    emphasis_words: list = field(default_factory=list)
    pivot_phrase: str = ""
    highlight_stat: str = ""
    reaction_emoji: str = ""
    caption_chunks: list = field(default_factory=list)

@dataclass
class Script:
    title: str = "미국-이란 종전 기대 증시 폭등 유가 폭락"
    hook_phrase: str = "이란 한 마디에\n월가가 폭발했다"
    description: str = "test"
    hashtags: list = field(default_factory=list)
    segments: list = field(default_factory=list)

temp_dir = Path("/app/temp/news_이란이_해협_열자_미국_증시_폭등했다")
segs = []
tests = [
    dict(text_content="", role="hook", caption="이란 한마디에 월가가 폭발했어요",
         caption_chunks=["이란 한마디에", "월가가 폭발"], emphasis_words=["월가"],
         reaction_emoji="💥", duration=2.5),
    dict(text_content="", role="body", caption="다우 1.79% 급등, 869포인트 올랐어요",
         caption_chunks=["다우 1.79% 급등", "869포인트!"], emphasis_words=["다우", "1.79%"],
         highlight_stat="+1.79%", duration=3.5),
    dict(text_content="", role="climax", caption="나스닥은 13일 연속 상승 1992년 이후 최장",
         caption_chunks=["나스닥", "13일 연속", "1992년 이후 최장"],
         emphasis_words=["나스닥", "13일"], highlight_stat="13일 연속",
         reaction_emoji="🚀", duration=5.0),
    dict(text_content="", role="twist", caption="반면 유가는 11% 폭락했어요",
         caption_chunks=["유가는 반대로", "11% 폭락"], emphasis_words=["11%", "폭락"],
         highlight_stat="-11%", reaction_emoji="📉", duration=3.0),
]
for i, t in enumerate(tests):
    media = temp_dir / f"seg_{i:02d}.mp4"
    if media.exists():
        segs.append(Seg(media_path=str(media), **t))

script = Script(segments=segs)

from src.editor.news_direct_renderer import render_news_shorts
out = render_news_shorts(
    script, "/app/output/test_full.mp4",
    theme_id="samprotv",
    ticker_text="속보 | 뉴욕증시 폭등 | 나스닥 13일 연속 | WTI -11% | 2차 협상 이슬라마바드",
    enable_transitions=True,
    enable_tts=False,      # TTS는 비용 발생 → 일단 False
    enable_bgm=False,      # BGM 파일 없으면 자동 skip
)
import os
print(f"OK: {out} ({os.path.getsize(out)/1024/1024:.2f}MB)")
