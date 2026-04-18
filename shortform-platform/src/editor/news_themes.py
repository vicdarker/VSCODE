"""
뉴스 숏츠 테마 정의.
새 테마 추가: THEMES 딕셔너리에 항목 추가.
"""

# 공용 폰트 경로
_SANS_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
_SANS_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
_SERIF_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
_BLACK_HAN_SANS = "/app/assets/fonts/BlackHanSans-Regular.ttf"  # 숏폼용 굵은 블록체


# 사용자 선택용 폰트 레지스트리 (UI 드롭다운 값 → 파일 경로)
FONT_REGISTRY: dict[str, dict] = {
    "noto_sans_bold":   {"path": _SANS_BOLD,                                        "name": "Noto Sans Bold (기본)",     "ttc_index": 2},
    "black_han_sans":   {"path": _BLACK_HAN_SANS,                                   "name": "Black Han Sans (숏폼)"},
    "jua":              {"path": "/app/assets/fonts/Jua-Regular.ttf",               "name": "Jua (둥근 캐주얼)"},
    "do_hyeon":         {"path": "/app/assets/fonts/DoHyeon-Regular.ttf",           "name": "Do Hyeon (친근)"},
    "gasoek_one":       {"path": "/app/assets/fonts/GasoekOne-Regular.ttf",         "name": "Gasoek One (임팩트)"},
    "gugi":             {"path": "/app/assets/fonts/Gugi-Regular.ttf",              "name": "Gugi (손글씨)"},
    "nanum_square_eb":  {"path": "/usr/share/fonts/truetype/nanum/NanumSquareEB.ttf","name": "NanumSquare ExtraBold"},
    "nanum_gothic_b":   {"path": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf","name": "NanumGothic Bold"},
    "nanum_myeongjo_eb":{"path": "/usr/share/fonts/truetype/nanum/NanumMyeongjoExtraBold.ttf","name": "NanumMyeongjo (신문체)"},
    "noto_serif_bold":  {"path": _SERIF_BOLD,                                       "name": "Noto Serif Bold",             "ttc_index": 2},
}


def resolve_font(font_id_or_path: str) -> str:
    """UI에서 넘어온 font_id를 실제 경로로. path가 직접 오면 그대로."""
    if not font_id_or_path:
        return _SANS_BOLD
    entry = FONT_REGISTRY.get(font_id_or_path)
    if entry:
        return entry["path"]
    return font_id_or_path  # 이미 경로

def list_fonts() -> list[dict]:
    return [{"id": k, "name": v["name"]} for k, v in FONT_REGISTRY.items()]

WHITE = (255, 255, 255, 255)
YELLOW = (255, 240, 0, 255)
BLACK = (0, 0, 0, 255)
RED = (220, 30, 30, 255)
ORANGE = (245, 130, 30, 255)
CYAN = (80, 220, 255, 255)
LIGHT_GRAY = (235, 235, 235, 255)


# ── 프리셋 vibe 메타 ──
# mood: shock / mourning / economy / celebrity / social / neutral / positive
# tone: formal / casual / bold / minimal / dramatic
# 기본 프리셋에 vibe 태그 달아두면 AI가 자동 추천 매핑.


THEMES = {
    # Remotion(React) 기반 프리미엄 — 애니메이션 제목/스프링 팝업/슬라이드 자막
    "remotion_samprotv": {
        "display_name": "프리미엄 (Remotion) - 삼프로tv 스타일 + 애니메이션",
        "layout": "letterbox",
        "canvas": (1080, 1920),
        "fixed_title": True,
        "engine": "remotion",      # ★ 이 플래그로 Remotion 렌더러 선택
        "remotion_theme_id": "samprotv",
    },
    "remotion_youtuber": {
        "display_name": "프리미엄 (Remotion) - 유튜버 스타일 + 애니메이션",
        "layout": "letterbox",
        "canvas": (1080, 1920),
        "fixed_title": True,
        "engine": "remotion",
        "remotion_theme_id": "youtuber",
    },

    # 삼프로tv 스타일: 상단 검정+굵은 흰 제목, 중앙 영상, 하단 검정+노란 자막
    "samprotv": {
        "display_name": "삼프로tv 스타일",
        "description": "상단 고정 타이틀, 중앙 영상, 하단 노란 자막. 경제·시사 뉴스 톤.",
        "vibe_moods": ["economy", "social", "neutral"],
        "vibe_tones": ["formal", "bold"],
        "layout": "letterbox",       # letterbox | fullscreen
        "canvas": (1080, 1920),
        "fixed_title": True,         # 상단은 hook_phrase 고정 (전 세그먼트 동일)
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
            "max_width": 0.82,
            "area": "bottom",
        },
    },

    # 바이럴 필박스: 첨부 이미지 레퍼런스 — Black Han Sans + 영상 위 검은 알약형 자막
    "viral_pill": {
        "display_name": "바이럴 필박스",
        "description": "Black Han Sans · 얇은 상/하, 영상 위 오버레이 자막. 범용 숏폼 뉴스.",
        "vibe_moods": ["shock", "celebrity", "social", "neutral"],
        "vibe_tones": ["bold", "casual"],
        "layout": "letterbox",
        "canvas": (1080, 1920),
        "letterbox": {
            "top_h": 290,      # 15% 상단 검정 — 2줄 타이틀
            "vid_h": 1280,     # 67% 중앙 영상
            "bot_h": 350,      # 18% 하단 브랜딩
            "bg": BLACK,
        },
        "fixed_title": True,
        "fixed_bottom_text": "구독 + 좋아요",
        "title": {
            "font": _BLACK_HAN_SANS,
            "size": 92,
            "color": WHITE,
            "stroke_w": 0,
            "stroke_color": BLACK,
            "line_spacing": 10,
            "max_width": 0.90,
            "area": "top",
            "accent_last_line": True,    # 마지막 줄 노랑
            "accent_color": YELLOW,
        },
        "caption": {
            "font": _BLACK_HAN_SANS,
            "size": 72,
            "color": YELLOW,
            "stroke_w": 8,                    # 배경 대신 두꺼운 검정 외곽선
            "stroke_color": BLACK,
            "line_spacing": 10,
            "max_width": 0.82,
            "area": "video_bottom_overlay",   # 영상 하단에 텍스트만
        },
        "bottom_brand": {
            "font": _BLACK_HAN_SANS,
            "size": 86,
            "color": WHITE,
            "stroke_w": 0,
            "stroke_color": BLACK,
            "line_spacing": 0,
            "max_width": 0.8,
            "area": "bottom",
        },
    },

    # 이슈?잇츄! 레퍼런스 — 빨강 타이틀 바 + 자극적 타이포
    "issue_chu": {
        "display_name": "이슈?잇츄! (바이럴·자극)",
        "description": "빨강+노랑+검정 대비. 이슈·가십 뉴스에 최적.",
        "vibe_moods": ["shock", "celebrity", "social"],
        "vibe_tones": ["bold", "dramatic", "casual"],
        "layout": "letterbox",
        "canvas": (1080, 1920),
        "letterbox": {"top_h": 320, "vid_h": 1240, "bot_h": 360, "bg": BLACK},
        "fixed_title": True,
        "fixed_bottom_text": "이슈? 잇츄!",
        "title": {
            "font": "/app/assets/fonts/GasoekOne-Regular.ttf",
            "size": 96, "color": WHITE,
            "stroke_w": 0, "stroke_color": BLACK,
            "line_spacing": 10, "max_width": 0.92,
            "area": "top",
            "accent_last_line": True,
            "accent_color": YELLOW,
        },
        "caption": {
            "font": _BLACK_HAN_SANS,
            "size": 74, "color": YELLOW,
            "stroke_w": 10, "stroke_color": BLACK,
            "line_spacing": 12, "max_width": 0.80,
            "area": "video_bottom_overlay",
        },
        "bottom_brand": {
            "font": "/app/assets/fonts/GasoekOne-Regular.ttf",
            "size": 90, "color": RED,
            "stroke_w": 0, "stroke_color": BLACK,
            "line_spacing": 0, "max_width": 0.8, "area": "bottom",
        },
    },

    # YTN 속보 스타일 — 빨강 BREAKING 배너 + 정통 serif
    "ytn_breaking": {
        "display_name": "YTN 속보 (정통 뉴스)",
        "description": "빨강 배너 + 세리프 타이틀. 정치·사건·속보에 적합.",
        "vibe_moods": ["social", "shock", "mourning", "neutral"],
        "vibe_tones": ["formal", "dramatic"],
        "layout": "letterbox",
        "canvas": (1080, 1920),
        "letterbox": {"top_h": 380, "vid_h": 1220, "bot_h": 320, "bg": (30, 0, 0, 255)},
        "fixed_title": True,
        "fixed_bottom_text": "속보",
        "title": {
            "font": _SERIF_BOLD, "ttc_index": 2,
            "size": 80, "color": WHITE,
            "stroke_w": 0, "stroke_color": BLACK,
            "line_spacing": 10, "max_width": 0.92,
            "area": "top",
            "accent_last_line": True,
            "accent_color": (255, 200, 0, 255),
        },
        "caption": {
            "font": _SANS_BOLD,
            "size": 62, "color": WHITE,
            "stroke_w": 7, "stroke_color": BLACK,
            "line_spacing": 10, "max_width": 0.85,
            "area": "video_bottom_overlay",
        },
        "bottom_brand": {
            "font": _SERIF_BOLD,
            "size": 92, "color": (255, 80, 80, 255),
            "stroke_w": 0, "stroke_color": BLACK,
            "line_spacing": 0, "max_width": 0.8, "area": "bottom",
        },
    },

    # 미니멀 화이트 — 흰 배경 + 회색 자막, 잔잔
    "minimal_white": {
        "display_name": "미니멀 (깔끔·차분)",
        "description": "흰 배경, 블랙 타이틀, 스트로크 없음. 경제·IT·문화 뉴스.",
        "vibe_moods": ["economy", "neutral", "positive"],
        "vibe_tones": ["minimal", "formal"],
        "layout": "letterbox",
        "canvas": (1080, 1920),
        "letterbox": {"top_h": 340, "vid_h": 1260, "bot_h": 320, "bg": (245, 245, 248, 255)},
        "fixed_title": True,
        "fixed_bottom_text": "",
        "title": {
            "font": _SANS_BOLD,
            "size": 82, "color": (20, 20, 25, 255),
            "stroke_w": 0, "stroke_color": WHITE,
            "line_spacing": 10, "max_width": 0.88,
            "area": "top",
            "accent_last_line": True,
            "accent_color": (70, 130, 240, 255),
        },
        "caption": {
            "font": _SANS_BOLD,
            "size": 64, "color": (30, 30, 35, 255),
            "stroke_w": 0, "stroke_color": WHITE,
            "line_spacing": 10, "max_width": 0.85,
            "area": "bottom",
        },
    },

    # 충격 레드 — 빨강+검정, 피 색, 가장 자극적
    "shock_red": {
        "display_name": "충격 레드 (극적·자극)",
        "description": "검정+빨강 피 색, 두꺼운 타이포. 충격적 사건·고발 뉴스.",
        "vibe_moods": ["shock", "mourning", "social"],
        "vibe_tones": ["dramatic", "bold"],
        "layout": "letterbox",
        "canvas": (1080, 1920),
        "letterbox": {"top_h": 310, "vid_h": 1250, "bot_h": 360, "bg": (15, 0, 0, 255)},
        "fixed_title": True,
        "fixed_bottom_text": "충격",
        "title": {
            "font": _BLACK_HAN_SANS,
            "size": 94, "color": WHITE,
            "stroke_w": 0, "stroke_color": BLACK,
            "line_spacing": 10, "max_width": 0.92,
            "area": "top",
            "accent_last_line": True,
            "accent_color": (255, 30, 30, 255),
        },
        "caption": {
            "font": _BLACK_HAN_SANS,
            "size": 72, "color": (255, 255, 255, 255),
            "stroke_w": 10, "stroke_color": (140, 0, 0, 255),
            "line_spacing": 10, "max_width": 0.82,
            "area": "video_bottom_overlay",
        },
        "bottom_brand": {
            "font": _BLACK_HAN_SANS,
            "size": 96, "color": (255, 30, 30, 255),
            "stroke_w": 0, "stroke_color": BLACK,
            "line_spacing": 0, "max_width": 0.8, "area": "bottom",
        },
    },

    # 유튜버 스타일: 얇은 상/하 검정, 큰 중앙 영상, 영상 위 빨간 스티커 자막
    "youtuber": {
        "display_name": "유튜버 스타일 (고정 제목 + 스티커 자막)",
        "description": "빨간 스티커 자막. 가벼운 이슈·연예 뉴스.",
        "vibe_moods": ["celebrity", "neutral"],
        "vibe_tones": ["casual", "bold"],
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


_COLOR_KEYS = {"color", "stroke_color", "accent_color", "bg", "pill_bg"}


def _normalize_value(key: str, v):
    """JSON list → tuple 변환 (색상 필드). PIL은 tuple 필요."""
    if key in _COLOR_KEYS and isinstance(v, list):
        return tuple(v)
    return v


def _deep_merge(base: dict, overrides: dict) -> dict:
    """dict deep-merge. overrides의 None 값은 무시.
    override가 dict이면 base에 해당 키가 없어도 재귀 머지 (빈 dict로 취급) —
    그래야 내부 색상 list → tuple 정규화가 적용됨.
    """
    out = dict(base)
    for k, v in (overrides or {}).items():
        if v is None:
            continue
        if isinstance(v, dict):
            base_sub = out.get(k) if isinstance(out.get(k), dict) else {}
            out[k] = _deep_merge(base_sub, v)
        else:
            out[k] = _normalize_value(k, v)
    return out


def apply_overrides(theme: dict, overrides: dict | None) -> dict:
    """
    UI에서 보낸 overrides를 테마에 병합.
    font_id는 FONT_REGISTRY로 resolve해서 font 경로로 치환.
    """
    if not overrides:
        return theme
    cleaned = dict(overrides)
    # font_id → font 경로 resolve (title/caption/bottom_brand 각각)
    for section in ("title", "caption", "bottom_brand"):
        sec = cleaned.get(section)
        if isinstance(sec, dict) and sec.get("font_id"):
            sec = dict(sec)
            sec["font"] = resolve_font(sec.pop("font_id"))
            cleaned[section] = sec
    # layout 비율 override (top_h/vid_h/bot_h)
    layout = cleaned.get("layout")
    if isinstance(layout, dict):
        merged_lb = dict(theme.get("letterbox", {}))
        merged_lb.update({k: v for k, v in layout.items() if v is not None})
        # 합이 canvas height 유지되도록 강제
        W, H = theme.get("canvas", (1080, 1920))
        total = merged_lb.get("top_h", 0) + merged_lb.get("vid_h", 0) + merged_lb.get("bot_h", 0)
        if total != H and total > 0:
            # 비율 유지 스케일
            s = H / total
            merged_lb["top_h"] = int(merged_lb["top_h"] * s)
            merged_lb["vid_h"] = int(merged_lb["vid_h"] * s)
            merged_lb["bot_h"] = H - merged_lb["top_h"] - merged_lb["vid_h"]
        cleaned["letterbox"] = merged_lb
        del cleaned["layout"]
    return _deep_merge(theme, cleaned)


def list_themes() -> list[dict]:
    """UI 표시용 테마 목록 (레거시)."""
    return [{"id": k, "name": v["display_name"]} for k, v in THEMES.items()]


# Remotion 테마와 fullscreen_overlay 등은 프리셋 카드에선 숨김
_PRESET_EXCLUDE = {"fullscreen_overlay"}


def _path_to_font_id(path: str) -> str:
    if not path:
        return ""
    for fid, entry in FONT_REGISTRY.items():
        if entry["path"] == path:
            return fid
    return ""


def _rgba_to_hex(c) -> str:
    if not c or not isinstance(c, (tuple, list)) or len(c) < 3:
        return "#ffffff"
    r, g, b = int(c[0]), int(c[1]), int(c[2])
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def get_preset_ui_config(preset_id: str) -> dict:
    """프리셋의 config → UI 입력값 형태로 평탄화 (hex 색상, font_id 등)."""
    theme = get_theme(preset_id)
    lb = theme.get("letterbox", {}) or {}
    t  = theme.get("title", {}) or {}
    c  = theme.get("caption", {}) or {}
    b  = theme.get("bottom_brand", {}) or {}
    return {
        "layout": {
            "top_h": lb.get("top_h", 290),
            "vid_h": lb.get("vid_h", 1280),
            "bot_h": lb.get("bot_h", 350),
        },
        "title": {
            "size": t.get("size", 92),
            "font_id": _path_to_font_id(t.get("font", "")),
            "color_hex": _rgba_to_hex(t.get("color")),
            "accent_last_line": bool(t.get("accent_last_line", False)),
            "accent_color_hex": _rgba_to_hex(t.get("accent_color") or (255, 240, 0, 255)),
        },
        "caption": {
            "area": c.get("area", "video_bottom_overlay"),
            "size": c.get("size", 72),
            "font_id": _path_to_font_id(c.get("font", "")),
            "color_hex": _rgba_to_hex(c.get("color")),
            "stroke_w": c.get("stroke_w", 8),
        },
        "fixed_bottom_text": theme.get("fixed_bottom_text", ""),
        "bottom_brand": {"size": b.get("size", 86)},
    }


def list_presets() -> list[dict]:
    """UI 카드 그리드용. Remotion/fullscreen은 숨김. vibe 태그는 클라이언트 2축 필터용."""
    out = []
    for k, v in THEMES.items():
        if k in _PRESET_EXCLUDE or v.get("engine") == "remotion":
            continue
        out.append({
            "id": k,
            "name": v.get("display_name", k),
            "description": v.get("description", ""),
            "vibe_moods": v.get("vibe_moods", []),
            "vibe_tones": v.get("vibe_tones", []),
            "thumbnail_url": f"/static/previews/preset_{k}.jpg",
        })
    return out
