"""직접 렌더링 테스트 - 기존 생성된 프로젝트의 미디어를 이용."""
import sys
sys.path.insert(0, '/app')

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
    title: str = "테스트"
    segments: list = None

# 최근 생성된 temp 디렉토리 사용
temp_dir = Path("/app/temp/news_이란이_해협_열자_미국_증시_폭등했다")
segs = []
test_data = [
    ("이란이 해협을 열었다\n미국 증시가 터졌다 🔥", "이란이 호르무즈 해협을 개방하자 뉴욕 증시가 폭발적으로 반응했습니다.", 3.0),
    ("다우존스\n+1.79% 급등", "다우존스 지수가 869포인트 급등하며 4만 9천을 돌파했습니다.", 3.5),
    ("나스닥\n13일 연속 상승\n1992년 이후 최장", "나스닥은 무려 13일 연속 상승, 1992년 이후 33년만에 최장기록입니다.", 4.0),
]

for i, (title, caption, dur) in enumerate(test_data):
    media = temp_dir / f"seg_{i:02d}.mp4"
    if not media.exists():
        print(f"skip seg_{i:02d}: no media")
        continue
    segs.append(Seg(str(media), title, caption, dur))

script = Script(segments=segs)

from src.editor.news_direct_renderer import render_news_shorts
out = render_news_shorts(script, "/app/output/test_direct.mp4")
print(f"생성 완료: {out}")

import os
print(f"파일 크기: {os.path.getsize(out)/1024/1024:.2f} MB")
