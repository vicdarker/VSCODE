"""
미디어 검색 결과 캐시 (SQLite, TTL 기반).
같은 (source, key)에 대한 응답을 N일 캐싱 — Wikimedia·og:image 등 안정 응답 위주.

사용:
    cache = MediaCache()
    val = cache.get("wiki", "이재명 대통령")
    if val is None:
        val = expensive_lookup(...)
        cache.put("wiki", "이재명 대통령", val, ttl_days=30)
"""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from src.common.logging_setup import get_logger
log = get_logger(__name__)


_DB_PATH = Path(os.environ.get("MEDIA_CACHE_DB", "data/media_cache.db"))


class MediaCache:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS cache (
        source     TEXT NOT NULL,
        key        TEXT NOT NULL,
        value      TEXT NOT NULL,
        expires_at REAL NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY (source, key)
    );
    CREATE INDEX IF NOT EXISTS cache_expires_idx ON cache(expires_at);
    """

    def __init__(self, db_path: Path | str = _DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False, isolation_level=None,
        )
        self._conn.executescript(self._SCHEMA)

    def get(self, source: str, key: str):
        """캐시 hit이면 값 반환. miss/만료면 None."""
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT value, expires_at FROM cache WHERE source = ? AND key = ?",
                (source, key),
            ).fetchone()
        if not row:
            return None
        value_json, expires_at = row
        if expires_at < now:
            return None
        try:
            return json.loads(value_json)
        except Exception:
            return None

    def put(self, source: str, key: str, value, ttl_days: float = 30.0) -> None:
        now = time.time()
        expires = now + (ttl_days * 86400)
        try:
            value_json = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            log.warning("캐시 직렬화 실패: source=%s key=%s err=%s", source, key, e)
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache(source, key, value, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, key, value_json, expires, now),
            )

    def invalidate(self, source: str, key: str | None = None) -> int:
        with self._lock:
            if key is None:
                cur = self._conn.execute("DELETE FROM cache WHERE source = ?", (source,))
            else:
                cur = self._conn.execute(
                    "DELETE FROM cache WHERE source = ? AND key = ?", (source, key),
                )
        return cur.rowcount

    def cleanup_expired(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM cache WHERE expires_at < ?", (time.time(),),
            )
        return cur.rowcount

    def stats(self) -> dict:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            by_source = self._conn.execute(
                "SELECT source, COUNT(*) FROM cache GROUP BY source"
            ).fetchall()
        return {"total": total, "by_source": dict(by_source)}


# 싱글톤
_cache_singleton: MediaCache | None = None


def get_media_cache() -> MediaCache:
    global _cache_singleton
    if _cache_singleton is None:
        _cache_singleton = MediaCache()
    return _cache_singleton
