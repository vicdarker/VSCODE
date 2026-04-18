"""
API 요청/응답 모델 + 작업 상태 관리 (인메모리, MVP용)
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    SELECTING = "selecting"
    EDITING = "editing"
    DONE = "done"
    FAILED = "failed"


class CreateJobRequest(BaseModel):
    source_type: str = "youtube"   # "youtube" | "blog"

    # YouTube
    url: str = ""

    # Blog
    blog_url: str = ""
    blog_text: str = ""

    # News
    news_url: str = ""
    news_text: str = ""
    news_title: str = ""

    duration: int = 60           # 숏폼 길이 (초)
    clips: int = 3               # 클립 수 (youtube) / 스크립트 수 (blog)
    style: str = "general"       # 스타일
    vertical: bool = True        # 9:16 변환 (youtube only)
    caption_mode: str = "word_pop"  # "word_pop" | "line_fade" | "none"
    make_thumbnail: bool = True  # 썸네일 자동 생성
    output_format: str = "mp4"   # "mp4" | "capcut"


class ClipInfo(BaseModel):
    index: int
    output_path: str
    video_url: str               # 브라우저에서 접근 가능한 URL
    thumbnail_url: str | None    # 썸네일 URL
    start: float
    end: float
    hook: str
    hashtags: list[str]


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int            # 0~100
    message: str
    clips: list[ClipInfo]
    created_at: str
    error: str | None = None
    request: dict | None = None


# --- 인메모리 잡 스토어 (MVP) ---

class JobStore:
    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}

    def create(self, req: CreateJobRequest) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = {
            "job_id": job_id,
            "status": JobStatus.PENDING,
            "progress": 0,
            "message": "대기 중",
            "clips": [],
            "created_at": datetime.now().isoformat(),
            "request": req.model_dump(),
            "error": None,
        }
        return job_id

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs):
        if job_id in self._jobs:
            self._jobs[job_id].update(kwargs)

    def all(self) -> list[dict]:
        return sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)


job_store = JobStore()
