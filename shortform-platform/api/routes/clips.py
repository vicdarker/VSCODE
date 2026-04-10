"""
클립 API - 개별 클립 정보 조회
GET /api/clips/{job_id} - 특정 작업의 클립 목록
"""

from fastapi import APIRouter, HTTPException
from api.models import ClipInfo, job_store

router = APIRouter()


@router.get("/{job_id}", response_model=list[ClipInfo])
async def get_clips(job_id: str):
    """완성된 클립 목록을 반환합니다."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return [ClipInfo(**c) for c in job["clips"]]
