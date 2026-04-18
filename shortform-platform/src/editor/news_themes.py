"""
뉴스 숏츠 테마 정의.
새 테마 추가: THEMES 딕셔너리에 항목 추가.
"""

# 공용 폰트 경로
_SANS_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
_SANS_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
_SERIF_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"

WHITE = (255, 255, 255, 255)
YELLOW = (255, 240, 0, 255)
BLACK = (0, 0, 0, 255)


THEMES = {
    # 삼프로tv 스타일: 상단 검정+굵은 흰 제목, 중앙 영상, 하단 검정+노란 자막
    "samprotv": {
        "display_name": "삼프로tv 스타일",
        "layout": "letterbox",       # letterbox | fullscreen
        "canvas": (1080, 1920),
        "letterbox": {
            "top_h": 630,            # 상단 검정 높이
            "vid_h": 810,            # 중앙 영상 4:3 (1080:810=4:3)
            "bot_h": 480,            # 하단 검정 높이 (630+810+480=1920)
            "bg": BLACK,
        },
        "title": {
            "font": _SANS_BOLD,
            "size": 96,
            "color": WHITE,
            "stroke_w": 0,
            "stroke_color": BLACK,
            "line_spacing": 14,
            "max_width": 0.88,
            "area": "top",           # top | bottom | center
        },
        "caption": {
            "font": _SANS_BOLD,
            "size": 64,
            "color": YELLOW,
            "stroke_w": 5,
            "stroke_color": BLACK,
            "line_spacing": 10,
            "max_width": 0.92,
            "area": "bottom",
        },
    },

    # 유튜버 스타일: 얇은 상/하 검정, 큰 중앙 영상, 영상 위 빨간 스티커 자막
    "youtuber": {
        "display_name": "유튜버 스타일 (고정 제목 + 스티커 자막)",
        "layout": "letterbox",
        "canvas": (1080, 1920),
        "letterbox": {
            "top_h": 290,      # 15% 상단 검정 (고정 제목용)
            "vid_h": 1320,     # 69% 중앙 영상 (풀폭)
            "bot_h": 310,      # 16% 하단 검정 (고정 브랜딩)
            "bg": BLACK,
        },
        "fixed_title": True,             # 모든 세그먼트 같은 제목 사용
        "fixed_bottom_text": "구독&공유",   # 하단 고정 브랜딩
        "title": {
            "font": _SANS_BOLD,
            "size": 72,
            "color": WHITE,
            "stroke_w": 0,
            "stroke_color": BLACK,
            "line_spacing": 8,
            "max_width": 0.90,
            "area": "top",
        },
        "caption": {
            "font": _SANS_BOLD,
            "size": 72,
            "color": (220, 30, 30, 255),   # 빨강
            "stroke_w": 8,
            "stroke_color": WHITE,          # 두꺼운 흰색 테두리 (스티커 느낌)
            "line_spacing": 12,
            "max_width": 0.85,
            "area": "video_bottom_overlay", # 영상 하단부 위에 오버레이
        },
        "bottom_brand": {
            "font": _SANS_BOLD,
            "size": 68,
            "color": WHITE,
            "stroke_w": 0,
            "stroke_color": BLACK,
            "line_spacing": 0,
            "max_width": 0.6,
            "area": "bottom",
        },
    },

    # 풀스크린 오버레이: 영상 전체, 제목은 화면 상단 1/3, 자막 하단
    "fullscreen_overlay": {
        "display_name": "풀스크린 오버레이",
        "layout": "fullscreen",
        "canvas": (1080, 1920),
        "title": {
            "font": _SANS_BOLD,
            "size": 88,
            "color": WHITE,
            "stroke_w": 6,
            "stroke_color": BLACK,
            "line_spacing": 12,
            "max_width": 0.88,
            "area": "top_overlay",    # 화면 상단 오버레이 (y 15%~35%)
        },
        "caption": {
            "font": _SANS_BOLD,
            "size": 58,
            "color": YELLOW,
            "stroke_w": 5,
            "stroke_color": BLACK,
            "line_spacing": 8,
            "max_width": 0.92,
            "area": "bottom_overlay", # 화면 하단 오버레이 (y 80%)
        },
    },
}


def get_theme(name: str) -> dict:
    """테마 조회. 없으면 samprotv 반환."""
    return THEMES.get(name, THEMES["samprotv"])


def list_themes() -> list[dict]:
    """UI 표시용 테마 목록."""
    return [{"id": k, "name": v["display_name"]} for k, v in THEMES.items()]
