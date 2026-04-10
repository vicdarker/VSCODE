"""
플랫폼 업로드 API
POST /api/publish/{platform}/{job_id}/{clip_index}  - 클립 업로드
GET  /api/publish/status                            - 연결된 계정 상태
GET  /api/publish/youtube/auth                      - YouTube OAuth 시작
GET  /api/publish/youtube/callback                  - YouTube OAuth 콜백
GET  /api/publish/tiktok/auth                       - TikTok OAuth 시작
GET  /api/publish/tiktok/callback                   - TikTok OAuth 콜백
"""

import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from api.models import job_store, ClipInfo
from src.publisher import youtube_publisher, tiktok_publisher

router = APIRouter()

# 서버 base URL (환경변수로 설정, 기본 localhost)
def _base_url():
    return os.environ.get("BASE_URL", "http://localhost:8000")


# ── 계정 연결 상태 ────────────────────────────────────────────────────────

@router.get("/status")
async def account_status():
    return {
        "youtube": youtube_publisher.is_authenticated(),
        "tiktok":  tiktok_publisher.is_authenticated(),
    }


# ── YouTube OAuth ─────────────────────────────────────────────────────────

@router.get("/youtube/auth")
async def youtube_auth():
    redirect_uri = f"{_base_url()}/api/publish/youtube/callback"
    auth_url = youtube_publisher.get_auth_url(redirect_uri)
    return RedirectResponse(auth_url)


@router.get("/youtube/callback")
async def youtube_callback(code: str):
    redirect_uri = f"{_base_url()}/api/publish/youtube/callback"
    youtube_publisher.exchange_code(code, redirect_uri)
    return RedirectResponse("/?connected=youtube")


# ── TikTok OAuth ──────────────────────────────────────────────────────────

@router.get("/tiktok/auth")
async def tiktok_auth():
    redirect_uri = f"{_base_url()}/api/publish/tiktok/callback"
    auth_url = tiktok_publisher.get_auth_url(redirect_uri)
    return RedirectResponse(auth_url)


@router.get("/tiktok/callback")
async def tiktok_callback(code: str):
    redirect_uri = f"{_base_url()}/api/publish/tiktok/callback"
    tiktok_publisher.exchange_code(code, redirect_uri)
    return RedirectResponse("/?connected=tiktok")


# ── 업로드 ────────────────────────────────────────────────────────────────

class PublishRequest(BaseModel):
    platforms: list[str]   # ["youtube", "tiktok"]


@router.post("/{job_id}/{clip_index}")
async def publish_clip(job_id: str, clip_index: int, req: PublishRequest):
    """
    특정 클립을 선택한 플랫폼에 업로드합니다.

    Args:
        job_id:     작업 ID
        clip_index: 클립 번호 (1부터 시작)
        req.platforms: 업로드할 플랫폼 목록
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    clip_data = next(
        (c for c in job["clips"] if c["index"] == clip_index), None
    )
    if not clip_data:
        raise HTTPException(status_code=404, detail="클립을 찾을 수 없습니다.")

    clip = ClipInfo(**clip_data)
    results = {}
    errors  = {}

    title       = clip.hook or f"숏폼 클립 {clip_index}"
    description = "\n".join(clip.hashtags)
    tags        = [t.lstrip("#") for t in clip.hashtags]

    for platform in req.platforms:
        try:
            if platform == "youtube":
                r = youtube_publisher.upload(
                    video_path=clip.output_path,
                    title=title,
                    description=description,
                    tags=tags,
                    thumbnail_path=_thumb_path(clip),
                )
                results[platform] = {"video_id": r.video_id, "url": r.url}

            elif platform == "tiktok":
                r = tiktok_publisher.upload(
                    video_path=clip.output_path,
                    title=title,
                    tags=clip.hashtags,
                )
                results[platform] = {"video_id": r.video_id, "url": r.url}

            else:
                errors[platform] = f"지원하지 않는 플랫폼: {platform}"

        except Exception as e:
            errors[platform] = str(e)

    return {"results": results, "errors": errors}


def _thumb_path(clip: ClipInfo) -> str | None:
    """ClipInfo에서 썸네일 실제 경로를 반환합니다."""
    if not clip.thumbnail_url:
        return None
    # /output/filename.jpg → output/filename.jpg
    return clip.thumbnail_url.lstrip("/")
