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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

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


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await ws_manager.connect(websocket, job_id)
    try:
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, job_id)
