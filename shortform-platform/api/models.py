"""
API 요청/응답 모델 + 작업 상태 관리.
저장소: SQLite (data/jobs.db) — 서버 재시작 시 히스토리 보존.
"""

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.common.logging_setup import get_logger
log = get_logger(__name__)


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
    output_format: str = "mp4"   # "mp4"

    # 사용자 커스터마이징 오버라이드
    theme_overrides: dict | None = None   # {title/caption/bottom_brand/layout ...}
    enable_highlight_stat: bool = False   # 수치 팝업 (기본 끔 — 영상 가림 방지)
    enable_remotion: bool = False         # Remotion 애니메이션 엔진 (렌더 느리지만 풍부)
    enable_ai_image: bool = False         # AI 이미지 생성 (DALL-E 3, 유료 ~$0.04/장)


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


# --- SQLite 잡 스토어 ---
# 서버 재시작 시 히스토리 보존. 단일 사용자/단일 머신 가정 (MVP).

_DB_PATH = Path(os.environ.get("JOBS_DB_PATH", "data/jobs.db"))


class JobStore:
    """공개 API는 dict 기반 — 호출측 코드 변경 없음.
    내부적으로 SQLite에 저장. JSON 직렬화로 복합 필드(request, clips) 보관.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id     TEXT PRIMARY KEY,
        status     TEXT NOT NULL,
        progress   INTEGER NOT NULL DEFAULT 0,
        message    TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        error      TEXT,
        request    TEXT NOT NULL DEFAULT '{}',
        clips      TEXT NOT NULL DEFAULT '[]',
        log_path   TEXT
    );
    CREATE INDEX IF NOT EXISTS jobs_created_idx ON jobs(created_at DESC);
    CREATE INDEX IF NOT EXISTS jobs_status_idx  ON jobs(status);
    """

    def __init__(self, db_path: Path | str = _DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # SQLite는 같은 connection 다중 스레드 사용 시 check_same_thread=False 필요
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False, isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(self._SCHEMA)
        log.info("JobStore opened: %s", self._db_path)

    # ── 내부 헬퍼 ──
    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        return {
            "job_id":     row["job_id"],
            "status":     row["status"],
            "progress":   row["progress"],
            "message":    row["message"],
            "created_at": row["created_at"],
            "error":      row["error"],
            "request":    json.loads(row["request"] or "{}"),
            "clips":      json.loads(row["clips"] or "[]"),
            "log_path":   row["log_path"],
        }

    # ── 공개 API ──
    def create(self, req: CreateJobRequest) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs(job_id, status, progress, message, created_at, updated_at, request, clips) "
                "VALUES (?, ?, 0, '대기 중', ?, ?, ?, '[]')",
                (job_id, JobStatus.PENDING.value, now, now,
                 json.dumps(req.model_dump(), ensure_ascii=False)),
            )
        return job_id

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def update(self, job_id: str, **kwargs) -> None:
        if not kwargs:
            return
        # JSON 필드는 직렬화
        for k in ("request", "clips"):
            if k in kwargs and not isinstance(kwargs[k], str):
                kwargs[k] = json.dumps(kwargs[k], ensure_ascii=False)
        # status가 enum이면 .value
        if "status" in kwargs and hasattr(kwargs["status"], "value"):
            kwargs["status"] = kwargs["status"].value
        kwargs["updated_at"] = datetime.now().isoformat()
        cols = list(kwargs.keys())
        set_clause = ", ".join(f"{c} = ?" for c in cols)
        params = list(kwargs.values()) + [job_id]
        with self._lock:
            self._conn.execute(
                f"UPDATE jobs SET {set_clause} WHERE job_id = ?", params,
            )

    def all(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete(self, job_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            return cur.rowcount > 0


job_store = JobStore()
