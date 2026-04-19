"""SQLite JobStore 기본 동작 테스트."""
import pytest
from api.models import CreateJobRequest, JobStatus


def test_create_and_get(isolated_jobstore):
    js = isolated_jobstore
    req = CreateJobRequest(source_type="news", news_text="테스트", duration=30)
    job_id = js.create(req)
    assert job_id and len(job_id) > 0
    job = js.get(job_id)
    assert job is not None
    assert job["status"] == JobStatus.PENDING.value
    assert job["progress"] == 0
    assert job["request"]["news_text"] == "테스트"


def test_update(isolated_jobstore):
    js = isolated_jobstore
    job_id = js.create(CreateJobRequest(source_type="news", news_text="x"))
    js.update(job_id, status=JobStatus.EDITING, progress=50, message="처리 중")
    job = js.get(job_id)
    assert job["status"] == JobStatus.EDITING.value
    assert job["progress"] == 50
    assert job["message"] == "처리 중"


def test_clips_json_roundtrip(isolated_jobstore):
    js = isolated_jobstore
    job_id = js.create(CreateJobRequest(source_type="news", news_text="x"))
    clips = [{"index": 1, "output_path": "x.mp4", "video_url": "/x.mp4",
              "thumbnail_url": None, "start": 0, "end": 60, "hook": "h",
              "hashtags": ["#a", "#b"]}]
    js.update(job_id, clips=clips, status=JobStatus.DONE)
    job = js.get(job_id)
    assert job["clips"] == clips


def test_all_orders_by_created_desc(isolated_jobstore):
    js = isolated_jobstore
    ids = [js.create(CreateJobRequest(source_type="news", news_text=f"n{i}"))
           for i in range(3)]
    all_jobs = js.all()
    assert len(all_jobs) >= 3
    # 최신이 먼저
    found_ids = [j["job_id"] for j in all_jobs[:3]]
    assert found_ids == ids[::-1]


def test_delete(isolated_jobstore):
    js = isolated_jobstore
    job_id = js.create(CreateJobRequest(source_type="news", news_text="x"))
    assert js.delete(job_id) is True
    assert js.get(job_id) is None
    assert js.delete(job_id) is False
