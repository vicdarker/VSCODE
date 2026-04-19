"""
작업(Job) REST API 엔드포인트
POST /api/jobs                 - 새 작업 생성 (영상 처리 시작)
GET  /api/jobs                 - 전체 작업 목록
GET  /api/jobs/{id}            - 특정 작업 상태 조회
POST /api/jobs/{id}/rerender   - 기존 미디어·TTS 재사용해 새 옵션으로 재렌더
DELETE /api/jobs/{id}          - 잡 삭제 (DB만, 파일은 cleanup이 처리)
GET  /api/jobs/{id}/log        - 잡 실행 로그 (run.log) 본문
"""

import asyncio
import os
import threading
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import PlainTextResponse

from api.models import CreateJobRequest, JobResponse, job_store

router = APIRouter()

USE_CELERY = os.environ.get("USE_CELERY", "false").lower() == "true"


def _run_job(job_id: str):
    """파이프라인을 백그라운드 스레드에서 실행합니다."""
    from worker.tasks import _run_pipeline
    _run_pipeline(job_id)


def _start_background(job_id: str):
    if USE_CELERY:
        from worker.tasks import generate_shortform
        generate_shortform.delay(job_id)
    else:
        from worker.tasks import set_event_loop
        set_event_loop(asyncio.get_running_loop())
        threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()


@router.post("", response_model=JobResponse, status_code=202)
async def create_job(req: CreateJobRequest):
    """숏폼 생성 작업을 시작합니다."""
    job_id = job_store.create(req)
    _start_background(job_id)
    return _to_response(job_store.get(job_id))


@router.get("", response_model=list[JobResponse])
async def list_jobs():
    return [_to_response(j) for j in job_store.all()]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return _to_response(job)


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    if not job_store.delete(job_id):
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"ok": True}


@router.get("/{job_id}/log", response_class=PlainTextResponse)
async def get_job_log(job_id: str, tail: int = 0):
    """잡 실행 로그 (run.log) 본문. tail>0이면 마지막 N줄만."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    log_path = job.get("log_path")
    if not log_path or not os.path.exists(log_path):
        return PlainTextResponse("(로그 없음)", status_code=200)
    try:
        with open(log_path, encoding="utf-8") as f:
            content = f.read()
        if tail > 0:
            content = "\n".join(content.splitlines()[-tail:])
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/rerender", response_model=JobResponse, status_code=202)
async def rerender_job(job_id: str, overrides: dict = Body(default_factory=dict)):
    """완료된 잡을 같은 미디어·TTS로 새 렌더 옵션으로 다시 렌더.

    overrides 받는 키:
      - theme_overrides   (자막·레이아웃 등)
      - enable_remotion, enable_transitions, enable_highlight_stat 등
      - tts_voice (TTS는 캐시 활용, 변경 시 재생성)
    동일 미디어 폴더(temp/news_*)·script.json을 재사용하므로 빠름.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="완료된 잡만 재렌더 가능합니다.")

    # 새 잡 생성 (원본 request 복사 + overrides 머지)
    new_req_dict = dict(job["request"])
    new_req_dict.update(overrides or {})
    # 재렌더 표시 — _run_pipeline에서 분기
    new_req_dict["_rerender_from"] = job_id
    from api.models import CreateJobRequest
    new_req = CreateJobRequest(**{k: v for k, v in new_req_dict.items()
                                  if k in CreateJobRequest.model_fields})
    new_job_id = job_store.create(new_req)
    # _rerender_from 같은 비표준 필드는 따로 request에 머지
    job_store.update(new_job_id, request={**new_req_dict})
    _start_background(new_job_id)
    return _to_response(job_store.get(new_job_id))


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
