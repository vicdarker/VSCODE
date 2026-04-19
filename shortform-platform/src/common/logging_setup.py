"""
프로젝트 전역 logging 셋업.
- 모듈별 logger: `logging.getLogger(__name__)`
- 잡별 file handler: `with job_log_handler(job_id, log_path): ...`
- print() 호환: `_print = make_print_capture(logger)` 같은 식으로 점진적 마이그레이션 가능
"""
import logging
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_INITIALIZED = False
_LOCK = threading.Lock()

# 잡별 file handler 컨테이너 — job_id → handler. 같은 잡 동시 실행 방지.
_JOB_HANDLERS: dict[str, logging.Handler] = {}


def setup_root_logging(level: int = logging.INFO) -> None:
    """프로세스 1회만 호출. uvicorn/celery 진입점에서."""
    global _INITIALIZED
    with _LOCK:
        if _INITIALIZED:
            return
        root = logging.getLogger()
        root.setLevel(level)
        # 기존 핸들러 제거 후 단일 stdout 핸들러
        for h in list(root.handlers):
            root.removeHandler(h)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        root.addHandler(sh)
        # uvicorn·anthropic·urllib 노이즈 줄이기
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("anthropic").setLevel(logging.WARNING)
        _INITIALIZED = True


@contextmanager
def job_log_handler(job_id: str, log_path: str | Path) -> Iterator[logging.Handler]:
    """이 컨텍스트 안에서 발생하는 모든 로그를 추가로 log_path에 기록.

    사용:
        with job_log_handler(job_id, "output/.../run.log"):
            run_pipeline(job_id)   # 이 안의 모든 logger 호출이 파일에도 기록됨
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
    handler.setLevel(logging.INFO)
    root = logging.getLogger()
    with _LOCK:
        # 이미 같은 job 핸들러 있으면 교체
        old = _JOB_HANDLERS.pop(job_id, None)
        if old:
            root.removeHandler(old)
            try:
                old.close()
            except Exception:
                pass
        _JOB_HANDLERS[job_id] = handler
        root.addHandler(handler)
    try:
        yield handler
    finally:
        with _LOCK:
            root.removeHandler(handler)
            _JOB_HANDLERS.pop(job_id, None)
        try:
            handler.close()
        except Exception:
            pass


def get_logger(name: str) -> logging.Logger:
    """모듈에서 `log = get_logger(__name__)` 패턴."""
    return logging.getLogger(name)
