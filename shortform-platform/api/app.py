"""
FastAPI 메인 앱 - REST API + WebSocket
"""

from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path

# ffmpeg PATH 자동 설정 (winget 설치 경로)
_ffmpeg = (
    Path.home()
    / "AppData/Local/Microsoft/WinGet/Packages"
    / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    / "ffmpeg-8.1-full_build/bin"
)
if _ffmpeg.exists():
    os.environ["PATH"] = str(_ffmpeg) + os.pathsep + os.environ.get("PATH", "")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.routes import jobs, clips, publish
from api.ws_manager import ws_manager


def _pregenerate_preset_thumbnails():
    """기동 시 각 프리셋 썸네일 PNG를 static/previews/에 굽기. 이미 있으면 스킵."""
    from pathlib import Path
    from PIL import Image, ImageDraw
    from src.editor.news_themes import list_presets, get_theme
    from src.editor.news_direct_renderer import _make_segment_overlay

    out_dir = Path("static/previews")
    out_dir.mkdir(parents=True, exist_ok=True)

    sample_title = "미국과 동맹인 나라 중\n최초로 국적선 통과"
    sample_caption = "몇 척만 통과했던거야"

    for p in list_presets():
        target = out_dir / f"preset_{p['id']}.jpg"
        if target.exists():
            continue
        try:
            theme = get_theme(p["id"])
            tmp = str(out_dir / f"_overlay_{p['id']}.png")
            _make_segment_overlay(
                title=sample_title, caption_chunk=sample_caption,
                theme=theme, emphasis_words=[], highlight_stat="",
                reaction_emoji="", role_color=(255, 100, 100),
                out_path=tmp,
            )
            W, H = theme["canvas"]
            lb = theme.get("letterbox") or {"top_h": 0, "vid_h": H, "bot_h": 0}
            bg = Image.new("RGB", (W, H), (55, 95, 145))
            d = ImageDraw.Draw(bg)
            bg_color = lb.get("bg", (0, 0, 0, 255))
            if isinstance(bg_color, (tuple, list)) and len(bg_color) >= 3:
                bg_fill = tuple(bg_color[:3])
            else:
                bg_fill = (0, 0, 0)
            d.rectangle([0, 0, W, lb["top_h"]], fill=bg_fill)
            d.rectangle([0, lb["top_h"] + lb["vid_h"], W, H], fill=bg_fill)
            ov = Image.open(tmp).convert("RGBA")
            bg_rgba = bg.convert("RGBA")
            bg_rgba.alpha_composite(ov)
            # 320x568 썸네일
            thumb = bg_rgba.convert("RGB").resize((320, 568), Image.LANCZOS)
            thumb.save(target, quality=85)
            Path(tmp).unlink(missing_ok=True)
            print(f"  [preset thumb] {p['id']} OK")
        except Exception as e:
            print(f"  [preset thumb] {p['id']} 실패: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _pregenerate_preset_thumbnails()
    except Exception as e:
        print(f"썸네일 사전 렌더 실패 (무시): {e}")
    yield


app = FastAPI(
    title="숏폼 자동 생성 플랫폼",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/output", StaticFiles(directory="output"), name="output")

templates = Jinja2Templates(directory="templates")

# 라우터 등록
app.include_router(jobs.router,    prefix="/api/jobs",    tags=["jobs"])
app.include_router(clips.router,   prefix="/api/clips",   tags=["clips"])
app.include_router(publish.router, prefix="/api/publish", tags=["publish"])


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/themes")
async def list_news_themes():
    """뉴스 숏츠 테마 목록 (레거시)"""
    from src.editor.news_themes import list_themes
    return {"themes": list_themes()}


@app.get("/api/presets")
async def list_presets_endpoint():
    """프리셋 카드 그리드용. 썸네일 URL 포함."""
    from src.editor.news_themes import list_presets
    return {"presets": list_presets()}


@app.get("/api/presets/{preset_id}/config")
async def get_preset_config(preset_id: str):
    """프리셋의 UI 입력값 형태 config 반환 (카드 선택 시 폼 초기화용)."""
    from src.editor.news_themes import get_preset_ui_config
    return get_preset_ui_config(preset_id)


@app.get("/api/fonts")
async def list_available_fonts():
    """자막/타이틀에 쓸 수 있는 폰트 목록"""
    from src.editor.news_themes import list_fonts
    return {"fonts": list_fonts()}


@app.post("/api/preview-layout")
async def preview_layout(payload: dict = Body(...)):
    """
    자막/타이틀 레이아웃 실시간 미리보기.
    payload: {theme_id, theme_overrides, title?, caption?, highlight_stat?}
    응답: image/png 바이트 (base64)
    """
    import base64, io
    from fastapi.responses import Response
    from PIL import Image, ImageDraw
    from src.editor.news_themes import get_theme, apply_overrides
    from src.editor.news_direct_renderer import _make_segment_overlay

    theme_id = payload.get("theme_id", "viral_pill")
    overrides = payload.get("theme_overrides")
    title   = payload.get("title", "미국과 동맹인 나라 중\n최초로 국적선 통과")
    caption = payload.get("caption", "몇 척만 통과했던거야")
    highlight = payload.get("highlight_stat", "")

    # Remotion 엔진 테마는 PIL 미리보기 불가 → 동일 스타일의 PIL 테마로 대체
    base = get_theme(theme_id)
    if base.get("engine") == "remotion":
        theme_id = base.get("remotion_theme_id") or "viral_pill"
        base = get_theme(theme_id)

    theme = apply_overrides(base, overrides)

    # 오버레이 생성
    tmp = "/tmp/preview_overlay.png"
    _make_segment_overlay(
        title=title, caption_chunk=caption, theme=theme,
        emphasis_words=[], highlight_stat=highlight, reaction_emoji="",
        role_color=(255, 100, 100), out_path=tmp,
    )
    # 가짜 영상 배경 (회색) + 테마의 letterbox 배경색 사용
    W, H = theme["canvas"]
    lb = theme.get("letterbox", {"top_h": 0, "vid_h": H, "bot_h": 0})
    bg_color = lb.get("bg", (0, 0, 0, 255))
    if isinstance(bg_color, (tuple, list)) and len(bg_color) >= 3:
        bg_fill = tuple(int(x) for x in bg_color[:3])
    else:
        bg_fill = (0, 0, 0)
    bg = Image.new("RGB", (W, H), (60, 90, 130))
    d = ImageDraw.Draw(bg)
    d.rectangle([0, 0, W, lb["top_h"]], fill=bg_fill)
    d.rectangle([0, lb["top_h"] + lb["vid_h"], W, H], fill=bg_fill)
    ov = Image.open(tmp).convert("RGBA")
    bg = bg.convert("RGBA")
    bg.alpha_composite(ov)
    # 50% 크기 (540x960)로 축소
    preview = bg.convert("RGB").resize((540, 960), Image.LANCZOS)
    buf = io.BytesIO()
    preview.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await ws_manager.connect(websocket, job_id)
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, job_id)
