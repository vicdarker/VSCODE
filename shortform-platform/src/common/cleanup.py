"""
디스크 정리 유틸리티.
- temp/news_*: 미디어 캐시 폴더 — 잡 종료 후 N일 또는 N개 초과 시 삭제
- output/news/scripts/{ts}_{stem}/: 스크립트 로그 — 같은 정책

기본 정책: 최신 30개 유지 + 7일 이상 된 것 삭제. 잡 시작 시 호출.
"""

import shutil
import time
from pathlib import Path

from src.common.logging_setup import get_logger
log = get_logger(__name__)


def _list_dirs_by_mtime(parent: Path, prefix: str = "") -> list[Path]:
    """parent 하위 디렉토리를 최신순(mtime desc)으로."""
    if not parent.exists():
        return []
    dirs = [p for p in parent.iterdir()
            if p.is_dir() and (not prefix or p.name.startswith(prefix))]
    return sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)


def _safe_rmtree(path: Path) -> bool:
    try:
        shutil.rmtree(path, ignore_errors=False)
        return True
    except Exception as e:
        log.warning("정리 실패: %s — %s", path, e)
        return False


def cleanup_directory(
    parent: Path | str,
    prefix: str = "",
    max_keep: int = 30,
    max_age_days: float = 7.0,
) -> tuple[int, int]:
    """parent 안의 prefix 디렉토리를 정리.
    유지 조건: 최신 max_keep 개 OR max_age_days 안쪽.
    반환: (삭제된 개수, 남은 개수)
    """
    parent = Path(parent)
    dirs = _list_dirs_by_mtime(parent, prefix)
    if not dirs:
        return (0, 0)
    now = time.time()
    age_threshold = now - (max_age_days * 86400)
    to_delete: list[Path] = []
    # 우선 max_keep 초과분 후보로
    for p in dirs[max_keep:]:
        to_delete.append(p)
    # 추가로 너무 오래된 것 (max_keep 안쪽이라도)
    for p in dirs[:max_keep]:
        if p.stat().st_mtime < age_threshold:
            to_delete.append(p)
    deleted = 0
    for p in to_delete:
        if _safe_rmtree(p):
            deleted += 1
    remaining = len(dirs) - deleted
    if deleted:
        log.info("[cleanup] %s/%s* — %d개 삭제, %d개 유지",
                 parent, prefix or "(all)", deleted, remaining)
    return (deleted, remaining)


def cleanup_all(max_keep: int = 30, max_age_days: float = 7.0) -> dict:
    """파이프라인이 사용하는 모든 임시·로그 폴더 정리."""
    targets = [
        ("temp", "news_"),
        ("output/news/scripts", ""),
    ]
    summary = {}
    for parent, prefix in targets:
        deleted, remaining = cleanup_directory(
            parent, prefix=prefix, max_keep=max_keep, max_age_days=max_age_days,
        )
        summary[f"{parent}/{prefix or '*'}"] = {"deleted": deleted, "remaining": remaining}
    return summary
