"""
작업(Job) REST API 엔드포인트
POST /api/jobs       - 새 작업 생성 (영상 처리 시작)
GET  /api/jobs       - 전체 작업 목록
GET  /api/jobs/{id}  - 특정 작업 상태 조회
"""

import asyncio
import os
import threading
from fastapi import APIRouter, HTTPException

from api.models import CreateJobRequest, JobResponse, job_store

router = APIRouter()

USE_CELERY = os.environ.get("USE_CELERY", "false").lower() == "true"


def _run_job(job_id: str):
    """파이프라인을 백그라운드 스레드에서 실행합니다."""
    from worker.tasks import _run_pipeline
    _run_pipeline(job_id)


@router.post("", response_model=JobResponse, status_code=202)
async def create_job(req: CreateJobRequest):
    """숏폼 생성 작업을 시작합니다."""
    job_id = job_store.create(req)

    if USE_CELERY:
        from worker.tasks import generate_shortform
        generate_shortform.delay(job_id)
    else:
        # 현재 실행 중인 이벤트 루프를 tasks 모듈에 등록
        from worker.tasks import set_event_loop
        set_event_loop(asyncio.get_running_loop())
        # Redis 없이 백그라운드 스레드로 실행
        t = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
        t.start()

    return _to_response(job_store.get(job_id))


@router.get("", response_model=list[JobResponse])
async def list_jobs():
    """전체 작업 목록을 반환합니다."""
    return [_to_response(j) for j in job_store.all()]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """특정 작업의 현재 상태를 반환합니다."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return _to_response(job)


def _to_response(job: dict) -> JobResponse:
    from api.models import ClipInfo
    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress=job["progress"],
        message=job["message"],
        clips=[ClipInfo(**c) for c in job["clips"]],
        created_at=job["created_at"],
        error=job.get("error"),
        request=job.get("request"),
    )
