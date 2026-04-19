"""
FastAPI 메인 앱 - REST API + WebSocket
"""

from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path

from src.common.paths import ensure_ffmpeg_in_path
ensure_ffmpeg_in_path()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.common.logging_setup import setup_root_logging
setup_root_logging()

from api.routes import jobs, clips, publish
from api.ws_manager import ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/api/fonts")
async def list_available_fonts():
    """자막/타이틀에 쓸 수 있는 폰트 목록"""
    from src.editor.news_themes import list_fonts
    return {"fonts": list_fonts()}


@app.post("/api/preview-layout")
async def preview_layout(payload: dict = Body(...)):
    """
    자막/타이틀 레이아웃 실시간 미리보기.
    payload: {theme_overrides, title?, caption?, highlight_stat?}
    응답: image/png 바이트
    """
    import io
    from fastapi.responses import Response
    from PIL import Image, ImageDraw
    from src.editor.news_themes import get_default_theme, apply_overrides
    from src.editor.news_direct_renderer import _make_segment_overlay

    overrides = payload.get("theme_overrides")
    title   = payload.get("title", "미국과 동맹인 나라 중\n최초로 국적선 통과")
    caption = payload.get("caption", "몇 척만 통과했던거야")
    highlight = payload.get("highlight_stat", "")

    base = get_default_theme()
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
