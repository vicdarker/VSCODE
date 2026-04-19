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
_FONT_DIR = "/opt/korean-fonts"

FONT_REGISTRY: dict[str, dict] = {
    # ─ Pretendard 9 weights (가장 인기 있는 모던 한글 고딕) ─
    "pretendard_thin":       {"path": f"{_FONT_DIR}/Pretendard-Thin.otf",       "name": "Pretendard Thin (얇음)"},
    "pretendard_extralight": {"path": f"{_FONT_DIR}/Pretendard-ExtraLight.otf", "name": "Pretendard ExtraLight"},
    "pretendard_light":      {"path": f"{_FONT_DIR}/Pretendard-Light.otf",      "name": "Pretendard Light"},
    "pretendard_regular":    {"path": f"{_FONT_DIR}/Pretendard-Regular.otf",    "name": "Pretendard Regular"},
    "pretendard_medium":     {"path": f"{_FONT_DIR}/Pretendard-Medium.otf",     "name": "Pretendard Medium"},
    "pretendard_semibold":   {"path": f"{_FONT_DIR}/Pretendard-SemiBold.otf",   "name": "Pretendard SemiBold"},
    "pretendard_bold":       {"path": f"{_FONT_DIR}/Pretendard-Bold.otf",       "name": "Pretendard Bold ⭐"},
    "pretendard_extrabold":  {"path": f"{_FONT_DIR}/Pretendard-ExtraBold.otf",  "name": "Pretendard ExtraBold"},
    "pretendard_black":      {"path": f"{_FONT_DIR}/Pretendard-Black.otf",      "name": "Pretendard Black (극굵)"},
    # ─ 배달의민족 시리즈 ─
    "bm_dohyeon":            {"path": f"{_FONT_DIR}/BMDOHYEON.ttf",             "name": "배민 도현 (굵은 고딕)"},
    "bm_jua":                {"path": f"{_FONT_DIR}/BMJUA.ttf",                 "name": "배민 주아 (둥글 캐주얼)"},
    "bm_hanna":              {"path": f"{_FONT_DIR}/BMHANNAPro.ttf",            "name": "배민 한나 (정통)"},
    "bm_yeonsung":           {"path": f"{_FONT_DIR}/BMYEONSUNG.ttf",            "name": "배민 연성 (네오 고딕)"},
    "bm_euljiro":            {"path": f"{_FONT_DIR}/BMEULJIRO.ttf",             "name": "배민 을지로체 (레트로)"},
    # ─ 여기어때 잘난체 (극굵 블록체) ─
    "jalnan_gothic":         {"path": f"{_FONT_DIR}/JalnanGothic.ttf",          "name": "여기어때 잘난체 (초굵 블록) ⭐"},
    # ─ Cafe24 시리즈 ─
    "cafe24_dangdanghae":    {"path": f"{_FONT_DIR}/Cafe24Dangdanghae.ttf",     "name": "Cafe24 당당해 (당당)"},
    "cafe24_ssurround":      {"path": f"{_FONT_DIR}/Cafe24Ssurround.ttf",       "name": "Cafe24 써라운드 (둥근)"},
    "cafe24_ohsquare":       {"path": f"{_FONT_DIR}/Cafe24Ohsquare.ttf",        "name": "Cafe24 오스퀘어 (각진)"},
    "cafe24_syongsyong":     {"path": f"{_FONT_DIR}/Cafe24Syongsyong.ttf",      "name": "Cafe24 숑숑 (귀여운)"},
    # ─ 산세리프 (고딕) — 모던·굵기 다양 ─
    "noto_sans_bold":       {"path": _SANS_BOLD,                                                 "name": "Noto Sans Bold (기본)",        "ttc_index": 2},
    "nanum_gothic_b":       {"path": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",       "name": "NanumGothic Bold"},
    "nanum_gothic_extra_b": {"path": "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf",  "name": "NanumGothic ExtraBold (극굵)"},
    "nanum_barun_gothic_b": {"path": "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",  "name": "NanumBarunGothic Bold (모던)"},
    "nanum_square_eb":      {"path": "/usr/share/fonts/truetype/nanum/NanumSquareEB.ttf",         "name": "NanumSquare ExtraBold (각진)"},
    "nanum_square_round_eb":{"path": "/usr/share/fonts/truetype/nanum/NanumSquareRoundEB.ttf",    "name": "NanumSquareRound ExtraBold (둥근각)"},
    # ─ 임팩트·숏폼 전용 ─
    "black_han_sans":       {"path": _BLACK_HAN_SANS,                                             "name": "Black Han Sans (숏폼·블록체)"},
    "gasoek_one":           {"path": "/app/assets/fonts/GasoekOne-Regular.ttf",                   "name": "Gasoek One (임팩트·강렬)"},
    # ─ 둥글고 캐주얼 ─
    "jua":                  {"path": "/app/assets/fonts/Jua-Regular.ttf",                         "name": "Jua (둥근 캐주얼)"},
    "do_hyeon":             {"path": "/app/assets/fonts/DoHyeon-Regular.ttf",                     "name": "Do Hyeon (친근)"},
    # ─ 손글씨 ─
    "gugi":                 {"path": "/app/assets/fonts/Gugi-Regular.ttf",                        "name": "Gugi (캘리·손글씨)"},
    "nanum_pen":            {"path": "/usr/share/fonts/truetype/nanum/NanumPen.ttf",              "name": "NanumPen (볼펜 손글씨)"},
    "nanum_barunpen_b":     {"path": "/usr/share/fonts/truetype/nanum/NanumBarunpenB.ttf",        "name": "NanumBarunpen Bold (두꺼운 볼펜)"},
    "nanum_brush":          {"path": "/usr/share/fonts/truetype/nanum/NanumBrush.ttf",            "name": "NanumBrush (붓글씨)"},
    # ─ 명조 (신문·격식) ─
    "nanum_myeongjo_b":     {"path": "/usr/share/fonts/truetype/nanum/NanumMyeongjoBold.ttf",     "name": "NanumMyeongjo Bold (명조)"},
    "nanum_myeongjo_eb":    {"path": "/usr/share/fonts/truetype/nanum/NanumMyeongjoExtraBold.ttf","name": "NanumMyeongjo ExtraBold (신문체)"},
    "noto_serif_bold":      {"path": _SERIF_BOLD,                                                 "name": "Noto Serif Bold",              "ttc_index": 2},
    # ─ 추가 Google Fonts Korean — PIL은 Noto 계열로 폴백 (Remotion만 정확) ─
    "bagel_fat_one":        {"path": _BLACK_HAN_SANS,  "name": "Bagel Fat One (통통·귀여움) ⋆"},
    "cute_font":            {"path": _SANS_BOLD,       "name": "Cute Font (귀여운 손글씨) ⋆",   "ttc_index": 2},
    "dokdo":                {"path": _SANS_BOLD,       "name": "Dokdo (독도 손글씨) ⋆",          "ttc_index": 2},
    "dongle":               {"path": _SANS_BOLD,       "name": "Dongle (둥글 얇음) ⋆",          "ttc_index": 2},
    "east_sea_dokdo":       {"path": _SANS_BOLD,       "name": "East Sea Dokdo (손글씨) ⋆",      "ttc_index": 2},
    "gaegu":                {"path": _SANS_BOLD,       "name": "Gaegu (어린이 손글씨) ⋆",       "ttc_index": 2},
    "gamja_flower":         {"path": _SANS_BOLD,       "name": "Gamja Flower (감자꽃) ⋆",        "ttc_index": 2},
    "gowun_batang":         {"path": _SERIF_BOLD,      "name": "Gowun Batang (모던 명조) ⋆",    "ttc_index": 2},
    "gowun_dodum":          {"path": _SANS_BOLD,       "name": "Gowun Dodum (부드러운 고딕) ⋆", "ttc_index": 2},
    "hahmlet":              {"path": _SERIF_BOLD,      "name": "Hahmlet (세리프) ⋆",             "ttc_index": 2},
    "hi_melody":            {"path": _SANS_BOLD,       "name": "Hi Melody (손글씨) ⋆",          "ttc_index": 2},
    "ibm_plex_sans_kr":     {"path": _SANS_BOLD,       "name": "IBM Plex Sans KR ⋆",             "ttc_index": 2},
    "kirang_haerang":       {"path": _SANS_BOLD,       "name": "Kirang Haerang (배민 기랑해랑) ⋆","ttc_index": 2},
    "poor_story":           {"path": _SANS_BOLD,       "name": "Poor Story (네오 손글씨) ⋆",    "ttc_index": 2},
    "single_day":           {"path": _SANS_BOLD,       "name": "Single Day (각진 캐주얼) ⋆",    "ttc_index": 2},
    "song_myung":           {"path": _SERIF_BOLD,      "name": "Song Myung (명조) ⋆",            "ttc_index": 2},
    "stylish":              {"path": _SANS_BOLD,       "name": "Stylish (세련 산세리프) ⋆",     "ttc_index": 2},
    "sunflower":            {"path": _SANS_BOLD,       "name": "Sunflower (산세리프) ⋆",        "ttc_index": 2},
    "yeon_sung":            {"path": _SANS_BOLD,       "name": "Yeon Sung (손글씨) ⋆",          "ttc_index": 2},
}
# ⭐ = 추천 / ⋆ = Remotion 전용 (PIL 프리뷰는 근사체)


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
    # ─ 단일 기본 테마 ─ 전 파이프라인의 시작값. 모든 속성은 UI 미세 조정으로 덮어씀.
    "default": {
        "display_name": "기본",
        "layout": "letterbox",
        "canvas": (1080, 1920),
        "letterbox": {
            "top_h": 290,
            "vid_h": 1280,
            "bot_h": 350,
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
            "accent_last_line": True,
            "accent_color": YELLOW,
        },
        "caption": {
            "font": _BLACK_HAN_SANS,
            "size": 72,
            "color": YELLOW,
            "stroke_w": 8,
            "stroke_color": BLACK,
            "line_spacing": 10,
            "max_width": 0.82,
            "area": "video_bottom_overlay",
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
}




def get_default_theme() -> dict:
    """기본 테마 반환 (항상 동일)."""
    return THEMES["default"]


def get_theme(name: str = "default") -> dict:
    """레거시 호환. 이름 무시하고 항상 기본 테마 반환."""
    return THEMES["default"]


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


def _path_to_font_id(path: str) -> str:
    if not path:
        return ""
    for fid, entry in FONT_REGISTRY.items():
        if entry["path"] == path:
            return fid
    return ""
