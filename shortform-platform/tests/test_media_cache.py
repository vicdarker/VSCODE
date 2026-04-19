"""MediaCache TTL·CRUD 테스트."""
import time
import pytest
from src.common.media_cache import MediaCache


def test_put_get(tmp_path):
    cache = MediaCache(tmp_path / "c.db")
    cache.put("wiki", "이재명", ["이재명", "url://x"], ttl_days=1)
    val = cache.get("wiki", "이재명")
    assert val == ["이재명", "url://x"]


def test_miss(tmp_path):
    cache = MediaCache(tmp_path / "c.db")
    assert cache.get("wiki", "없음") is None


def test_expiration(tmp_path):
    cache = MediaCache(tmp_path / "c.db")
    cache.put("wiki", "a", "v", ttl_days=-1)  # 이미 만료
    assert cache.get("wiki", "a") is None


def test_invalidate(tmp_path):
    cache = MediaCache(tmp_path / "c.db")
    cache.put("wiki", "a", 1, ttl_days=10)
    cache.put("wiki", "b", 2, ttl_days=10)
    assert cache.invalidate("wiki", "a") == 1
    assert cache.get("wiki", "a") is None
    assert cache.get("wiki", "b") == 2
    # 전체 source 삭제
    assert cache.invalidate("wiki") == 1


def test_cleanup_expired(tmp_path):
    cache = MediaCache(tmp_path / "c.db")
    cache.put("wiki", "a", 1, ttl_days=-1)
    cache.put("wiki", "b", 2, ttl_days=10)
    deleted = cache.cleanup_expired()
    assert deleted == 1
    assert cache.get("wiki", "b") == 2


def test_stats(tmp_path):
    cache = MediaCache(tmp_path / "c.db")
    cache.put("wiki", "a", 1)
    cache.put("og", "x", 2)
    s = cache.stats()
    assert s["total"] == 2
    assert s["by_source"]["wiki"] == 1
    assert s["by_source"]["og"] == 1
