"""유튜버 테마 테스트"""
import sys; sys.path.insert(0, '/app')
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Seg:
    media_path: str
    text_content: str
    caption: str
    duration: float

@dataclass
class Script:
    title: str = "인도 모디 총리가 이 대통령 초청한 이유"
    segments: list = None

temp_dir = Path("/app/temp/news_이란이_해협_열자_미국_증시_폭등했다")
segs = []
test_data = [
    ("이거 하나만 알면 끝", "대통령이 인도 국빈 방문하는 이유", 3.0),
    ("알고보니 놀라운 사실", "무려 8년 만의 한국 대통령 국빈 방문이다", 3.5),
    ("결론은 이것", "에너지 공급망 공조다", 3.0),
]

for i, (title, caption, dur) in enumerate(test_data):
    media = temp_dir / f"seg_{i:02d}.mp4"
    if media.exists():
        segs.append(Seg(str(media), title, caption, dur))

script = Script(segments=segs)

from src.editor.news_direct_renderer import render_news_shorts
out = render_news_shorts(script, "/app/output/test_youtuber.mp4", theme_id="youtuber")
import os
print(f"OK: {out} ({os.path.getsize(out)/1024/1024:.2f}MB)")
