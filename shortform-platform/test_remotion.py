"""Remotion 렌더 테스트"""
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
    highlight_stat: str = ""
    reaction_emoji: str = ""
    caption_chunks: list = field(default_factory=list)

@dataclass
class Script:
    title: str = "미국-이란 종전 증시 폭등"
    hook_phrase: str = "이란 한 마디에\n월가가 폭발했다"
    segments: list = field(default_factory=list)

temp_dir = Path("/app/temp/news_이란이_해협_열자_미국_증시_폭등했다")
segs = [
    Seg(str(temp_dir / "seg_00.mp4"), role="hook",
        caption="이란이 한마디에 월가가 터졌어요",
        caption_chunks=["이란 한마디에", "월가가 폭발"],
        emphasis_words=["월가"], reaction_emoji="💥", duration=2.5),
    Seg(str(temp_dir / "seg_01.mp4"), role="body",
        caption="다우 1.79% 급등 869포인트",
        caption_chunks=["다우 1.79% 급등", "869포인트!"],
        emphasis_words=["1.79%"], highlight_stat="+1.79%", duration=3.5),
    Seg(str(temp_dir / "seg_02.mp4"), role="climax",
        caption="나스닥 13일 연속 최장 기록",
        caption_chunks=["나스닥 13일 연속", "1992년 이후 최장"],
        emphasis_words=["13일", "최장"], highlight_stat="13일 연속",
        reaction_emoji="🚀", duration=4.5),
]
segs = [s for s in segs if Path(s.media_path).exists()]
print(f"사용 세그먼트: {len(segs)}개")

script = Script(segments=segs)
from src.editor.news_remotion_renderer import render_news_shorts_remotion
import time
start = time.time()
out = render_news_shorts_remotion(script, "/app/output/test_remotion.mp4", theme_id="samprotv")
elapsed = time.time() - start
import os
print(f"OK: {out} ({os.path.getsize(out)/1024/1024:.2f}MB) — {elapsed:.1f}s")
