"""pytest 공용 fixture."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 프로젝트 루트를 path에 추가 (테스트가 src/api/worker import 가능하게)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def temp_db(tmp_path):
    """잡별 격리된 SQLite DB."""
    db = tmp_path / "test_jobs.db"
    os.environ["JOBS_DB_PATH"] = str(db)
    yield db


@pytest.fixture
def isolated_jobstore(temp_db):
    """매 테스트 fresh JobStore (모듈 캐시 우회)."""
    import importlib
    import api.models
    importlib.reload(api.models)
    from api.models import job_store
    return job_store


@pytest.fixture
def tmp_workdir(tmp_path, monkeypatch):
    """temp/output을 tmp_path 하위로."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "temp").mkdir(exist_ok=True)
    (tmp_path / "output" / "news" / "scripts").mkdir(parents=True, exist_ok=True)
    return tmp_path
