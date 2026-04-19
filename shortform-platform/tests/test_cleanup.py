"""디렉토리 cleanup 테스트."""
import time
from pathlib import Path

from src.common.cleanup import cleanup_directory


def test_keeps_newest_n(tmp_path):
    parent = tmp_path / "temp"
    parent.mkdir()
    for i in range(5):
        (parent / f"news_{i:02d}").mkdir()
        time.sleep(0.01)  # mtime 분리
    deleted, remaining = cleanup_directory(parent, prefix="news_", max_keep=3,
                                           max_age_days=999)
    assert deleted == 2
    assert remaining == 3


def test_age_threshold(tmp_path):
    parent = tmp_path / "temp"
    parent.mkdir()
    old = parent / "news_old"
    old.mkdir()
    # 10일 전 mtime
    old_time = time.time() - (10 * 86400)
    import os
    os.utime(old, (old_time, old_time))
    new = parent / "news_new"
    new.mkdir()
    deleted, remaining = cleanup_directory(parent, prefix="news_", max_keep=10,
                                           max_age_days=7)
    assert deleted == 1   # old만
    assert remaining == 1
    assert not old.exists()
    assert new.exists()


def test_empty_directory(tmp_path):
    deleted, remaining = cleanup_directory(tmp_path / "nothing", prefix="x_")
    assert (deleted, remaining) == (0, 0)
